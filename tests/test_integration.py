"""End-to-end integration tests for CEM Monitor."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import timedelta
import time

# conftest.py handles path setup and Home Assistant mocking
from custom_components.cem_monitor import async_setup_entry, async_unload_entry, async_reload_entry
from custom_components.cem_monitor.api import CEMClient, AuthResult
from custom_components.cem_monitor.coordinator import CEMAuthCoordinator
from custom_components.cem_monitor.userinfo_coordinator import CEMUserInfoCoordinator
from custom_components.cem_monitor.objects_coordinator import CEMObjectsCoordinator
from custom_components.cem_monitor.meters_coordinator import CEMMetersCoordinator
from custom_components.cem_monitor.meter_counters_coordinator import CEMMeterCountersCoordinator
from custom_components.cem_monitor.counter_reading_coordinator import CEMCounterReadingCoordinator
from custom_components.cem_monitor.const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_VAR_IDS,
    CONF_COUNTER_UPDATE_INTERVAL_MINUTES,
    DEFAULT_COUNTER_UPDATE_INTERVAL_MINUTES,
)


class AsyncCreateTaskMock:
    """Mock for async_create_task that properly handles coroutines and tracks calls."""
    
    def __init__(self):
        self._call_count = 0
        self._calls = []
        self._tasks = []
    
    def __call__(self, coro):
        """Handle async_create_task call (synchronous, like Home Assistant)."""
        self._call_count += 1
        self._calls.append(coro)
        # In Home Assistant, async_create_task schedules the coroutine as a task
        # Create a task to consume the coroutine and avoid warnings
        # The task will be garbage collected, but at least it's properly created
        if asyncio.iscoroutine(coro):
            try:
                # Try to get the current event loop
                loop = asyncio.get_event_loop()
                task = loop.create_task(coro)
                self._tasks.append(task)
            except RuntimeError:
                # No event loop running, create task in a new loop context
                # This shouldn't happen in tests, but handle it gracefully
                pass
        # Return a mock task object
        return MagicMock()
    
    @property
    def called(self):
        """Check if the mock was called."""
        return self._call_count > 0
    
    @property
    def call_count(self):
        """Get the number of calls."""
        return self._call_count


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.data = {}
    hass.async_create_task = AsyncCreateTaskMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = AsyncMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_reload = AsyncMock()
    return hass


@pytest.fixture
def mock_entry():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.data = {CONF_USERNAME: "test_user", CONF_PASSWORD: "test_pass"}
    entry.options = {
        CONF_VAR_IDS: [104437, 102496],
        CONF_COUNTER_UPDATE_INTERVAL_MINUTES: 30,
    }
    entry.entry_id = "test_entry_id"
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock(return_value=MagicMock())
    return entry


@pytest.fixture
def mock_auth_result():
    """Create a mock AuthResult."""
    return AuthResult(
        access_token="test_token",
        valid_to_ms=int((time.time() + 3600) * 1000),
        cookie_value="test_cookie",
    )


class TestIntegrationSetup:
    """Test full integration setup flow."""

    @pytest.mark.asyncio
    async def test_full_setup_flow(self, mock_hass, mock_entry, mock_auth_result):
        """Test full setup flow creates all coordinators."""
        with patch('custom_components.cem_monitor.async_get_clientsession') as mock_get_session, \
             patch('custom_components.cem_monitor.CEMClient') as mock_client_class, \
             patch('custom_components.cem_monitor.CEMAuthCoordinator') as mock_auth_class, \
             patch('custom_components.cem_monitor.CEMUserInfoCoordinator') as mock_userinfo_class, \
             patch('custom_components.cem_monitor.CEMObjectsCoordinator') as mock_objects_class, \
             patch('custom_components.cem_monitor.CEMMetersCoordinator') as mock_meters_class, \
             patch('custom_components.cem_monitor.CEMMeterCountersCoordinator') as mock_meter_counters_class, \
             patch('custom_components.cem_monitor.CEMCounterReadingCoordinator') as mock_counter_class, \
             patch('custom_components.cem_monitor.TypesCache') as mock_cache_class, \
             patch('custom_components.cem_monitor.async_track_time_interval') as mock_track_interval:
            
            # Setup mocks
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session
            mock_client = MagicMock(spec=CEMClient)
            mock_client_class.return_value = mock_client
            
            # Mock auth coordinator
            mock_auth = MagicMock(spec=CEMAuthCoordinator)
            mock_auth.token = "test_token"
            mock_auth._last_result = mock_auth_result
            mock_auth.async_config_entry_first_refresh = AsyncMock()
            mock_auth_class.return_value = mock_auth
            
            # Mock userinfo coordinator
            mock_userinfo = MagicMock(spec=CEMUserInfoCoordinator)
            mock_userinfo.async_config_entry_first_refresh = AsyncMock()
            mock_userinfo.data = {"company": "Test Co"}
            mock_userinfo_class.return_value = mock_userinfo
            
            # Mock objects coordinator
            mock_objects = MagicMock(spec=CEMObjectsCoordinator)
            mock_objects.async_config_entry_first_refresh = AsyncMock()
            mock_objects.data = {
                "objects": [],
                "raw_by_mis": {},
            }
            mock_objects_class.return_value = mock_objects
            
            # Mock meters coordinator
            mock_meters = MagicMock(spec=CEMMetersCoordinator)
            mock_meters.async_config_entry_first_refresh = AsyncMock()
            mock_meters.data = {
                "meters": [
                    {
                        "me_id": 101,
                        "mis_id": 1,
                        "me_name": "Meter 1",
                        "raw": {"me_serial": "me101"},
                    },
                ],
            }
            mock_meters_class.return_value = mock_meters
            
            # Mock meter counters coordinator
            mock_meter_counters = MagicMock(spec=CEMMeterCountersCoordinator)
            mock_meter_counters.async_config_entry_first_refresh = AsyncMock()
            mock_meter_counters.data = {
                "counters": [
                    {"var_id": 104437, "name": "Counter 1"},
                    {"var_id": 102496, "name": "Counter 2"},
                ],
                "raw_map": {
                    104437: {"var_id": 104437, "pot_id": 1},
                    102496: {"var_id": 102496, "pot_id": 1},
                },
            }
            mock_meter_counters_class.return_value = mock_meter_counters
            
            # Mock counter reading coordinator
            mock_counter = MagicMock(spec=CEMCounterReadingCoordinator)
            mock_counter.async_config_entry_first_refresh = AsyncMock()
            mock_counter_class.return_value = mock_counter
            
            # Mock cache
            mock_cache = MagicMock()
            mock_cache.load = AsyncMock(return_value=({}, {}, True))
            mock_cache.save = AsyncMock()
            mock_cache_class.return_value = mock_cache
            
            # Mock timer
            mock_track_interval.return_value = MagicMock()
            
            # Run setup
            result = await async_setup_entry(mock_hass, mock_entry)
            
            # Verify setup succeeded
            assert result is True
            
            # Verify coordinators were created
            mock_auth_class.assert_called_once()
            mock_userinfo_class.assert_called_once()
            mock_objects_class.assert_called_once()
            mock_meters_class.assert_called_once()
            
            # Verify coordinators were refreshed
            mock_auth.async_config_entry_first_refresh.assert_called_once()
            mock_userinfo.async_config_entry_first_refresh.assert_called_once()
            mock_objects.async_config_entry_first_refresh.assert_called_once()
            mock_meters.async_config_entry_first_refresh.assert_called_once()
            
            # Verify bag was created
            assert DOMAIN in mock_hass.data
            assert mock_entry.entry_id in mock_hass.data[DOMAIN]
            bag = mock_hass.data[DOMAIN][mock_entry.entry_id]
            assert "client" in bag
            assert "coordinator" in bag
            assert "userinfo" in bag
            assert "objects" in bag
            assert "meters" in bag
            
            # Verify service was registered
            assert mock_hass.services.async_register.called

    @pytest.mark.asyncio
    async def test_setup_creates_counter_coordinators_for_selected_var_ids(self, mock_hass, mock_entry, mock_auth_result):
        """Test that counter coordinators are created for selected var_ids."""
        with patch('custom_components.cem_monitor.async_get_clientsession') as mock_get_session, \
             patch('custom_components.cem_monitor.CEMClient') as mock_client_class, \
             patch('custom_components.cem_monitor.CEMAuthCoordinator') as mock_auth_class, \
             patch('custom_components.cem_monitor.CEMUserInfoCoordinator') as mock_userinfo_class, \
             patch('custom_components.cem_monitor.CEMObjectsCoordinator') as mock_objects_class, \
             patch('custom_components.cem_monitor.CEMMetersCoordinator') as mock_meters_class, \
             patch('custom_components.cem_monitor.CEMMeterCountersCoordinator') as mock_meter_counters_class, \
             patch('custom_components.cem_monitor.CEMCounterReadingCoordinator') as mock_counter_class, \
             patch('custom_components.cem_monitor.TypesCache') as mock_cache_class, \
             patch('custom_components.cem_monitor.async_track_time_interval') as mock_track_interval:
            
            # Setup mocks
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session
            mock_client = MagicMock(spec=CEMClient)
            mock_client_class.return_value = mock_client
            
            # Mock auth coordinator
            mock_auth = MagicMock(spec=CEMAuthCoordinator)
            mock_auth.token = "test_token"
            mock_auth._last_result = mock_auth_result
            mock_auth.async_config_entry_first_refresh = AsyncMock()
            mock_auth_class.return_value = mock_auth
            
            # Mock userinfo coordinator
            mock_userinfo = MagicMock(spec=CEMUserInfoCoordinator)
            mock_userinfo.async_config_entry_first_refresh = AsyncMock()
            mock_userinfo.data = {}
            mock_userinfo_class.return_value = mock_userinfo
            
            # Mock objects coordinator
            mock_objects = MagicMock(spec=CEMObjectsCoordinator)
            mock_objects.async_config_entry_first_refresh = AsyncMock()
            mock_objects.data = {"objects": [], "raw_by_mis": {}}
            mock_objects_class.return_value = mock_objects
            
            # Mock meters coordinator
            mock_meters = MagicMock(spec=CEMMetersCoordinator)
            mock_meters.async_config_entry_first_refresh = AsyncMock()
            mock_meters.data = {
                "meters": [
                    {
                        "me_id": 101,
                        "mis_id": 1,
                        "me_name": "Meter 1",
                        "raw": {"me_serial": "me101"},
                    },
                ],
            }
            mock_meters_class.return_value = mock_meters
            
            # Mock meter counters coordinator
            mock_meter_counters = MagicMock(spec=CEMMeterCountersCoordinator)
            mock_meter_counters.async_config_entry_first_refresh = AsyncMock()
            mock_meter_counters.data = {
                "counters": [
                    {"var_id": 104437, "name": "Counter 1", "pot_type": 1},
                    {"var_id": 102496, "name": "Counter 2", "pot_type": 1},
                    {"var_id": 102497, "name": "Counter 3", "pot_type": 1},  # Not selected
                ],
                "raw_map": {
                    104437: {"var_id": 104437, "pot_id": 1},
                    102496: {"var_id": 102496, "pot_id": 1},
                    102497: {"var_id": 102497, "pot_id": 1},
                },
            }
            mock_meter_counters_class.return_value = mock_meter_counters
            
            # Mock counter reading coordinator
            counter_instances = {}
            def counter_factory(*args, **kwargs):
                var_id = kwargs.get("var_id")
                if var_id not in counter_instances:
                    mock_counter = MagicMock(spec=CEMCounterReadingCoordinator)
                    mock_counter.async_config_entry_first_refresh = AsyncMock()
                    counter_instances[var_id] = mock_counter
                return counter_instances[var_id]
            mock_counter_class.side_effect = counter_factory
            
            # Mock cache
            mock_cache = MagicMock()
            mock_cache.load = AsyncMock(return_value=({}, {}, True))
            mock_cache_class.return_value = mock_cache
            
            # Mock timer
            mock_track_interval.return_value = MagicMock()
            
            # Run setup
            await async_setup_entry(mock_hass, mock_entry)
            
            # Verify counter coordinators were created only for selected var_ids
            assert mock_counter_class.call_count == 2  # Only for 104437 and 102496
            assert 104437 in counter_instances
            assert 102496 in counter_instances
            assert 102497 not in counter_instances  # Not selected
            
            # Verify bag contains counter_readings
            bag = mock_hass.data[DOMAIN][mock_entry.entry_id]
            assert "counter_readings" in bag
            assert len(bag["counter_readings"]) == 2

    @pytest.mark.asyncio
    async def test_service_registration(self, mock_hass, mock_entry, mock_auth_result):
        """Test that cem_monitor.get_raw service is registered."""
        with patch('custom_components.cem_monitor.async_get_clientsession') as mock_get_session, \
             patch('custom_components.cem_monitor.CEMClient') as mock_client_class, \
             patch('custom_components.cem_monitor.CEMAuthCoordinator') as mock_auth_class, \
             patch('custom_components.cem_monitor.CEMUserInfoCoordinator') as mock_userinfo_class, \
             patch('custom_components.cem_monitor.CEMObjectsCoordinator') as mock_objects_class, \
             patch('custom_components.cem_monitor.CEMMetersCoordinator') as mock_meters_class, \
             patch('custom_components.cem_monitor.CEMMeterCountersCoordinator') as mock_meter_counters_class, \
             patch('custom_components.cem_monitor.CEMCounterReadingCoordinator') as mock_counter_class, \
             patch('custom_components.cem_monitor.TypesCache') as mock_cache_class, \
             patch('custom_components.cem_monitor.async_track_time_interval') as mock_track_interval:
            
            # Setup mocks
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session
            mock_client = MagicMock(spec=CEMClient)
            mock_client_class.return_value = mock_client
            
            # Mock auth coordinator
            mock_auth = MagicMock(spec=CEMAuthCoordinator)
            mock_auth.token = "test_token"
            mock_auth._last_result = mock_auth_result
            mock_auth.async_config_entry_first_refresh = AsyncMock()
            mock_auth_class.return_value = mock_auth
            
            # Mock other coordinators
            mock_userinfo = MagicMock(spec=CEMUserInfoCoordinator)
            mock_userinfo.async_config_entry_first_refresh = AsyncMock()
            mock_userinfo.data = {}
            mock_userinfo_class.return_value = mock_userinfo
            
            mock_objects = MagicMock(spec=CEMObjectsCoordinator)
            mock_objects.async_config_entry_first_refresh = AsyncMock()
            mock_objects.data = {"objects": [], "raw_by_mis": {}}
            mock_objects_class.return_value = mock_objects
            
            mock_meters = MagicMock(spec=CEMMetersCoordinator)
            mock_meters.async_config_entry_first_refresh = AsyncMock()
            mock_meters.data = {"meters": []}
            mock_meters_class.return_value = mock_meters
            
            # Mock cache
            mock_cache = MagicMock()
            mock_cache.load = AsyncMock(return_value=({}, {}, True))
            mock_cache_class.return_value = mock_cache
            
            # Mock timer
            mock_track_interval.return_value = MagicMock()
            
            # Run setup
            await async_setup_entry(mock_hass, mock_entry)
            
            # Verify service was registered
            mock_hass.services.async_register.assert_called_once()
            call_args = mock_hass.services.async_register.call_args
            assert call_args[0][0] == DOMAIN
            assert call_args[0][1] == "get_raw"

    @pytest.mark.asyncio
    async def test_unload_flow(self, mock_hass, mock_entry):
        """Test unload flow cleans up resources."""
        # Setup bag with data
        bag = {
            "client": MagicMock(),
            "coordinator": MagicMock(),
            "counter_readings": {},
            "counter_refresh_unsub": MagicMock(),
        }
        mock_hass.data.setdefault(DOMAIN, {})[mock_entry.entry_id] = bag
        
        # Mock unsub function
        mock_unsub = MagicMock()
        bag["counter_refresh_unsub"] = mock_unsub
        
        # Run unload
        result = await async_unload_entry(mock_hass, mock_entry)
        
        # Verify unload succeeded
        assert result is True
        
        # Verify timer was unsubscribed
        mock_unsub.assert_called_once()
        
        # Verify bag was removed
        assert mock_entry.entry_id not in mock_hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_reload_entry(self, mock_hass, mock_entry):
        """Test reload entry triggers reload."""
        # Run reload
        await async_reload_entry(mock_hass, mock_entry)
        
        # Verify reload was called
        mock_hass.config_entries.async_reload.assert_called_once_with(mock_entry.entry_id)

    @pytest.mark.asyncio
    async def test_options_flow_update_triggers_reload(self, mock_hass, mock_entry):
        """Test that options flow update triggers reload."""
        # Setup bag
        bag = {
            "client": MagicMock(),
            "coordinator": MagicMock(),
            "counter_readings": {},
        }
        mock_hass.data.setdefault(DOMAIN, {})[mock_entry.entry_id] = bag
        
        # Get the update listener that was registered
        # This is set up in async_setup_entry via entry.add_update_listener
        update_listener = mock_entry.add_update_listener.return_value
        
        # Simulate options update
        await async_reload_entry(mock_hass, mock_entry)
        
        # Verify reload was called
        mock_hass.config_entries.async_reload.assert_called_once_with(mock_entry.entry_id)

    @pytest.mark.asyncio
    async def test_counter_refresh_timer_setup(self, mock_hass, mock_entry, mock_auth_result):
        """Test that counter refresh timer is set up with correct interval."""
        with patch('custom_components.cem_monitor.async_get_clientsession') as mock_get_session, \
             patch('custom_components.cem_monitor.CEMClient') as mock_client_class, \
             patch('custom_components.cem_monitor.CEMAuthCoordinator') as mock_auth_class, \
             patch('custom_components.cem_monitor.CEMUserInfoCoordinator') as mock_userinfo_class, \
             patch('custom_components.cem_monitor.CEMObjectsCoordinator') as mock_objects_class, \
             patch('custom_components.cem_monitor.CEMMetersCoordinator') as mock_meters_class, \
             patch('custom_components.cem_monitor.CEMMeterCountersCoordinator') as mock_meter_counters_class, \
             patch('custom_components.cem_monitor.CEMCounterReadingCoordinator') as mock_counter_class, \
             patch('custom_components.cem_monitor.TypesCache') as mock_cache_class, \
             patch('custom_components.cem_monitor.async_track_time_interval') as mock_track_interval:
            
            # Setup mocks
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session
            mock_client = MagicMock(spec=CEMClient)
            mock_client_class.return_value = mock_client
            
            # Mock auth coordinator
            mock_auth = MagicMock(spec=CEMAuthCoordinator)
            mock_auth.token = "test_token"
            mock_auth._last_result = mock_auth_result
            mock_auth.async_config_entry_first_refresh = AsyncMock()
            mock_auth_class.return_value = mock_auth
            
            # Mock other coordinators
            mock_userinfo = MagicMock(spec=CEMUserInfoCoordinator)
            mock_userinfo.async_config_entry_first_refresh = AsyncMock()
            mock_userinfo.data = {}
            mock_userinfo_class.return_value = mock_userinfo
            
            mock_objects = MagicMock(spec=CEMObjectsCoordinator)
            mock_objects.async_config_entry_first_refresh = AsyncMock()
            mock_objects.data = {"objects": [], "raw_by_mis": {}}
            mock_objects_class.return_value = mock_objects
            
            mock_meters = MagicMock(spec=CEMMetersCoordinator)
            mock_meters.async_config_entry_first_refresh = AsyncMock()
            mock_meters.data = {"meters": []}
            mock_meters_class.return_value = mock_meters
            
            # Mock cache
            mock_cache = MagicMock()
            mock_cache.load = AsyncMock(return_value=({}, {}, True))
            mock_cache_class.return_value = mock_cache
            
            # Mock timer
            mock_track_interval.return_value = MagicMock()
            
            # Run setup
            await async_setup_entry(mock_hass, mock_entry)
            
            # Verify timer was set up with correct interval (30 minutes from options)
            mock_track_interval.assert_called_once()
            call_args = mock_track_interval.call_args
            assert call_args[0][0] == mock_hass
            assert call_args[0][2] == timedelta(minutes=30)  # From mock_entry.options

