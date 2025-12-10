# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.7.5] - 2025-12-11

### Fixed
- Improved cache refresh logic for `counter_value_types` with better empty-value detection
  - Enhanced logging shows exact state when forcing refresh (None, type, length)
  - More robust check handles edge cases correctly
- Fixed cache save logic to prevent saving empty `counter_value_types`
  - Only saves to cache if `counter_value_types` has valid data (length > 0)
  - Prevents empty mappings from being cached and reused

### Technical
- All 153 tests passing (34 API tests, improved coverage to 87%)

## [0.7.4] - 2025-12-10

### Fixed
- Enhanced cache refresh logic: now forces refresh if `counter_value_types` is empty
  - Handles stale cached data from previous bug where empty mappings were cached
  - Ensures fresh data is fetched even if cache appears valid but contains empty data

### Added
- Comprehensive unit tests with real API response data:
  - `TestGetPotTypes`: tests for `get_pot_types` with wrapped response format
  - `TestGetMeters`: tests for `get_meters` with real data structure
  - `TestGetCountersByMeter`: tests for `get_counters_by_meter` with filtering
  - `TestGetCountersForObject`: tests for `get_counters_for_object` with plain array
  - Updated `TestGetObjects` with real response showing empty names
  - Updated `TestGetCounterValueTypes` with full real API response structure
- Enhanced debug logging for `counter_value_types`:
  - Logs full mapping when built from API
  - Logs available keys when lookup fails
  - Logs loaded mapping from cache

### Technical
- API test coverage improved from 16% to 87%
- All 32 tests passing
- Tests now use real API response formats for better reliability

## [0.7.3] - 2025-12-10

### Fixed
- Fixed code formatting issues in test files to comply with ruff formatting rules

## [0.7.2] - 2025-12-10

### Fixed
- Fixed bug where `cik_nazev` (counter value type names) was not being retrieved from API endpoint id=11
  - The API returns a list of objects, but the code was incorrectly converting lists to empty dicts
  - Now properly handles list responses and extracts `cik_nazev` values correctly

### Added
- Added comprehensive unit tests for `get_counter_value_types` API method
  - Tests for list responses (actual API behavior)
  - Tests for dict responses (wrapped responses)
  - Tests for retry behavior and error handling
  - Improved API coverage from 16% to 56%

## [0.7.1] - 2025-12-10

### Fixed
- Fixed all linting errors (ruff)
- Fixed all type checking errors (mypy)
- Fixed code formatting issues
- Resolved CI/CD pipeline failures

### Technical
- All CI checks now passing (linting, formatting, type checking, tests)
- Improved type annotations for better code quality
- Code properly formatted with ruff

## [0.7.0] - 2025-12-10

### Changed
- **Repository structure reorganization** for better maintainability
  - Code organized into `coordinators/` and `utils/` subdirectories
  - Tests reorganized into `unit/`, `integration/`, and `coordinators/` subdirectories
- Added modern Python tooling (pyproject.toml, ruff, mypy, pre-commit hooks)
- Enhanced CI/CD with linting, type checking, and formatting checks
- Documentation moved to `docs/` directory

### Technical
- All coordinator classes moved to `coordinators/` subdirectory
- Utility modules (retry, discovery) moved to `utils/` subdirectory
- Improved code organization and maintainability
- No functional changes - this is a refactoring release

### Note
This release contains internal restructuring only. No breaking changes for end users.

## [0.6.4] - 2024-XX-XX

### Added
- Batch API support for counter readings
- Configurable update intervals for counter readings
- Caching for pot_types and counter_value_types with 7-day TTL
- Debug service `cem_monitor.get_raw` for inspecting API responses

### Changed
- Improved error handling with automatic token refresh on 401 errors
- Better handling of shared counters across meters

### Fixed
- SSL verification configuration
- Token refresh timing

## [0.6.0] - 2024-XX-XX

### Added
- Initial release
- Support for CEM account authentication
- Object, meter, and counter discovery
- Hierarchical counter selection during setup
- Sensor entities for counter readings
- Device structure for accounts and objects

[Unreleased]: https://github.com/eMeF1/ha-cem-monitoring-integration/compare/v0.7.5...HEAD
[0.7.5]: https://github.com/eMeF1/ha-cem-monitoring-integration/compare/v0.7.4...v0.7.5
[0.7.4]: https://github.com/eMeF1/ha-cem-monitoring-integration/compare/v0.7.3...v0.7.4
[0.7.3]: https://github.com/eMeF1/ha-cem-monitoring-integration/compare/v0.7.2...v0.7.3
[0.7.2]: https://github.com/eMeF1/ha-cem-monitoring-integration/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/eMeF1/ha-cem-monitoring-integration/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/eMeF1/ha-cem-monitoring-integration/compare/v0.6.4...v0.7.0
[0.6.4]: https://github.com/eMeF1/ha-cem-monitoring-integration/compare/v0.6.0...v0.6.4
[0.6.0]: https://github.com/eMeF1/ha-cem-monitoring-integration/releases/tag/v0.6.0

