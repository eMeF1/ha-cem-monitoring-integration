from __future__ import annotations

import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from aiohttp import ClientResponseError
from aiohttp.client_exceptions import ClientConnectorCertificateError
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from .api import AuthResult, CEMClient
from .cache import TypesCache
from .const import (
    CONF_COUNTER_UPDATE_INTERVAL_MINUTES,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VAR_IDS,
    CONF_VERIFY_SSL,
    DEFAULT_COUNTER_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
    MAX_COUNTER_UPDATE_INTERVAL_MINUTES,
    MIN_COUNTER_UPDATE_INTERVAL_MINUTES,
)
from .coordinators import _create_session
from .utils import get_int, get_str_nonempty

_LOGGER = logging.getLogger(__name__)


def _parse_csv_to_ints(csv: str) -> list[int]:
    if not csv:
        return []
    out: list[int] = []
    for part in csv.split(","):
        s = part.strip()
        if not s:
            continue
        out.append(int(s))
    return out


def _resolve_object_name(
    mis_id: int | None,
    raw_by_mis: dict[int, dict[str, Any]],
    mis_name_by_id: dict[int, str | None],
) -> tuple[str | None, int | None]:
    """Return (resolved_name, source_mis_id). If mis has no name, climb via mis_idp to find a named ancestor."""
    if mis_id is None:
        return None, None

    visited: set[int] = set()
    cur = int(mis_id)

    while cur and cur not in visited:
        visited.add(cur)
        name = mis_name_by_id.get(cur)
        if get_str_nonempty(name):
            return name, cur
        raw = raw_by_mis.get(cur) or {}
        parent = raw.get("mis_idp")
        try:
            cur = int(parent) if parent is not None else None
        except Exception:
            cur = None

    return None, None


async def _fetch_objects_tree(
    hass: HomeAssistant, client: CEMClient, auth_result: AuthResult
) -> dict[int, dict[str, Any]]:
    """Fetch and build hierarchical tree: Objects → Meters → Counters."""
    token = auth_result.access_token
    cookie = auth_result.cookie_value

    # Load pot_types from cache first (read-only, cache updates handled in __init__.py)
    types_cache = TypesCache(hass)
    pot_by_id, _, cache_valid = await types_cache.load()

    if not cache_valid or not pot_by_id:
        # Cache miss/invalid/expired - fetch from API
        # Note: We don't save to cache here; cache updates are handled during setup in __init__.py
        pot_by_id = {}
        try:
            pot_payload = await client.get_pot_types(token, cookie)
            pot_list = pot_payload.get("data") if isinstance(pot_payload, dict) else pot_payload
            if isinstance(pot_list, list):
                for p in pot_list:
                    pid = get_int(p, "pot_id")
                    if pid is not None:
                        pot_by_id[pid] = p
        except Exception as err:
            _LOGGER.warning("Failed to fetch pot_types: %s", err)
            pot_by_id = {}

    # Fetch objects (id=23)
    objects_raw = await client.get_objects(token, cookie)

    # Store raw objects for parent resolution
    raw_by_mis: dict[int, dict[str, Any]] = {}
    mis_name_by_id: dict[int, str | None] = {}

    # Build objects map and name mapping
    objects_map: dict[int, dict[str, Any]] = {}
    for obj in objects_raw:
        mis_id = get_int(obj, "mis_id", "misid", "misId", "id")
        if mis_id is None:
            continue

        raw_by_mis[mis_id] = obj
        mis_name = get_str_nonempty(
            obj.get("mis_nazev"),
            obj.get("mis_name"),
            obj.get("name"),
            obj.get("nazev"),
            obj.get("název"),
            obj.get("caption"),
            obj.get("description"),
        )
        mis_name_by_id[mis_id] = mis_name

        objects_map[mis_id] = {
            "mis_id": mis_id,
            "mis_name": mis_name,
            "meters": {},
        }

    # Resolve object names by climbing parent hierarchy
    for mis_id, obj_data in objects_map.items():
        resolved_name, _ = _resolve_object_name(mis_id, raw_by_mis, mis_name_by_id)
        if resolved_name:
            obj_data["mis_name"] = resolved_name

    # Fetch all meters (id=108)
    meters_raw = await client.get_meters(token, cookie)

    # Group meters by mis_id
    meters_by_object: dict[int, list[dict[str, Any]]] = {}
    for meter in meters_raw:
        mis_id = get_int(meter, "mis_id", "misid", "misId", "object_id", "obj_id")
        if mis_id is None:
            continue
        if mis_id not in meters_by_object:
            meters_by_object[mis_id] = []
        meters_by_object[mis_id].append(meter)

    # For each object, fetch meters and their counters
    for mis_id, obj_data in objects_map.items():
        meters_list = meters_by_object.get(mis_id, [])

        for meter in meters_list:
            me_id = get_int(meter, "me_id", "meid", "meId", "id")
            if me_id is None:
                continue

            me_serial = get_str_nonempty(
                meter.get("me_serial"),
                meter.get("serial"),
            )
            me_name = get_str_nonempty(
                meter.get("me_name"),
                meter.get("name"),
                meter.get("nazev"),
                meter.get("název"),
            )

            # Fetch counters for this meter (id=107)
            try:
                counters_raw = await client.get_counters_by_meter(me_id, token, cookie)
            except Exception as err:
                _LOGGER.warning("Failed to fetch counters for meter %s: %s", me_id, err)
                counters_raw = []

            # Process counters
            meter_counters: dict[int, dict[str, Any]] = {}
            first_lt_key = None
            first_jed_nazev = None
            first_jed_zkr = None

            for counter in counters_raw:
                var_id = get_int(counter, "var_id", "varId", "varid", "id")
                if var_id is None:
                    continue

                counter_name = get_str_nonempty(
                    counter.get("poc_desc"),
                    counter.get("name"),
                    counter.get("nazev"),
                    counter.get("název"),
                    counter.get("caption"),
                    counter.get("popis"),
                    counter.get("description"),
                )

                # Get pot_info for this counter
                pot_id = get_int(counter, "pot_id")
                pot_info = pot_by_id.get(pot_id) if pot_id is not None else None

                # Use first counter's pot_info for meter display
                if pot_info and first_lt_key is None:
                    first_lt_key = pot_info.get("lt_key")
                    first_jed_nazev = pot_info.get("jed_nazev")
                    first_jed_zkr = pot_info.get("jed_zkr")

                meter_counters[var_id] = {
                    "var_id": var_id,
                    "name": counter_name,
                    "pot_id": pot_id,
                    "pot_info": pot_info,
                }

            # Only store meters that have at least one counter
            if meter_counters:
                obj_data["meters"][me_id] = {
                    "me_id": me_id,
                    "me_serial": me_serial or f"me{me_id}",
                    "me_name": me_name,
                    "lt_key": first_lt_key or "",
                    "jed_nazev": first_jed_nazev or "",
                    "jed_zkr": first_jed_zkr or "",
                    "counters": meter_counters,
                }

    return objects_map


class CEMConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            username_raw = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            username = (username_raw or "").strip()
            username_key = username.lower()

            # Prevent duplicate username entries
            for entry in self._async_current_entries():
                if entry.data.get(CONF_USERNAME, "").strip().lower() == username_key:
                    errors["base"] = "already_configured"
                    return self.async_show_form(
                        step_id="user", data_schema=self._schema(), errors=errors
                    )

            await self.async_set_unique_id(f"{DOMAIN}_{username_key}")
            self._abort_if_unique_id_configured()

            # Validate credentials
            verify_ssl = user_input.get(CONF_VERIFY_SSL, True)
            session = _create_session(self.hass, verify_ssl)
            client = CEMClient(session)
            try:
                auth_result = await client.authenticate(username, password)
            except ClientConnectorCertificateError as err:
                # SSL certificate error - suggest disabling SSL verification
                _LOGGER.warning("SSL certificate verification failed during config flow: %s", err)
                errors["base"] = "ssl_certificate_error"
                return self.async_show_form(
                    step_id="user", data_schema=self._schema(), errors=errors
                )
            except ClientResponseError as err:
                if err.status in (401, 403):
                    errors["base"] = "invalid_auth"
                else:
                    errors["base"] = "cannot_connect"
                return self.async_show_form(
                    step_id="user", data_schema=self._schema(), errors=errors
                )
            except Exception as err:
                _LOGGER.exception("Unexpected error during authentication: %s", err)
                errors["base"] = "unknown"
                return self.async_show_form(
                    step_id="user", data_schema=self._schema(), errors=errors
                )

            # Store credentials and auth result in flow data for next step
            self.hass.data.setdefault(DOMAIN, {})
            flow_data_key = f"{DOMAIN}_flow_{self.flow_id}"
            self.hass.data[DOMAIN][flow_data_key] = {
                CONF_USERNAME: username,
                CONF_PASSWORD: password,
                CONF_VERIFY_SSL: verify_ssl,
                "auth_result": auth_result,
                "client": client,
            }

            # Proceed to counter selection step
            return await self.async_step_select_counters()

        return self.async_show_form(step_id="user", data_schema=self._schema(), errors=errors)

    def _schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_VERIFY_SSL, default=True): bool,
            }
        )

    async def async_step_select_counters(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: Select counters from hierarchical tree."""
        errors: dict[str, str] = {}

        # Retrieve stored credentials and auth
        flow_data_key = f"{DOMAIN}_flow_{self.flow_id}"
        flow_data = self.hass.data.get(DOMAIN, {}).get(flow_data_key)

        if not flow_data:
            return self.async_abort(reason="no_flow_data")

        username = flow_data[CONF_USERNAME]
        password = flow_data[CONF_PASSWORD]
        auth_result: AuthResult = flow_data["auth_result"]
        client: CEMClient = flow_data["client"]

        if user_input is not None:
            # User has selected counters
            selected_var_ids = user_input.get("selected_counters", [])
            if not selected_var_ids:
                errors["base"] = "no_counters_selected"
            else:
                # Convert string IDs to integers
                try:
                    var_ids = [int(vid) for vid in selected_var_ids]
                except (ValueError, TypeError):
                    errors["base"] = "invalid_counter_selection"

                if not errors:
                    # Clean up flow data
                    self.hass.data[DOMAIN].pop(flow_data_key, None)

                    # Create config entry
                    options: dict = {}
                    if var_ids:
                        options[CONF_VAR_IDS] = var_ids

                    verify_ssl = flow_data.get(CONF_VERIFY_SSL, True)

                    return self.async_create_entry(
                        title=f"CEM Monitor ({username})" if username else "CEM Monitor",
                        data={
                            CONF_USERNAME: username,
                            CONF_PASSWORD: password,
                            CONF_VERIFY_SSL: verify_ssl,
                        },
                        options=options,
                    )

        # Fetch and build tree structure
        try:
            tree_data = await _fetch_objects_tree(self.hass, client, auth_result)
        except Exception as err:
            _LOGGER.exception("Error fetching objects tree: %s", err)
            errors["base"] = "fetch_failed"
            return self.async_show_form(
                step_id="select_counters",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        # Build selection options with hierarchical display
        counter_options: dict[str, str] = {}
        for mis_id, obj_data in tree_data.items():
            mis_name = obj_data.get("mis_name") or f"Object {mis_id}"

            for me_id, meter_data in obj_data.get("meters", {}).items():
                me_serial = meter_data.get("me_serial") or f"me{me_id}"
                lt_key = meter_data.get("lt_key") or ""

                for var_id, counter_data in meter_data.get("counters", {}).items():
                    counter_name = counter_data.get("name") or f"Counter {var_id}"

                    # Use separator-based format for better readability in dropdown
                    full_label = f"{mis_name} ({mis_id}) → {me_serial} - {lt_key} ({me_id}) → {counter_name} ({var_id})"
                    counter_options[str(var_id)] = full_label

        if not counter_options:
            errors["base"] = "no_counters_available"
            return self.async_show_form(
                step_id="select_counters",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        schema = vol.Schema(
            {
                vol.Required("selected_counters", default=[]): vol.All(
                    cv.multi_select(counter_options),
                    vol.Length(min=1, msg="Please select at least one counter"),
                ),
            }
        )

        return self.async_show_form(
            step_id="select_counters",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        # IMPORTANT: staticmethod (no self), and not async
        return CEMOptionsFlow(config_entry)


class CEMOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}

        # Get existing credentials from config entry
        username = self._entry.data.get(CONF_USERNAME)
        password = self._entry.data.get(CONF_PASSWORD)

        if user_input is not None:
            # User has submitted the form
            selected_var_ids = user_input.get("selected_counters", [])
            var_ids = []
            if selected_var_ids:
                try:
                    var_ids = [int(vid) for vid in selected_var_ids]
                except (ValueError, TypeError):
                    errors["base"] = "invalid_counter_selection"

            # Validate counter update interval
            interval = user_input.get(CONF_COUNTER_UPDATE_INTERVAL_MINUTES)
            if interval is not None:
                try:
                    interval_int = int(interval)
                    if (
                        interval_int < MIN_COUNTER_UPDATE_INTERVAL_MINUTES
                        or interval_int > MAX_COUNTER_UPDATE_INTERVAL_MINUTES
                    ):
                        errors[CONF_COUNTER_UPDATE_INTERVAL_MINUTES] = "interval_range"
                except (ValueError, TypeError):
                    errors[CONF_COUNTER_UPDATE_INTERVAL_MINUTES] = "invalid_interval"

            # Get verify_ssl setting
            verify_ssl = user_input.get(CONF_VERIFY_SSL, True)

            if not errors:
                options_data = {}
                # Only store var_ids if provided (empty list means show all)
                if var_ids:
                    options_data[CONF_VAR_IDS] = var_ids
                # Always store the interval (default is set in schema, so it's always present)
                interval_value = (
                    int(interval)
                    if interval is not None
                    else DEFAULT_COUNTER_UPDATE_INTERVAL_MINUTES
                )
                options_data[CONF_COUNTER_UPDATE_INTERVAL_MINUTES] = interval_value

                # Update entry.data with verify_ssl if it changed
                verify_ssl_changed = verify_ssl != self._entry.data.get(CONF_VERIFY_SSL, True)
                if verify_ssl_changed:
                    new_data = {**self._entry.data, CONF_VERIFY_SSL: verify_ssl}
                    self.hass.config_entries.async_update_entry(self._entry, data=new_data)

                result = self.async_create_entry(title="", data=options_data)

                # Reload the integration after flow completes to apply SSL setting change
                if verify_ssl_changed:
                    self.hass.async_create_task(
                        self.hass.config_entries.async_reload(self._entry.entry_id)
                    )

                return result

        # Fetch tree data for hierarchical selection
        existing_var_ids = self._entry.options.get(CONF_VAR_IDS, [])
        existing_interval = self._entry.options.get(
            CONF_COUNTER_UPDATE_INTERVAL_MINUTES, DEFAULT_COUNTER_UPDATE_INTERVAL_MINUTES
        )
        existing_verify_ssl = self._entry.data.get(CONF_VERIFY_SSL, True)

        # Authenticate and fetch tree
        if not username or not password:
            errors["base"] = "missing_credentials"
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        session = _create_session(self.hass, existing_verify_ssl)
        client = CEMClient(session)
        try:
            auth_result = await client.authenticate(username, password)
        except ClientConnectorCertificateError as err:
            # SSL certificate error - allow user to disable SSL verification
            _LOGGER.warning("SSL certificate verification failed during options flow: %s", err)
            errors["base"] = "ssl_certificate_error"
            # Still show the form with verify_ssl checkbox so user can disable it
            schema = vol.Schema(
                {
                    vol.Optional("selected_counters", default=[]): cv.multi_select({}),
                    vol.Required(
                        CONF_COUNTER_UPDATE_INTERVAL_MINUTES,
                        default=existing_interval,
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_COUNTER_UPDATE_INTERVAL_MINUTES,
                            max=MAX_COUNTER_UPDATE_INTERVAL_MINUTES,
                        ),
                    ),
                    vol.Optional(
                        CONF_VERIFY_SSL, default=False
                    ): bool,  # Suggest disabling SSL verification
                }
            )
            return self.async_show_form(
                step_id="init",
                data_schema=schema,
                errors=errors,
            )
        except ClientResponseError as err:
            if err.status in (401, 403):
                errors["base"] = "invalid_auth"
            else:
                errors["base"] = "cannot_connect"
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({}),
                errors=errors,
            )
        except Exception as err:
            _LOGGER.exception("Unexpected error during authentication: %s", err)
            errors["base"] = "unknown"
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        # Fetch and build tree structure
        try:
            tree_data = await _fetch_objects_tree(self.hass, client, auth_result)
        except Exception as err:
            _LOGGER.exception("Error fetching objects tree: %s", err)
            errors["base"] = "fetch_failed"
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        # Build selection options with hierarchical display
        counter_options: dict[str, str] = {}
        for mis_id, obj_data in tree_data.items():
            mis_name = obj_data.get("mis_name") or f"Object {mis_id}"

            for me_id, meter_data in obj_data.get("meters", {}).items():
                me_serial = meter_data.get("me_serial") or f"me{me_id}"
                lt_key = meter_data.get("lt_key") or ""

                for var_id, counter_data in meter_data.get("counters", {}).items():
                    counter_name = counter_data.get("name") or f"Counter {var_id}"

                    # Use separator-based format for better readability in dropdown
                    full_label = f"{mis_name} ({mis_id}) → {me_serial} - {lt_key} ({me_id}) → {counter_name} ({var_id})"
                    counter_options[str(var_id)] = full_label

        if not counter_options:
            errors["base"] = "no_counters_available"
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        # Pre-select existing counters
        default_selected = [str(vid) for vid in existing_var_ids if str(vid) in counter_options]

        schema = vol.Schema(
            {
                vol.Optional("selected_counters", default=default_selected): cv.multi_select(
                    counter_options
                ),
                vol.Required(
                    CONF_COUNTER_UPDATE_INTERVAL_MINUTES,
                    default=existing_interval,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_COUNTER_UPDATE_INTERVAL_MINUTES,
                        max=MAX_COUNTER_UPDATE_INTERVAL_MINUTES,
                    ),
                ),
                vol.Optional(CONF_VERIFY_SSL, default=existing_verify_ssl): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
