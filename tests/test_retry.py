"""Tests for retry logic and error classification."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from aiohttp import ClientResponseError, ClientError, ClientConnectorError, ServerTimeoutError

import sys
from pathlib import Path

# Add custom_components to path for testing
sys.path.insert(0, str(Path(__file__).parent.parent))

from custom_components.cem_monitor.retry import (
    is_retryable_error,
    is_401_error,
    async_retry_with_backoff,
    RetryableError,
)


class TestErrorClassification:
    """Test error classification functions."""

    def test_is_retryable_network_errors(self):
        """Test that network errors are retryable."""
        assert is_retryable_error(ClientConnectorError(None, None)) is True
        assert is_retryable_error(ServerTimeoutError()) is True
        assert is_retryable_error(asyncio.TimeoutError()) is True

    def test_is_retryable_5xx_errors(self):
        """Test that 5xx server errors are retryable."""
        error_500 = ClientResponseError(None, None, status=500)
        error_503 = ClientResponseError(None, None, status=503)
        assert is_retryable_error(error_500) is True
        assert is_retryable_error(error_503) is True

    def test_is_not_retryable_401(self):
        """Test that 401 errors are not retryable."""
        error_401 = ClientResponseError(None, None, status=401)
        assert is_retryable_error(error_401) is False

    def test_is_not_retryable_4xx_errors(self):
        """Test that 4xx client errors are not retryable."""
        error_404 = ClientResponseError(None, None, status=404)
        error_400 = ClientResponseError(None, None, status=400)
        error_403 = ClientResponseError(None, None, status=403)
        assert is_retryable_error(error_404) is False
        assert is_retryable_error(error_400) is False
        assert is_retryable_error(error_403) is False

    def test_is_not_retryable_value_error(self):
        """Test that ValueError is not retryable."""
        assert is_retryable_error(ValueError("test")) is False

    def test_is_401_error_detection(self):
        """Test 401 error detection."""
        error_401 = ClientResponseError(None, None, status=401)
        error_404 = ClientResponseError(None, None, status=404)
        assert is_401_error(error_401) is True
        assert is_401_error(error_404) is False
        assert is_401_error(ValueError("401 error")) is True  # String contains 401


class TestRetryWithBackoff:
    """Test retry logic with exponential backoff."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        """Test that successful call doesn't retry."""
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await async_retry_with_backoff(func, max_retries=3)
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_success_after_retries(self):
        """Test that retry eventually succeeds."""
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ClientConnectorError(None, None)
            return "success"

        result = await async_retry_with_backoff(func, max_retries=3, initial_delay=0.1)
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """Test that max retries are respected."""
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            raise ClientConnectorError(None, None)

        with pytest.raises(ClientConnectorError):
            await async_retry_with_backoff(func, max_retries=2, initial_delay=0.1)

        assert call_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_no_retry_on_non_retryable_error(self):
        """Test that non-retryable errors fail immediately."""
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            raise ClientResponseError(None, None, status=404)

        with pytest.raises(ClientResponseError):
            await async_retry_with_backoff(func, max_retries=3, initial_delay=0.1)

        assert call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self):
        """Test that backoff delays increase exponentially."""
        delays = []
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ClientConnectorError(None, None)
            return "success"

        with patch("asyncio.sleep") as mock_sleep:
            async def sleep_side_effect(delay):
                delays.append(delay)

            mock_sleep.side_effect = sleep_side_effect

            await async_retry_with_backoff(
                func, max_retries=3, initial_delay=1.0, exponential_base=2.0, jitter=False
            )

            # Should have 2 delays (before 2nd and 3rd attempt)
            assert len(delays) == 2
            # First delay should be ~1s, second ~2s
            assert 0.9 <= delays[0] <= 1.1
            assert 1.9 <= delays[1] <= 2.1

    @pytest.mark.asyncio
    async def test_max_delay_respected(self):
        """Test that max delay is not exceeded."""
        delays = []
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ClientConnectorError(None, None)
            return "success"

        with patch("asyncio.sleep") as mock_sleep:
            async def sleep_side_effect(delay):
                delays.append(delay)

            mock_sleep.side_effect = sleep_side_effect

            await async_retry_with_backoff(
                func,
                max_retries=3,
                initial_delay=10.0,  # Would be 20s on second retry
                max_delay=5.0,  # But capped at 5s
                exponential_base=2.0,
                jitter=False,
            )

            # All delays should be capped at max_delay
            assert all(d <= 5.0 for d in delays)

    @pytest.mark.asyncio
    async def test_jitter_added(self):
        """Test that jitter adds randomness to delays."""
        delays = []
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ClientConnectorError(None, None)
            return "success"

        with patch("asyncio.sleep") as mock_sleep:
            async def sleep_side_effect(delay):
                delays.append(delay)

            mock_sleep.side_effect = sleep_side_effect

            await async_retry_with_backoff(
                func, max_retries=3, initial_delay=1.0, jitter=True
            )

            # With jitter, delay should be between 1.0 and 1.25 (1.0 + 25%)
            assert len(delays) == 1
            assert 1.0 <= delays[0] <= 1.25

    @pytest.mark.asyncio
    async def test_context_logging(self):
        """Test that context is included in retry logging."""
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ClientConnectorError(None, None)
            return "success"

        with patch("custom_components.cem_monitor.retry._LOGGER") as mock_logger:
            await async_retry_with_backoff(
                func, max_retries=3, initial_delay=0.1, context="TestContext"
            )

            # Check that debug was called with context
            debug_calls = [call for call in mock_logger.debug.call_args_list if call]
            assert len(debug_calls) > 0
            # At least one call should mention the context
            assert any("TestContext" in str(call) for call in debug_calls)

