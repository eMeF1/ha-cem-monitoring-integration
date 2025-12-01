from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from .api import CEMClient
from .coordinator import CEMBaseCoordinator, CEMAuthCoordinator
from .discovery import select_water_var_ids
from .utils import ms_to_iso

_LOGGER = logging.getLogger(__name__)


class CEMMeterCountersCoordinator(CEMBaseCoordinator):
    """Counters for a specific meter (id=107&me_id=...)."""

    def __init__(self, hass: HomeAssistant, client: CEMClient, auth: CEMAuthCoordinator, me_id: int, mis_id: Optional[int], me_name: Optional[str]) -> None:
        super().__init__(hass, logger=_LOGGER, name=f"cem_monitor_counters_me_{me_id}", auth=auth, update_interval=timedelta(hours=12))
        self._client = client
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
        token, cookie = await self._ensure_token()

        try:
            raw_items = await self._client.get_counters_by_meter(self._me_id, token, cookie)
        except Exception as err:
            # Handle 401 by refreshing token and retrying once
            raw_items = await self._handle_401_error(
                err,
                lambda t, c: self._client.get_counters_by_meter(self._me_id, t, c),
                f"CEM counters(me={self._me_id})",
                f"Counters(me={self._me_id})",
            )

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