"""Tests for coordinators with mocked API calls."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from aiohttp import ClientResponseError

# conftest.py handles path setup and Home Assistant mocking
from custom_components.cem_monitor.coordinator import CEMAuthCoordinator
from custom_components.cem_monitor.userinfo_coordinator import CEMUserInfoCoordinator
from custom_components.cem_monitor.counter_reading_coordinator import CEMCounterReadingCoordinator
from custom_components.cem_monitor.objects_coordinator import CEMObjectsCoordinator
from custom_components.cem_monitor.meters_coordinator import CEMMetersCoordinator
from custom_components.cem_monitor.meter_counters_coordinator import CEMMeterCountersCoordinator
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


class TestAuthCoordinator:
    """Test CEMAuthCoordinator."""

    @pytest.mark.asyncio
    async def test_auth_success(self, mock_hass, mock_entry):
        """Test successful authentication with valid credentials."""
        with patch('custom_components.cem_monitor.coordinator.async_get_clientsession') as mock_get_session, \
             patch('custom_components.cem_monitor.coordinator.CEMClient') as mock_client_class:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            future_expiry = datetime.now(timezone.utc) + timedelta(hours=2)
            valid_to_ms = int(future_expiry.timestamp() * 1000)
            
            mock_client.authenticate = AsyncMock(
                return_value=AuthResult(
                    access_token="test_access_token",
                    valid_to_ms=valid_to_ms,
                    cookie_value="test_cookie_value"
                )
            )
            
            coordinator = CEMAuthCoordinator(mock_hass, mock_entry)
            result = await coordinator._async_update_data()
            
            assert result["connected"] is True
            assert result["cookie_present"] is True
            assert coordinator.token == "test_access_token"
            assert coordinator.token_expires_at is not None
            assert coordinator._last_result.cookie_value == "test_cookie_value"
            mock_client.authenticate.assert_called_once_with("test_user", "test_pass")

    @pytest.mark.asyncio
    async def test_auth_failure_401(self, mock_hass, mock_entry):
        """Test authentication failure with 401 error."""
        from aiohttp import RequestInfo
        request_info = RequestInfo(url="http://test.com", method="POST", headers={}, real_url="http://test.com")
        
        with patch('custom_components.cem_monitor.coordinator.async_get_clientsession') as mock_get_session, \
             patch('custom_components.cem_monitor.coordinator.CEMClient') as mock_client_class:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            mock_client.authenticate = AsyncMock(
                side_effect=ClientResponseError(request_info, None, status=401)
            )
            
            coordinator = CEMAuthCoordinator(mock_hass, mock_entry)
            
            with pytest.raises(UpdateFailed) as exc_info:
                await coordinator._async_update_data()
            
            assert "Auth failed" in str(exc_info.value)
            assert coordinator.token is None

    @pytest.mark.asyncio
    async def test_auth_failure_403(self, mock_hass, mock_entry):
        """Test authentication failure with 403 error."""
        from aiohttp import RequestInfo
        request_info = RequestInfo(url="http://test.com", method="POST", headers={}, real_url="http://test.com")
        
        with patch('custom_components.cem_monitor.coordinator.async_get_clientsession') as mock_get_session, \
             patch('custom_components.cem_monitor.coordinator.CEMClient') as mock_client_class:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            mock_client.authenticate = AsyncMock(
                side_effect=ClientResponseError(request_info, None, status=403)
            )
            
            coordinator = CEMAuthCoordinator(mock_hass, mock_entry)
            
            with pytest.raises(UpdateFailed) as exc_info:
                await coordinator._async_update_data()
            
            assert "Auth failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_auth_network_error(self, mock_hass, mock_entry):
        """Test authentication failure with network error."""
        with patch('custom_components.cem_monitor.coordinator.async_get_clientsession') as mock_get_session, \
             patch('custom_components.cem_monitor.coordinator.CEMClient') as mock_client_class:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            from aiohttp.client_exceptions import ServerTimeoutError
            mock_client.authenticate = AsyncMock(
                side_effect=ServerTimeoutError()
            )
            
            coordinator = CEMAuthCoordinator(mock_hass, mock_entry)
            
            with pytest.raises(UpdateFailed) as exc_info:
                await coordinator._async_update_data()
            
            assert "Auth failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_token_expiry_calculation(self, mock_hass, mock_entry):
        """Test token expiry calculation and refresh scheduling."""
        with patch('custom_components.cem_monitor.coordinator.async_get_clientsession') as mock_get_session, \
             patch('custom_components.cem_monitor.coordinator.CEMClient') as mock_client_class:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            # Set expiry to 1 hour from now
            future_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
            valid_to_ms = int(future_expiry.timestamp() * 1000)
            
            mock_client.authenticate = AsyncMock(
                return_value=AuthResult(
                    access_token="test_token",
                    valid_to_ms=valid_to_ms,
                    cookie_value="test_cookie"
                )
            )
            
            coordinator = CEMAuthCoordinator(mock_hass, mock_entry)
            result = await coordinator._async_update_data()
            
            # Should schedule refresh ~5 minutes before expiry (min 5 minutes)
            # With 1 hour expiry, should be 55 minutes (3600 - 300)
            assert result["token_expires_in_sec"] > 0
            assert coordinator._update_interval_seconds >= 300  # At least 5 minutes

    @pytest.mark.asyncio
    async def test_token_expiry_short(self, mock_hass, mock_entry):
        """Test token expiry calculation for short-lived tokens."""
        with patch('custom_components.cem_monitor.coordinator.async_get_clientsession') as mock_get_session, \
             patch('custom_components.cem_monitor.coordinator.CEMClient') as mock_client_class:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            # Set expiry to 10 minutes from now (less than 600 seconds)
            future_expiry = datetime.now(timezone.utc) + timedelta(minutes=10)
            valid_to_ms = int(future_expiry.timestamp() * 1000)
            
            mock_client.authenticate = AsyncMock(
                return_value=AuthResult(
                    access_token="test_token",
                    valid_to_ms=valid_to_ms,
                    cookie_value="test_cookie"
                )
            )
            
            coordinator = CEMAuthCoordinator(mock_hass, mock_entry)
            result = await coordinator._async_update_data()
            
            # Should use minimum 5 minutes (300 seconds) for short-lived tokens
            assert coordinator._update_interval_seconds == 300

    @pytest.mark.asyncio
    async def test_cookie_extraction(self, mock_hass, mock_entry):
        """Test cookie extraction from response."""
        with patch('custom_components.cem_monitor.coordinator.async_get_clientsession') as mock_get_session, \
             patch('custom_components.cem_monitor.coordinator.CEMClient') as mock_client_class:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            future_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
            valid_to_ms = int(future_expiry.timestamp() * 1000)
            
            mock_client.authenticate = AsyncMock(
                return_value=AuthResult(
                    access_token="test_token",
                    valid_to_ms=valid_to_ms,
                    cookie_value="extracted_cookie"
                )
            )
            
            coordinator = CEMAuthCoordinator(mock_hass, mock_entry)
            result = await coordinator._async_update_data()
            
            assert result["cookie_present"] is True
            assert coordinator._last_result.cookie_value == "extracted_cookie"

    @pytest.mark.asyncio
    async def test_cookie_missing(self, mock_hass, mock_entry):
        """Test handling when cookie is missing from response."""
        with patch('custom_components.cem_monitor.coordinator.async_get_clientsession') as mock_get_session, \
             patch('custom_components.cem_monitor.coordinator.CEMClient') as mock_client_class:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            future_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
            valid_to_ms = int(future_expiry.timestamp() * 1000)
            
            mock_client.authenticate = AsyncMock(
                return_value=AuthResult(
                    access_token="test_token",
                    valid_to_ms=valid_to_ms,
                    cookie_value=None
                )
            )
            
            coordinator = CEMAuthCoordinator(mock_hass, mock_entry)
            result = await coordinator._async_update_data()
            
            assert result["cookie_present"] is False
            assert coordinator._last_result.cookie_value is None

    @pytest.mark.asyncio
    async def test_token_property(self, mock_hass, mock_entry):
        """Test token property returns access_token."""
        with patch('custom_components.cem_monitor.coordinator.async_get_clientsession') as mock_get_session, \
             patch('custom_components.cem_monitor.coordinator.CEMClient') as mock_client_class:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            future_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
            valid_to_ms = int(future_expiry.timestamp() * 1000)
            
            mock_client.authenticate = AsyncMock(
                return_value=AuthResult(
                    access_token="property_test_token",
                    valid_to_ms=valid_to_ms,
                    cookie_value="test_cookie"
                )
            )
            
            coordinator = CEMAuthCoordinator(mock_hass, mock_entry)
            await coordinator._async_update_data()
            
            assert coordinator.token == "property_test_token"

    @pytest.mark.asyncio
    async def test_token_property_none(self, mock_hass, mock_entry):
        """Test token property returns None when no auth result."""
        with patch('custom_components.cem_monitor.coordinator.async_get_clientsession') as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session
            coordinator = CEMAuthCoordinator(mock_hass, mock_entry)
            assert coordinator.token is None

    @pytest.mark.asyncio
    async def test_token_expires_at_property(self, mock_hass, mock_entry):
        """Test token_expires_at property returns correct datetime."""
        with patch('custom_components.cem_monitor.coordinator.async_get_clientsession') as mock_get_session, \
             patch('custom_components.cem_monitor.coordinator.CEMClient') as mock_client_class:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            future_expiry = datetime.now(timezone.utc) + timedelta(hours=2)
            valid_to_ms = int(future_expiry.timestamp() * 1000)
            
            mock_client.authenticate = AsyncMock(
                return_value=AuthResult(
                    access_token="test_token",
                    valid_to_ms=valid_to_ms,
                    cookie_value="test_cookie"
                )
            )
            
            coordinator = CEMAuthCoordinator(mock_hass, mock_entry)
            await coordinator._async_update_data()
            
            expires_at = coordinator.token_expires_at
            assert expires_at is not None
            assert isinstance(expires_at, datetime)
            # Allow small tolerance for timing
            assert abs((expires_at - future_expiry).total_seconds()) < 1

    @pytest.mark.asyncio
    async def test_token_expires_at_property_none(self, mock_hass, mock_entry):
        """Test token_expires_at property returns None when no auth result."""
        with patch('custom_components.cem_monitor.coordinator.async_get_clientsession') as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session
            coordinator = CEMAuthCoordinator(mock_hass, mock_entry)
            assert coordinator.token_expires_at is None


class TestObjectsCoordinator:
    """Test CEMObjectsCoordinator."""

    @pytest.mark.asyncio
    async def test_objects_success(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test successful fetch of objects list (id=23 endpoint)."""
        coordinator = CEMObjectsCoordinator(mock_hass, mock_client, mock_auth_coordinator)
        
        raw_items = [
            {"mis_id": 1, "mis_nazev": "Object 1", "mis_idp": None},
            {"mis_id": 2, "mis_name": "Object 2", "mis_idp": 1},
            {"id": 3, "name": "Object 3", "parent_id": 2},
        ]
        
        mock_client.get_objects = AsyncMock(return_value=raw_items)
        
        result = await coordinator._async_update_data()
        
        assert len(result["objects"]) == 3
        assert result["objects"][0]["mis_id"] == 1
        assert result["objects"][0]["mis_name"] == "Object 1"
        assert result["objects"][1]["mis_id"] == 2
        assert result["objects"][1]["mis_name"] == "Object 2"
        assert result["objects"][1]["mis_idp"] == 1
        assert len(result["raw_by_mis"]) == 3
        assert result["raw_by_mis"][1] == raw_items[0]
        assert result["objects_raw"] == raw_items

    @pytest.mark.asyncio
    async def test_objects_401_refresh_token(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test that 401 triggers token refresh and retry."""
        call_count = 0
        
        async def get_objects_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ClientResponseError(None, None, status=401)
            return [{"mis_id": 1, "mis_nazev": "Object 1"}]
        
        mock_client.get_objects = AsyncMock(side_effect=get_objects_side_effect)
        mock_auth_coordinator.async_request_refresh = AsyncMock()
        mock_auth_coordinator.token = "new_token"
        mock_auth_coordinator._last_result.cookie_value = "new_cookie"
        
        coordinator = CEMObjectsCoordinator(mock_hass, mock_client, mock_auth_coordinator)
        
        result = await coordinator._async_update_data()
        
        assert len(result["objects"]) == 1
        assert call_count == 2  # Initial call + retry after refresh
        mock_auth_coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_objects_401_persists_after_refresh(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test that persistent 401 after refresh raises UpdateFailed."""
        mock_client.get_objects = AsyncMock(
            side_effect=ClientResponseError(None, None, status=401)
        )
        mock_auth_coordinator.async_request_refresh = AsyncMock()
        mock_auth_coordinator.token = "new_token"
        
        coordinator = CEMObjectsCoordinator(mock_hass, mock_client, mock_auth_coordinator)
        
        with pytest.raises(UpdateFailed) as exc_info:
            await coordinator._async_update_data()
        
        assert "authentication failed after token refresh" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_objects_data_structure_parsing(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test data structure parsing (objects list, raw_by_mis mapping)."""
        coordinator = CEMObjectsCoordinator(mock_hass, mock_client, mock_auth_coordinator)
        
        raw_items = [
            {"mis_id": 10, "mis_nazev": "Site A", "mis_idp": None},
            {"misid": 20, "nazev": "Site B", "parent_id": 10},
            {"id": 30, "caption": "Site C", "parent": 20},
        ]
        
        mock_client.get_objects = AsyncMock(return_value=raw_items)
        
        result = await coordinator._async_update_data()
        
        assert len(result["objects"]) == 3
        assert result["objects"][0]["mis_id"] == 10
        assert result["objects"][0]["mis_name"] == "Site A"
        assert result["objects"][1]["mis_id"] == 20
        assert result["objects"][1]["mis_name"] == "Site B"
        assert result["objects"][1]["mis_idp"] == 10
        assert result["objects"][2]["mis_id"] == 30
        assert result["objects"][2]["mis_name"] == "Site C"
        assert result["objects"][2]["mis_idp"] == 20
        assert 10 in result["raw_by_mis"]
        assert 20 in result["raw_by_mis"]
        assert 30 in result["raw_by_mis"]

    @pytest.mark.asyncio
    async def test_objects_name_extraction(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test object name extraction with various field names."""
        coordinator = CEMObjectsCoordinator(mock_hass, mock_client, mock_auth_coordinator)
        
        raw_items = [
            {"mis_id": 1, "mis_nazev": "Name 1"},
            {"mis_id": 2, "mis_name": "Name 2"},
            {"mis_id": 3, "name": "Name 3"},
            {"mis_id": 4, "nazev": "Name 4"},
            {"mis_id": 5, "caption": "Name 5"},
            {"mis_id": 6, "description": "Name 6"},
        ]
        
        mock_client.get_objects = AsyncMock(return_value=raw_items)
        
        result = await coordinator._async_update_data()
        
        assert result["objects"][0]["mis_name"] == "Name 1"
        assert result["objects"][1]["mis_name"] == "Name 2"
        assert result["objects"][2]["mis_name"] == "Name 3"
        assert result["objects"][3]["mis_name"] == "Name 4"
        assert result["objects"][4]["mis_name"] == "Name 5"
        assert result["objects"][5]["mis_name"] == "Name 6"

    @pytest.mark.asyncio
    async def test_objects_parent_hierarchy(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test parent hierarchy resolution."""
        coordinator = CEMObjectsCoordinator(mock_hass, mock_client, mock_auth_coordinator)
        
        raw_items = [
            {"mis_id": 1, "mis_nazev": "Root", "mis_idp": None},
            {"mis_id": 2, "mis_nazev": "Child 1", "mis_idp": 1},
            {"mis_id": 3, "mis_nazev": "Child 2", "parent_id": 1},
            {"mis_id": 4, "mis_nazev": "Grandchild", "parent": 2},
        ]
        
        mock_client.get_objects = AsyncMock(return_value=raw_items)
        
        result = await coordinator._async_update_data()
        
        assert result["objects"][0]["mis_idp"] is None  # Root has no parent
        assert result["objects"][1]["mis_idp"] == 1  # Child 1 parent is 1
        assert result["objects"][2]["mis_idp"] == 1  # Child 2 parent is 1
        assert result["objects"][3]["mis_idp"] == 2  # Grandchild parent is 2

    @pytest.mark.asyncio
    async def test_objects_skips_invalid_items(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test that items without mis_id are skipped."""
        coordinator = CEMObjectsCoordinator(mock_hass, mock_client, mock_auth_coordinator)
        
        raw_items = [
            {"mis_id": 1, "mis_nazev": "Valid 1"},
            {"name": "Invalid - no mis_id"},
            {"mis_id": 2, "mis_nazev": "Valid 2"},
            {"some_field": "Invalid - no mis_id"},
        ]
        
        mock_client.get_objects = AsyncMock(return_value=raw_items)
        
        result = await coordinator._async_update_data()
        
        assert len(result["objects"]) == 2
        assert result["objects"][0]["mis_id"] == 1
        assert result["objects"][1]["mis_id"] == 2


class TestMetersCoordinator:
    """Test CEMMetersCoordinator."""

    @pytest.mark.asyncio
    async def test_meters_success(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test successful fetch of meters list (id=108 endpoint)."""
        coordinator = CEMMetersCoordinator(mock_hass, mock_client, mock_auth_coordinator)
        
        raw_items = [
            {"me_id": 101, "mis_id": 1, "name": "Meter 1"},
            {"meid": 102, "misid": 2, "nazev": "Meter 2"},
            {"meId": 103, "object_id": 1, "caption": "Meter 3"},
        ]
        
        mock_client.get_meters = AsyncMock(return_value=raw_items)
        
        result = await coordinator._async_update_data()
        
        assert len(result["meters"]) == 3
        assert result["meters"][0]["me_id"] == 101
        assert result["meters"][0]["mis_id"] == 1
        assert result["meters"][0]["me_name"] == "Meter 1"
        assert result["meters"][1]["me_id"] == 102
        assert result["meters"][1]["mis_id"] == 2
        assert result["meters"][1]["me_name"] == "Meter 2"

    @pytest.mark.asyncio
    async def test_meters_401_refresh_token(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test that 401 triggers token refresh and retry."""
        call_count = 0
        
        async def get_meters_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ClientResponseError(None, None, status=401)
            return [{"me_id": 101, "mis_id": 1, "name": "Meter 1"}]
        
        mock_client.get_meters = AsyncMock(side_effect=get_meters_side_effect)
        mock_auth_coordinator.async_request_refresh = AsyncMock()
        mock_auth_coordinator.token = "new_token"
        mock_auth_coordinator._last_result.cookie_value = "new_cookie"
        
        coordinator = CEMMetersCoordinator(mock_hass, mock_client, mock_auth_coordinator)
        
        result = await coordinator._async_update_data()
        
        assert len(result["meters"]) == 1
        assert call_count == 2  # Initial call + retry after refresh
        mock_auth_coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_meters_401_persists_after_refresh(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test that persistent 401 after refresh raises UpdateFailed."""
        mock_client.get_meters = AsyncMock(
            side_effect=ClientResponseError(None, None, status=401)
        )
        mock_auth_coordinator.async_request_refresh = AsyncMock()
        mock_auth_coordinator.token = "new_token"
        
        coordinator = CEMMetersCoordinator(mock_hass, mock_client, mock_auth_coordinator)
        
        with pytest.raises(UpdateFailed) as exc_info:
            await coordinator._async_update_data()
        
        assert "authentication failed after token refresh" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_meters_data_parsing(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test meter data parsing (me_id, mis_id, me_name extraction)."""
        coordinator = CEMMetersCoordinator(mock_hass, mock_client, mock_auth_coordinator)
        
        raw_items = [
            {"me_id": 201, "mis_id": 10, "name": "Water Meter"},
            {"meid": 202, "misid": 20, "nazev": "Gas Meter"},
            {"meId": 203, "object_id": 30, "caption": "Electric Meter"},
            {"id": 204, "obj_id": 40, "description": "Heat Meter"},
        ]
        
        mock_client.get_meters = AsyncMock(return_value=raw_items)
        
        result = await coordinator._async_update_data()
        
        assert len(result["meters"]) == 4
        assert result["meters"][0]["me_id"] == 201
        assert result["meters"][0]["mis_id"] == 10
        assert result["meters"][0]["me_name"] == "Water Meter"
        assert result["meters"][1]["me_id"] == 202
        assert result["meters"][1]["mis_id"] == 20
        assert result["meters"][1]["me_name"] == "Gas Meter"
        assert result["meters"][2]["me_id"] == 203
        assert result["meters"][2]["mis_id"] == 30
        assert result["meters"][2]["me_name"] == "Electric Meter"
        assert result["meters"][3]["me_id"] == 204
        assert result["meters"][3]["mis_id"] == 40
        assert result["meters"][3]["me_name"] == "Heat Meter"

    @pytest.mark.asyncio
    async def test_meters_name_extraction(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test meter name extraction with various field names."""
        coordinator = CEMMetersCoordinator(mock_hass, mock_client, mock_auth_coordinator)
        
        raw_items = [
            {"me_id": 1, "mis_id": 1, "name": "Name 1"},
            {"me_id": 2, "mis_id": 1, "nazev": "Name 2"},
            {"me_id": 3, "mis_id": 1, "název": "Name 3"},
            {"me_id": 4, "mis_id": 1, "caption": "Name 4"},
            {"me_id": 5, "mis_id": 1, "popis": "Name 5"},
            {"me_id": 6, "mis_id": 1, "description": "Name 6"},
            {"me_id": 7, "mis_id": 1, "me_name": "Name 7"},
        ]
        
        mock_client.get_meters = AsyncMock(return_value=raw_items)
        
        result = await coordinator._async_update_data()
        
        assert result["meters"][0]["me_name"] == "Name 1"
        assert result["meters"][1]["me_name"] == "Name 2"
        assert result["meters"][2]["me_name"] == "Name 3"
        assert result["meters"][3]["me_name"] == "Name 4"
        assert result["meters"][4]["me_name"] == "Name 5"
        assert result["meters"][5]["me_name"] == "Name 6"
        assert result["meters"][6]["me_name"] == "Name 7"

    @pytest.mark.asyncio
    async def test_meters_skips_invalid_items(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test that items without me_id are skipped."""
        coordinator = CEMMetersCoordinator(mock_hass, mock_client, mock_auth_coordinator)
        
        raw_items = [
            {"me_id": 1, "mis_id": 1, "name": "Valid 1"},
            {"name": "Invalid - no me_id"},
            {"me_id": 2, "mis_id": 2, "name": "Valid 2"},
            {"some_field": "Invalid - no me_id"},
        ]
        
        mock_client.get_meters = AsyncMock(return_value=raw_items)
        
        result = await coordinator._async_update_data()
        
        assert len(result["meters"]) == 2
        assert result["meters"][0]["me_id"] == 1
        assert result["meters"][1]["me_id"] == 2

    @pytest.mark.asyncio
    async def test_meters_raw_data_preserved(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test that raw data is preserved in the result."""
        coordinator = CEMMetersCoordinator(mock_hass, mock_client, mock_auth_coordinator)
        
        raw_item = {"me_id": 301, "mis_id": 1, "name": "Test Meter", "extra_field": "extra_value"}
        raw_items = [raw_item]
        
        mock_client.get_meters = AsyncMock(return_value=raw_items)
        
        result = await coordinator._async_update_data()
        
        assert result["meters"][0]["raw"] == raw_item
        assert result["meters"][0]["raw"]["extra_field"] == "extra_value"


class TestMeterCountersCoordinator:
    """Test CEMMeterCountersCoordinator."""

    @pytest.mark.asyncio
    async def test_meter_counters_success(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test successful fetch of counters for a meter (id=107 endpoint)."""
        coordinator = CEMMeterCountersCoordinator(
            mock_hass, mock_client, mock_auth_coordinator, me_id=501, mis_id=1, me_name="Test Meter"
        )
        
        raw_items = [
            {
                "var_id": 1001,
                "name": "Water Counter",
                "unit": "m³",
                "timestamp_ms": 1234567890,
            },
            {
                "varId": 1002,
                "nazev": "Gas Counter",
                "jednotka": "m³",
                "timestamp": 1234567891,
            },
        ]
        
        mock_client.get_counters_by_meter = AsyncMock(return_value=raw_items)
        
        result = await coordinator._async_update_data()
        
        assert result["me_id"] == 501
        assert result["mis_id"] == 1
        assert result["me_name"] == "Test Meter"
        assert len(result["counters"]) == 2
        assert result["counters"][0]["var_id"] == 1001
        assert result["counters"][0]["name"] == "Water Counter"
        assert result["counters"][0]["unit"] == "m³"
        assert result["counters"][0]["timestamp_ms"] == 1234567890
        assert result["counters"][1]["var_id"] == 1002
        assert result["counters"][1]["name"] == "Gas Counter"
        assert result["counters"][1]["unit"] == "m³"
        assert result["counters"][1]["timestamp_ms"] == 1234567891
        assert len(result["raw_map"]) == 2
        assert result["raw_map"][1001] == raw_items[0]
        assert result["raw_map"][1002] == raw_items[1]

    @pytest.mark.asyncio
    async def test_meter_counters_401_refresh_token(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test that 401 triggers token refresh and retry."""
        call_count = 0
        
        async def get_counters_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ClientResponseError(None, None, status=401)
            return [{"var_id": 1001, "name": "Counter 1", "unit": "m³"}]
        
        mock_client.get_counters_by_meter = AsyncMock(side_effect=get_counters_side_effect)
        mock_auth_coordinator.async_request_refresh = AsyncMock()
        mock_auth_coordinator.token = "new_token"
        mock_auth_coordinator._last_result.cookie_value = "new_cookie"
        
        coordinator = CEMMeterCountersCoordinator(
            mock_hass, mock_client, mock_auth_coordinator, me_id=501, mis_id=1, me_name="Test Meter"
        )
        
        result = await coordinator._async_update_data()
        
        assert len(result["counters"]) == 1
        assert call_count == 2  # Initial call + retry after refresh
        mock_auth_coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_meter_counters_401_persists_after_refresh(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test that persistent 401 after refresh raises UpdateFailed."""
        mock_client.get_counters_by_meter = AsyncMock(
            side_effect=ClientResponseError(None, None, status=401)
        )
        mock_auth_coordinator.async_request_refresh = AsyncMock()
        mock_auth_coordinator.token = "new_token"
        
        coordinator = CEMMeterCountersCoordinator(
            mock_hass, mock_client, mock_auth_coordinator, me_id=501, mis_id=1, me_name="Test Meter"
        )
        
        with pytest.raises(UpdateFailed) as exc_info:
            await coordinator._async_update_data()
        
        assert "authentication failed after token refresh" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_meter_counters_data_parsing(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test counter data parsing (var_id, name, unit, timestamp extraction)."""
        coordinator = CEMMeterCountersCoordinator(
            mock_hass, mock_client, mock_auth_coordinator, me_id=501, mis_id=1, me_name="Test Meter"
        )
        
        raw_items = [
            {"var_id": 2001, "name": "Counter 1", "unit": "m³", "timestamp_ms": 1000},
            {"varId": 2002, "nazev": "Counter 2", "jednotka": "l", "ts": 2000},
            {"varid": 2003, "caption": "Counter 3", "unit": "kWh", "time": 3000},
            {"id": 2004, "popis": "Counter 4", "unit": "m³", "ts_ms": 4000},
        ]
        
        mock_client.get_counters_by_meter = AsyncMock(return_value=raw_items)
        
        result = await coordinator._async_update_data()
        
        assert len(result["counters"]) == 4
        assert result["counters"][0]["var_id"] == 2001
        assert result["counters"][0]["name"] == "Counter 1"
        assert result["counters"][0]["unit"] == "m³"
        assert result["counters"][0]["timestamp_ms"] == 1000
        assert result["counters"][1]["var_id"] == 2002
        assert result["counters"][1]["name"] == "Counter 2"
        assert result["counters"][1]["unit"] == "l"
        assert result["counters"][1]["timestamp_ms"] == 2000
        assert result["counters"][2]["var_id"] == 2003
        assert result["counters"][2]["name"] == "Counter 3"
        assert result["counters"][2]["unit"] == "kWh"
        assert result["counters"][2]["timestamp_ms"] == 3000
        assert result["counters"][3]["var_id"] == 2004
        assert result["counters"][3]["name"] == "Counter 4"
        assert result["counters"][3]["unit"] == "m³"
        assert result["counters"][3]["timestamp_ms"] == 4000

    @pytest.mark.asyncio
    async def test_meter_counters_raw_map_structure(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test raw_map structure."""
        coordinator = CEMMeterCountersCoordinator(
            mock_hass, mock_client, mock_auth_coordinator, me_id=501, mis_id=1, me_name="Test Meter"
        )
        
        raw_item1 = {"var_id": 3001, "name": "Counter 1", "unit": "m³", "extra": "data"}
        raw_item2 = {"var_id": 3002, "name": "Counter 2", "unit": "l"}
        raw_items = [raw_item1, raw_item2]
        
        mock_client.get_counters_by_meter = AsyncMock(return_value=raw_items)
        
        result = await coordinator._async_update_data()
        
        assert len(result["raw_map"]) == 2
        assert result["raw_map"][3001] == raw_item1
        assert result["raw_map"][3001]["extra"] == "data"
        assert result["raw_map"][3002] == raw_item2

    @pytest.mark.asyncio
    async def test_meter_counters_water_var_ids_selection(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test water_var_ids selection via select_water_var_ids()."""
        coordinator = CEMMeterCountersCoordinator(
            mock_hass, mock_client, mock_auth_coordinator, me_id=501, mis_id=1, me_name="Test Meter"
        )
        
        raw_items = [
            {"var_id": 4001, "name": "Water Counter", "unit": "m³", "type": "water"},
            {"var_id": 4002, "name": "Gas Counter", "unit": "m³", "type": "gas"},
            {"var_id": 4003, "name": "Cold Water", "unit": "m³"},
            {"var_id": 4004, "name": "Hot Water", "unit": "l"},
            {"var_id": 4005, "name": "Electricity", "unit": "kWh"},
        ]
        
        mock_client.get_counters_by_meter = AsyncMock(return_value=raw_items)
        
        result = await coordinator._async_update_data()
        
        # Should identify water-related counters
        assert isinstance(result["water_var_ids"], list)
        # Water counters should be in the list (4001, 4003, 4004)
        assert 4001 in result["water_var_ids"] or 4003 in result["water_var_ids"] or 4004 in result["water_var_ids"]

    @pytest.mark.asyncio
    async def test_meter_counters_skips_invalid_items(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test that items without var_id are skipped."""
        coordinator = CEMMeterCountersCoordinator(
            mock_hass, mock_client, mock_auth_coordinator, me_id=501, mis_id=1, me_name="Test Meter"
        )
        
        raw_items = [
            {"var_id": 5001, "name": "Valid 1", "unit": "m³"},
            {"name": "Invalid - no var_id", "unit": "m³"},
            {"var_id": 5002, "name": "Valid 2", "unit": "l"},
            {"some_field": "Invalid - no var_id"},
        ]
        
        mock_client.get_counters_by_meter = AsyncMock(return_value=raw_items)
        
        result = await coordinator._async_update_data()
        
        assert len(result["counters"]) == 2
        assert result["counters"][0]["var_id"] == 5001
        assert result["counters"][1]["var_id"] == 5002

    @pytest.mark.asyncio
    async def test_meter_counters_timestamp_iso(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test that timestamp_iso is generated from timestamp_ms."""
        coordinator = CEMMeterCountersCoordinator(
            mock_hass, mock_client, mock_auth_coordinator, me_id=501, mis_id=1, me_name="Test Meter"
        )
        
        raw_items = [
            {"var_id": 6001, "name": "Counter 1", "unit": "m³", "timestamp_ms": 1234567890000},
        ]
        
        mock_client.get_counters_by_meter = AsyncMock(return_value=raw_items)
        
        result = await coordinator._async_update_data()
        
        assert result["counters"][0]["timestamp_ms"] == 1234567890000
        assert result["counters"][0]["timestamp_iso"] is not None
        assert isinstance(result["counters"][0]["timestamp_iso"], str)

    @pytest.mark.asyncio
    async def test_meter_counters_properties(self, mock_hass, mock_client, mock_auth_coordinator):
        """Test coordinator properties (me_id, mis_id, me_name)."""
        coordinator = CEMMeterCountersCoordinator(
            mock_hass, mock_client, mock_auth_coordinator, me_id=701, mis_id=10, me_name="Property Test Meter"
        )
        
        assert coordinator.me_id == 701
        assert coordinator.mis_id == 10
        assert coordinator.me_name == "Property Test Meter"
        
        # Test with None values
        coordinator2 = CEMMeterCountersCoordinator(
            mock_hass, mock_client, mock_auth_coordinator, me_id=702, mis_id=None, me_name=None
        )
        
        assert coordinator2.me_id == 702
        assert coordinator2.mis_id is None
        assert coordinator2.me_name is None

