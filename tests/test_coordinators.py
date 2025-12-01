"""Tests for coordinators with mocked API calls."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from aiohttp import ClientResponseError

# conftest.py handles path setup and Home Assistant mocking
from custom_components.cem_monitor.coordinator import CEMAuthCoordinator
from custom_components.cem_monitor.userinfo_coordinator import CEMUserInfoCoordinator
from custom_components.cem_monitor.counter_reading_coordinator import CEMCounterReadingCoordinator
from custom_components.cem_monitor.api import CEMClient, AuthResult

# Use standard Exception for UpdateFailed in tests
UpdateFailed = Exception


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
        """Test that network errors are retried by API client.
        
        Note: Since we're mocking get_user_info at the coordinator level, we're actually
        bypassing the API client's retry logic. This test verifies that the coordinator
        can handle network errors that occur after the API client's retry logic has
        exhausted all retries. The API client's retry logic is tested separately in test_api.py.
        """
        from aiohttp.client_exceptions import ServerTimeoutError

        call_count = 0

        async def get_user_info_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Simulate that retry logic already tried and failed, now raise the final error
            # This tests that coordinator handles errors after retries are exhausted
            if call_count == 1:
                raise ServerTimeoutError()
            # On retry (coordinator level, not API client level), succeed
            return {"firma": "Test Co", "fir_id": 123}

        mock_client.get_user_info = AsyncMock(side_effect=get_user_info_side_effect)

        coordinator = CEMUserInfoCoordinator(mock_hass, mock_client, mock_auth_coordinator)

        # The coordinator should catch the error and raise UpdateFailed
        # since network errors are not 401 errors, so they won't trigger token refresh
        with pytest.raises(UpdateFailed) as exc_info:
            await coordinator._async_update_data()

        assert "UserInfo failed" in str(exc_info.value)
        assert call_count == 1  # Coordinator catches the error after API client retries are exhausted


class TestCounterReadingCoordinator:
    """Test CEMCounterReadingCoordinator."""

    @pytest.mark.asyncio
    async def test_counter_reading_success(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test successful counter reading fetch."""
        coordinator = CEMCounterReadingCoordinator(mock_hass, mock_client, mock_auth_coordinator, var_id=123)

        mock_client.get_counter_reading = AsyncMock(
            return_value={"value": 123.45, "timestamp_ms": 1234567890}
        )

        result = await coordinator._async_update_data()

        assert result["value"] == 123.45
        assert result["timestamp_ms"] == 1234567890

    @pytest.mark.asyncio
    async def test_counter_reading_401_refresh_token(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test that 401 triggers token refresh and retry."""
        call_count = 0

        async def get_counter_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ClientResponseError(None, None, status=401)
            return {"value": 123.45, "timestamp_ms": 1234567890}

        mock_client.get_counter_reading = AsyncMock(side_effect=get_counter_side_effect)
        mock_auth_coordinator.async_request_refresh = AsyncMock()
        mock_auth_coordinator.token = "new_token"

        coordinator = CEMCounterReadingCoordinator(mock_hass, mock_client, mock_auth_coordinator, var_id=123)

        result = await coordinator._async_update_data()

        assert result["value"] == 123.45
        assert call_count == 2
        mock_auth_coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_counter_reading_no_token_after_refresh(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test that missing token after refresh raises UpdateFailed."""
        from aiohttp import RequestInfo
        request_info = RequestInfo(url="http://test.com", method="GET", headers={}, real_url="http://test.com")
        mock_client.get_counter_reading = AsyncMock(
            side_effect=ClientResponseError(request_info, None, status=401)
        )
        mock_auth_coordinator.async_request_refresh = AsyncMock()
        mock_auth_coordinator.token = None  # Token refresh failed

        coordinator = CEMCounterReadingCoordinator(mock_hass, mock_client, mock_auth_coordinator, var_id=123)

        with pytest.raises(UpdateFailed) as exc_info:
            await coordinator._async_update_data()

        assert "no token available after refresh" in str(exc_info.value).lower() or "no token available for counter" in str(exc_info.value).lower()

