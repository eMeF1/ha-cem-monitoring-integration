"""Tests for TypesCache with mocked Home Assistant Store."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone

from custom_components.cem_monitor.cache import TypesCache, CACHE_VERSION, CACHE_TTL_DAYS


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    return hass


@pytest.fixture
def mock_store():
    """Create a mock Store instance."""
    store = MagicMock()
    store.async_load = AsyncMock(return_value=None)
    store.async_save = AsyncMock()
    store.async_remove = AsyncMock()
    return store


@pytest.fixture
def types_cache(mock_hass, mock_store):
    """Create TypesCache with mocked store."""
    with patch('custom_components.cem_monitor.cache.Store', return_value=mock_store):
        cache = TypesCache(mock_hass)
        cache._store = mock_store
        return cache


class TestTypesCacheLoad:
    """Test cache loading functionality."""

    @pytest.mark.asyncio
    async def test_load_cache_miss(self, types_cache, mock_store):
        """Test loading when no cache exists."""
        mock_store.async_load.return_value = None
        
        pot_types, counter_value_types, is_valid = await types_cache.load()
        
        assert pot_types is None
        assert counter_value_types is None
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_load_cache_hit(self, types_cache, mock_store):
        """Test loading valid cache."""
        cached_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        mock_store.async_load.return_value = {
            "version": CACHE_VERSION,
            "cached_at": cached_at,
            "pot_types": {
                "1": {"pot_id": 1, "jed_zkr": "m³"},
                "2": {"pot_id": 2, "jed_zkr": "kWh"},
            },
            "counter_value_types": {
                "0": "Přírustková",
                "1": "Absolutní",
            },
        }
        
        pot_types, counter_value_types, is_valid = await types_cache.load()
        
        assert is_valid is True
        assert len(pot_types) == 2
        assert pot_types[1]["jed_zkr"] == "m³"
        assert pot_types[2]["jed_zkr"] == "kWh"
        assert len(counter_value_types) == 2
        assert counter_value_types[0] == "Přírustková"
        assert counter_value_types[1] == "Absolutní"

    @pytest.mark.asyncio
    async def test_load_cache_expired(self, types_cache, mock_store):
        """Test loading expired cache."""
        cached_at = (datetime.now(timezone.utc) - timedelta(days=CACHE_TTL_DAYS + 1)).isoformat()
        mock_store.async_load.return_value = {
            "version": CACHE_VERSION,
            "cached_at": cached_at,
            "pot_types": {"1": {"pot_id": 1}},
            "counter_value_types": {"0": "Test"},
        }
        
        pot_types, counter_value_types, is_valid = await types_cache.load()
        
        assert is_valid is False
        assert pot_types is None
        assert counter_value_types is None

    @pytest.mark.asyncio
    async def test_load_cache_valid_near_boundary(self, types_cache, mock_store):
        """Test loading cache near TTL boundary (still valid)."""
        # Cache is 6 days old - should be valid (under 7 day TTL)
        cached_at = (datetime.now(timezone.utc) - timedelta(days=CACHE_TTL_DAYS - 1)).isoformat()
        mock_store.async_load.return_value = {
            "version": CACHE_VERSION,
            "cached_at": cached_at,
            "pot_types": {"1": {"pot_id": 1}},
            "counter_value_types": {"0": "Test"},
        }
        
        pot_types, counter_value_types, is_valid = await types_cache.load()
        
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_load_version_mismatch(self, types_cache, mock_store):
        """Test loading cache with wrong version."""
        cached_at = datetime.now(timezone.utc).isoformat()
        mock_store.async_load.return_value = {
            "version": CACHE_VERSION + 1,  # Wrong version
            "cached_at": cached_at,
            "pot_types": {"1": {"pot_id": 1}},
            "counter_value_types": {"0": "Test"},
        }
        
        pot_types, counter_value_types, is_valid = await types_cache.load()
        
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_load_missing_pot_types(self, types_cache, mock_store):
        """Test loading cache with missing pot_types."""
        cached_at = datetime.now(timezone.utc).isoformat()
        mock_store.async_load.return_value = {
            "version": CACHE_VERSION,
            "cached_at": cached_at,
            # Missing pot_types
            "counter_value_types": {"0": "Test"},
        }
        
        pot_types, counter_value_types, is_valid = await types_cache.load()
        
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_load_missing_counter_value_types(self, types_cache, mock_store):
        """Test loading cache with missing counter_value_types."""
        cached_at = datetime.now(timezone.utc).isoformat()
        mock_store.async_load.return_value = {
            "version": CACHE_VERSION,
            "cached_at": cached_at,
            "pot_types": {"1": {"pot_id": 1}},
            # Missing counter_value_types
        }
        
        pot_types, counter_value_types, is_valid = await types_cache.load()
        
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_load_missing_cached_at(self, types_cache, mock_store):
        """Test loading cache with missing cached_at timestamp."""
        mock_store.async_load.return_value = {
            "version": CACHE_VERSION,
            # Missing cached_at
            "pot_types": {"1": {"pot_id": 1}},
            "counter_value_types": {"0": "Test"},
        }
        
        pot_types, counter_value_types, is_valid = await types_cache.load()
        
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_load_invalid_timestamp(self, types_cache, mock_store):
        """Test loading cache with invalid timestamp."""
        mock_store.async_load.return_value = {
            "version": CACHE_VERSION,
            "cached_at": "invalid-timestamp",
            "pot_types": {"1": {"pot_id": 1}},
            "counter_value_types": {"0": "Test"},
        }
        
        pot_types, counter_value_types, is_valid = await types_cache.load()
        
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_load_invalid_key_types(self, types_cache, mock_store):
        """Test loading cache with invalid key types (non-numeric)."""
        cached_at = datetime.now(timezone.utc).isoformat()
        mock_store.async_load.return_value = {
            "version": CACHE_VERSION,
            "cached_at": cached_at,
            "pot_types": {
                "invalid_key": {"pot_id": 1},  # Invalid - should be skipped
                "1": {"pot_id": 1},  # Valid
            },
            "counter_value_types": {
                "not_a_number": "Test",  # Invalid - should be skipped
                "0": "Valid",  # Valid
            },
        }
        
        pot_types, counter_value_types, is_valid = await types_cache.load()
        
        assert is_valid is True
        assert len(pot_types) == 1
        assert 1 in pot_types
        assert len(counter_value_types) == 1
        assert 0 in counter_value_types
        assert counter_value_types[0] == "Valid"

    @pytest.mark.asyncio
    async def test_load_empty_cache(self, types_cache, mock_store):
        """Test loading cache with empty data."""
        cached_at = datetime.now(timezone.utc).isoformat()
        mock_store.async_load.return_value = {
            "version": CACHE_VERSION,
            "cached_at": cached_at,
            "pot_types": {},
            "counter_value_types": {},
        }
        
        pot_types, counter_value_types, is_valid = await types_cache.load()
        
        assert is_valid is True
        assert pot_types == {}
        assert counter_value_types == {}

    @pytest.mark.asyncio
    async def test_load_error_handling(self, types_cache, mock_store):
        """Test error handling during cache load."""
        mock_store.async_load.side_effect = ValueError("Invalid JSON")
        
        pot_types, counter_value_types, is_valid = await types_cache.load()
        
        assert is_valid is False
        assert pot_types is None
        assert counter_value_types is None


class TestTypesCacheSave:
    """Test cache saving functionality."""

    @pytest.mark.asyncio
    async def test_save_success(self, types_cache, mock_store):
        """Test successful cache save."""
        pot_types = {
            1: {"pot_id": 1, "jed_zkr": "m³"},
            2: {"pot_id": 2, "jed_zkr": "kWh"},
        }
        counter_value_types = {
            0: "Přírustková",
            1: "Absolutní",
        }
        
        await types_cache.save(pot_types, counter_value_types)
        
        mock_store.async_save.assert_called_once()
        saved_data = mock_store.async_save.call_args[0][0]
        assert saved_data["version"] == CACHE_VERSION
        assert "cached_at" in saved_data
        # Verify timestamp is valid ISO format
        datetime.fromisoformat(saved_data["cached_at"])
        assert len(saved_data["pot_types"]) == 2
        assert saved_data["pot_types"]["1"]["jed_zkr"] == "m³"
        assert saved_data["pot_types"]["2"]["jed_zkr"] == "kWh"
        assert len(saved_data["counter_value_types"]) == 2
        assert saved_data["counter_value_types"]["0"] == "Přírustková"
        assert saved_data["counter_value_types"]["1"] == "Absolutní"

    @pytest.mark.asyncio
    async def test_save_empty_data(self, types_cache, mock_store):
        """Test saving empty data."""
        await types_cache.save({}, {})
        
        mock_store.async_save.assert_called_once()
        saved_data = mock_store.async_save.call_args[0][0]
        assert saved_data["pot_types"] == {}
        assert saved_data["counter_value_types"] == {}

    @pytest.mark.asyncio
    async def test_save_large_data(self, types_cache, mock_store):
        """Test saving large amounts of data."""
        pot_types = {i: {"pot_id": i, "jed_zkr": f"unit{i}"} for i in range(100)}
        counter_value_types = {i: f"Type{i}" for i in range(10)}
        
        await types_cache.save(pot_types, counter_value_types)
        
        mock_store.async_save.assert_called_once()
        saved_data = mock_store.async_save.call_args[0][0]
        assert len(saved_data["pot_types"]) == 100
        assert len(saved_data["counter_value_types"]) == 10

    @pytest.mark.asyncio
    async def test_save_error_handling(self, types_cache, mock_store):
        """Test error handling during save."""
        mock_store.async_save.side_effect = IOError("Storage error")
        
        # Should not raise exception
        await types_cache.save({1: {"pot_id": 1}}, {0: "Test"})


class TestTypesCacheClear:
    """Test cache clearing functionality."""

    @pytest.mark.asyncio
    async def test_clear_success(self, types_cache, mock_store):
        """Test successful cache clear."""
        await types_cache.clear()
        
        mock_store.async_remove.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_error_handling(self, types_cache, mock_store):
        """Test error handling during clear."""
        mock_store.async_remove.side_effect = IOError("Storage error")
        
        # Should not raise exception
        await types_cache.clear()


class TestTypesCacheRoundTrip:
    """Test save and load round-trip scenarios."""

    @pytest.mark.asyncio
    async def test_save_and_load_round_trip(self, types_cache, mock_store):
        """Test saving data and then loading it back."""
        pot_types = {
            1: {"pot_id": 1, "jed_zkr": "m³", "jed_nazev": "metr krychlový"},
            2: {"pot_id": 2, "jed_zkr": "kWh", "jed_nazev": "kilowatthodina"},
        }
        counter_value_types = {
            0: "Přírustková",
            1: "Absolutní",
            3: "Derivovaná",
        }
        
        # Save
        await types_cache.save(pot_types, counter_value_types)
        saved_data = mock_store.async_save.call_args[0][0]
        
        # Simulate loading the saved data
        mock_store.async_load.return_value = saved_data
        
        # Load
        loaded_pot_types, loaded_counter_value_types, is_valid = await types_cache.load()
        
        assert is_valid is True
        assert len(loaded_pot_types) == 2
        assert loaded_pot_types[1]["jed_zkr"] == "m³"
        assert loaded_pot_types[2]["jed_zkr"] == "kWh"
        assert len(loaded_counter_value_types) == 3
        assert loaded_counter_value_types[0] == "Přírustková"
        assert loaded_counter_value_types[1] == "Absolutní"
        assert loaded_counter_value_types[3] == "Derivovaná"

