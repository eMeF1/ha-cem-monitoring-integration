"""Pytest configuration and fixtures for CEM Monitor tests."""
import sys
from pathlib import Path
from types import ModuleType
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
# Mock callback decorator (used by config_flow)
def mock_callback(func):
    """Mock callback decorator - just returns the function unchanged."""
    return func
sys.modules['homeassistant.core'].callback = mock_callback
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
# Create proper base classes for ConfigFlow and OptionsFlow
class MockConfigFlow:
    """Mock ConfigFlow base class."""
    def __init__(self, *args, **kwargs):
        self.hass = None
        self.flow_id = None
        self._current_entries = []
    
    def _async_current_entries(self):
        """Return current entries."""
        return iter(self._current_entries)
    
    def async_set_unique_id(self, unique_id):
        pass
    
    def _abort_if_unique_id_configured(self):
        pass
    
    def async_show_form(self, step_id, data_schema=None, errors=None):
        return {"type": "form", "step_id": step_id, "errors": errors or {}}
    
    def async_create_entry(self, title, data, options=None):
        return {"type": "create_entry", "title": title, "data": data, "options": options or {}}
    
    def async_abort(self, reason):
        return {"type": "abort", "reason": reason}

class MockOptionsFlow:
    """Mock OptionsFlow base class."""
    def __init__(self, entry):
        self._entry = entry
    
    def async_show_form(self, step_id, data_schema=None, errors=None):
        return {"type": "form", "step_id": step_id, "errors": errors or {}}
    
    def async_create_entry(self, title, data):
        return {"type": "create_entry", "title": title, "data": data}

sys.modules['homeassistant.config_entries'] = homeassistant_config_entries_mock
sys.modules['homeassistant.config_entries'].ConfigEntry = MagicMock
sys.modules['homeassistant.config_entries'].ConfigFlow = MockConfigFlow
sys.modules['homeassistant.config_entries'].OptionsFlow = MockOptionsFlow
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
# Mock config_validation with cv.multi_select
config_validation_mock = MagicMock()
multi_select_mock = MagicMock()
config_validation_mock.multi_select = multi_select_mock
sys.modules['homeassistant.helpers.config_validation'] = config_validation_mock
sys.modules['homeassistant.helpers.config_validation'].cv = config_validation_mock

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

# Mock voluptuous (used by config_flow)
# Create a proper module-like object
class VoluptuousModule(ModuleType):
    """Mock voluptuous module."""
    pass

voluptuous_module = VoluptuousModule('voluptuous')

# Create mock Schema class that can be instantiated and called
class MockSchema:
    def __init__(self, schema_dict=None):
        self._schema = schema_dict or {}
    def __call__(self, data=None):
        return data or {}
    def __getitem__(self, key):
        return self._schema.get(key)

# Create mock decorators/functions
class MockRequired:
    def __init__(self, *args, **kwargs):
        pass

class MockOptional:
    def __init__(self, *args, **kwargs):
        pass

class MockAll:
    def __init__(self, *args, **kwargs):
        pass

class MockLength:
    def __init__(self, *args, **kwargs):
        pass

class MockCoerce:
    def __init__(self, *args, **kwargs):
        pass

class MockRange:
    def __init__(self, *args, **kwargs):
        pass

voluptuous_module.Schema = MockSchema
voluptuous_module.Required = MockRequired
voluptuous_module.Optional = MockOptional
voluptuous_module.All = MockAll
voluptuous_module.Length = MockLength
voluptuous_module.Coerce = MockCoerce
voluptuous_module.Range = MockRange

sys.modules['voluptuous'] = voluptuous_module

# Mock aiohttp (used by config_flow and api)
aiohttp_module = ModuleType('aiohttp')

# Create proper exception classes for aiohttp
class MockClientResponseError(Exception):
    def __init__(self, request_info=None, history=None, status=None, **kwargs):
        self.request_info = request_info
        self.history = history
        self.status = status
        super().__init__(**kwargs)

class MockRequestInfo:
    def __init__(self, url=None, method=None, headers=None, real_url=None):
        self.url = url
        self.method = method
        self.headers = headers or {}
        self.real_url = real_url or url

class MockClientConnectorError(Exception):
    pass

class MockServerTimeoutError(Exception):
    pass

class MockClientError(Exception):
    pass

class MockClientTimeout:
    """Mock ClientTimeout class."""
    def __init__(self, *args, **kwargs):
        pass

# Add all classes to aiohttp module (can be imported directly from aiohttp)
aiohttp_module.ClientResponseError = MockClientResponseError
aiohttp_module.RequestInfo = MockRequestInfo
aiohttp_module.ClientSession = MagicMock()
aiohttp_module.ClientTimeout = MockClientTimeout
aiohttp_module.ClientError = MockClientError
aiohttp_module.ClientConnectorError = MockClientConnectorError
aiohttp_module.ServerTimeoutError = MockServerTimeoutError

# Mock client_exceptions submodule
client_exceptions_module = ModuleType('aiohttp.client_exceptions')
client_exceptions_module.ClientConnectorError = MockClientConnectorError
client_exceptions_module.ServerTimeoutError = MockServerTimeoutError
client_exceptions_module.ClientError = MockClientError

aiohttp_module.client_exceptions = client_exceptions_module

sys.modules['aiohttp'] = aiohttp_module
sys.modules['aiohttp.client_exceptions'] = client_exceptions_module

# Add custom_components to path
sys.path.insert(0, str(Path(__file__).parent.parent))

