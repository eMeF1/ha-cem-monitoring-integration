"""
User info coordinator for CEM Monitoring Integration.

This coordinator fetches account and user information using the CEM API endpoint id=9.

Purpose:
- Retrieves account metadata (company_id, customer_id, person_id)
- Extracts user display information (display_name, company)
- Provides login validity period information
- Used for device naming and account-level sensor entities

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
from ..const import DOMAIN
from ..utils import ms_to_iso
from .base import CEMAuthCoordinator, CEMBaseCoordinator

_LOGGER = logging.getLogger(__name__)


class CEMUserInfoCoordinator(CEMBaseCoordinator):
    """Fetches account/user info using the token from CEMAuthCoordinator."""

    def __init__(self, hass: HomeAssistant, client: CEMClient, auth: CEMAuthCoordinator) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_userinfo",
            auth=auth,
            update_interval=timedelta(hours=12),
        )
        self._client = client

    async def _async_update_data(self) -> dict[str, Any]:
        token, cookie = await self._ensure_token()

        try:
            data = await self._client.get_user_info(token, cookie)
        except Exception as err:
            # Handle 401 by refreshing token and retrying once
            data = await self._handle_401_error(
                err,
                lambda t, c: self._client.get_user_info(t, c),
                "CEM userinfo",
                "UserInfo",
            )

        display_name = (data.get("show_name") or "").strip() or None

        return {
            "ok": True,
            "display_name": display_name,
            "company": (data.get("firma") or "").strip() or None,
            "person_id": data.get("oso_id"),
            "company_id": data.get("fir_id"),  # <- used for naming
            "customer_id": data.get("zak_id"),
            "login_valid_from": ms_to_iso(data.get("log_od")),
            "login_valid_to": ms_to_iso(data.get("log_do")),
        }
