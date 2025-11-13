from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later

from .const import (
    DOMAIN,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    CONF_USERNAME,
    CONF_PASSWORD,
)
from .api import CEMClient, AuthResult

_LOGGER = logging.getLogger(__name__)


class CEMAuthCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinates CEM authentication; stores token/cookie/expiry in memory and refreshes before expiry."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        super().__init__(hass, logger=_LOGGER, name=f"{DOMAIN}_auth", update_interval=None)
        self.entry = entry
        session = async_get_clientsession(hass)
        # 🔧 FIX: new CEMClient signature only takes the aiohttp session
        self._client = CEMClient(session)
        self._last_result: Optional[AuthResult] = None
        self._update_interval_seconds = DEFAULT_UPDATE_INTERVAL_SECONDS
        self._unsub_timer = None

    @property
    def token(self) -> Optional[str]:
        return self._last_result.access_token if self._last_result else None

    @property
    def token_expires_at(self):
        if not self._last_result:
            return None
        return datetime.fromtimestamp(self._last_result.valid_to_ms / 1000, tz=timezone.utc)

    async def _async_update_data(self) -> dict[str, Any]:
        username = self.entry.data[CONF_USERNAME]
        password = self.entry.data[CONF_PASSWORD]

        try:
            result = await self._client.authenticate(username, password)
        except Exception as err:
            _LOGGER.warning("CEM auth failed: %s", err)
            raise UpdateFailed(f"Auth failed: {err}") from err

        self._last_result = result

        now_ts = datetime.now(timezone.utc).timestamp()
        secs_to_expiry = int(result.valid_to_ms / 1000 - now_ts)
        secs_to_expiry = max(secs_to_expiry, 0)

        # Re-auth ~5 minutes before expiry (min 5 minutes)
        next_interval = 300 if secs_to_expiry <= 600 else (secs_to_expiry - 300)
        self._update_interval_seconds = max(300, int(next_interval))  # >= 5 min

        return {
            "connected": True,
            "token_expires_at_iso": self.token_expires_at.isoformat() if self.token_expires_at else None,
            "token_expires_in_sec": secs_to_expiry,
            "cookie_present": self._last_result.cookie_value is not None,
        }

    def async_refresh_later(self) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

        def _cb(_now) -> None:
            async def _run():
                await self.async_request_refresh()
                self.async_refresh_later()
            self.hass.async_create_task(_run())

        self._unsub_timer = async_call_later(self.hass, self._update_interval_seconds, _cb)

    def async_cancel_timer(self) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None