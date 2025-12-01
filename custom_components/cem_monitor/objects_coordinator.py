from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CEMClient
from .coordinator import CEMAuthCoordinator
from .const import DOMAIN
from .retry import is_401_error
from .utils import get_int, get_str

_LOGGER = logging.getLogger(__name__)


class CEMObjectsCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches objects (sites) via id=23 and exposes both compact and raw results."""

    def __init__(self, hass: HomeAssistant, client: CEMClient, auth: CEMAuthCoordinator) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_objects",
            update_interval=timedelta(hours=12),
        )
        self._client = client
        self._auth = auth

    async def _async_update_data(self) -> dict[str, Any]:
        token = self._auth.token
        if not token:
            await self._auth.async_request_refresh()
            token = self._auth.token
            if not token:
                raise UpdateFailed("No token available for objects")

        cookie = self._auth._last_result.cookie_value if self._auth._last_result else None

        try:
            raw_items: List[Dict[str, Any]] = await self._client.get_objects(token, cookie)
        except Exception as err:
            # Handle 401 by refreshing token and retrying once
            if is_401_error(err):
                _LOGGER.debug("CEM objects: 401 error, refreshing token and retrying")
                await self._auth.async_request_refresh()
                token = self._auth.token
                if not token:
                    raise UpdateFailed("No token available after refresh for objects") from err
                cookie = self._auth._last_result.cookie_value if self._auth._last_result else None
                try:
                    raw_items = await self._client.get_objects(token, cookie)
                except Exception as retry_err:
                    if is_401_error(retry_err):
                        raise UpdateFailed("Objects failed: authentication failed after token refresh") from retry_err
                    raise UpdateFailed(f"Objects failed after token refresh: {retry_err}") from retry_err
            else:
                # Other errors (network errors are already retried by API client)
                raise UpdateFailed(f"id=23 failed: {err}") from err

        objects: List[Dict[str, Any]] = []
        raw_by_mis: Dict[int, Dict[str, Any]] = {}

        for it in raw_items:
            mis_id = get_int(it, "mis_id", "misid", "misId", "id")
            if mis_id is None:
                continue
            mis_name = get_str(it, "mis_nazev", "mis_name", "name", "nazev", "název", "caption", "description")
            mis_idp = get_int(it, "mis_idp", "parent_id", "parent")
            objects.append(
                {
                    "mis_id": mis_id,
                    "mis_name": mis_name,
                    "mis_idp": mis_idp,
                }
            )
            raw_by_mis[mis_id] = it

        return {
            # Compact for quick UI inspection
            "objects": objects,
            # Full original payload from id=23 (array of dicts)
            "objects_raw": raw_items,
            # Map for efficient lookup from mis_id -> raw object
            "raw_by_mis": raw_by_mis,
        }