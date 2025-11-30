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
sys.modules['homeassistant.core'] = homeassistant_core_mock
sys.modules['homeassistant.core'].HomeAssistant = MagicMock
sys.modules['homeassistant.helpers'] = homeassistant_helpers_mock
sys.modules['homeassistant.helpers.update_coordinator'] = homeassistant_update_coordinator_mock
sys.modules['homeassistant.helpers.update_coordinator'].DataUpdateCoordinator = MagicMock
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

# Add custom_components to path
sys.path.insert(0, str(Path(__file__).parent.parent))

