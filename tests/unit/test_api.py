"""Tests for API client with mocked HTTP responses."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientConnectorError, ClientResponseError
from aiohttp.client_exceptions import ServerTimeoutError

# conftest.py handles path setup and Home Assistant mocking
from custom_components.cem_monitor.api import AuthResult, CEMClient


class AsyncContextManager:
    """Async context manager that can be configured with a response.

    Python 3.11 compatible: ensures proper exception handling and
    return value handling for async context managers.
    """

    def __init__(self):
        self._response = None
        self._side_effect = None

    def set_response(self, response):
        """Set the response that will be returned by __aenter__."""
        self._response = response
        # Clear side_effect when setting response
        self._side_effect = None

    def set_side_effect(self, side_effect):
        """Set a side effect function for __aenter__."""
        self._side_effect = side_effect
        # Clear response when setting side_effect
        self._response = None

    async def __aenter__(self):
        """Enter the async context manager.

        Python 3.11: ensures proper handling of side effects and responses.
        """
        if self._side_effect is not None:
            # Await the side effect and return its result
            # Python 3.11: exceptions will propagate naturally
            return await self._side_effect()
        return self._response

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit the async context manager.

        Python 3.11: properly handles exceptions and returns None.
        """
        # Return None to indicate exceptions should not be suppressed
        return None


@pytest.fixture
def mock_session():
    """Create a mock aiohttp session.

    Python 3.11 compatible: uses AsyncMock without strict spec to avoid
    issues with spec validation in Python 3.11.
    """
    # Python 3.11: Avoid using spec=ClientSession directly as it may cause issues
    # Instead, create AsyncMock and configure methods manually
    session = AsyncMock()

    # Create context managers that can be configured
    post_context = AsyncContextManager()
    get_context = AsyncContextManager()

    # Make post and get return the context managers
    session.post = MagicMock(return_value=post_context)
    session.get = MagicMock(return_value=get_context)

    # Store references so tests can configure them
    session._post_context = post_context
    session._get_context = get_context

    return session


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
        mock_response.text = AsyncMock(
            return_value='{"access_token": "token123", "valid_to": 1234567890}'
        )
        mock_response.json = AsyncMock(
            return_value={"access_token": "token123", "valid_to": 1234567890}
        )
        mock_response.raise_for_status = MagicMock()

        mock_session._post_context.set_response(mock_response)

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
            mock_response.text = AsyncMock(
                return_value='{"access_token": "token", "valid_to": 1234567890}'
            )
            mock_response.json = AsyncMock(
                return_value={"access_token": "token", "valid_to": 1234567890}
            )
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_session._post_context.set_side_effect(post_side_effect)

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
            request_info = RequestInfo(
                url="http://test.com", method="POST", headers={}, real_url="http://test.com"
            )
            raise ClientResponseError(request_info, None, status=401)

        mock_session._post_context.set_side_effect(post_side_effect)

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

        mock_session._get_context.set_response(mock_response)

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

        mock_session._get_context.set_side_effect(get_side_effect)

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

        mock_session._get_context.set_response(mock_response)

        result = await client.get_objects("token", "cookie")

        assert len(result) == 1
        assert result[0]["mis_id"] == 1

    @pytest.mark.asyncio
    async def test_get_objects_retry_on_connection_error(self, client, mock_session):
        """Test that connection errors are retried."""
        call_count = 0

        async def get_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ClientConnectorError(None, OSError("Connection failed"))
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value="[]")
            mock_response.json = AsyncMock(return_value=[])
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_session._get_context.set_side_effect(get_side_effect)

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
        mock_response.json = AsyncMock(return_value=[{"value": 123.45, "timestamp": 1234567890}])
        mock_response.raise_for_status = MagicMock()

        mock_session._get_context.set_response(mock_response)

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
            request_info = RequestInfo(
                url="http://test.com", method="GET", headers={}, real_url="http://test.com"
            )
            raise ClientResponseError(request_info, None, status=404)

        mock_session._get_context.set_side_effect(get_side_effect)

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

        mock_session._post_context.set_response(mock_response)

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

        mock_session._post_context.set_response(mock_response)

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

        mock_session._post_context.set_response(mock_response)

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

        mock_session._post_context.set_response(mock_response)

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

        mock_session._post_context.set_response(mock_response)

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

        mock_session._post_context.set_response(mock_response)

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
            mock_response.text = AsyncMock(
                return_value='[{"value": 123.45, "timestamp": 1234567890, "var_id": 104437}]'
            )
            mock_response.json = AsyncMock(
                return_value=[{"value": 123.45, "timestamp": 1234567890, "var_id": 104437}]
            )
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_session._post_context.set_side_effect(post_side_effect)

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
            mock_response.text = AsyncMock(
                return_value='[{"value": 123.45, "timestamp": 1234567890, "var_id": 104437}]'
            )
            mock_response.json = AsyncMock(
                return_value=[{"value": 123.45, "timestamp": 1234567890, "var_id": 104437}]
            )
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_session._post_context.set_side_effect(post_side_effect)

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

        mock_session._post_context.set_response(mock_response)

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

        mock_session._post_context.set_response(mock_response)

        with pytest.raises(ValueError, match="unexpected response"):
            await client.get_counter_readings_batch([104437], "token", "cookie")

    @pytest.mark.asyncio
    async def test_get_counter_readings_batch_401_error(self, client, mock_session):
        """Test that 401 error in batch request is raised (not retried at API level)."""
        from aiohttp import RequestInfo

        request_info = RequestInfo(
            url="http://test.com", method="POST", headers={}, real_url="http://test.com"
        )
        call_count = 0

        async def post_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ClientResponseError(request_info, None, status=401)

        mock_session._post_context.set_side_effect(post_side_effect)

        with pytest.raises(ClientResponseError) as exc_info:
            await client.get_counter_readings_batch([104437], "token", "cookie")

        assert exc_info.value.status == 401
        assert call_count == 1  # API client doesn't retry 401, coordinator handles it

    @pytest.mark.asyncio
    async def test_get_counter_readings_batch_401_then_success_after_token_refresh(
        self, client, mock_session
    ):
        """Test batch request that fails with 401, then succeeds after token refresh.

        Note: This test simulates the coordinator-level retry pattern where:
        1. Batch API call returns 401
        2. Coordinator refreshes token
        3. Batch API call retried with new token succeeds
        """
        from aiohttp import RequestInfo

        request_info = RequestInfo(
            url="http://test.com", method="POST", headers={}, real_url="http://test.com"
        )
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

        mock_session._post_context.set_side_effect(post_side_effect)

        # Simulate coordinator-level retry pattern
        from custom_components.cem_monitor.utils.retry import is_401_error

        try:
            result = await client.get_counter_readings_batch([104437], "old_token", "old_cookie")
        except ClientResponseError as err:
            if is_401_error(err):
                # Coordinator would refresh token here, then retry
                result = await client.get_counter_readings_batch(
                    [104437], "new_token", "new_cookie"
                )
            else:
                raise

        assert len(result) == 1
        assert result[104437]["value"] == 123.45
        assert call_count == 2  # Initial call + retry after token refresh

    @pytest.mark.asyncio
    async def test_get_counter_readings_batch_401_persists_after_refresh(
        self, client, mock_session
    ):
        """Test batch request that fails with 401 even after token refresh."""
        from aiohttp import RequestInfo

        request_info = RequestInfo(
            url="http://test.com", method="POST", headers={}, real_url="http://test.com"
        )
        call_count = 0

        async def post_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Always returns 401
            raise ClientResponseError(request_info, None, status=401)

        mock_session._post_context.set_side_effect(post_side_effect)

        # Simulate coordinator-level retry pattern
        from custom_components.cem_monitor.utils.retry import is_401_error

        try:
            await client.get_counter_readings_batch([104437], "old_token", "old_cookie")
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


class TestGetCounterValueTypes:
    """Test get_counter_value_types method."""

    @pytest.mark.asyncio
    async def test_get_counter_value_types_success_list(self, client, mock_session):
        """Test successful get_counter_value_types when API returns a list (actual behavior)."""
        # Real API response format with all fields
        real_api_response = [
            {
                "cik_nazev": "Přírustková",
                "lt_key": "LB_CIS_50_1",
                "cik_fk": 1,
                "cik_char": None,
                "cik_cislo": 0,
                "cik_double": 0.000,
                "cik_pzn": "(napr. Vodomer)  Sloupcovy graf. Pro hodiny/dny/mesice/roky se dela rozdil posledni a prvni hodnoty pripadne rozdil hodnot aproximovanych.",
                "cik_cislo2": None,
                "cik_zprac": None,
                "cik_akt": True,
            },
            {
                "cik_nazev": "Výčtová",
                "lt_key": "LB_CIS_50_2",
                "cik_fk": 2,
                "cik_char": None,
                "cik_cislo": 0,
                "cik_double": 0.000,
                "cik_pzn": "(napr. Dverni spinac) ",
                "cik_cislo2": None,
                "cik_zprac": None,
                "cik_akt": True,
            },
            {
                "cik_nazev": "Absolutní součtová",
                "lt_key": "LB_CIS_50_3",
                "cik_fk": 3,
                "cik_char": None,
                "cik_cislo": 0,
                "cik_double": 0.000,
                "cik_pzn": "(napr. Denostupne, jen nektere pristroje)  Sloupcovy graf. Pro hodiny/dny/mesice/roky se dela soucet ze vsech hodnot.",
                "cik_cislo2": None,
                "cik_zprac": None,
                "cik_akt": True,
            },
            {
                "cik_nazev": "Absolutní",
                "lt_key": "LB_CIS_50_0",
                "cik_fk": 0,
                "cik_char": None,
                "cik_cislo": 0,
                "cik_double": 0.000,
                "cik_pzn": "(napr. Teplomer)  Carovy graf. Pro hodiny/dny/mesice/roky se dela vazeny prumer ze vsech hodnot.",
                "cik_cislo2": None,
                "cik_zprac": None,
                "cik_akt": True,
            },
        ]

        mock_response = AsyncMock()
        mock_response.status = 200
        import json

        mock_response.text = AsyncMock(return_value=json.dumps(real_api_response))
        mock_response.json = AsyncMock(return_value=real_api_response)
        mock_response.raise_for_status = MagicMock()

        mock_session._get_context.set_response(mock_response)

        result = await client.get_counter_value_types("token", "cookie", cis=50)

        assert isinstance(result, list)
        assert len(result) == 4
        # Verify all expected values are present
        cik_fk_values = {item["cik_fk"]: item["cik_nazev"] for item in result}
        assert cik_fk_values[0] == "Absolutní"
        assert cik_fk_values[1] == "Přírustková"
        assert cik_fk_values[2] == "Výčtová"
        assert cik_fk_values[3] == "Absolutní součtová"

    @pytest.mark.asyncio
    async def test_get_counter_value_types_success_dict(self, client, mock_session):
        """Test successful get_counter_value_types when API returns a dict (wrapped response)."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(
            return_value='{"data": [{"cik_fk": 0, "cik_nazev": "Přírustková"}]}'
        )
        mock_response.json = AsyncMock(
            return_value={"data": [{"cik_fk": 0, "cik_nazev": "Přírustková"}]}
        )
        mock_response.raise_for_status = MagicMock()

        mock_session._get_context.set_response(mock_response)

        result = await client.get_counter_value_types("token", "cookie", cis=50)

        assert isinstance(result, dict)
        assert "data" in result

    @pytest.mark.asyncio
    async def test_get_counter_value_types_empty_list(self, client, mock_session):
        """Test get_counter_value_types with empty list response."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="[]")
        mock_response.json = AsyncMock(return_value=[])
        mock_response.raise_for_status = MagicMock()

        mock_session._get_context.set_response(mock_response)

        result = await client.get_counter_value_types("token", "cookie", cis=50)

        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_counter_value_types_retry_on_timeout(self, client, mock_session):
        """Test that get_counter_value_types retries on timeout."""
        call_count = 0

        async def get_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ServerTimeoutError()
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(
                return_value='[{"cik_fk": 0, "cik_nazev": "Přírustková"}]'
            )
            mock_response.json = AsyncMock(return_value=[{"cik_fk": 0, "cik_nazev": "Přírustková"}])
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_session._get_context.set_side_effect(get_side_effect)

        result = await client.get_counter_value_types("token", "cookie", cis=50)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["cik_nazev"] == "Přírustková"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_get_counter_value_types_retry_on_500(self, client, mock_session):
        """Test that get_counter_value_types retries on 500 error."""
        call_count = 0

        async def get_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ClientResponseError(None, None, status=500)
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value='[{"cik_fk": 1, "cik_nazev": "Absolutní"}]')
            mock_response.json = AsyncMock(return_value=[{"cik_fk": 1, "cik_nazev": "Absolutní"}])
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_session._get_context.set_side_effect(get_side_effect)

        result = await client.get_counter_value_types("token", "cookie", cis=50)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["cik_nazev"] == "Absolutní"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_get_counter_value_types_no_retry_on_401(self, client, mock_session):
        """Test that 401 errors are not retried."""
        from aiohttp import RequestInfo

        call_count = 0

        async def get_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            request_info = RequestInfo(
                url="http://test.com", method="GET", headers={}, real_url="http://test.com"
            )
            raise ClientResponseError(request_info, None, status=401)

        mock_session._get_context.set_side_effect(get_side_effect)

        with pytest.raises(ClientResponseError):
            await client.get_counter_value_types("token", "cookie", cis=50)

        assert call_count == 1  # No retries


class TestGetPotTypes:
    """Test get_pot_types method."""

    @pytest.mark.asyncio
    async def test_get_pot_types_success_wrapped(self, client, mock_session):
        """Test successful get_pot_types when API returns wrapped response (actual behavior)."""
        # Real API response format - wrapped in {"data": [...], "action": "get"}
        real_api_response = {
            "data": [
                {
                    "ptv_id": None,
                    "lt_key": "LB_POCTYP_TEP",
                    "pot_id": 8,
                    "jed_nazev": "KPD°",
                    "pot_defcolor": "#C05800",
                    "jed_zkr": "KPD°",
                    "pot_type": 3,
                    "jed_id": 5,
                },
                {
                    "ptv_id": 4,
                    "lt_key": "LB_POCTYP_KONT",
                    "pot_id": 28,
                    "jed_nazev": " ",
                    "pot_defcolor": "#004c70",
                    "jed_zkr": " ",
                    "pot_type": 2,
                    "jed_id": 102,
                },
                {
                    "ptv_id": None,
                    "lt_key": "LB_POCTYP_ELVT",
                    "pot_id": 1,
                    "jed_nazev": "kWh",
                    "pot_defcolor": "#9C0F0F",
                    "jed_zkr": "kWh",
                    "pot_type": 1,
                    "jed_id": 1,
                },
                {
                    "ptv_id": None,
                    "lt_key": "LB_POCTYP_SV",
                    "pot_id": 3,
                    "jed_nazev": "m³",
                    "pot_defcolor": "#0000C0",
                    "jed_zkr": "m³",
                    "pot_type": 1,
                    "jed_id": 3,
                },
            ],
            "action": "get",
        }

        mock_response = AsyncMock()
        mock_response.status = 200
        import json

        mock_response.text = AsyncMock(return_value=json.dumps(real_api_response))
        mock_response.json = AsyncMock(return_value=real_api_response)
        mock_response.raise_for_status = MagicMock()

        mock_session._get_context.set_response(mock_response)

        result = await client.get_pot_types("token", "cookie")

        assert isinstance(result, dict)
        assert "data" in result
        assert len(result["data"]) == 4
        # Verify pot_type values are present
        assert result["data"][0]["pot_id"] == 8
        assert result["data"][0]["pot_type"] == 3
        assert result["data"][2]["pot_id"] == 1
        assert result["data"][2]["pot_type"] == 1

    @pytest.mark.asyncio
    async def test_get_pot_types_empty_data(self, client, mock_session):
        """Test get_pot_types with empty data array."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"data": [], "action": "get"}')
        mock_response.json = AsyncMock(return_value={"data": [], "action": "get"})
        mock_response.raise_for_status = MagicMock()

        mock_session._get_context.set_response(mock_response)

        result = await client.get_pot_types("token", "cookie")

        assert isinstance(result, dict)
        assert result["data"] == []


class TestGetMeters:
    """Test get_meters method with real API response format."""

    @pytest.mark.asyncio
    async def test_get_meters_success_wrapped(self, client, mock_session):
        """Test successful get_meters when API returns wrapped response (actual behavior)."""
        # Real API response format - wrapped in {"data": [...], "action": "get"}
        real_api_response = {
            "data": [
                {
                    "me_fakt": False,
                    "me_zapoc": True,
                    "me_sdil": None,
                    "me_extid": None,
                    "me_id": 80225,
                    "me_plom": None,
                    "me_serial": "41020614",
                    "me_typ_pzn": None,
                    "me_alarm": 168,
                    "me_desc": None,
                    "me_od": 1631570400000,
                    "me_over": 1631570400000,
                    "me_pot_id": 3,
                    "met_id": 549,
                    "me_do": None,
                    "mis_id": 116900,
                },
                {
                    "me_fakt": False,
                    "me_zapoc": True,
                    "me_sdil": None,
                    "me_extid": None,
                    "me_id": 78680,
                    "me_plom": None,
                    "me_serial": "46147845",
                    "me_typ_pzn": None,
                    "me_alarm": 168,
                    "me_desc": None,
                    "me_od": 1609369200000,
                    "me_over": 1609369200000,
                    "me_pot_id": 3,
                    "met_id": 549,
                    "me_do": 1631570340000,
                    "mis_id": 116900,
                },
            ],
            "action": "get",
        }

        mock_response = AsyncMock()
        mock_response.status = 200
        import json

        mock_response.text = AsyncMock(return_value=json.dumps(real_api_response))
        mock_response.json = AsyncMock(return_value=real_api_response)
        mock_response.raise_for_status = MagicMock()

        mock_session._get_context.set_response(mock_response)

        result = await client.get_meters("token", "cookie")

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["me_id"] == 80225
        assert result[0]["me_serial"] == "41020614"
        assert result[0]["mis_id"] == 116900
        assert result[1]["me_id"] == 78680
        assert result[1]["me_serial"] == "46147845"


class TestGetCountersByMeter:
    """Test get_counters_by_meter method with real API response format."""

    @pytest.mark.asyncio
    async def test_get_counters_by_meter_success_wrapped(self, client, mock_session):
        """Test successful get_counters_by_meter when API returns wrapped response (actual behavior)."""
        # Real API response format - wrapped in {"data": [...], "action": "get"}
        real_api_response = {
            "data": [
                {
                    "var_lastvar": 846.963,
                    "var_nasob": 1.0,
                    "poc_typode": 0,
                    "poc_insaval": None,
                    "poc_serv": None,
                    "var_lastonly": False,
                    "var_minint": None,
                    "me_id": 78680,
                    "var_lasttime": 1631570340000,
                    "poc_primary": True,
                    "poc_servis": None,
                    "pot_id": 3,
                    "var_q": 0.0,
                    "var_id": 102496,
                    "poc_desc": None,
                    "poc_perioda": 4,
                    "poc_extid": None,
                    "tds_id": None,
                },
                {
                    "var_lastvar": 585.51,
                    "var_nasob": 1.0,
                    "poc_typode": 2,
                    "poc_insaval": None,
                    "poc_serv": None,
                    "var_lastonly": False,
                    "var_minint": None,
                    "me_id": 80225,
                    "var_lasttime": 1765404105000,
                    "poc_primary": True,
                    "poc_servis": None,
                    "pot_id": 3,
                    "var_q": 0.0,
                    "var_id": 104437,
                    "poc_desc": None,
                    "poc_perioda": 4,
                    "poc_extid": None,
                    "tds_id": None,
                },
            ],
            "action": "get",
        }

        mock_response = AsyncMock()
        mock_response.status = 200
        import json

        mock_response.text = AsyncMock(return_value=json.dumps(real_api_response))
        mock_response.json = AsyncMock(return_value=real_api_response)
        mock_response.raise_for_status = MagicMock()

        mock_session._get_context.set_response(mock_response)

        result = await client.get_counters_by_meter(80225, "token", "cookie")

        assert isinstance(result, list)
        # get_counters_by_meter filters by me_id, so only counter with me_id=80225 remains
        assert len(result) == 1
        assert result[0]["var_id"] == 104437
        assert result[0]["pot_id"] == 3
        assert result[0]["me_id"] == 80225


class TestGetCountersForObject:
    """Test get_counters_for_object method with real API response format."""

    @pytest.mark.asyncio
    async def test_get_counters_for_object_success_list(self, client, mock_session):
        """Test successful get_counters_for_object when API returns plain array (actual behavior)."""
        # Real API response format - plain array (not wrapped)
        real_api_response = [
            {
                "me_id": 80225,
                "pot_id": 3,
                "poc_typode": 2,
                "var_id": 104437,
                "poc_extid": None,
                "poc_perioda": 4,
                "poc_serv": None,
                "var_nasob": 1.000,
                "poc_primary": True,
                "poc_insaval": None,
                "var_lastonly": False,
                "tds_id": None,
                "uni_id": None,
                "var_lastvar": 585.510,
                "var_lasttime": 1765407705000,
                "var_type": 1,
                "var_q": 0.000,
                "var_minint": None,
                "var_exceed": None,
            }
        ]

        mock_response = AsyncMock()
        mock_response.status = 200
        import json

        mock_response.text = AsyncMock(return_value=json.dumps(real_api_response))
        mock_response.json = AsyncMock(return_value=real_api_response)
        mock_response.raise_for_status = MagicMock()

        mock_session._get_context.set_response(mock_response)

        result = await client.get_counters_for_object(116850, "token", "cookie")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["var_id"] == 104437
        assert result[0]["pot_id"] == 3
        assert result[0]["me_id"] == 80225


class TestGetObjects:
    """Test get_objects method with real API response format."""

    @pytest.mark.asyncio
    async def test_get_objects_success_list_real(self, client, mock_session):
        """Test successful get_objects with real API response format (plain array)."""
        # Real API response format - plain array (not wrapped)
        real_api_response = [
            {
                "mis_id": 116850,
                "mis_idp": 117761,
                "mit_id": 3,
                "mis_nazev": "A 133",
                "mis_nazev2": None,
                "mis_od": 1609372800000,
                "mis_do": None,
                "mis_extid1": None,
                "mis_extid2": None,
                "adr_id": None,
                "mis_sort": 13,
                "mis_pzn": None,
                "prk_id": None,
                "mis_inst_pzn": None,
            },
            {
                "mis_id": 116900,
                "mis_idp": 116850,
                "mit_id": -1000,
                "mis_nazev": "",
                "mis_nazev2": None,
                "mis_od": 1609372800000,
                "mis_do": None,
                "mis_extid1": None,
                "mis_extid2": None,
                "adr_id": None,
                "mis_sort": 1,
                "mis_pzn": None,
                "prk_id": None,
                "mis_inst_pzn": None,
            },
        ]

        mock_response = AsyncMock()
        mock_response.status = 200
        import json

        mock_response.text = AsyncMock(return_value=json.dumps(real_api_response))
        mock_response.json = AsyncMock(return_value=real_api_response)
        mock_response.raise_for_status = MagicMock()

        mock_session._get_context.set_response(mock_response)

        result = await client.get_objects("token", "cookie")

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["mis_id"] == 116850
        assert result[0]["mis_nazev"] == "A 133"
        assert result[1]["mis_id"] == 116900
        assert result[1]["mis_nazev"] == ""  # Empty name (unnamed object)
