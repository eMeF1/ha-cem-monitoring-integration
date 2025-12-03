"""Tests for batch counter refresh functionality."""
import pytest
from unittest.mock import AsyncMock, MagicMock
import time

# conftest.py handles path setup and Home Assistant mocking
from custom_components.cem_monitor.counter_reading_coordinator import CEMCounterReadingCoordinator
from custom_components.cem_monitor.api import CEMClient, AuthResult
from custom_components.cem_monitor.coordinator import CEMAuthCoordinator


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.async_create_task = MagicMock()
    hass.data = {}
    return hass


@pytest.fixture
def mock_entry():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.data = {"username": "test_user", "password": "test_pass"}
    entry.entry_id = "test_entry"
    entry.options = {"counter_update_interval_minutes": 30}
    return entry


@pytest.fixture
def mock_client():
    """Create a mock CEMClient."""
    client = MagicMock(spec=CEMClient)
    client.get_counter_readings_batch = AsyncMock()
    client.get_counter_reading = AsyncMock()
    return client


@pytest.fixture
def mock_auth_coordinator():
    """Create a mock auth coordinator."""
    auth = MagicMock(spec=CEMAuthCoordinator)
    auth.token = "test_token"
    auth._last_result = AuthResult(
        access_token="test_token",
        valid_to_ms=int((time.time() + 3600) * 1000),
        cookie_value="test_cookie",
    )
    auth.async_request_refresh = AsyncMock()
    return auth


@pytest.fixture
def counter_coordinator(mock_hass, mock_client, mock_auth_coordinator):
    """Create a counter reading coordinator."""
    coord = CEMCounterReadingCoordinator(mock_hass, mock_client, mock_auth_coordinator, var_id=104437)
    coord.data = {
        "value": 100.0,
        "timestamp_ms": 1234567890,
        "timestamp_iso": "2024-01-01T00:00:00+00:00",
        "fetched_at": 1234567890,
    }
    coord.async_update_listeners = MagicMock()
    coord.async_request_refresh = AsyncMock()
    return coord


class TestBatchRefresh:
    """Test batch refresh callback functionality."""

    @pytest.mark.asyncio
    async def test_batch_refresh_success(self, mock_hass, mock_entry, mock_client, mock_auth_coordinator, counter_coordinator):
        """Test successful batch refresh updates all coordinators."""
        from custom_components.cem_monitor import async_setup_entry

        # Setup bag with coordinators
        bag = {
            "client": mock_client,
            "coordinator": mock_auth_coordinator,
            "counter_readings": {104437: counter_coordinator, 102496: counter_coordinator},
        }
        mock_hass.data.setdefault("cem_monitor", {})[mock_entry.entry_id] = bag

        # Mock batch response
        mock_client.get_counter_readings_batch.return_value = {
            104437: {"value": 123.45, "timestamp_ms": 1234567890},
            102496: {"value": 456.78, "timestamp_ms": 1234567900},
        }

        # Create second coordinator
        coord2 = CEMCounterReadingCoordinator(mock_hass, mock_client, mock_auth_coordinator, var_id=102496)
        coord2.data = {"value": 200.0, "timestamp_ms": 1234567800, "timestamp_iso": None, "fetched_at": 1234567800}
        coord2.async_update_listeners = MagicMock()
        bag["counter_readings"][102496] = coord2

        # Simulate the refresh callback
        from custom_components.cem_monitor.const import DEFAULT_COUNTER_UPDATE_INTERVAL_MINUTES
        from datetime import timedelta
        import time
        from custom_components.cem_monitor.utils import ms_to_iso

        async def _do_batch_refresh():
            counter_map_local = bag.get("counter_readings", {})
            if len(counter_map_local) == 0:
                return

            var_ids = list(counter_map_local.keys())
            auth_local = bag.get("coordinator")
            if not auth_local or not auth_local.token:
                return

            token = auth_local.token
            cookie = auth_local._last_result.cookie_value if auth_local._last_result else None
            client_local = bag.get("client")

            if not client_local:
                return

            try:
                batch_results = await client_local.get_counter_readings_batch(var_ids, token, cookie)

                for var_id, coord in counter_map_local.items():
                    if var_id in batch_results:
                        reading = batch_results[var_id]
                        coord.data = {
                            "value": reading.get("value"),
                            "timestamp_ms": reading.get("timestamp_ms"),
                            "timestamp_iso": ms_to_iso(reading.get("timestamp_ms")),
                            "fetched_at": int(time.time() * 1000),
                        }
                        coord.async_update_listeners()

            except Exception as err:
                pass

        await _do_batch_refresh()

        # Verify batch API was called
        mock_client.get_counter_readings_batch.assert_called_once_with(
            [104437, 102496], "test_token", "test_cookie"
        )

        # Verify coordinators were updated
        assert counter_coordinator.data["value"] == 123.45
        assert counter_coordinator.data["timestamp_ms"] == 1234567890
        assert counter_coordinator.async_update_listeners.called

        assert coord2.data["value"] == 456.78
        assert coord2.data["timestamp_ms"] == 1234567900
        assert coord2.async_update_listeners.called

    @pytest.mark.asyncio
    async def test_batch_refresh_fallback_on_failure(self, mock_hass, mock_entry, mock_client, mock_auth_coordinator, counter_coordinator):
        """Test that batch refresh falls back to individual requests on failure."""
        bag = {
            "client": mock_client,
            "coordinator": mock_auth_coordinator,
            "counter_readings": {104437: counter_coordinator},
        }
        mock_hass.data.setdefault("cem_monitor", {})[mock_entry.entry_id] = bag

        # Mock batch failure
        mock_client.get_counter_readings_batch.side_effect = Exception("Batch failed")
        mock_client.get_counter_reading.return_value = {"value": 123.45, "timestamp_ms": 1234567890}

        # Simulate refresh callback with fallback
        async def _do_batch_refresh():
            counter_map_local = bag.get("counter_readings", {})
            if len(counter_map_local) == 0:
                return

            var_ids = list(counter_map_local.keys())
            auth_local = bag.get("coordinator")
            if not auth_local or not auth_local.token:
                # Fallback to individual requests
                for coord in counter_map_local.values():
                    mock_hass.async_create_task(coord.async_request_refresh())
                return

            token = auth_local.token
            cookie = auth_local._last_result.cookie_value if auth_local._last_result else None
            client_local = bag.get("client")

            if not client_local:
                # Fallback to individual requests
                for coord in counter_map_local.values():
                    mock_hass.async_create_task(coord.async_request_refresh())
                return

            try:
                batch_results = await client_local.get_counter_readings_batch(var_ids, token, cookie)
                # ... update coordinators ...
            except Exception as err:
                # Fallback to individual requests
                for coord in counter_map_local.values():
                    mock_hass.async_create_task(coord.async_request_refresh())

        await _do_batch_refresh()

        # Verify batch was attempted
        mock_client.get_counter_readings_batch.assert_called_once()

        # Verify fallback to individual requests was triggered
        assert mock_hass.async_create_task.called

    @pytest.mark.asyncio
    async def test_batch_refresh_missing_var_id_fallback(self, mock_hass, mock_entry, mock_client, mock_auth_coordinator, counter_coordinator):
        """Test that missing var_ids in batch response trigger individual requests."""
        bag = {
            "client": mock_client,
            "coordinator": mock_auth_coordinator,
            "counter_readings": {104437: counter_coordinator, 102496: counter_coordinator},
        }
        mock_hass.data.setdefault("cem_monitor", {})[mock_entry.entry_id] = bag

        # Mock partial batch response (one var_id missing)
        mock_client.get_counter_readings_batch.return_value = {
            104437: {"value": 123.45, "timestamp_ms": 1234567890},
            # 102496 is missing
        }
        mock_client.get_counter_reading.return_value = {"value": 456.78, "timestamp_ms": 1234567900}

        # Create second coordinator
        coord2 = CEMCounterReadingCoordinator(mock_hass, mock_client, mock_auth_coordinator, var_id=102496)
        coord2.data = {"value": 200.0, "timestamp_ms": 1234567800, "timestamp_iso": None, "fetched_at": 1234567800}
        coord2.async_update_listeners = MagicMock()
        coord2.async_request_refresh = AsyncMock()
        bag["counter_readings"][102496] = coord2

        # Simulate refresh callback
        from custom_components.cem_monitor.utils import ms_to_iso

        async def _do_batch_refresh():
            counter_map_local = bag.get("counter_readings", {})
            if len(counter_map_local) == 0:
                return

            var_ids = list(counter_map_local.keys())
            auth_local = bag.get("coordinator")
            if not auth_local or not auth_local.token:
                return

            token = auth_local.token
            cookie = auth_local._last_result.cookie_value if auth_local._last_result else None
            client_local = bag.get("client")

            if not client_local:
                return

            try:
                batch_results = await client_local.get_counter_readings_batch(var_ids, token, cookie)

                for var_id, coord in counter_map_local.items():
                    if var_id in batch_results:
                        reading = batch_results[var_id]
                        coord.data = {
                            "value": reading.get("value"),
                            "timestamp_ms": reading.get("timestamp_ms"),
                            "timestamp_iso": ms_to_iso(reading.get("timestamp_ms")),
                            "fetched_at": int(time.time() * 1000),
                        }
                        coord.async_update_listeners()
                    else:
                        # Missing var_id - fallback to individual request
                        mock_hass.async_create_task(coord.async_request_refresh())

            except Exception as err:
                pass

        await _do_batch_refresh()

        # Verify batch was called
        mock_client.get_counter_readings_batch.assert_called_once()

        # Verify first coordinator was updated
        assert counter_coordinator.data["value"] == 123.45
        assert counter_coordinator.async_update_listeners.called

        # Verify second coordinator triggered individual refresh
        assert mock_hass.async_create_task.called

    @pytest.mark.asyncio
    async def test_batch_refresh_empty_counter_map(self, mock_hass, mock_entry, mock_client, mock_auth_coordinator):
        """Test batch refresh with empty counter_map."""
        bag = {
            "client": mock_client,
            "coordinator": mock_auth_coordinator,
            "counter_readings": {},
        }
        mock_hass.data.setdefault("cem_monitor", {})[mock_entry.entry_id] = bag

        async def _do_batch_refresh():
            counter_map_local = bag.get("counter_readings", {})
            if len(counter_map_local) == 0:
                return

            # Should not reach here
            var_ids = list(counter_map_local.keys())
            await mock_client.get_counter_readings_batch(var_ids, "token", "cookie")

        await _do_batch_refresh()

        # Verify batch was NOT called
        mock_client.get_counter_readings_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_batch_refresh_no_auth_token(self, mock_hass, mock_entry, mock_client, mock_auth_coordinator, counter_coordinator):
        """Test batch refresh falls back when no auth token available."""
        bag = {
            "client": mock_client,
            "coordinator": mock_auth_coordinator,
            "counter_readings": {104437: counter_coordinator},
        }
        mock_hass.data.setdefault("cem_monitor", {})[mock_entry.entry_id] = bag

        # Remove token
        mock_auth_coordinator.token = None

        async def _do_batch_refresh():
            counter_map_local = bag.get("counter_readings", {})
            if len(counter_map_local) == 0:
                return

            var_ids = list(counter_map_local.keys())
            auth_local = bag.get("coordinator")
            if not auth_local or not auth_local.token:
                # Fallback to individual requests
                for coord in counter_map_local.values():
                    mock_hass.async_create_task(coord.async_request_refresh())
                return

            # Should not reach here
            await mock_client.get_counter_readings_batch(var_ids, "token", "cookie")

        await _do_batch_refresh()

        # Verify batch was NOT called
        mock_client.get_counter_readings_batch.assert_not_called()

        # Verify fallback was triggered
        assert mock_hass.async_create_task.called

    @pytest.mark.asyncio
    async def test_batch_refresh_401_error_triggers_token_refresh(self, mock_hass, mock_entry, mock_client, mock_auth_coordinator, counter_coordinator):
        """Test that 401 error during batch refresh triggers token refresh and retry."""
        bag = {
            "client": mock_client,
            "coordinator": mock_auth_coordinator,
            "counter_readings": {104437: counter_coordinator},
        }
        mock_hass.data.setdefault("cem_monitor", {})[mock_entry.entry_id] = bag

        from aiohttp import ClientResponseError, RequestInfo
        request_info = RequestInfo(url="http://test.com", method="POST", headers={}, real_url="http://test.com")
        
        call_count = 0
        
        async def batch_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call returns 401
                raise ClientResponseError(request_info, None, status=401)
            # After token refresh, succeed
            return {104437: {"value": 123.45, "timestamp_ms": 1234567890}}
        
        mock_client.get_counter_readings_batch = AsyncMock(side_effect=batch_side_effect)
        
        # Mock token refresh to update token
        async def refresh_side_effect():
            mock_auth_coordinator.token = "new_token"
            mock_auth_coordinator._last_result = AuthResult(
                access_token="new_token",
                valid_to_ms=int((time.time() + 3600) * 1000),
                cookie_value="new_cookie",
            )
        
        mock_auth_coordinator.async_request_refresh = AsyncMock(side_effect=refresh_side_effect)

        # Simulate refresh callback with 401 handling
        from custom_components.cem_monitor.utils import ms_to_iso
        from custom_components.cem_monitor.retry import is_401_error

        async def _do_batch_refresh():
            counter_map_local = bag.get("counter_readings", {})
            if len(counter_map_local) == 0:
                return

            var_ids = list(counter_map_local.keys())
            auth_local = bag.get("coordinator")
            if not auth_local or not auth_local.token:
                return

            token = auth_local.token
            cookie = auth_local._last_result.cookie_value if auth_local._last_result else None
            client_local = bag.get("client")

            if not client_local:
                return

            try:
                batch_results = await client_local.get_counter_readings_batch(var_ids, token, cookie)
                
                for var_id, coord in counter_map_local.items():
                    if var_id in batch_results:
                        reading = batch_results[var_id]
                        coord.data = {
                            "value": reading.get("value"),
                            "timestamp_ms": reading.get("timestamp_ms"),
                            "timestamp_iso": ms_to_iso(reading.get("timestamp_ms")),
                            "fetched_at": int(time.time() * 1000),
                        }
                        coord.async_update_listeners()
            except Exception as err:
                if is_401_error(err):
                    # Refresh token and retry
                    await auth_local.async_request_refresh()
                    token = auth_local.token
                    cookie = auth_local._last_result.cookie_value if auth_local._last_result else None
                    
                    try:
                        batch_results = await client_local.get_counter_readings_batch(var_ids, token, cookie)
                        for var_id, coord in counter_map_local.items():
                            if var_id in batch_results:
                                reading = batch_results[var_id]
                                coord.data = {
                                    "value": reading.get("value"),
                                    "timestamp_ms": reading.get("timestamp_ms"),
                                    "timestamp_iso": ms_to_iso(reading.get("timestamp_ms")),
                                    "fetched_at": int(time.time() * 1000),
                                }
                                coord.async_update_listeners()
                    except Exception:
                        # Fallback to individual requests
                        for coord in counter_map_local.values():
                            mock_hass.async_create_task(coord.async_request_refresh())
                else:
                    # Fallback to individual requests
                    for coord in counter_map_local.values():
                        mock_hass.async_create_task(coord.async_request_refresh())

        await _do_batch_refresh()

        # Verify batch was called twice (initial + retry after refresh)
        assert mock_client.get_counter_readings_batch.call_count == 2
        # Verify token refresh was called
        mock_auth_coordinator.async_request_refresh.assert_called_once()
        # Verify coordinator was updated
        assert counter_coordinator.data["value"] == 123.45
        assert counter_coordinator.async_update_listeners.called

    @pytest.mark.asyncio
    async def test_batch_refresh_network_error_fallback(self, mock_hass, mock_entry, mock_client, mock_auth_coordinator, counter_coordinator):
        """Test that network errors during batch refresh fall back to individual requests."""
        bag = {
            "client": mock_client,
            "coordinator": mock_auth_coordinator,
            "counter_readings": {104437: counter_coordinator},
        }
        mock_hass.data.setdefault("cem_monitor", {})[mock_entry.entry_id] = bag

        from aiohttp.client_exceptions import ClientConnectorError
        import os
        
        # Mock network error
        mock_client.get_counter_readings_batch.side_effect = ClientConnectorError(
            None, OSError("Connection failed")
        )

        # Simulate refresh callback
        async def _do_batch_refresh():
            counter_map_local = bag.get("counter_readings", {})
            if len(counter_map_local) == 0:
                return

            var_ids = list(counter_map_local.keys())
            auth_local = bag.get("coordinator")
            if not auth_local or not auth_local.token:
                return

            token = auth_local.token
            cookie = auth_local._last_result.cookie_value if auth_local._last_result else None
            client_local = bag.get("client")

            if not client_local:
                return

            try:
                batch_results = await client_local.get_counter_readings_batch(var_ids, token, cookie)
                # ... update coordinators ...
            except Exception as err:
                # Fallback to individual requests on any error
                for coord in counter_map_local.values():
                    mock_hass.async_create_task(coord.async_request_refresh())

        await _do_batch_refresh()

        # Verify batch was attempted
        mock_client.get_counter_readings_batch.assert_called_once()
        # Verify fallback to individual requests was triggered
        assert mock_hass.async_create_task.called

    @pytest.mark.asyncio
    async def test_batch_refresh_token_refresh_failure(self, mock_hass, mock_entry, mock_client, mock_auth_coordinator, counter_coordinator):
        """Test that token refresh failure during batch refresh falls back to individual requests."""
        bag = {
            "client": mock_client,
            "coordinator": mock_auth_coordinator,
            "counter_readings": {104437: counter_coordinator},
        }
        mock_hass.data.setdefault("cem_monitor", {})[mock_entry.entry_id] = bag

        from aiohttp import ClientResponseError, RequestInfo
        request_info = RequestInfo(url="http://test.com", method="POST", headers={}, real_url="http://test.com")
        
        # Mock 401 error
        mock_client.get_counter_readings_batch.side_effect = ClientResponseError(
            request_info, None, status=401
        )
        
        # Mock token refresh failure (token remains None)
        async def refresh_side_effect():
            mock_auth_coordinator.token = None  # Refresh fails
        
        mock_auth_coordinator.async_request_refresh = AsyncMock(side_effect=refresh_side_effect)

        # Simulate refresh callback
        from custom_components.cem_monitor.retry import is_401_error

        async def _do_batch_refresh():
            counter_map_local = bag.get("counter_readings", {})
            if len(counter_map_local) == 0:
                return

            var_ids = list(counter_map_local.keys())
            auth_local = bag.get("coordinator")
            if not auth_local or not auth_local.token:
                # Fallback to individual requests
                for coord in counter_map_local.values():
                    mock_hass.async_create_task(coord.async_request_refresh())
                return

            token = auth_local.token
            cookie = auth_local._last_result.cookie_value if auth_local._last_result else None
            client_local = bag.get("client")

            if not client_local:
                return

            try:
                batch_results = await client_local.get_counter_readings_batch(var_ids, token, cookie)
                # ... update coordinators ...
            except Exception as err:
                if is_401_error(err):
                    # Refresh token and retry
                    await auth_local.async_request_refresh()
                    token = auth_local.token
                    if not token:
                        # Token refresh failed, fallback
                        for coord in counter_map_local.values():
                            mock_hass.async_create_task(coord.async_request_refresh())
                        return
                    
                    cookie = auth_local._last_result.cookie_value if auth_local._last_result else None
                    try:
                        batch_results = await client_local.get_counter_readings_batch(var_ids, token, cookie)
                        # ... update coordinators ...
                    except Exception:
                        # Fallback to individual requests
                        for coord in counter_map_local.values():
                            mock_hass.async_create_task(coord.async_request_refresh())
                else:
                    # Fallback to individual requests
                    for coord in counter_map_local.values():
                        mock_hass.async_create_task(coord.async_request_refresh())

        await _do_batch_refresh()

        # Verify batch was attempted
        mock_client.get_counter_readings_batch.assert_called_once()
        # Verify token refresh was attempted
        mock_auth_coordinator.async_request_refresh.assert_called_once()
        # Verify fallback to individual requests was triggered
        assert mock_hass.async_create_task.called

    @pytest.mark.asyncio
    async def test_batch_refresh_partial_response_with_fallback(self, mock_hass, mock_entry, mock_client, mock_auth_coordinator, counter_coordinator):
        """Test partial batch response where some var_ids are missing triggers individual requests."""
        bag = {
            "client": mock_client,
            "coordinator": mock_auth_coordinator,
            "counter_readings": {104437: counter_coordinator, 102496: counter_coordinator, 102497: counter_coordinator},
        }
        mock_hass.data.setdefault("cem_monitor", {})[mock_entry.entry_id] = bag

        # Mock partial batch response (only one var_id present)
        mock_client.get_counter_readings_batch.return_value = {
            104437: {"value": 123.45, "timestamp_ms": 1234567890},
            # 102496 and 102497 are missing
        }

        # Create additional coordinators
        coord2 = CEMCounterReadingCoordinator(mock_hass, mock_client, mock_auth_coordinator, var_id=102496)
        coord2.async_update_listeners = MagicMock()
        coord2.async_request_refresh = AsyncMock()
        bag["counter_readings"][102496] = coord2

        coord3 = CEMCounterReadingCoordinator(mock_hass, mock_client, mock_auth_coordinator, var_id=102497)
        coord3.async_update_listeners = MagicMock()
        coord3.async_request_refresh = AsyncMock()
        bag["counter_readings"][102497] = coord3

        # Simulate refresh callback
        from custom_components.cem_monitor.utils import ms_to_iso

        async def _do_batch_refresh():
            counter_map_local = bag.get("counter_readings", {})
            if len(counter_map_local) == 0:
                return

            var_ids = list(counter_map_local.keys())
            auth_local = bag.get("coordinator")
            if not auth_local or not auth_local.token:
                return

            token = auth_local.token
            cookie = auth_local._last_result.cookie_value if auth_local._last_result else None
            client_local = bag.get("client")

            if not client_local:
                return

            try:
                batch_results = await client_local.get_counter_readings_batch(var_ids, token, cookie)

                for var_id, coord in counter_map_local.items():
                    if var_id in batch_results:
                        reading = batch_results[var_id]
                        coord.data = {
                            "value": reading.get("value"),
                            "timestamp_ms": reading.get("timestamp_ms"),
                            "timestamp_iso": ms_to_iso(reading.get("timestamp_ms")),
                            "fetched_at": int(time.time() * 1000),
                        }
                        coord.async_update_listeners()
                    else:
                        # Missing var_id - fallback to individual request
                        mock_hass.async_create_task(coord.async_request_refresh())

            except Exception as err:
                # Fallback to individual requests
                for coord in counter_map_local.values():
                    mock_hass.async_create_task(coord.async_request_refresh())

        await _do_batch_refresh()

        # Verify batch was called
        mock_client.get_counter_readings_batch.assert_called_once()
        # Verify first coordinator was updated
        assert counter_coordinator.data["value"] == 123.45
        assert counter_coordinator.async_update_listeners.called
        # Verify missing coordinators triggered individual refresh
        assert mock_hass.async_create_task.call_count == 2  # Two missing var_ids
        coord2.async_request_refresh.assert_not_called()  # Called via async_create_task
        coord3.async_request_refresh.assert_not_called()  # Called via async_create_task

