from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, List

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .coordinator import CEMAuthCoordinator
from .api import CEMClient
from .discovery import select_water_var_ids
from .const import DOMAIN
from .utils import ms_to_iso

_LOGGER = logging.getLogger(__name__)

class CEMCountersCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches 'Last counters readings' (id=21) and normalizes output."""

    def __init__(self, hass: HomeAssistant, client: CEMClient, auth: CEMAuthCoordinator) -> None:
        super().__init__(hass, logger=_LOGGER, name=f"{DOMAIN}_counters", update_interval=timedelta(hours=12))
        self._client = client
        self._auth = auth

    async def _async_update_data(self) -> dict[str, Any]:
        token = self._auth.token
        if not token:
            await self._auth.async_request_refresh()
            token = self._auth.token
            if not token:
                raise UpdateFailed("No token available for counters")

        cookie = self._auth._last_result.cookie_value if self._auth._last_result else None

        try:
            payload = await self._client.get_last_counters_readings(token, cookie)
        except Exception as err:
            raise UpdateFailed(f"id=21 failed: {err}") from err

        counters: List[dict[str, Any]] = []
        for item in payload:
            var_id = None
            for k in ("var_id", "varId", "varid", "id"):
                if k in item:
                    try:
                        var_id = int(item[k]); break
                    except Exception:
                        pass
            if var_id is None:
                continue

            name = None
            for k in ("name", "nazev", "název", "caption", "popis", "description"):
                if k in item and isinstance(item[k], str) and item[k].strip():
                    name = item[k].strip(); break

            unit = None
            for k in ("unit", "jednotka"):
                if k in item and isinstance(item[k], str) and item[k].strip():
                    unit = item[k].strip(); break

            ts_ms = None
            for k in ("timestamp", "time", "ts", "ts_ms", "timestamp_ms"):
                if k in item:
                    try:
                        ts_ms = int(item[k]); break
                    except Exception:
                        pass

            counters.append({
                "var_id": var_id,
                "name": name,
                "unit": unit,
                "timestamp_ms": ts_ms,
                "timestamp_iso": ms_to_iso(ts_ms),
                "raw": item,  # kept internal
            })

        water_var_ids = select_water_var_ids(payload)
        return {"counters": counters, "water_var_ids": water_var_ids}