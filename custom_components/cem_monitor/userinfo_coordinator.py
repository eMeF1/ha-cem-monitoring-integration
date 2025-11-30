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

_LOGGER = logging.getLogger(__name__)


def _ms_to_iso(ms: Any) -> str | None:
    try:
        if ms in (None, "", 0):
            return None
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return None


class CEMUserInfoCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches account/user info using the token from CEMAuthCoordinator."""

    def __init__(self, hass: HomeAssistant, client: CEMClient, auth: CEMAuthCoordinator) -> None:
        super().__init__(hass, logger=_LOGGER, name=f"{DOMAIN}_userinfo", update_interval=timedelta(hours=12))
        self._client = client
        self._auth = auth

    async def _async_update_data(self) -> dict[str, Any]:
        token = self._auth.token
        if not token:
            await self._auth.async_request_refresh()
            token = self._auth.token
            if not token:
                raise UpdateFailed("No token available for userinfo")

        cookie = self._auth._last_result.cookie_value if self._auth._last_result else None

        try:
            data = await self._client.get_user_info(token, cookie)
        except Exception as err:
            # Handle 401 by refreshing token and retrying once
            if is_401_error(err):
                _LOGGER.debug("CEM userinfo: 401 error, refreshing token and retrying")
                await self._auth.async_request_refresh()
                token = self._auth.token
                if not token:
                    raise UpdateFailed("No token available after refresh for userinfo") from err
                cookie = self._auth._last_result.cookie_value if self._auth._last_result else None
                try:
                    data = await self._client.get_user_info(token, cookie)
                except Exception as retry_err:
                    if is_401_error(retry_err):
                        raise UpdateFailed("UserInfo failed: authentication failed after token refresh") from retry_err
                    raise UpdateFailed(f"UserInfo failed after token refresh: {retry_err}") from retry_err
            else:
                # Other errors (network errors are already retried by API client)
                raise UpdateFailed(f"UserInfo failed: {err}") from err

        display_name = (data.get("show_name") or "").strip() or None

        return {
            "ok": True,
            "display_name": display_name,
            "company": (data.get("firma") or "").strip() or None,
            "person_id": data.get("oso_id"),
            "company_id": data.get("fir_id"),   # <- used for naming
            "customer_id": data.get("zak_id"),
            "login_valid_from": _ms_to_iso(data.get("log_od")),
            "login_valid_to": _ms_to_iso(data.get("log_do")),
        }