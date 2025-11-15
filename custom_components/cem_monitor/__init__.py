from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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

    # 5) For each meter: fetch counters (id=107), pick water counters, wire water (id=8)
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

        # Select "water-ish" counters first; else fall back to all
        selected_var_ids: List[int] = []
        for c in counters:
            vid = _ival(c, "var_id", "varid", "varId")
            unit = _snonempty(c.get("unit"), c.get("jednotka"))
            name = _snonempty(c.get("name"), c.get("var_name"), c.get("poc_extid"))
            if vid is None:
                continue
            if unit and unit.lower() in {"l", "liter", "litre", "liters", "litres", "m3", "m³"}:
                selected_var_ids.append(int(vid))
            elif name and "vod" in name.lower():
                selected_var_ids.append(int(vid))
        if not selected_var_ids and counters:
            selected_var_ids = [
                int(_ival(c, "var_id", "varid", "varId"))
                for c in counters
                if _ival(c, "var_id", "varid", "varId") is not None
            ]

        # Wire water coordinators
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
            "water": this_meter_water,                 # var_id -> water coordinator (id=8)
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