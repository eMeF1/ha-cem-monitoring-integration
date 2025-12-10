from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable
from typing import Callable, TypeVar

from aiohttp import ClientError, ClientResponseError
from aiohttp.client_exceptions import ClientConnectorError, ServerTimeoutError

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


class RetryableError(Exception):
    """Exception raised for errors that should be retried."""

    pass


def is_retryable_error(error: Exception) -> bool:
    """
    Determine if an error is retryable.

    Retryable errors:
    - Network errors (ClientConnectorError, ServerTimeoutError, asyncio.TimeoutError)
    - HTTP 5xx server errors

    Non-retryable errors:
    - HTTP 401 (unauthorized) - should trigger token refresh instead
    - HTTP 404 (not found)
    - HTTP 400 (bad request)
    - Other 4xx client errors
    - ValueError and other non-network errors
    """
    # HTTP response errors - check these FIRST before general ClientError
    if isinstance(error, ClientResponseError):
        status = error.status
        # 5xx server errors are retryable
        if 500 <= status < 600:
            return True
        # 401, 404, 400, and other 4xx are not retryable
        if 400 <= status < 500:
            return False

    # Network and connection errors
    if isinstance(error, (ClientConnectorError, ServerTimeoutError, asyncio.TimeoutError)):
        return True

    # General aiohttp client errors (network issues) - but NOT ClientResponseError (already handled above)
    if isinstance(error, ClientError) and not isinstance(error, ClientResponseError):
        return True

    # Non-network errors are not retryable
    return False


def is_401_error(error: Exception) -> bool:
    """Check if error is a 401 Unauthorized error."""
    if isinstance(error, ClientResponseError):
        status: int = error.status
        is_401: bool = status == 401
        return is_401
    try:
        error_str: str = str(error)
        contains_401: bool = "401" in error_str
        return contains_401
    except Exception:
        return False


async def async_retry_with_backoff(
    func: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 10.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    context: str = "",
) -> T:
    """
    Retry an async function with exponential backoff.

    Args:
        func: Async function to retry (no arguments)
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay in seconds (default: 10.0)
        exponential_base: Base for exponential backoff (default: 2.0)
        jitter: Add random jitter to prevent thundering herd (default: True)
        context: Context string for logging (default: "")

    Returns:
        Result of the function call

    Raises:
        Last exception if all retries are exhausted
        RetryableError if error is not retryable
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception as err:
            last_exception = err

            # Check if error is retryable
            if not is_retryable_error(err):
                _LOGGER.debug(
                    "%sNon-retryable error on attempt %d/%d: %s",
                    f"{context}: " if context else "",
                    attempt + 1,
                    max_retries + 1,
                    err,
                )
                raise

            # If this was the last attempt, raise the error
            if attempt >= max_retries:
                try:
                    err_str = str(err)
                except Exception:
                    err_str = repr(err)
                _LOGGER.warning(
                    "%sMax retries (%d) exceeded, giving up: %s",
                    f"{context}: " if context else "",
                    max_retries + 1,
                    err_str,
                )
                raise

            # Calculate delay with exponential backoff
            delay = min(initial_delay * (exponential_base**attempt), max_delay)

            # Add jitter (0-25% random variation)
            if jitter:
                jitter_amount = delay * 0.25 * random.random()
                delay = delay + jitter_amount

            try:
                err_str = str(err)
            except Exception:
                err_str = repr(err)
            _LOGGER.debug(
                "%sRetryable error on attempt %d/%d, retrying in %.2fs: %s",
                f"{context}: " if context else "",
                attempt + 1,
                max_retries + 1,
                delay,
                err_str,
            )

            await asyncio.sleep(delay)

    # Should never reach here, but just in case
    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected error in retry logic")
