"""Tests for config flow edge cases."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import ClientResponseError

# conftest.py handles path setup and Home Assistant mocking
from custom_components.cem_monitor.config_flow import CEMConfigFlow, CEMOptionsFlow, _fetch_objects_tree
from custom_components.cem_monitor.api import CEMClient, AuthResult
from custom_components.cem_monitor.const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_VAR_IDS,
    CONF_COUNTER_UPDATE_INTERVAL_MINUTES,
    MIN_COUNTER_UPDATE_INTERVAL_MINUTES,
    MAX_COUNTER_UPDATE_INTERVAL_MINUTES,
    DEFAULT_COUNTER_UPDATE_INTERVAL_MINUTES,
)


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.data = {}
    hass.config_entries = MagicMock()
    hass.config_entries.flow = MagicMock()
    return hass


@pytest.fixture
def mock_entry():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.data = {CONF_USERNAME: "test_user", CONF_PASSWORD: "test_pass"}
    entry.options = {}
    entry.entry_id = "test_entry_id"
    return entry


@pytest.fixture
def mock_client():
    """Create a mock CEMClient."""
    client = MagicMock(spec=CEMClient)
    return client


@pytest.fixture
def mock_auth_result():
    """Create a mock AuthResult."""
    return AuthResult(
        access_token="test_token",
        valid_to_ms=1234567890000,
        cookie_value="test_cookie",
    )


class TestCEMConfigFlow:
    """Test CEMConfigFlow edge cases."""

    @pytest.mark.asyncio
    async def test_empty_counter_selection(self, mock_hass, mock_auth_result):
        """Test that selecting no counters shows error."""
        flow = CEMConfigFlow()
        flow.hass = mock_hass
        flow.flow_id = "test_flow_id"
        
        # Setup flow data
        flow_data_key = f"{DOMAIN}_flow_{flow.flow_id}"
        mock_hass.data.setdefault(DOMAIN, {})[flow_data_key] = {
            CONF_USERNAME: "test_user",
            CONF_PASSWORD: "test_pass",
            "auth_result": mock_auth_result,
            "client": MagicMock(),
        }
        
        # Mock _fetch_objects_tree to return some counters
        with patch('custom_components.cem_monitor.config_flow._fetch_objects_tree', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {
                1: {
                    "mis_name": "Object 1",
                    "meters": {
                        101: {
                            "me_serial": "me101",
                            "lt_key": "water",
                            "counters": {
                                1001: {"name": "Counter 1"},
                            },
                        },
                    },
                },
            }
            
            # Try to submit with empty selection
            result = await flow.async_step_select_counters(user_input={"selected_counters": []})
            
            # Should show form with error
            assert result["type"] == "form"
            assert result["step_id"] == "select_counters"
            assert result["errors"]["base"] == "no_counters_selected"

    @pytest.mark.asyncio
    async def test_invalid_counter_selection(self, mock_hass, mock_auth_result):
        """Test that invalid counter selection shows error."""
        flow = CEMConfigFlow()
        flow.hass = mock_hass
        flow.flow_id = "test_flow_id"
        
        # Setup flow data
        flow_data_key = f"{DOMAIN}_flow_{flow.flow_id}"
        mock_hass.data.setdefault(DOMAIN, {})[flow_data_key] = {
            CONF_USERNAME: "test_user",
            CONF_PASSWORD: "test_pass",
            "auth_result": mock_auth_result,
            "client": MagicMock(),
        }
        
        # Mock _fetch_objects_tree
        with patch('custom_components.cem_monitor.config_flow._fetch_objects_tree', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {
                1: {
                    "mis_name": "Object 1",
                    "meters": {
                        101: {
                            "me_serial": "me101",
                            "lt_key": "water",
                            "counters": {
                                1001: {"name": "Counter 1"},
                            },
                        },
                    },
                },
            }
            
            # Try to submit with invalid selection (non-integer string)
            result = await flow.async_step_select_counters(user_input={"selected_counters": ["invalid"]})
            
            # Should show form with error
            assert result["type"] == "form"
            assert result["step_id"] == "select_counters"
            assert result["errors"]["base"] == "invalid_counter_selection"

    @pytest.mark.asyncio
    async def test_missing_flow_data(self, mock_hass):
        """Test that missing flow data aborts the flow."""
        flow = CEMConfigFlow()
        flow.hass = mock_hass
        flow.flow_id = "test_flow_id"
        
        # Don't setup flow data - it should be missing
        
        result = await flow.async_step_select_counters()
        
        # Should abort
        assert result["type"] == "abort"
        assert result["reason"] == "no_flow_data"

    @pytest.mark.asyncio
    async def test_tree_fetch_failure(self, mock_hass, mock_auth_result):
        """Test error handling when object tree fetch fails."""
        flow = CEMConfigFlow()
        flow.hass = mock_hass
        flow.flow_id = "test_flow_id"
        
        # Setup flow data
        flow_data_key = f"{DOMAIN}_flow_{flow.flow_id}"
        mock_hass.data.setdefault(DOMAIN, {})[flow_data_key] = {
            CONF_USERNAME: "test_user",
            CONF_PASSWORD: "test_pass",
            "auth_result": mock_auth_result,
            "client": MagicMock(),
        }
        
        # Mock _fetch_objects_tree to raise exception
        with patch('custom_components.cem_monitor.config_flow._fetch_objects_tree', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = Exception("Fetch failed")
            
            result = await flow.async_step_select_counters()
            
            # Should show form with error
            assert result["type"] == "form"
            assert result["step_id"] == "select_counters"
            assert result["errors"]["base"] == "fetch_failed"

    @pytest.mark.asyncio
    async def test_no_counters_available(self, mock_hass, mock_auth_result):
        """Test error when no counters are available."""
        flow = CEMConfigFlow()
        flow.hass = mock_hass
        flow.flow_id = "test_flow_id"
        
        # Setup flow data
        flow_data_key = f"{DOMAIN}_flow_{flow.flow_id}"
        mock_hass.data.setdefault(DOMAIN, {})[flow_data_key] = {
            CONF_USERNAME: "test_user",
            CONF_PASSWORD: "test_pass",
            "auth_result": mock_auth_result,
            "client": MagicMock(),
        }
        
        # Mock _fetch_objects_tree to return empty tree
        with patch('custom_components.cem_monitor.config_flow._fetch_objects_tree', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {}
            
            result = await flow.async_step_select_counters()
            
            # Should show form with error
            assert result["type"] == "form"
            assert result["step_id"] == "select_counters"
            assert result["errors"]["base"] == "no_counters_available"


class TestCEMOptionsFlow:
    """Test CEMOptionsFlow edge cases."""

    @pytest.mark.asyncio
    async def test_invalid_interval_below_minimum(self, mock_hass, mock_entry, mock_auth_result):
        """Test that interval below minimum shows error."""
        flow = CEMOptionsFlow(mock_entry)
        flow.hass = mock_hass
        
        # Mock authentication and tree fetch
        with patch('custom_components.cem_monitor.config_flow._create_session') as mock_create_session, \
             patch('custom_components.cem_monitor.config_flow.CEMClient') as mock_client_class, \
             patch('custom_components.cem_monitor.config_flow._fetch_objects_tree', new_callable=AsyncMock) as mock_fetch:
            
            mock_session = MagicMock()
            mock_create_session.return_value = mock_session
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.authenticate = AsyncMock(return_value=mock_auth_result)
            mock_fetch.return_value = {
                1: {
                    "mis_name": "Object 1",
                    "meters": {
                        101: {
                            "me_serial": "me101",
                            "lt_key": "water",
                            "counters": {
                                1001: {"name": "Counter 1"},
                            },
                        },
                    },
                },
            }
            
            # First call to show form
            result = await flow.async_step_init()
            assert result["type"] == "form"
            
            # Try to submit with interval below minimum
            result = await flow.async_step_init(user_input={
                "selected_counters": [],
                CONF_COUNTER_UPDATE_INTERVAL_MINUTES: MIN_COUNTER_UPDATE_INTERVAL_MINUTES - 1,
            })
            
            # Should show form with error
            assert result["type"] == "form"
            assert result["step_id"] == "init"
            assert CONF_COUNTER_UPDATE_INTERVAL_MINUTES in result["errors"]
            assert result["errors"][CONF_COUNTER_UPDATE_INTERVAL_MINUTES] == "interval_range"

    @pytest.mark.asyncio
    async def test_invalid_interval_above_maximum(self, mock_hass, mock_entry, mock_auth_result):
        """Test that interval above maximum shows error."""
        flow = CEMOptionsFlow(mock_entry)
        flow.hass = mock_hass
        
        # Mock authentication and tree fetch
        with patch('custom_components.cem_monitor.config_flow._create_session') as mock_create_session, \
             patch('custom_components.cem_monitor.config_flow.CEMClient') as mock_client_class, \
             patch('custom_components.cem_monitor.config_flow._fetch_objects_tree', new_callable=AsyncMock) as mock_fetch:
            
            mock_session = MagicMock()
            mock_create_session.return_value = mock_session
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.authenticate = AsyncMock(return_value=mock_auth_result)
            mock_fetch.return_value = {
                1: {
                    "mis_name": "Object 1",
                    "meters": {
                        101: {
                            "me_serial": "me101",
                            "lt_key": "water",
                            "counters": {
                                1001: {"name": "Counter 1"},
                            },
                        },
                    },
                },
            }
            
            # First call to show form
            result = await flow.async_step_init()
            assert result["type"] == "form"
            
            # Try to submit with interval above maximum
            result = await flow.async_step_init(user_input={
                "selected_counters": [],
                CONF_COUNTER_UPDATE_INTERVAL_MINUTES: MAX_COUNTER_UPDATE_INTERVAL_MINUTES + 1,
            })
            
            # Should show form with error
            assert result["type"] == "form"
            assert result["step_id"] == "init"
            assert CONF_COUNTER_UPDATE_INTERVAL_MINUTES in result["errors"]
            assert result["errors"][CONF_COUNTER_UPDATE_INTERVAL_MINUTES] == "interval_range"

    @pytest.mark.asyncio
    async def test_invalid_interval_non_integer(self, mock_hass, mock_entry, mock_auth_result):
        """Test that non-integer interval shows error."""
        flow = CEMOptionsFlow(mock_entry)
        flow.hass = mock_hass
        
        # Mock authentication and tree fetch
        with patch('custom_components.cem_monitor.config_flow._create_session') as mock_create_session, \
             patch('custom_components.cem_monitor.config_flow.CEMClient') as mock_client_class, \
             patch('custom_components.cem_monitor.config_flow._fetch_objects_tree', new_callable=AsyncMock) as mock_fetch:
            
            mock_session = MagicMock()
            mock_create_session.return_value = mock_session
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.authenticate = AsyncMock(return_value=mock_auth_result)
            mock_fetch.return_value = {
                1: {
                    "mis_name": "Object 1",
                    "meters": {
                        101: {
                            "me_serial": "me101",
                            "lt_key": "water",
                            "counters": {
                                1001: {"name": "Counter 1"},
                            },
                        },
                    },
                },
            }
            
            # First call to show form
            result = await flow.async_step_init()
            assert result["type"] == "form"
            
            # Try to submit with non-integer interval
            result = await flow.async_step_init(user_input={
                "selected_counters": [],
                CONF_COUNTER_UPDATE_INTERVAL_MINUTES: "not_a_number",
            })
            
            # Should show form with error
            assert result["type"] == "form"
            assert result["step_id"] == "init"
            assert CONF_COUNTER_UPDATE_INTERVAL_MINUTES in result["errors"]
            assert result["errors"][CONF_COUNTER_UPDATE_INTERVAL_MINUTES] == "invalid_interval"

    @pytest.mark.asyncio
    async def test_invalid_interval_none(self, mock_hass, mock_entry, mock_auth_result):
        """Test that None interval is handled."""
        flow = CEMOptionsFlow(mock_entry)
        flow.hass = mock_hass
        
        # Mock authentication and tree fetch
        with patch('custom_components.cem_monitor.config_flow._create_session') as mock_create_session, \
             patch('custom_components.cem_monitor.config_flow.CEMClient') as mock_client_class, \
             patch('custom_components.cem_monitor.config_flow._fetch_objects_tree', new_callable=AsyncMock) as mock_fetch:
            
            mock_session = MagicMock()
            mock_create_session.return_value = mock_session
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.authenticate = AsyncMock(return_value=mock_auth_result)
            mock_fetch.return_value = {
                1: {
                    "mis_name": "Object 1",
                    "meters": {
                        101: {
                            "me_serial": "me101",
                            "lt_key": "water",
                            "counters": {
                                1001: {"name": "Counter 1"},
                            },
                        },
                    },
                },
            }
            
            # First call to show form
            result = await flow.async_step_init()
            assert result["type"] == "form"
            
            # Try to submit with None interval (should use default)
            result = await flow.async_step_init(user_input={
                "selected_counters": [],
                CONF_COUNTER_UPDATE_INTERVAL_MINUTES: None,
            })
            
            # Should succeed and use default
            assert result["type"] == "create_entry"
            assert result["data"][CONF_COUNTER_UPDATE_INTERVAL_MINUTES] == DEFAULT_COUNTER_UPDATE_INTERVAL_MINUTES

    @pytest.mark.asyncio
    async def test_auth_failure_401_during_options_flow(self, mock_hass, mock_entry, mock_auth_result):
        """Test 401 error during options flow authentication."""
        flow = CEMOptionsFlow(mock_entry)
        flow.hass = mock_hass
        
        # Mock authentication failure
        with patch('custom_components.cem_monitor.config_flow._create_session') as mock_create_session, \
             patch('custom_components.cem_monitor.config_flow.CEMClient') as mock_client_class:
            
            mock_session = MagicMock()
            mock_create_session.return_value = mock_session
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            from aiohttp import RequestInfo
            request_info = RequestInfo(url="http://test.com", method="POST", headers={}, real_url="http://test.com")
            mock_client.authenticate = AsyncMock(
                side_effect=ClientResponseError(request_info, None, status=401)
            )
            
            result = await flow.async_step_init()
            
            # Should show form with error
            assert result["type"] == "form"
            assert result["step_id"] == "init"
            assert result["errors"]["base"] == "invalid_auth"

    @pytest.mark.asyncio
    async def test_auth_failure_403_during_options_flow(self, mock_hass, mock_entry, mock_auth_result):
        """Test 403 error during options flow authentication."""
        flow = CEMOptionsFlow(mock_entry)
        flow.hass = mock_hass
        
        # Mock authentication failure
        with patch('custom_components.cem_monitor.config_flow._create_session') as mock_create_session, \
             patch('custom_components.cem_monitor.config_flow.CEMClient') as mock_client_class:
            
            mock_session = MagicMock()
            mock_create_session.return_value = mock_session
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            from aiohttp import RequestInfo
            request_info = RequestInfo(url="http://test.com", method="POST", headers={}, real_url="http://test.com")
            mock_client.authenticate = AsyncMock(
                side_effect=ClientResponseError(request_info, None, status=403)
            )
            
            result = await flow.async_step_init()
            
            # Should show form with error
            assert result["type"] == "form"
            assert result["step_id"] == "init"
            assert result["errors"]["base"] == "invalid_auth"

    @pytest.mark.asyncio
    async def test_missing_credentials_during_options_flow(self, mock_hass):
        """Test missing credentials during options flow."""
        entry = MagicMock()
        entry.data = {}  # No credentials
        entry.options = {}
        entry.entry_id = "test_entry_id"
        
        flow = CEMOptionsFlow(entry)
        flow.hass = mock_hass
        
        result = await flow.async_step_init()
        
        # Should show form with error
        assert result["type"] == "form"
        assert result["step_id"] == "init"
        assert result["errors"]["base"] == "missing_credentials"

    @pytest.mark.asyncio
    async def test_tree_fetch_failure_during_options_flow(self, mock_hass, mock_entry, mock_auth_result):
        """Test tree fetch failure during options flow."""
        flow = CEMOptionsFlow(mock_entry)
        flow.hass = mock_hass
        
        # Mock authentication success but tree fetch failure
        with patch('custom_components.cem_monitor.config_flow._create_session') as mock_create_session, \
             patch('custom_components.cem_monitor.config_flow.CEMClient') as mock_client_class, \
             patch('custom_components.cem_monitor.config_flow._fetch_objects_tree', new_callable=AsyncMock) as mock_fetch:
            
            mock_session = MagicMock()
            mock_create_session.return_value = mock_session
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.authenticate = AsyncMock(return_value=mock_auth_result)
            mock_fetch.side_effect = Exception("Tree fetch failed")
            
            result = await flow.async_step_init()
            
            # Should show form with error
            assert result["type"] == "form"
            assert result["step_id"] == "init"
            assert result["errors"]["base"] == "fetch_failed"

    @pytest.mark.asyncio
    async def test_invalid_counter_selection_during_options_flow(self, mock_hass, mock_entry, mock_auth_result):
        """Test invalid counter selection during options flow."""
        flow = CEMOptionsFlow(mock_entry)
        flow.hass = mock_hass
        
        # Mock authentication and tree fetch
        with patch('custom_components.cem_monitor.config_flow._create_session') as mock_create_session, \
             patch('custom_components.cem_monitor.config_flow.CEMClient') as mock_client_class, \
             patch('custom_components.cem_monitor.config_flow._fetch_objects_tree', new_callable=AsyncMock) as mock_fetch:
            
            mock_session = MagicMock()
            mock_create_session.return_value = mock_session
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.authenticate = AsyncMock(return_value=mock_auth_result)
            mock_fetch.return_value = {
                1: {
                    "mis_name": "Object 1",
                    "meters": {
                        101: {
                            "me_serial": "me101",
                            "lt_key": "water",
                            "counters": {
                                1001: {"name": "Counter 1"},
                            },
                        },
                    },
                },
            }
            
            # First call to show form
            result = await flow.async_step_init()
            assert result["type"] == "form"
            
            # Try to submit with invalid counter selection
            result = await flow.async_step_init(user_input={
                "selected_counters": ["invalid"],
                CONF_COUNTER_UPDATE_INTERVAL_MINUTES: 30,
            })
            
            # Should show form with error
            assert result["type"] == "form"
            assert result["step_id"] == "init"
            assert result["errors"]["base"] == "invalid_counter_selection"

