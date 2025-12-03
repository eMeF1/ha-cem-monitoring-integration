from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Optional, Tuple

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Cache version - increment when cache format changes
CACHE_VERSION = 1

# Cache TTL - refresh after 7 days (pot_types and counter_value_types rarely change)
CACHE_TTL_DAYS = 7

# Storage key for the global cache
STORAGE_KEY = f"{DOMAIN}_global_types"
STORAGE_VERSION = 1


class TypesCache:
    """Manages persistent caching of pot_types and counter_value_types."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the cache."""
        self.hass = hass
        self._store = Store[dict[str, Any]](hass, STORAGE_VERSION, STORAGE_KEY)

    async def load(
        self,
    ) -> Tuple[Optional[dict[int, dict[str, Any]]], Optional[dict[int, str]], bool]:
        """
        Load cached data from storage.

        Returns:
            Tuple of (pot_types, counter_value_types, is_valid)
            Returns (None, None, False) if cache is missing/invalid/expired
        """
        try:
            cached_data = await self._store.async_load()
            if not cached_data:
                _LOGGER.debug("CEM types cache: no cache found")
                return None, None, False

            # Validate cache version
            cache_version = cached_data.get("version", 0)
            if cache_version != CACHE_VERSION:
                _LOGGER.debug(
                    "CEM types cache: version mismatch (cached=%d, expected=%d)",
                    cache_version,
                    CACHE_VERSION,
                )
                return None, None, False

            # Validate cache structure
            if not isinstance(cached_data.get("pot_types"), dict):
                _LOGGER.debug("CEM types cache: invalid pot_types structure")
                return None, None, False

            if not isinstance(cached_data.get("counter_value_types"), dict):
                _LOGGER.debug("CEM types cache: invalid counter_value_types structure")
                return None, None, False

            # Check TTL
            cached_at_str = cached_data.get("cached_at")
            if not cached_at_str:
                _LOGGER.debug("CEM types cache: missing cached_at timestamp")
                return None, None, False

            try:
                cached_at = datetime.fromisoformat(cached_at_str)
                if cached_at.tzinfo is None:
                    cached_at = cached_at.replace(tzinfo=timezone.utc)
                age = datetime.now(timezone.utc) - cached_at
                if age > timedelta(days=CACHE_TTL_DAYS):
                    _LOGGER.debug(
                        "CEM types cache: expired (age=%d days, max=%d days)",
                        age.days,
                        CACHE_TTL_DAYS,
                    )
                    return None, None, False
            except (ValueError, TypeError) as err:
                _LOGGER.debug("CEM types cache: invalid cached_at timestamp: %s", err)
                return None, None, False

            # Convert dict keys to int (JSON stores keys as strings)
            pot_types: dict[int, dict[str, Any]] = {}
            for k, v in cached_data["pot_types"].items():
                try:
                    pot_types[int(k)] = v
                except (ValueError, TypeError):
                    _LOGGER.debug("CEM types cache: invalid pot_id key: %s", k)
                    continue

            counter_value_types: dict[int, str] = {}
            for k, v in cached_data["counter_value_types"].items():
                try:
                    counter_value_types[int(k)] = v
                except (ValueError, TypeError):
                    _LOGGER.debug("CEM types cache: invalid pot_type key: %s", k)
                    continue

            _LOGGER.debug(
                "CEM types cache: loaded %d pot_types and %d counter_value_types (age=%d days)",
                len(pot_types),
                len(counter_value_types),
                age.days,
            )
            return pot_types, counter_value_types, True

        except Exception as err:
            _LOGGER.debug("CEM types cache: error loading cache: %s", err)
            return None, None, False

    async def save(
        self,
        pot_types: dict[int, dict[str, Any]],
        counter_value_types: dict[int, str],
    ) -> None:
        """
        Save data to cache.

        Args:
            pot_types: Mapping of pot_id -> pot type data
            counter_value_types: Mapping of pot_type -> counter value type name
        """
        try:
            # Convert int keys to strings for JSON serialization
            pot_types_json = {str(k): v for k, v in pot_types.items()}
            counter_value_types_json = {str(k): v for k, v in counter_value_types.items()}

            cache_data: dict[str, Any] = {
                "version": CACHE_VERSION,
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "pot_types": pot_types_json,
                "counter_value_types": counter_value_types_json,
            }

            await self._store.async_save(cache_data)
            _LOGGER.debug(
                "CEM types cache: saved %d pot_types and %d counter_value_types",
                len(pot_types),
                len(counter_value_types),
            )
        except Exception as err:
            _LOGGER.warning("CEM types cache: error saving cache: %s", err)

    async def clear(self) -> None:
        """Clear the cache."""
        try:
            await self._store.async_remove()
            _LOGGER.debug("CEM types cache: cleared")
        except Exception as err:
            _LOGGER.warning("CEM types cache: error clearing cache: %s", err)

