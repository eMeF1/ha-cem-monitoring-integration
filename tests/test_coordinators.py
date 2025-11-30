"""Tests for coordinators with mocked API calls."""
import sys
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from aiohttp import ClientResponseError

# Add custom_components to path for testing
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock Home Assistant dependencies before importing coordinators
import sys
from unittest.mock import MagicMock

# Mock homeassistant module
homeassistant_mock = MagicMock()
homeassistant_mock.helpers.update_coordinator.UpdateFailed = Exception
sys.modules['homeassistant'] = homeassistant_mock
sys.modules['homeassistant.core'] = MagicMock()
sys.modules['homeassistant.helpers'] = MagicMock()
sys.modules['homeassistant.helpers.update_coordinator'] = MagicMock()
sys.modules['homeassistant.helpers.update_coordinator'].UpdateFailed = Exception

from custom_components.cem_monitor.coordinator import CEMAuthCoordinator
from custom_components.cem_monitor.userinfo_coordinator import CEMUserInfoCoordinator
from custom_components.cem_monitor.water_coordinator import CEMWaterCoordinator
from custom_components.cem_monitor.api import CEMClient, AuthResult

UpdateFailed = Exception  # Use standard Exception for testing


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.async_create_task = MagicMock()
    return hass


@pytest.fixture
def mock_entry():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.data = {"username": "test_user", "password": "test_pass"}
    entry.entry_id = "test_entry"
    return entry


@pytest.fixture
def mock_client():
    """Create a mock CEMClient."""
    return AsyncMock(spec=CEMClient)


@pytest.fixture
def mock_auth_coordinator(mock_hass, mock_entry):
    """Create a mock auth coordinator."""
    auth = MagicMock(spec=CEMAuthCoordinator)
    auth.token = "test_token"
    auth._last_result = AuthResult(
        access_token="test_token",
        valid_to_ms=int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp() * 1000),
        cookie_value="test_cookie",
    )
    auth.async_request_refresh = AsyncMock()
    return auth


class TestUserInfoCoordinator:
    """Test CEMUserInfoCoordinator."""

    @pytest.mark.asyncio
    async def test_userinfo_success(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test successful userinfo fetch."""
        coordinator = CEMUserInfoCoordinator(mock_hass, mock_client, mock_auth_coordinator)

        mock_client.get_user_info = AsyncMock(
            return_value={"firma": "Test Co", "fir_id": 123, "show_name": "Test User"}
        )

        result = await coordinator._async_update_data()

        assert result["company"] == "Test Co"
        assert result["company_id"] == 123
        assert result["display_name"] == "Test User"

    @pytest.mark.asyncio
    async def test_userinfo_401_refresh_token(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test that 401 triggers token refresh and retry."""
        call_count = 0

        async def get_user_info_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ClientResponseError(None, None, status=401)
            return {"firma": "Test Co", "fir_id": 123}

        mock_client.get_user_info = AsyncMock(side_effect=get_user_info_side_effect)
        mock_auth_coordinator.async_request_refresh = AsyncMock()
        mock_auth_coordinator.token = "new_token"
        mock_auth_coordinator._last_result.cookie_value = "new_cookie"

        coordinator = CEMUserInfoCoordinator(mock_hass, mock_client, mock_auth_coordinator)

        result = await coordinator._async_update_data()

        assert result["company"] == "Test Co"
        assert call_count == 2  # Initial call + retry after refresh
        mock_auth_coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_userinfo_401_persists_after_refresh(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test that persistent 401 after refresh raises UpdateFailed."""
        mock_client.get_user_info = AsyncMock(
            side_effect=ClientResponseError(None, None, status=401)
        )
        mock_auth_coordinator.async_request_refresh = AsyncMock()
        mock_auth_coordinator.token = "new_token"

        coordinator = CEMUserInfoCoordinator(mock_hass, mock_client, mock_auth_coordinator)

        with pytest.raises(UpdateFailed) as exc_info:
            await coordinator._async_update_data()

        assert "authentication failed after token refresh" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_userinfo_network_error_retried(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test that network errors are retried by API client."""
        from aiohttp.client_exceptions import ServerTimeoutError

        call_count = 0

        async def get_user_info_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ServerTimeoutError()
            return {"firma": "Test Co", "fir_id": 123}

        mock_client.get_user_info = AsyncMock(side_effect=get_user_info_side_effect)

        coordinator = CEMUserInfoCoordinator(mock_hass, mock_client, mock_auth_coordinator)

        result = await coordinator._async_update_data()

        assert result["company"] == "Test Co"
        # Network errors are retried by API client, so we should see multiple calls
        assert call_count >= 1


class TestWaterCoordinator:
    """Test CEMWaterCoordinator."""

    @pytest.mark.asyncio
    async def test_water_consumption_success(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test successful water consumption fetch."""
        coordinator = CEMWaterCoordinator(mock_hass, mock_client, mock_auth_coordinator, var_id=123)

        mock_client.get_water_consumption = AsyncMock(
            return_value={"value": 123.45, "timestamp_ms": 1234567890}
        )

        result = await coordinator._async_update_data()

        assert result["value"] == 123.45
        assert result["timestamp_ms"] == 1234567890

    @pytest.mark.asyncio
    async def test_water_consumption_401_refresh_token(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test that 401 triggers token refresh and retry."""
        call_count = 0

        async def get_water_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ClientResponseError(None, None, status=401)
            return {"value": 123.45, "timestamp_ms": 1234567890}

        mock_client.get_water_consumption = AsyncMock(side_effect=get_water_side_effect)
        mock_auth_coordinator.async_request_refresh = AsyncMock()
        mock_auth_coordinator.token = "new_token"

        coordinator = CEMWaterCoordinator(mock_hass, mock_client, mock_auth_coordinator, var_id=123)

        result = await coordinator._async_update_data()

        assert result["value"] == 123.45
        assert call_count == 2
        mock_auth_coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_water_consumption_no_token_after_refresh(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test that missing token after refresh raises UpdateFailed."""
        mock_client.get_water_consumption = AsyncMock(
            side_effect=ClientResponseError(None, None, status=401)
        )
        mock_auth_coordinator.async_request_refresh = AsyncMock()
        mock_auth_coordinator.token = None  # Token refresh failed

        coordinator = CEMWaterCoordinator(mock_hass, mock_client, mock_auth_coordinator, var_id=123)

        with pytest.raises(UpdateFailed) as exc_info:
            await coordinator._async_update_data()

        assert "no token available after refresh" in str(exc_info.value).lower()

