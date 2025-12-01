from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CEMClient
from .coordinator import CEMAuthCoordinator
from .discovery import select_water_var_ids
from .const import DOMAIN
from .utils import ms_to_iso

_LOGGER = logging.getLogger(__name__)


class CEMObjectCountersCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Counters for a specific object (id=45&mis_id=...)."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: CEMClient,
        auth: CEMAuthCoordinator,
        mis_id: int,
        mis_name: Optional[str],
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_counters_{mis_id}",
            update_interval=timedelta(hours=12),
        )
        self._client = client
        self._auth = auth
        self._mis_id = int(mis_id)
        self._mis_name = mis_name

    @property
    def mis_id(self) -> int:
        return self._mis_id

    @property
    def mis_name(self) -> Optional[str]:
        return self._mis_name

    async def _async_update_data(self) -> dict[str, Any]:
        token = self._auth.token
        if not token:
            await self._auth.async_request_refresh()
            token = self._auth.token
            if not token:
                raise UpdateFailed("No token available for counters")

        cookie = self._auth._last_result.cookie_value if self._auth._last_result else None

        try:
            raw_items: List[Dict[str, Any]] = await self._client.get_counters_for_object(
                self._mis_id, token, cookie
            )
        except Exception as err:
            raise UpdateFailed(f"id=45 mis={self._mis_id} failed: {err}") from err

        # Choose likely water counters (heuristics work on the raw payload)
        water_var_ids = select_water_var_ids(raw_items)

        # Build compact counters list and a var_id -> raw mapping for sensors
        counters: List[dict] = []
        raw_map: Dict[int, Dict[str, Any]] = {}

        for item in raw_items:
            # Extract keys robustly
            var_id = None
            for k in ("var_id", "varId", "varid", "id"):
                if k in item:
                    try:
                        var_id = int(item[k])
                        break
                    except Exception:
                        pass
            if var_id is None:
                continue

            name = None
            for k in ("name", "nazev", "název", "caption", "popis", "description"):
                if isinstance(item.get(k), str) and item[k].strip():
                    name = item[k].strip()
                    break

            unit = None
            for k in ("unit", "jednotka"):
                if isinstance(item.get(k), str) and item[k].strip():
                    unit = item[k].strip()
                    break

            ts_ms = None
            for k in ("timestamp", "time", "ts", "ts_ms", "timestamp_ms"):
                if k in item:
                    try:
                        ts_ms = int(item[k])
                        break
                    except Exception:
                        pass

            counters.append(
                {
                    "var_id": var_id,
                    "name": name,
                    "unit": unit,
                    "timestamp_ms": ts_ms,
                    "timestamp_iso": ms_to_iso(ts_ms),
                }
            )
            raw_map[var_id] = item  # store the full raw JSON for per-var lookup

        return {
            "mis_id": self._mis_id,
            "mis_name": self._mis_name,
            "counters": counters,
            "water_var_ids": water_var_ids,
            # NEW: expose raw for sensors (list and map)
            "counters_raw": raw_items,   # full array as returned by ID 45
            "raw_map": raw_map,          # { var_id: raw_item }
        }