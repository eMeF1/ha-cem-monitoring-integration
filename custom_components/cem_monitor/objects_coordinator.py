"""
Objects coordinator for CEM Monitoring Integration.

This coordinator fetches the list of objects (sites/places) associated with the account
using the CEM API endpoint id=23.

Purpose:
- Retrieves all objects (mis_id) available for the authenticated account
- Extracts object metadata (mis_id, mis_name, mis_idp for parent relationships)
- Used during integration setup to organize meters and counters by location
- Provides object information for device hierarchy and entity naming

Update Frequency:
- Every 12 hours (timedelta(hours=12))
- Updates are triggered automatically by Home Assistant's coordinator mechanism
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from .api import CEMClient
from .coordinator import CEMBaseCoordinator, CEMAuthCoordinator
from .const import DOMAIN
from .utils import get_int, get_str

_LOGGER = logging.getLogger(__name__)


class CEMObjectsCoordinator(CEMBaseCoordinator):
    """Fetches objects (sites) via id=23 and exposes both compact and raw results."""

    def __init__(self, hass: HomeAssistant, client: CEMClient, auth: CEMAuthCoordinator) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_objects",
            auth=auth,
            update_interval=timedelta(hours=12),
        )
        self._client = client

    async def _async_update_data(self) -> dict[str, Any]:
        token, cookie = await self._ensure_token()

        try:
            raw_items: List[Dict[str, Any]] = await self._client.get_objects(token, cookie)
        except Exception as err:
            # Handle 401 by refreshing token and retrying once
            raw_items = await self._handle_401_error(
                err,
                lambda t, c: self._client.get_objects(t, c),
                "CEM objects",
                "Objects",
            )

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