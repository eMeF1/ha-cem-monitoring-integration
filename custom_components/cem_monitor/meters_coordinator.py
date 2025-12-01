from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from .api import CEMClient
from .coordinator import CEMBaseCoordinator, CEMAuthCoordinator
from .utils import get_int, get_str

_LOGGER = logging.getLogger(__name__)


class CEMMetersCoordinator(CEMBaseCoordinator):
    """Fetches list of meters (id=108)."""

    def __init__(self, hass: HomeAssistant, client: CEMClient, auth: CEMAuthCoordinator) -> None:
        super().__init__(hass, logger=_LOGGER, name="cem_monitor_meters", auth=auth, update_interval=timedelta(hours=12))
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

        meters: List[Dict[str, Any]] = []
        for it in items:
            me_id = get_int(it, "me_id", "meid", "meId", "id")
            if me_id is None:
                continue
            mis_id = get_int(it, "mis_id", "misid", "misId", "object_id", "obj_id")
            me_name = get_str(it, "name", "nazev", "název", "caption", "popis", "description", "me_name")
            meters.append({"me_id": me_id, "mis_id": mis_id, "me_name": me_name, "raw": it})

        return {"meters": meters}