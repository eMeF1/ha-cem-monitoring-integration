from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .coordinator import CEMAuthCoordinator
from .api import CEMClient
from .const import DOMAIN
from .retry import is_401_error
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
            update_interval=None,
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
            # Handle 401 by refreshing token and retrying once
            if is_401_error(err):
                _LOGGER.debug("CEM water(var_id=%s): 401 error, refreshing token and retrying", self._var_id)
                await self._auth.async_request_refresh()
                token = self._auth.token
                if not token:
                    raise UpdateFailed(f"No token available after refresh for water(var_id={self._var_id})") from err
                cookie = self._auth._last_result.cookie_value if self._auth._last_result else None
                try:
                    reading = await self._client.get_water_consumption(self._var_id, token, cookie)
                except Exception as retry_err:
                    if is_401_error(retry_err):
                        raise UpdateFailed(f"Water consumption(var_id={self._var_id}) failed: authentication failed after token refresh") from retry_err
                    raise UpdateFailed(f"Water consumption(var_id={self._var_id}) failed after token refresh: {retry_err}") from retry_err
            else:
                # Other errors (network errors are already retried by API client)
                raise UpdateFailed(f"Water consumption failed: {err}") from err

        return {
            "value": reading.get("value"),
            "timestamp_ms": reading.get("timestamp_ms"),
            "timestamp_iso": _ms_to_iso(reading.get("timestamp_ms")),
            "fetched_at": int(time.time() * 1000),  # ensures coordinator data always changes
        }