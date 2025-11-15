from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .coordinator import CEMAuthCoordinator
from .api import CEMClient
from .const import DOMAIN
import time

_LOGGER = logging.getLogger(__name__)

def _ms_to_iso(ms: Any) -> str | None:
    try:
        if ms is None:
            return None
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return None

class CEMWaterCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches water consumption using id=8 for a specific var_id."""

    def __init__(self, hass: HomeAssistant, client: CEMClient, auth: CEMAuthCoordinator, var_id: int) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_water_{var_id}",
            update_interval=timedelta(minutes=5),
        )
        self._client = client
        self._auth = auth
        self._var_id = int(var_id)

        # Always call async_update_listeners() even if data hasn't changed
        self.always_update = True

    @property
    def var_id(self) -> int:
        return self._var_id

    async def _async_update_data(self) -> dict[str, Any]:
        token = self._auth.token
        if not token:
            await self._auth.async_request_refresh()
            token = self._auth.token
            if not token:
                raise UpdateFailed("No token available for water consumption")

        cookie = self._auth._last_result.cookie_value if self._auth._last_result else None

        try:
            reading = await self._client.get_water_consumption(self._var_id, token, cookie)
        except Exception as err:
            status = getattr(err, "status", None)
            if status == 401 or "401" in str(err):
                await self._auth.async_request_refresh()
                token = self._auth.token
                cookie = self._auth._last_result.cookie_value if self._auth._last_result else None
                reading = await self._client.get_water_consumption(self._var_id, token, cookie)
            else:
                raise UpdateFailed(f"Water consumption failed: {err}") from err

        return {
            "value": reading.get("value"),
            "timestamp_ms": reading.get("timestamp_ms"),
            "timestamp_iso": _ms_to_iso(reading.get("timestamp_ms")),
            "fetched_at": int(time.time() * 1000),  # ensures coordinator data always changes
        }