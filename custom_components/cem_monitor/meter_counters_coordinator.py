from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CEMClient
from .coordinator import CEMAuthCoordinator
from .discovery import select_water_var_ids
from .retry import is_401_error
from .utils import ms_to_iso

_LOGGER = logging.getLogger(__name__)


class CEMMeterCountersCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Counters for a specific meter (id=107&me_id=...)."""

    def __init__(self, hass: HomeAssistant, client: CEMClient, auth: CEMAuthCoordinator, me_id: int, mis_id: Optional[int], me_name: Optional[str]) -> None:
        super().__init__(hass, logger=_LOGGER, name=f"cem_monitor_counters_me_{me_id}", update_interval=timedelta(hours=12))
        self._client = client
        self._auth = auth
        self._me_id = int(me_id)
        self._mis_id = mis_id
        self._me_name = me_name

    @property
    def me_id(self) -> int:
        return self._me_id

    @property
    def mis_id(self) -> Optional[int]:
        return self._mis_id

    @property
    def me_name(self) -> Optional[str]:
        return self._me_name

    async def _async_update_data(self) -> dict[str, Any]:
        token = self._auth.token
        if not token:
            await self._auth.async_request_refresh()
            token = self._auth.token
            if not token:
                raise UpdateFailed("No token available for counters")

        cookie = self._auth._last_result.cookie_value if self._auth._last_result else None

        try:
            raw_items = await self._client.get_counters_by_meter(self._me_id, token, cookie)
        except Exception as err:
            # Handle 401 by refreshing token and retrying once
            if is_401_error(err):
                _LOGGER.debug("CEM counters(me=%s): 401 error, refreshing token and retrying", self._me_id)
                await self._auth.async_request_refresh()
                token = self._auth.token
                if not token:
                    raise UpdateFailed(f"No token available after refresh for counters(me={self._me_id})") from err
                cookie = self._auth._last_result.cookie_value if self._auth._last_result else None
                try:
                    raw_items = await self._client.get_counters_by_meter(self._me_id, token, cookie)
                except Exception as retry_err:
                    if is_401_error(retry_err):
                        raise UpdateFailed(f"Counters(me={self._me_id}) failed: authentication failed after token refresh") from retry_err
                    raise UpdateFailed(f"Counters(me={self._me_id}) failed after token refresh: {retry_err}") from retry_err
            else:
                # Other errors (network errors are already retried by API client)
                raise UpdateFailed(f"id=107 me={self._me_id} failed: {err}") from err

        water_var_ids = select_water_var_ids(raw_items)

        counters: List[dict] = []
        raw_map: Dict[int, Dict[str, Any]] = {}

        for item in raw_items:
            # robust key extraction
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
            raw_map[var_id] = item

        return {
            "me_id": self._me_id,
            "mis_id": self._mis_id,
            "me_name": self._me_name,
            "counters": counters,
            "water_var_ids": water_var_ids,
            "counters_raw": raw_items,  # full array from ID 107
            "raw_map": raw_map,         # { var_id: full raw object }
        }