"""Tests for API client with mocked HTTP responses."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import ClientResponseError, ClientConnectorError, ClientSession
from aiohttp.client_exceptions import ServerTimeoutError

# conftest.py handles path setup and Home Assistant mocking
from custom_components.cem_monitor.api import CEMClient, AuthResult


@pytest.fixture
def mock_session():
    """Create a mock aiohttp session."""
    return AsyncMock(spec=ClientSession)


@pytest.fixture
def client(mock_session):
    """Create CEMClient with mocked session."""
    return CEMClient(mock_session)


class TestAuthenticate:
    """Test authentication method."""

    @pytest.mark.asyncio
    async def test_authenticate_success(self, client, mock_session):
        """Test successful authentication."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.cookies = {"CEMAPI": MagicMock(value="test_cookie")}
        mock_response.text = AsyncMock(return_value='{"access_token": "token123", "valid_to": 1234567890}')
        mock_response.json = AsyncMock(return_value={"access_token": "token123", "valid_to": 1234567890})
        mock_response.raise_for_status = MagicMock()

        mock_session.post.return_value.__aenter__.return_value = mock_response

        result = await client.authenticate("user", "pass")

        assert isinstance(result, AuthResult)
        assert result.access_token == "token123"
        assert result.valid_to_ms == 1234567890
        assert result.cookie_value == "test_cookie"

    @pytest.mark.asyncio
    async def test_authenticate_retry_on_timeout(self, client, mock_session):
        """Test that authentication retries on timeout."""
        call_count = 0

        async def post_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ServerTimeoutError()
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.cookies = {"CEMAPI": MagicMock(value="cookie")}
            mock_response.text = AsyncMock(return_value='{"access_token": "token", "valid_to": 1234567890}')
            mock_response.json = AsyncMock(return_value={"access_token": "token", "valid_to": 1234567890})
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_session.post.return_value.__aenter__.side_effect = post_side_effect

        result = await client.authenticate("user", "pass")

        assert result.access_token == "token"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_authenticate_no_retry_on_401(self, client, mock_session):
        """Test that 401 errors are not retried."""
        from aiohttp import RequestInfo
        call_count = 0

        async def post_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            request_info = RequestInfo(url="http://test.com", method="POST", headers={}, real_url="http://test.com")
            raise ClientResponseError(request_info, None, status=401)

        mock_session.post.return_value.__aenter__.side_effect = post_side_effect

        with pytest.raises(ClientResponseError):
            await client.authenticate("user", "pass")

        assert call_count == 1  # No retries


class TestGetUserInfo:
    """Test get_user_info method."""

    @pytest.mark.asyncio
    async def test_get_user_info_success(self, client, mock_session):
        """Test successful get_user_info."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"firma": "Test Co", "fir_id": 123}')
        mock_response.json = AsyncMock(return_value={"firma": "Test Co", "fir_id": 123})
        mock_response.raise_for_status = MagicMock()

        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await client.get_user_info("token", "cookie")

        assert result["firma"] == "Test Co"
        assert result["fir_id"] == 123

    @pytest.mark.asyncio
    async def test_get_user_info_retry_on_500(self, client, mock_session):
        """Test that 500 errors are retried."""
        call_count = 0

        async def get_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ClientResponseError(None, None, status=500)
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value='{"firma": "Test"}')
            mock_response.json = AsyncMock(return_value={"firma": "Test"})
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_session.get.return_value.__aenter__.side_effect = get_side_effect

        result = await client.get_user_info("token", "cookie")

        assert result["firma"] == "Test"
        assert call_count == 2


class TestGetObjects:
    """Test get_objects method."""

    @pytest.mark.asyncio
    async def test_get_objects_success(self, client, mock_session):
        """Test successful get_objects."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='[{"mis_id": 1, "mis_nazev": "Object 1"}]')
        mock_response.json = AsyncMock(return_value=[{"mis_id": 1, "mis_nazev": "Object 1"}])
        mock_response.raise_for_status = MagicMock()

        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await client.get_objects("token", "cookie")

        assert len(result) == 1
        assert result[0]["mis_id"] == 1

    @pytest.mark.asyncio
    async def test_get_objects_retry_on_connection_error(self, client, mock_session):
        """Test that connection errors are retried."""
        import os
        call_count = 0

        async def get_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ClientConnectorError(None, OSError("Connection failed"))
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value='[]')
            mock_response.json = AsyncMock(return_value=[])
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_session.get.return_value.__aenter__.side_effect = get_side_effect

        result = await client.get_objects("token", "cookie")

        assert result == []
        assert call_count == 2


class TestGetCounterReading:
    """Test get_counter_reading method."""

    @pytest.mark.asyncio
    async def test_get_counter_reading_success(self, client, mock_session):
        """Test successful get_counter_reading."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='[{"value": 123.45, "timestamp": 1234567890}]')
        mock_response.json = AsyncMock(
            return_value=[{"value": 123.45, "timestamp": 1234567890}]
        )
        mock_response.raise_for_status = MagicMock()

        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await client.get_counter_reading(123, "token", "cookie")

        assert result["value"] == 123.45
        assert result["timestamp_ms"] == 1234567890

    @pytest.mark.asyncio
    async def test_get_counter_reading_no_retry_on_404(self, client, mock_session):
        """Test that 404 errors are not retried."""
        from aiohttp import RequestInfo
        call_count = 0

        async def get_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            request_info = RequestInfo(url="http://test.com", method="GET", headers={}, real_url="http://test.com")
            raise ClientResponseError(request_info, None, status=404)

        mock_session.get.return_value.__aenter__.side_effect = get_side_effect

        with pytest.raises(ClientResponseError):
            await client.get_counter_reading(123, "token", "cookie")

        assert call_count == 1  # No retries


class TestGetCounterReadingsBatch:
    """Test get_counter_readings_batch method."""

    @pytest.mark.asyncio
    async def test_get_counter_readings_batch_success(self, client, mock_session):
        """Test successful batch request with multiple var_ids."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(
            return_value='[{"value": 123.45, "timestamp": 1234567890, "var_id": 104437}, {"value": 456.78, "timestamp": 1234567900, "var_id": 102496}]'
        )
        mock_response.json = AsyncMock(
            return_value=[
                {"value": 123.45, "timestamp": 1234567890, "var_id": 104437},
                {"value": 456.78, "timestamp": 1234567900, "var_id": 102496},
            ]
        )
        mock_response.raise_for_status = MagicMock()

        mock_session.post.return_value.__aenter__.return_value = mock_response

        result = await client.get_counter_readings_batch([104437, 102496], "token", "cookie")

        assert len(result) == 2
        assert result[104437]["value"] == 123.45
        assert result[104437]["timestamp_ms"] == 1234567890
        assert result[102496]["value"] == 456.78
        assert result[102496]["timestamp_ms"] == 1234567900

        # Verify POST was called with correct JSON body
        mock_session.post.assert_called_once()
        call_kwargs = mock_session.post.call_args[1]
        assert call_kwargs["json"] == [{"var_id": 104437}, {"var_id": 102496}]

    @pytest.mark.asyncio
    async def test_get_counter_readings_batch_partial_response(self, client, mock_session):
        """Test batch request where some var_ids are missing from response."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(
            return_value='[{"value": 123.45, "timestamp": 1234567890, "var_id": 104437}]'
        )
        mock_response.json = AsyncMock(
            return_value=[{"value": 123.45, "timestamp": 1234567890, "var_id": 104437}]
        )
        mock_response.raise_for_status = MagicMock()

        mock_session.post.return_value.__aenter__.return_value = mock_response

        result = await client.get_counter_readings_batch([104437, 102496], "token", "cookie")

        # Only one var_id in result
        assert len(result) == 1
        assert 104437 in result
        assert 102496 not in result
        assert result[104437]["value"] == 123.45

    @pytest.mark.asyncio
    async def test_get_counter_readings_batch_empty_list(self, client, mock_session):
        """Test batch request with empty var_ids list."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="[]")
        mock_response.json = AsyncMock(return_value=[])
        mock_response.raise_for_status = MagicMock()

        mock_session.post.return_value.__aenter__.return_value = mock_response

        result = await client.get_counter_readings_batch([], "token", "cookie")

        assert len(result) == 0
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_counter_readings_batch_empty_response(self, client, mock_session):
        """Test batch request with empty response array."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="[]")
        mock_response.json = AsyncMock(return_value=[])
        mock_response.raise_for_status = MagicMock()

        mock_session.post.return_value.__aenter__.return_value = mock_response

        with patch("custom_components.cem_monitor.api._LOGGER") as mock_logger:
            result = await client.get_counter_readings_batch([104437, 102496], "token", "cookie")

            assert len(result) == 0
            assert result == {}
            
            # Verify warning is logged for empty response with requested var_ids
            mock_logger.warning.assert_called_once()
            # Check the format string and arguments
            warning_format = mock_logger.warning.call_args[0][0]
            warning_args = mock_logger.warning.call_args[0][1:]
            assert "API returned empty list" in warning_format
            assert len(warning_args) == 2
            assert warning_args[0] == 2  # number of var_ids
            assert isinstance(warning_args[1], list)  # sorted var_ids list

    @pytest.mark.asyncio
    async def test_get_counter_readings_batch_missing_fields(self, client, mock_session):
        """Test batch request where some readings have missing fields."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(
            return_value='[{"value": 123.45, "timestamp": 1234567890, "var_id": 104437}, {"var_id": 102496}]'
        )
        mock_response.json = AsyncMock(
            return_value=[
                {"value": 123.45, "timestamp": 1234567890, "var_id": 104437},
                {"var_id": 102496},  # Missing value and timestamp
            ]
        )
        mock_response.raise_for_status = MagicMock()

        mock_session.post.return_value.__aenter__.return_value = mock_response

        result = await client.get_counter_readings_batch([104437, 102496], "token", "cookie")

        # Only valid reading should be in result
        assert len(result) == 1
        assert 104437 in result
        assert 102496 not in result

    @pytest.mark.asyncio
    async def test_get_counter_readings_batch_missing_var_id(self, client, mock_session):
        """Test batch request where some readings have missing var_id."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(
            return_value='[{"value": 123.45, "timestamp": 1234567890, "var_id": 104437}, {"value": 456.78, "timestamp": 1234567900}]'
        )
        mock_response.json = AsyncMock(
            return_value=[
                {"value": 123.45, "timestamp": 1234567890, "var_id": 104437},
                {"value": 456.78, "timestamp": 1234567900},  # Missing var_id
            ]
        )
        mock_response.raise_for_status = MagicMock()

        mock_session.post.return_value.__aenter__.return_value = mock_response

        result = await client.get_counter_readings_batch([104437, 102496], "token", "cookie")

        # Only reading with var_id should be in result
        assert len(result) == 1
        assert 104437 in result
        assert 102496 not in result

    @pytest.mark.asyncio
    async def test_get_counter_readings_batch_retry_on_timeout(self, client, mock_session):
        """Test that batch request retries on timeout."""
        call_count = 0

        async def post_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ServerTimeoutError()
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value='[{"value": 123.45, "timestamp": 1234567890, "var_id": 104437}]')
            mock_response.json = AsyncMock(
                return_value=[{"value": 123.45, "timestamp": 1234567890, "var_id": 104437}]
            )
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_session.post.return_value.__aenter__.side_effect = post_side_effect

        result = await client.get_counter_readings_batch([104437], "token", "cookie")

        assert result[104437]["value"] == 123.45
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_get_counter_readings_batch_retry_on_500(self, client, mock_session):
        """Test that batch request retries on 500 error."""
        call_count = 0

        async def post_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ClientResponseError(None, None, status=500)
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value='[{"value": 123.45, "timestamp": 1234567890, "var_id": 104437}]')
            mock_response.json = AsyncMock(
                return_value=[{"value": 123.45, "timestamp": 1234567890, "var_id": 104437}]
            )
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_session.post.return_value.__aenter__.side_effect = post_side_effect

        result = await client.get_counter_readings_batch([104437], "token", "cookie")

        assert result[104437]["value"] == 123.45
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_get_counter_readings_batch_wrapped_response(self, client, mock_session):
        """Test batch request with wrapped response (data key)."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(
            return_value='{"data": [{"value": 123.45, "timestamp": 1234567890, "var_id": 104437}]}'
        )
        mock_response.json = AsyncMock(
            return_value={"data": [{"value": 123.45, "timestamp": 1234567890, "var_id": 104437}]}
        )
        mock_response.raise_for_status = MagicMock()

        mock_session.post.return_value.__aenter__.return_value = mock_response

        result = await client.get_counter_readings_batch([104437], "token", "cookie")

        assert len(result) == 1
        assert result[104437]["value"] == 123.45
        assert result[104437]["timestamp_ms"] == 1234567890

    @pytest.mark.asyncio
    async def test_get_counter_readings_batch_invalid_response_format(self, client, mock_session):
        """Test batch request with invalid response format (not a list)."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"error": "invalid"}')
        mock_response.json = AsyncMock(return_value={"error": "invalid"})
        mock_response.raise_for_status = MagicMock()

        mock_session.post.return_value.__aenter__.return_value = mock_response

        with pytest.raises(ValueError, match="unexpected response"):
            await client.get_counter_readings_batch([104437], "token", "cookie")

    @pytest.mark.asyncio
    async def test_get_counter_readings_batch_401_error(self, client, mock_session):
        """Test that 401 error in batch request is raised (not retried at API level)."""
        from aiohttp import RequestInfo
        request_info = RequestInfo(url="http://test.com", method="POST", headers={}, real_url="http://test.com")
        call_count = 0

        async def post_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ClientResponseError(request_info, None, status=401)

        mock_session.post.return_value.__aenter__.side_effect = post_side_effect

        with pytest.raises(ClientResponseError) as exc_info:
            await client.get_counter_readings_batch([104437], "token", "cookie")

        assert exc_info.value.status == 401
        assert call_count == 1  # API client doesn't retry 401, coordinator handles it

    @pytest.mark.asyncio
    async def test_get_counter_readings_batch_401_then_success_after_token_refresh(self, client, mock_session):
        """Test batch request that fails with 401, then succeeds after token refresh.
        
        Note: This test simulates the coordinator-level retry pattern where:
        1. Batch API call returns 401
        2. Coordinator refreshes token
        3. Batch API call retried with new token succeeds
        """
        from aiohttp import RequestInfo
        request_info = RequestInfo(url="http://test.com", method="POST", headers={}, real_url="http://test.com")
        call_count = 0

        async def post_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call with old token returns 401
                raise ClientResponseError(request_info, None, status=401)
            # Second call with new token succeeds
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(
                return_value='[{"value": 123.45, "timestamp": 1234567890, "var_id": 104437}]'
            )
            mock_response.json = AsyncMock(
                return_value=[{"value": 123.45, "timestamp": 1234567890, "var_id": 104437}]
            )
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_session.post.return_value.__aenter__.side_effect = post_side_effect

        # Simulate coordinator-level retry pattern
        from custom_components.cem_monitor.retry import is_401_error
        
        try:
            result = await client.get_counter_readings_batch([104437], "old_token", "old_cookie")
        except ClientResponseError as err:
            if is_401_error(err):
                # Coordinator would refresh token here, then retry
                result = await client.get_counter_readings_batch([104437], "new_token", "new_cookie")
            else:
                raise

        assert len(result) == 1
        assert result[104437]["value"] == 123.45
        assert call_count == 2  # Initial call + retry after token refresh

    @pytest.mark.asyncio
    async def test_get_counter_readings_batch_401_persists_after_refresh(self, client, mock_session):
        """Test batch request that fails with 401 even after token refresh."""
        from aiohttp import RequestInfo
        request_info = RequestInfo(url="http://test.com", method="POST", headers={}, real_url="http://test.com")
        call_count = 0

        async def post_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Always returns 401
            raise ClientResponseError(request_info, None, status=401)

        mock_session.post.return_value.__aenter__.side_effect = post_side_effect

        # Simulate coordinator-level retry pattern
        from custom_components.cem_monitor.retry import is_401_error
        
        try:
            result = await client.get_counter_readings_batch([104437], "old_token", "old_cookie")
        except ClientResponseError as err:
            if is_401_error(err):
                # Coordinator would refresh token here, then retry
                # But retry also fails with 401
                with pytest.raises(ClientResponseError) as exc_info:
                    await client.get_counter_readings_batch([104437], "new_token", "new_cookie")
                assert exc_info.value.status == 401
                assert call_count == 2  # Initial call + retry after token refresh
            else:
                raise

