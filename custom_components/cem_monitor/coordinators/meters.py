"""
Meters coordinator for CEM Monitoring Integration.

This coordinator fetches the list of all meters associated with the account
using the CEM API endpoint id=108.

Purpose:
- Retrieves all meters (me_id) available for the authenticated account
- Extracts meter metadata (me_id, mis_id, me_name)
- Used during integration setup to discover available meters
- Provides meter information for hierarchical counter selection

Update Frequency:
- Every 12 hours (timedelta(hours=12))
- Updates are triggered automatically by Home Assistant's coordinator mechanism
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant

from ..api import CEMClient
from ..utils import get_int, get_str
from .base import CEMAuthCoordinator, CEMBaseCoordinator

_LOGGER = logging.getLogger(__name__)


class CEMMetersCoordinator(CEMBaseCoordinator):
    """Fetches list of meters (id=108)."""

    def __init__(self, hass: HomeAssistant, client: CEMClient, auth: CEMAuthCoordinator) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name="cem_monitor_meters",
            auth=auth,
            update_interval=timedelta(hours=12),
        )
        self._client = client

    async def _async_update_data(self) -> dict[str, Any]:
        token, cookie = await self._ensure_token()

        try:
            items = await self._client.get_meters(token, cookie)  # fetch all; we map locally
        except Exception as err:
            # Handle 401 by refreshing token and retrying once
            items = await self._handle_401_error(
                err,
                lambda t, c: self._client.get_meters(t, c),
                "CEM meters",
                "Meters",
            )

        meters: list[dict[str, Any]] = []
        for it in items:
            me_id = get_int(it, "me_id", "meid", "meId", "id")
            if me_id is None:
                continue
            mis_id = get_int(it, "mis_id", "misid", "misId", "object_id", "obj_id")
            me_name = get_str(
                it, "name", "nazev", "název", "caption", "popis", "description", "me_name"
            )
            meters.append({"me_id": me_id, "mis_id": mis_id, "me_name": me_name, "raw": it})

        return {"meters": meters}
