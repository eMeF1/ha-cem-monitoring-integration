from __future__ import annotations

import logging
import voluptuous as vol
from aiohttp import ClientResponseError
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_USERNAME, CONF_PASSWORD, CONF_VAR_IDS, CONF_VAR_IDS_CSV
from .api import CEMClient

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
                    return self.async_show_form(step_id="user", data_schema=self._schema(), errors=errors)

            await self.async_set_unique_id(f"{DOMAIN}_{username_key}")
            self._abort_if_unique_id_configured()

            # Validate credentials
            session = async_get_clientsession(self.hass)
            client = CEMClient(session)
            try:
                await client.authenticate(username, password)
            except ClientResponseError as err:
                if err.status in (401, 403):
                    errors["base"] = "invalid_auth"
                else:
                    errors["base"] = "cannot_connect"
                return self.async_show_form(step_id="user", data_schema=self._schema(), errors=errors)
            except Exception as err:
                _LOGGER.exception("Unexpected error during authentication: %s", err)
                errors["base"] = "unknown"
                return self.async_show_form(step_id="user", data_schema=self._schema(), errors=errors)

            options: dict = {}
            csv_val = user_input.get(CONF_VAR_IDS_CSV, "") or ""
            try:
                var_ids = _parse_csv_to_ints(csv_val)
            except Exception:
                errors["base"] = "invalid_var_ids"
                return self.async_show_form(step_id="user", data_schema=self._schema(), errors=errors)

            if var_ids:
                options[CONF_VAR_IDS] = var_ids

            return self.async_create_entry(
                title=f"CEM Monitor ({username})" if username else "CEM Monitor",
                data={CONF_USERNAME: username, CONF_PASSWORD: password},
                options=options,
            )

        return self.async_show_form(step_id="user", data_schema=self._schema(), errors=errors)

    def _schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_VAR_IDS_CSV, description={"suggested_value": ""}): str,
            }
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
        if user_input is not None:
            try:
                var_ids = _parse_csv_to_ints(user_input.get(CONF_VAR_IDS_CSV, ""))
            except Exception:
                errors["base"] = "invalid_var_ids"
            else:
                return self.async_create_entry(title="", data={CONF_VAR_IDS: var_ids})

        existing = self._entry.options.get(CONF_VAR_IDS, [])
        csv_default = ",".join(str(v) for v in existing)
        schema = vol.Schema({vol.Required(CONF_VAR_IDS_CSV, default=csv_default): str})
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)