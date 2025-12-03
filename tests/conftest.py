"""Pytest configuration and fixtures for CEM Monitor tests."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Mock Home Assistant modules BEFORE importing any custom components
# This prevents ModuleNotFoundError when custom components try to import HA

# Create mock modules
homeassistant_mock = MagicMock()
homeassistant_core_mock = MagicMock()
homeassistant_helpers_mock = MagicMock()
homeassistant_config_entries_mock = MagicMock()
homeassistant_update_coordinator_mock = MagicMock()
homeassistant_aiohttp_client_mock = MagicMock()
homeassistant_event_mock = MagicMock()

# Set up the module structure
sys.modules['homeassistant'] = homeassistant_mock
# Create a mock HomeAssistant class
class MockHomeAssistant:
    """Mock HomeAssistant class."""
    pass

sys.modules['homeassistant.core'] = homeassistant_core_mock
sys.modules['homeassistant.core'].HomeAssistant = MockHomeAssistant
sys.modules['homeassistant.helpers'] = homeassistant_helpers_mock
# Create a mock class that supports subscriptable type hints
class MockDataUpdateCoordinator:
    """Mock DataUpdateCoordinator that supports type hints."""
    def __init__(self, *args, **kwargs):
        pass
    def __class_getitem__(cls, item):
        # Support DataUpdateCoordinator[dict[str, Any]] syntax
        return cls

sys.modules['homeassistant.helpers.update_coordinator'] = homeassistant_update_coordinator_mock
sys.modules['homeassistant.helpers.update_coordinator'].DataUpdateCoordinator = MockDataUpdateCoordinator
sys.modules['homeassistant.helpers.update_coordinator'].UpdateFailed = Exception
sys.modules['homeassistant.helpers.aiohttp_client'] = homeassistant_aiohttp_client_mock
sys.modules['homeassistant.helpers.aiohttp_client'].async_get_clientsession = MagicMock
sys.modules['homeassistant.helpers.event'] = homeassistant_event_mock
sys.modules['homeassistant.helpers.event'].async_track_time_interval = MagicMock
sys.modules['homeassistant.helpers.event'].async_call_later = MagicMock
sys.modules['homeassistant.config_entries'] = homeassistant_config_entries_mock
sys.modules['homeassistant.config_entries'].ConfigEntry = MagicMock
sys.modules['homeassistant.config_entries'].ConfigFlow = MagicMock
sys.modules['homeassistant.config_entries'].OptionsFlow = MagicMock
sys.modules['homeassistant.data_entry_flow'] = MagicMock()
sys.modules['homeassistant.data_entry_flow'].FlowResult = dict
sys.modules['homeassistant.components.sensor'] = MagicMock()
sys.modules['homeassistant.components.sensor'].SensorEntity = MagicMock
sys.modules['homeassistant.components.sensor'].SensorDeviceClass = MagicMock
sys.modules['homeassistant.components.sensor'].SensorStateClass = MagicMock
sys.modules['homeassistant.const'] = MagicMock()
sys.modules['homeassistant.const'].EntityCategory = MagicMock()
sys.modules['homeassistant.const'].UnitOfVolume = MagicMock()
sys.modules['homeassistant.const'].Platform = MagicMock()
sys.modules['homeassistant.helpers.entity'] = MagicMock()
sys.modules['homeassistant.helpers.entity'].DeviceInfo = dict
sys.modules['homeassistant.helpers'] = MagicMock()
sys.modules['homeassistant.helpers'].device_registry = MagicMock()
sys.modules['homeassistant.helpers.device_registry'] = MagicMock()
sys.modules['homeassistant.helpers.device_registry'].async_get = MagicMock()
sys.modules['homeassistant.helpers.config_validation'] = MagicMock()
sys.modules['homeassistant.helpers.config_validation'].cv = MagicMock()

# Mock Store helper for caching
homeassistant_helpers_storage_mock = MagicMock()

# Create a mock Store class that supports async methods and type hints
class MockStore:
    """Mock Store class for testing."""
    def __init__(self, hass, version, key):
        self.hass = hass
        self.version = version
        self.key = key
        self._data = None
    
    async def async_load(self):
        return self._data
    
    async def async_save(self, data):
        self._data = data
    
    async def async_remove(self):
        self._data = None
    
    def __class_getitem__(cls, item):
        # Support Store[dict[str, Any]] syntax
        return cls

sys.modules['homeassistant.helpers.storage'] = homeassistant_helpers_storage_mock
sys.modules['homeassistant.helpers.storage'].Store = MockStore

# Add custom_components to path
sys.path.insert(0, str(Path(__file__).parent.parent))

