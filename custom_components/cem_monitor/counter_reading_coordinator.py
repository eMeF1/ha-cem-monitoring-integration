"""
Counter reading coordinator for CEM Monitoring Integration.

This coordinator fetches the latest reading value for a specific counter (var_id)
using the CEM API endpoint id=8.

Purpose:
- Retrieves the most recent counter reading (value and timestamp) for a given var_id
- Used by sensor entities to display current counter values
- Supports batch updates via the main integration refresh mechanism

Update Frequency:
- Manual updates only (no automatic periodic refresh)
- Updates are triggered by the integration's batch refresh mechanism
- Default batch refresh interval: 30 minutes (configurable via integration options)
"""
from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from .coordinator import CEMBaseCoordinator, CEMAuthCoordinator
from .api import CEMClient
from .const import DOMAIN
from .utils import ms_to_iso

_LOGGER = logging.getLogger(__name__)

class CEMCounterReadingCoordinator(CEMBaseCoordinator):
    """Fetches counter reading using id=8 for a specific var_id."""

    def __init__(self, hass: HomeAssistant, client: CEMClient, auth: CEMAuthCoordinator, var_id: int) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_counter_{var_id}",
            auth=auth,
            update_interval=None,
        )
        self._client = client
        self._var_id = int(var_id)

        # Always call async_update_listeners() even if data hasn't changed
        self.always_update = True

    @property
    def var_id(self) -> int:
        return self._var_id

    async def _async_update_data(self) -> dict[str, Any]:
        token, cookie = await self._ensure_token(" for counter reading")

        try:
            reading = await self._client.get_counter_reading(self._var_id, token, cookie)
        except Exception as err:
            # Handle 401 by refreshing token and retrying once
            reading = await self._handle_401_error(
                err,
                lambda t, c: self._client.get_counter_reading(self._var_id, t, c),
                f"CEM counter(var_id={self._var_id})",
                f"Counter reading(var_id={self._var_id})",
            )

        return {
            "value": reading.get("value"),
            "timestamp_ms": reading.get("timestamp_ms"),
            "timestamp_iso": ms_to_iso(reading.get("timestamp_ms")),
            "fetched_at": int(time.time() * 1000),  # ensures coordinator data always changes
        }

