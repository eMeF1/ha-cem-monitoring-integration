"""
Base coordinator classes for CEM Monitoring Integration.

This module provides the foundation for all coordinators in the integration:
- CEMBaseCoordinator: Base class with standardized 401 error handling
- CEMAuthCoordinator: Manages authentication tokens and cookies

Update Frequencies:
- CEMAuthCoordinator: Dynamic (refreshes ~5 minutes before token expiry, minimum 5 minutes)
"""
from __future__ import annotations

import logging
import ssl
from datetime import datetime, timezone
from typing import Any, Optional, Callable, Awaitable

from aiohttp import ClientSession, TCPConnector
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later

from ..const import (
    DOMAIN,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_VERIFY_SSL,
)
from ..api import CEMClient, AuthResult
from ..utils.retry import is_401_error

_LOGGER = logging.getLogger(__name__)


def _create_session(hass: HomeAssistant, verify_ssl: bool = True) -> ClientSession:
    """
    Create a ClientSession with optional SSL verification disabled.
    
    Args:
        hass: HomeAssistant instance
        verify_ssl: If False, disables SSL certificate verification (security risk!)
        
    Returns:
        ClientSession configured with appropriate SSL settings
    """
    if verify_ssl:
        return async_get_clientsession(hass)
    
    # Create session with SSL verification disabled
    _LOGGER.warning(
        "CEM Monitor: SSL certificate verification is DISABLED. "
        "This is a security risk and should only be used as a workaround for server-side certificate issues."
    )
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    connector = TCPConnector(ssl=ssl_context)
    return ClientSession(connector=connector)


class CEMBaseCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Base coordinator class that provides standardized 401 error handling."""

    def __init__(self, hass: HomeAssistant, logger: logging.Logger, name: str, auth: "CEMAuthCoordinator", update_interval=None) -> None:
        """Initialize base coordinator with auth reference."""
        super().__init__(hass, logger=logger, name=name, update_interval=update_interval)
        self._auth = auth

    def _get_auth_credentials(self) -> tuple[Optional[str], Optional[str]]:
        """
        Get current token and cookie from auth coordinator.
        
        Returns:
            Tuple of (token, cookie). Both may be None.
        """
        token = self._auth.token
        cookie = self._auth._last_result.cookie_value if self._auth._last_result else None
        return token, cookie

    async def _ensure_token(self, context: str = "") -> tuple[str, Optional[str]]:
        """
        Ensure we have a valid token, refreshing if necessary.
        
        Args:
            context: Optional context string for error messages (e.g., "for counter reading")
        
        Returns:
            Tuple of (token, cookie). Token is guaranteed to be non-None.
            
        Raises:
            UpdateFailed: If no token is available even after refresh.
        """
        token = self._auth.token
        if not token:
            await self._auth.async_request_refresh()
            token = self._auth.token
            if not token:
                error_msg = f"No token available{context}"
                raise UpdateFailed(error_msg)
        cookie = self._auth._last_result.cookie_value if self._auth._last_result else None
        return token, cookie

    async def _handle_401_error(
        self,
        err: Exception,
        api_call: Callable[[str, Optional[str]], Awaitable[Any]],
        context: str,
        error_prefix: str,
    ) -> Any:
        """
        Handle 401 errors by refreshing token and retrying once.
        
        Args:
            err: The exception that was raised
            api_call: Async callable that performs the API call with (token, cookie) arguments
            context: Context string for logging (e.g., "CEM counters(me=123)")
            error_prefix: Prefix for UpdateFailed messages (e.g., "Counters(me=123)")
            
        Returns:
            Result from the API call after successful retry
            
        Raises:
            UpdateFailed: If 401 persists after refresh, or if other errors occur
        """
        if not is_401_error(err):
            # Not a 401 error, raise it as UpdateFailed
            raise UpdateFailed(f"{error_prefix} failed: {err}") from err

        # Handle 401 by refreshing token and retrying once
        _LOGGER.debug("%s: 401 error, refreshing token and retrying", context)
        await self._auth.async_request_refresh()
        token, cookie = await self._ensure_token(f" after refresh for {error_prefix}")

        try:
            return await api_call(token, cookie)
        except Exception as retry_err:
            if is_401_error(retry_err):
                raise UpdateFailed(f"{error_prefix} failed: authentication failed after token refresh") from retry_err
            raise UpdateFailed(f"{error_prefix} failed after token refresh: {retry_err}") from retry_err


class CEMAuthCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinates CEM authentication; stores token/cookie/expiry in memory and refreshes before expiry."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        super().__init__(hass, logger=_LOGGER, name=f"{DOMAIN}_auth", update_interval=None)
        self.entry = entry
        verify_ssl = entry.data.get(CONF_VERIFY_SSL, True)
        session = _create_session(hass, verify_ssl)
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

