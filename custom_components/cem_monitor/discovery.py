from __future__ import annotations

import logging
from typing import Any, Iterable, Optional, List, Tuple

_LOGGER = logging.getLogger(__name__)

_WATER_NAME_HINTS = (
    "water", "h2o", "cold water", "hot water",
    "voda", "studena", "studená", "tepla", "teplá", "vodomer", "vodoměr",
)
_WATER_UNIT_HINTS = ("m3", "m³", "l", "lit", "liter", "litre", "liters", "litres")
_WATER_TYPE_HINTS = ("water", "voda", "vodomer", "vodoměr")

def _get_int(item: dict[str, Any], *keys: str) -> Optional[int]:
    for k in keys:
        if k in item:
            try:
                return int(item[k])
            except Exception:
                pass
    return None

def _get_str(item: dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

def _looks_like_water(item: dict[str, Any]) -> int:
    name = _get_str(item, "name", "nazev", "název", "caption", "popis", "description").lower()
    unit = _get_str(item, "unit", "jednotka").lower()
    ctype = _get_str(item, "type", "typ", "medium", "druh").lower()
    score = 0
    if name:
        score += sum(h in name for h in _WATER_NAME_HINTS)
    if unit:
        score += sum(h in unit for h in _WATER_UNIT_HINTS)
    if ctype:
        score += sum(h in ctype for h in _WATER_TYPE_HINTS)
    if score == 0 and unit in ("m3", "m³", "l"):
        score = 1
    return score

def _get_timestamp_ms(item: dict[str, Any]) -> int:
    for k in ("timestamp", "time", "ts", "ts_ms", "timestamp_ms"):
        v = item.get(k)
        try:
            return int(v)
        except Exception:
            continue
    return 0

def select_water_var_ids(counters: Iterable[dict[str, Any]]) -> List[int]:
    ranked: List[Tuple[int,int,int]] = []
    for item in counters or []:
        var_id = _get_int(item, "var_id", "varId", "varid", "id")
        if var_id is None:
            continue
        score = _looks_like_water(item)
        if score <= 0:
            continue
        ts = _get_timestamp_ms(item)
        ranked.append((var_id, score, ts))
    ranked.sort(key=lambda t: (t[1], t[2]), reverse=True)
    var_ids = [r[0] for r in ranked]
    if var_ids:
        _LOGGER.debug("Auto-discovery: water var_ids=%s", var_ids)
    else:
        _LOGGER.debug("Auto-discovery: no water-like counters found")
    return var_ids