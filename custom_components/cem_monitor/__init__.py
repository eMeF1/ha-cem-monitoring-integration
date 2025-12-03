from __future__ import annotations

from datetime import timedelta
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    DOMAIN,
    CONF_VAR_IDS,
    CONF_COUNTER_UPDATE_INTERVAL_MINUTES,
    DEFAULT_COUNTER_UPDATE_INTERVAL_MINUTES,
)
from .api import CEMClient
from .cache import TypesCache
from .coordinator import CEMAuthCoordinator
from .userinfo_coordinator import CEMUserInfoCoordinator
from .objects_coordinator import CEMObjectsCoordinator
from .meters_coordinator import CEMMetersCoordinator
from .meter_counters_coordinator import CEMMeterCountersCoordinator
from .counter_reading_coordinator import CEMCounterReadingCoordinator
from .utils import get_int, get_str_nonempty, ms_to_iso

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


def _build_objects_maps(objects_data: dict[str, Any]) -> tuple[dict[int, dict], dict[int, Optional[str]]]:
    """
    Build:
      - raw_by_mis: mis_id -> raw record (contains mis_idp)
      - mis_name_by_id: mis_id -> 'mis_nazev' (may be empty/None)
    """
    raw_by_mis: dict[int, dict] = {}
    mis_name_by_id: dict[int, Optional[str]] = {}

    if objects_data:
        rbm = objects_data.get("raw_by_mis") or {}
        # Keys may be strings; normalize to int
        for k, raw in rbm.items():
            try:
                mid = int(k)
            except Exception:
                continue
            raw_by_mis[mid] = raw
            mis_name_by_id[mid] = get_str_nonempty(
                raw.get("mis_nazev"),
                raw.get("mis_name"),
                raw.get("name"),
                raw.get("nazev"),
                raw.get("název"),
                raw.get("caption"),
                raw.get("description"),
            )

    return raw_by_mis, mis_name_by_id


def _resolve_object_name(
    mis_id: Optional[int],
    raw_by_mis: dict[int, dict],
    mis_name_by_id: dict[int, Optional[str]],
) -> Tuple[Optional[str], Optional[int]]:
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


async def _fetch_pot_types_from_api(
    client: CEMClient, token: Optional[str], cookie: Optional[str]
) -> Dict[int, Dict[str, Any]]:
    """
    Fetch pot_types from API (id=222).

    Returns:
        Dictionary mapping pot_id -> pot type data
    """
    pot_by_id: Dict[int, Dict[str, Any]] = {}
    if not token:
        _LOGGER.warning("CEM pot_types: no auth token available, skipping id=222")
        return pot_by_id

    try:
        _LOGGER.debug("CEM pot_types: fetching global pot type list (id=222)")
        pot_payload = await client.get_pot_types(token, cookie)
        # id=222 returns {"data": [...], "action": "get"}
        pot_list = pot_payload.get("data") if isinstance(pot_payload, dict) else pot_payload
        if not isinstance(pot_list, list):
            _LOGGER.debug("CEM pot_types: unexpected response %r", pot_payload)
        else:
            count = 0
            for p in pot_list:
                pid = p.get("pot_id")
                if pid is None:
                    continue
                try:
                    pid_int = int(pid)
                except Exception:
                    continue
                pot_by_id[pid_int] = p
                count += 1
            _LOGGER.debug(
                "CEM pot_types: built mapping for %d pot_id values",
                count,
            )
    except Exception as err:
        _LOGGER.debug("CEM pot_types: failed to fetch global pot types: %s", err)

    return pot_by_id


async def _fetch_counter_value_types_from_api(
    client: CEMClient, token: Optional[str], cookie: Optional[str]
) -> Dict[int, str]:
    """
    Fetch counter_value_types from API (id=11&cis=50).

    Returns:
        Dictionary mapping pot_type -> counter value type name
    """
    counter_value_types: Dict[int, str] = {}
    if not token:
        _LOGGER.warning("CEM counter_value_types: no auth token available, skipping id=11")
        return counter_value_types

    try:
        _LOGGER.debug("CEM counter_value_types: fetching counter value types (id=11&cis=50)")
        cvt_payload = await client.get_counter_value_types(token, cookie, cis=50)
        # id=11 returns an array of objects
        cvt_list = cvt_payload if isinstance(cvt_payload, list) else (cvt_payload.get("data") if isinstance(cvt_payload, dict) else [])
        if isinstance(cvt_list, list):
            count = 0
            for item in cvt_list:
                if not isinstance(item, dict):
                    continue
                cik_fk = item.get("cik_fk")
                cik_nazev = item.get("cik_nazev")
                if cik_fk is not None and isinstance(cik_nazev, str) and cik_nazev.strip():
                    try:
                        pot_type_key = int(cik_fk)
                        counter_value_types[pot_type_key] = cik_nazev.strip()
                        count += 1
                    except Exception:
                        continue
            _LOGGER.debug(
                "CEM counter_value_types: built mapping for %d pot_type values",
                count,
            )
    except Exception as err:
        _LOGGER.debug("CEM counter_value_types: failed to fetch counter value types: %s", err)

    return counter_value_types


# ----------------------------
# HA entry points
# ----------------------------
async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload integration when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up CEM Monitoring Integration from a config entry."""
    session = async_get_clientsession(hass)
    client = CEMClient(session)

    hass.data.setdefault(DOMAIN, {})
    bag: Dict[str, Any] = hass.data[DOMAIN].setdefault(entry.entry_id, {})
    bag["client"] = client

    # Register update listener to reload integration when options change
    entry.async_on_unload(
        entry.add_update_listener(async_reload_entry)
    )

    # Get allowed var_ids from config entry options (user selection)
    allowed_var_ids: Optional[List[int]] = entry.options.get(CONF_VAR_IDS)
    allowed_var_ids_set: Optional[set[int]] = None
    if allowed_var_ids:
        allowed_var_ids_set = set(allowed_var_ids)
        _LOGGER.debug("CEM: Filtering counters to var_ids=%s", allowed_var_ids)
    else:
        _LOGGER.debug("CEM: No var_ids filter set, exposing all eligible counters")

    # 1) Auth (id=4)
    auth = CEMAuthCoordinator(hass, entry)
    bag["coordinator"] = auth
    await auth.async_config_entry_first_refresh()

    # Service: cem_monitor.get_raw -> fire event with raw JSON from selected endpoint
    async def handle_get_raw(call: ServiceCall) -> None:
        endpoint = call.data["endpoint"]
        _LOGGER.debug("CEM get_raw service called: endpoint=%s, data=%s", endpoint, call.data)

        # Ensure we have a valid token
        token = auth.token
        if not token:
            await auth.async_request_refresh()
            token = auth.token
        if not token:
            _LOGGER.error("CEM get_raw: no token available even after refresh")
            return

        cookie = auth._last_result.cookie_value if auth._last_result else None

        try:
            if endpoint == "user_info":
                data = await client.get_user_info(token, cookie)
            elif endpoint == "objects":
                data = await client.get_objects(token, cookie)
            elif endpoint == "meters":
                mis_id = call.data.get("mis_id")
                data = await client.get_meters(token, cookie, mis_id)
            elif endpoint == "counters_by_meter":
                me_id = call.data.get("me_id")
                if me_id is None:
                    _LOGGER.error("CEM get_raw: me_id is required for counters_by_meter")
                    return
                data = await client.get_counters_by_meter(int(me_id), token, cookie)
            elif endpoint == "counter_last":
                var_id = call.data.get("var_id")
                if var_id is None:
                    _LOGGER.error("CEM get_raw: var_id is required for counter_last")
                    return
                # For counter_last we want the raw id=8 payload, not the processed dict,
                # so we re-implement the call similar to CEMClient.get_counter_reading
                from .const import COUNTER_LAST_URL
                headers = await client._auth_headers(token, cookie)  # type: ignore[attr-defined]
                url = f"{COUNTER_LAST_URL}&var_id={int(var_id)}"
                from aiohttp import ClientTimeout
                timeout = ClientTimeout(total=20)
                async with client._session.get(url, headers=headers, timeout=timeout) as resp:  # type: ignore[attr-defined]
                    resp.raise_for_status()
                    text = await resp.text()
                    _LOGGER.debug("CEM get_raw counter_last: HTTP %s", resp.status)
                    _LOGGER.debug("CEM get_raw counter_last: raw body (first 300 chars): %s", text[:300])
                    data = await resp.json(content_type=None)
            else:
                _LOGGER.error("CEM get_raw: unknown endpoint %s", endpoint)
                return
        except Exception as err:
            _LOGGER.exception("CEM get_raw(%s) failed: %s", endpoint, err)
            return

        _LOGGER.info("CEM get_raw(%s) -> %s", endpoint, data)

        # Fire an event with the raw JSON so you can inspect it
        hass.bus.async_fire(
            f"{DOMAIN}_raw_response",
            {
                "endpoint": endpoint,
                "data": data,
                "context_id": call.context.id,
            },
        )

    hass.services.async_register(DOMAIN, "get_raw", handle_get_raw)


    # 2) Account info (id=9)
    ui = CEMUserInfoCoordinator(hass, client, auth)
    bag["userinfo"] = ui
    await ui.async_config_entry_first_refresh()

    # 3) Objects (id=23)
    objects = CEMObjectsCoordinator(hass, client, auth)
    bag["objects"] = objects
    await objects.async_config_entry_first_refresh()

    raw_by_mis, mis_name_by_id = _build_objects_maps(objects.data or {})

    # 4) Meters (id=108)
    meters = CEMMetersCoordinator(hass, client, auth)
    bag["meters"] = meters
    await meters.async_config_entry_first_refresh()

    meters_list: List[Dict[str, Any]] = []
    if meters.data:
        if isinstance(meters.data, dict):
            if isinstance(meters.data.get("meters"), list):
                meters_list = meters.data["meters"]
            elif isinstance(meters.data.get("data"), list):
                meters_list = meters.data["data"]
        elif isinstance(meters.data, list):
            meters_list = meters.data

    meters_map: Dict[int, Dict[str, Any]] = {}
    bag["meters_map"] = meters_map

    # var_id -> [me_id, ...]   (shared counters across meters)
    var_shares: Dict[int, List[int]] = {}
    bag["var_shares"] = var_shares

    # One counter reading coordinator per var_id per account
    counter_map: Dict[int, CEMCounterReadingCoordinator] = bag.setdefault("counter_readings", {})

    # Load pot_types and counter_value_types from cache or fetch from API
    token = auth.token
    cookie = auth._last_result.cookie_value if auth._last_result else None

    # Initialize cache
    types_cache = TypesCache(hass)
    
    # Try loading from cache first
    pot_by_id, counter_value_types, cache_valid = await types_cache.load()
    
    if not cache_valid:
        # Cache miss/invalid/expired - fetch from API
        _LOGGER.debug("CEM types cache: cache miss or invalid, fetching from API")
        
        pot_by_id = await _fetch_pot_types_from_api(client, token, cookie)
        counter_value_types = await _fetch_counter_value_types_from_api(client, token, cookie)
        
        # Save to cache for next time (only if we got valid data)
        if pot_by_id or counter_value_types:
            await types_cache.save(pot_by_id, counter_value_types)
            _LOGGER.debug("CEM types cache: saved fetched data to cache")
    else:
        _LOGGER.debug("CEM types cache: loaded from cache")

    bag["pot_types"] = pot_by_id
    bag["counter_value_types"] = counter_value_types
    _LOGGER.debug("CEM pot_types: loaded %d pot/unit definitions", len(pot_by_id))
    _LOGGER.debug("CEM counter_value_types: loaded %d value type definitions", len(counter_value_types))



    # 5) For each meter: fetch counters (id=107), select numeric counters, wire coordinators (id=8)
    for m in meters_list:
        me_id = get_int(m, "me_id", "meid", "meId")
        if me_id is None:
            continue

        me_name = get_str_nonempty(m.get("me_name"), m.get("me_desc"))
        me_serial = get_str_nonempty(m.get("me_serial"), (m.get("raw") or {}).get("me_serial"))
        mis_id = get_int(m, "mis_id", "misid", "misId", "object_id", "obj_id")

        # Resolve a friendly object name (climb parent if unnamed)
        mis_name, mis_name_source = _resolve_object_name(mis_id, raw_by_mis, mis_name_by_id)

        # Counters (id=107&me_id)
        mc = CEMMeterCountersCoordinator(hass, client, auth, me_id=me_id, me_name=me_name, mis_id=mis_id)
        await mc.async_config_entry_first_refresh()
        mc_data = mc.data or {}
        counters = mc_data.get("counters") or []
        raw_map: Dict[int, Dict[str, Any]] = mc_data.get("raw_map") or {}

        # Build metadata for each counter and decide which ones to expose
        meter_counters_meta: Dict[int, Dict[str, Any]] = {}
        selected_var_ids: List[int] = []

        for c in counters:
            if not isinstance(c, dict):
                continue

            # 1) Resolve var_id from simplified counter
            vid_raw = c.get("var_id")
            if vid_raw is None:
                continue
            try:
                vid = int(vid_raw)
            except Exception:
                continue

            # 2) Get the full raw counter for this var_id (includes pot_id)
            raw_c = raw_map.get(vid) or {}
            if not isinstance(raw_c, dict):
                raw_c = {}

            # 3) Resolve pot_id and pot_info
            pot_id_raw = raw_c.get("pot_id") or c.get("pot_id")
            pot_id_int: Optional[int] = None
            pot_info: Optional[Dict[str, Any]] = None
            if pot_id_raw is not None:
                try:
                    pot_id_int = int(pot_id_raw)
                except Exception:
                    pot_id_int = None
                if pot_id_int is not None:
                    pot_info = pot_by_id.get(pot_id_int)

            # 4) Resolve pot_type from pot_info (CEM: 0=instantaneous,1=total,2=state,3=derived)
            pot_type: Optional[int] = None
            if isinstance(pot_info, dict):
                try:
                    pt_raw = pot_info.get("pot_type")
                    pot_type = int(pt_raw) if pt_raw is not None else None
                except Exception:
                    pot_type = None

            # For now we expose:
            #   - type 0, 1, 3 as numeric sensors
            #   - skip type 2 (door, contact, secure, etc.)
            if pot_type == 2:
                continue

            # Filter by user selection if CONF_VAR_IDS is set
            if allowed_var_ids_set is not None and vid not in allowed_var_ids_set:
                continue

            # Lookup cik_nazev from counter_value_types using pot_type
            cik_nazev: Optional[str] = None
            if pot_type is not None:
                cik_nazev = counter_value_types.get(pot_type)

            meter_counters_meta[vid] = {
                "var_id": vid,
                "pot_id": pot_id_int,
                "pot_type": pot_type,
                "pot_info": pot_info,
                "raw_counter": raw_c,
                "cik_nazev": cik_nazev,
            }
            selected_var_ids.append(vid)

        _LOGGER.debug(
            "CEM meter %s counters_meta built for var_ids=%s",
            me_id,
            list(meter_counters_meta.keys()),
        )

        # Wire coordinators for all selected counters (unchanged)
        this_meter_counters: Dict[int, CEMCounterReadingCoordinator] = {}
        for vid in selected_var_ids:
            if vid not in counter_map:
                counter_map[vid] = CEMCounterReadingCoordinator(hass, client, auth, var_id=vid)
                await counter_map[vid].async_config_entry_first_refresh()
            this_meter_counters[vid] = counter_map[vid]
            var_shares.setdefault(int(vid), []).append(int(me_id))

        meters_map[int(me_id)] = {
            "me_name": me_name,
            "me_serial": me_serial,
            "mis_id": mis_id,
            "mis_name": mis_name,
            "mis_name_source_mis_id": mis_name_source,
            "counters": mc,
            "counters_meta": meter_counters_meta,
            "counter_readings": this_meter_counters,
        }

    # Periodic refresh for all counter reading coordinators (id=8)
    # Clean up existing timer if it exists (in case of reload/options change)
    existing_unsub = bag.get("counter_refresh_unsub")
    if callable(existing_unsub):
        existing_unsub()
        _LOGGER.debug("CEM: Cleaned up existing counter refresh timer")
    
    # Get configured update interval or use default (30 minutes)
    update_interval_minutes = entry.options.get(
        CONF_COUNTER_UPDATE_INTERVAL_MINUTES, DEFAULT_COUNTER_UPDATE_INTERVAL_MINUTES
    )
    update_interval = timedelta(minutes=update_interval_minutes)
    _LOGGER.debug("CEM: Counter update interval set to %d minutes", update_interval_minutes)

    @callback
    def _counter_refresh_callback(now) -> None:
        """Callback for periodic counter refresh - uses batch API when possible."""
        async def _do_batch_refresh() -> None:
            counter_map_local: Dict[int, CEMCounterReadingCoordinator] = bag.get("counter_readings", {})
            count = len(counter_map_local)
            _LOGGER.debug("CEM counter: scheduled refresh tick (%d coordinators)", count)
            
            if count == 0:
                return
            
            # Collect all var_ids
            var_ids = list(counter_map_local.keys())
            
            # Get auth credentials
            auth_local = bag.get("coordinator")
            if not auth_local or not auth_local.token:
                _LOGGER.warning("CEM counter batch: no auth token available, falling back to individual requests")
                # Fallback to individual requests
                for coord in counter_map_local.values():
                    hass.async_create_task(coord.async_request_refresh())
                return
            
            token = auth_local.token
            cookie = auth_local._last_result.cookie_value if auth_local._last_result else None
            client_local = bag.get("client")
            
            if not client_local:
                _LOGGER.warning("CEM counter batch: no client available, falling back to individual requests")
                # Fallback to individual requests
                for coord in counter_map_local.values():
                    hass.async_create_task(coord.async_request_refresh())
                return
            
            # Attempt batch API call
            try:
                batch_results = await client_local.get_counter_readings_batch(var_ids, token, cookie)
                
                # Update each coordinator with batch results
                for var_id, coord in counter_map_local.items():
                    if var_id in batch_results:
                        reading = batch_results[var_id]
                        # Format data to match what _async_update_data returns
                        coord.data = {
                            "value": reading.get("value"),
                            "timestamp_ms": reading.get("timestamp_ms"),
                            "timestamp_iso": ms_to_iso(reading.get("timestamp_ms")),
                            "fetched_at": int(time.time() * 1000),  # ensures coordinator data always changes
                        }
                        coord.async_update_listeners()
                    else:
                        # Missing var_id in batch response - fallback to individual request
                        _LOGGER.debug("CEM counter batch: var_id %d not in batch response, using individual request", var_id)
                        hass.async_create_task(coord.async_request_refresh())
                
                _LOGGER.debug("CEM counter batch: successfully updated %d/%d coordinators", len(batch_results), count)
                
            except Exception as err:
                _LOGGER.warning("CEM counter batch: batch request failed (%s), falling back to individual requests", err)
                # Fallback to individual requests on error
                for coord in counter_map_local.values():
                    hass.async_create_task(coord.async_request_refresh())
        
        hass.async_create_task(_do_batch_refresh())

    # Run at configured interval (default: 30 minutes)
    bag["counter_refresh_unsub"] = async_track_time_interval(
        hass, _counter_refresh_callback, update_interval
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        bag = hass.data[DOMAIN].pop(entry.entry_id, None)
        if bag is not None:
            unsub = bag.get("counter_refresh_unsub")
            if callable(unsub):
                unsub()
    return unload_ok