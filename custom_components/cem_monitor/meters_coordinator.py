from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CEMClient
from .coordinator import CEMAuthCoordinator
from .retry import is_401_error

_LOGGER = logging.getLogger(__name__)


class CEMMetersCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches list of meters (id=108)."""

    def __init__(self, hass: HomeAssistant, client: CEMClient, auth: CEMAuthCoordinator) -> None:
        super().__init__(hass, logger=_LOGGER, name="cem_monitor_meters", update_interval=timedelta(hours=12))
        self._client = client
        self._auth = auth

    async def _async_update_data(self) -> dict[str, Any]:
        token = self._auth.token
        if not token:
            await self._auth.async_request_refresh()
            token = self._auth.token
            if not token:
                raise UpdateFailed("No token available for meters")

        cookie = self._auth._last_result.cookie_value if self._auth._last_result else None

        try:
            items = await self._client.get_meters(token, cookie)  # fetch all; we map locally
        except Exception as err:
            # Handle 401 by refreshing token and retrying once
            if is_401_error(err):
                _LOGGER.debug("CEM meters: 401 error, refreshing token and retrying")
                await self._auth.async_request_refresh()
                token = self._auth.token
                if not token:
                    raise UpdateFailed("No token available after refresh for meters") from err
                cookie = self._auth._last_result.cookie_value if self._auth._last_result else None
                try:
                    items = await self._client.get_meters(token, cookie)
                except Exception as retry_err:
                    if is_401_error(retry_err):
                        raise UpdateFailed("Meters failed: authentication failed after token refresh") from retry_err
                    raise UpdateFailed(f"Meters failed after token refresh: {retry_err}") from retry_err
            else:
                # Other errors (network errors are already retried by API client)
                raise UpdateFailed(f"id=108 failed: {err}") from err

        def _ival(d: Dict[str, Any], keys: List[str]) -> Optional[int]:
            for k in keys:
                if k in d:
                    try:
                        return int(d[k])
                    except Exception:
                        return None
            return None

        def _sval(d: Dict[str, Any], keys: List[str]) -> Optional[str]:
            for k in keys:
                v = d.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            return None

        meters: List[Dict[str, Any]] = []
        for it in items:
            me_id = _ival(it, ["me_id", "meid", "meId", "id"])
            if me_id is None:
                continue
            mis_id = _ival(it, ["mis_id", "misid", "misId", "object_id", "obj_id"])
            me_name = _sval(it, ["name", "nazev", "název", "caption", "popis", "description", "me_name"])
            meters.append({"me_id": me_id, "mis_id": mis_id, "me_name": me_name, "raw": it})

        return {"meters": meters}