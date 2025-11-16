from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN
from .api import CEMClient
from .coordinator import CEMAuthCoordinator
from .userinfo_coordinator import CEMUserInfoCoordinator
from .objects_coordinator import CEMObjectsCoordinator
from .meters_coordinator import CEMMetersCoordinator
from .meter_counters_coordinator import CEMMeterCountersCoordinator
from .water_coordinator import CEMWaterCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


# ----------------------------
# Helpers
# ----------------------------
def _ival(d: Dict[str, Any], *keys: str) -> Optional[int]:
    for k in keys:
        if k in d and d[k] is not None:
            try:
                return int(d[k])
            except Exception:
                return None
    return None


def _snonempty(*vals: Optional[str]) -> Optional[str]:
    for v in vals:
        if isinstance(v, str):
            s = v.strip()
            if s:
                return s
    return None


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
            mis_name_by_id[mid] = _snonempty(
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
        if _snonempty(name):
            return name, cur
        raw = raw_by_mis.get(cur) or {}
        parent = raw.get("mis_idp")
        try:
            cur = int(parent) if parent is not None else None
        except Exception:
            cur = None

    return None, None


# ----------------------------
# HA entry points
# ----------------------------
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up CEM Monitoring Integration from a config entry."""
    session = async_get_clientsession(hass)
    client = CEMClient(session)

    hass.data.setdefault(DOMAIN, {})
    bag: Dict[str, Any] = hass.data[DOMAIN].setdefault(entry.entry_id, {})
    bag["client"] = client

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
            elif endpoint == "water_last":
                var_id = call.data.get("var_id")
                if var_id is None:
                    _LOGGER.error("CEM get_raw: var_id is required for water_last")
                    return
                # For water_last we want the raw id=8 payload, not the processed dict,
                # so we re-implement the call similar to CEMClient.get_water_consumption
                from .const import WATER_LAST_URL
                headers = await client._auth_headers(token, cookie)  # type: ignore[attr-defined]
                url = f"{WATER_LAST_URL}&var_id={int(var_id)}"
                from aiohttp import ClientTimeout
                timeout = ClientTimeout(total=20)
                async with client._session.get(url, headers=headers, timeout=timeout) as resp:  # type: ignore[attr-defined]
                    resp.raise_for_status()
                    text = await resp.text()
                    _LOGGER.debug("CEM get_raw water_last: HTTP %s", resp.status)
                    _LOGGER.debug("CEM get_raw water_last: raw body (first 300 chars): %s", text[:300])
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

    # One water coordinator per var_id per account
    water_map: Dict[int, CEMWaterCoordinator] = bag.setdefault("water", {})

    # NEW: Build pot_types mapping using id=222 (per met_id from meters)
    pot_by_id: Dict[int, Dict[str, Any]] = {}

    token = auth.token
    cookie = auth._last_result.cookie_value if auth._last_result else None

    if token and meters_list:
        met_ids_seen: set[int] = set()
        _LOGGER.debug("CEM pot_types: meters_list has %d entries", len(meters_list))

        for m in meters_list:
            # met_id can be stored under different keys, be defensive
            met_id_raw = m.get("met_id") or m.get("metId")
            if met_id_raw is None:
                continue
            try:
                met_id_int = int(met_id_raw)
            except Exception:
                continue

            # Avoid calling id=222 multiple times for the same met_id
            if met_id_int in met_ids_seen:
                continue
            met_ids_seen.add(met_id_int)

            try:
                _LOGGER.debug("CEM pot_types: fetching pot types for met_id=%s", met_id_int)
                pot_payload = await client.get_pot_types(met_id_int, token, cookie)
                # id=222 returns {"data": [...], "action": "get"}
                pot_list = pot_payload.get("data") if isinstance(pot_payload, dict) else pot_payload
                if not isinstance(pot_list, list):
                    _LOGGER.debug("CEM pot_types(met_id=%s): unexpected response %r", met_id_int, pot_payload)
                    continue

                for p in pot_list:
                    pid = p.get("pot_id")
                    if pid is None:
                        continue
                    try:
                        pid_int = int(pid)
                    except Exception:
                        continue
                    # Last one wins if duplicates, which is fine – they should be identical
                    pot_by_id[pid_int] = p
            except Exception as err:
                _LOGGER.debug("CEM pot_types(met_id=%s) failed: %s", met_id_int, err)
    else:
        if not token:
            _LOGGER.warning("CEM pot_types: no auth token available, skipping id=222")
        elif not meters_list:
            _LOGGER.debug("CEM pot_types: meters_list is empty, skipping id=222")

    bag["pot_types"] = pot_by_id
    _LOGGER.debug(
        "CEM pot_types: loaded %d pot/unit definitions from %s met_ids",
        len(pot_by_id),
        "no" if not token or not meters_list else "some",
    )




    # 5) For each meter: fetch counters (id=107), select numeric counters, wire coordinators (id=8)
    for m in meters_list:
        me_id = _ival(m, "me_id", "meid", "meId")
        if me_id is None:
            continue

        me_name = _snonempty(m.get("me_name"), m.get("me_desc"))
        me_serial = _snonempty(m.get("me_serial"), (m.get("raw") or {}).get("me_serial"))
        mis_id = _ival(m, "mis_id", "misid", "misId", "object_id", "obj_id")

        # Resolve a friendly object name (climb parent if unnamed)
        mis_name, mis_name_source = _resolve_object_name(mis_id, raw_by_mis, mis_name_by_id)

        # Counters (id=107&me_id)
        mc = CEMMeterCountersCoordinator(hass, client, auth, me_id=me_id, me_name=me_name, mis_id=mis_id)
        await mc.async_config_entry_first_refresh()
        counters = (mc.data or {}).get("counters") or []

        # Build metadata for each counter and decide which ones to expose
        meter_counters_meta: Dict[int, Dict[str, Any]] = {}
        selected_var_ids: List[int] = []

        for c in counters:
            # Many coordinators wrap the raw CEM record under "raw"
            raw_c = c.get("raw") if isinstance(c, dict) else None
            if not isinstance(raw_c, dict):
                raw_c = c if isinstance(c, dict) else {}

            vid = _ival(raw_c, "var_id", "varid", "varId")
            if vid is None:
                continue
            vid = int(vid)

            pot_id = _ival(raw_c, "pot_id", "potId")
            pot_info = pot_by_id.get(pot_id) if pot_id is not None else None

            pot_type: Optional[int] = None
            if isinstance(pot_info, dict):
                pt_raw = pot_info.get("pot_type")
                try:
                    pot_type = int(pt_raw) if pt_raw is not None else None
                except Exception:
                    pot_type = None

            # pot_type meaning (CEM):
            #   0 = instantaneous (measurement)
            #   1 = cumulative (total)
            #   2 = state / binary / special
            #   3 = derived / profile / special cumulative
            #
            # For now we expose:
            #   - type 0, 1, 3 as numeric sensors
            #   - skip type 2 (door, contact, secure, etc.)
            if pot_type == 2:
                continue

            meter_counters_meta[vid] = {
                "var_id": vid,
                "pot_id": pot_id,
                "pot_type": pot_type,
                "pot_info": pot_info,
                "raw_counter": raw_c or c,
            }
            selected_var_ids.append(vid)

        # Wire coordinators for all selected counters
        this_meter_water: Dict[int, CEMWaterCoordinator] = {}
        for vid in selected_var_ids:
            if vid not in water_map:
                water_map[vid] = CEMWaterCoordinator(hass, client, auth, var_id=vid)
                await water_map[vid].async_config_entry_first_refresh()
            this_meter_water[vid] = water_map[vid]
            var_shares.setdefault(int(vid), []).append(int(me_id))

        meters_map[int(me_id)] = {
            "me_name": me_name,
            "me_serial": me_serial,
            "mis_id": mis_id,
            "mis_name": mis_name,                      # resolved (or parent's name)
            "mis_name_source_mis_id": mis_name_source, # diagnostic
            "counters": mc,                            # coordinator (id=107)
            "counters_meta": meter_counters_meta,      # var_id -> pot/unit metadata
            "water": this_meter_water,                 # var_id -> coordinator (id=8)
            "selected_var_ids": selected_var_ids,
        }

    # Periodic refresh for all water coordinators (id=8)
    @callback
    def _water_refresh_callback(now) -> None:
        water_map_local: Dict[int, CEMWaterCoordinator] = bag.get("water", {})
        count = len(water_map_local)
        _LOGGER.debug("CEM water: scheduled refresh tick (%d coordinators)", count)
        for coord in water_map_local.values():
            # schedule the coroutine properly
            hass.async_create_task(coord.async_request_refresh())

    # Run every 5 minutes
    bag["water_refresh_unsub"] = async_track_time_interval(
        hass, _water_refresh_callback, timedelta(minutes=5)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        bag = hass.data[DOMAIN].pop(entry.entry_id, None)
        if bag is not None:
            unsub = bag.get("water_refresh_unsub")
            if callable(unsub):
                unsub()
    return unload_ok