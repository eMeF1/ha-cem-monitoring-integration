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

