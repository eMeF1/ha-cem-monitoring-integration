# Development Guide

This guide will help you set up a development environment for the CEM Monitoring Integration.

## Prerequisites

- Python 3.9 or higher
- Home Assistant (for testing)
- Git

## Setup

### 1. Clone the Repository

```bash
git clone https://github.com/eMeF1/ha-cem-monitoring-integration.git
cd ha-cem-monitoring-integration
```

### 2. Install Development Dependencies

```bash
pip install -r requirements-test.txt
```

Or using the project's optional dependencies:

```bash
pip install -e ".[test]"
```

### 3. Install Pre-commit Hooks (Optional but Recommended)

```bash
pip install pre-commit
pre-commit install
```

This will automatically run linting and formatting checks before each commit.

## Development Workflow

### Running Tests

Run all tests:

```bash
pytest
```

Run tests with coverage:

```bash
pytest --cov=custom_components.cem_monitor --cov-report=html
```

Run specific test file:

```bash
pytest tests/unit/test_api.py
```

### Code Quality Checks

#### Linting

Check code with ruff:

```bash
ruff check custom_components tests
```

Auto-fix issues:

```bash
ruff check --fix custom_components tests
```

#### Formatting

Check formatting:

```bash
ruff format --check custom_components tests
```

Format code:

```bash
ruff format custom_components tests
```

#### Type Checking

Run mypy:

```bash
mypy custom_components
```

### Testing in Home Assistant

1. Copy the `custom_components/cem_monitor` directory to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Configure the integration through the UI

For development, you can use a symlink:

```bash
ln -s /path/to/repo/custom_components/cem_monitor /path/to/homeassistant/config/custom_components/cem_monitor
```

## Project Structure

```
custom_components/cem_monitor/
├── __init__.py              # Integration setup
├── api.py                   # CEM API client
├── cache.py                 # Caching logic
├── config_flow.py           # Configuration UI
├── const.py                 # Constants
├── sensor.py                # Sensor entities
├── coordinators/            # Coordinator classes
│   ├── base.py              # Base coordinator
│   ├── userinfo.py          # User info coordinator
│   ├── objects.py           # Objects coordinator
│   ├── meters.py            # Meters coordinator
│   ├── meter_counters.py    # Meter counters coordinator
│   └── counter_reading.py   # Counter reading coordinator
└── utils/                   # Utility modules
    ├── discovery.py         # Discovery utilities
    └── retry.py             # Retry logic

tests/
├── unit/                    # Unit tests
├── integration/             # Integration tests
└── coordinators/            # Coordinator tests
```

## Code Style

- Follow PEP 8 style guide
- Use type hints for all function signatures
- Maximum line length: 100 characters
- Use `ruff` for linting and formatting
- Use `mypy` for type checking

## Adding New Features

1. Create a feature branch from `main`
2. Make your changes
3. Add tests for new functionality
4. Ensure all tests pass
5. Run linting and type checking
6. Update documentation if needed
7. Submit a pull request

## Debugging

### Enable Debug Logging

Add to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.cem_monitor: debug
```

### Using the Debug Service

The integration provides a `cem_monitor.get_raw` service for debugging API calls:

```yaml
service: cem_monitor.get_raw
data:
  endpoint: counter_last
  var_id: 104437
```

Listen for the response event:

```yaml
event: cem_monitor_raw_response
```

## Common Issues

### Import Errors After Reorganization

If you encounter import errors after code reorganization, ensure all imports are updated to reflect the new structure:

- Coordinators: `from .coordinators.base import CEMBaseCoordinator`
- Utils: `from .utils.retry import is_401_error`

### Test Failures

If tests fail after reorganization:

1. Check that test imports match the new structure
2. Ensure `conftest.py` is in the correct location
3. Verify `pytest.ini` testpaths are correct

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution guidelines.

## Resources

- [Home Assistant Developer Documentation](https://developers.home-assistant.io/)
- [Home Assistant Integration Architecture](https://developers.home-assistant.io/docs/architecture_index/)
- [CEM API Documentation](https://cemapi.unimonitor.eu/)

