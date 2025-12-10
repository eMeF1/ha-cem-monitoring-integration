# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/eMeF1/ha-cem-monitoring-integration/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/eMeF1/ha-cem-monitoring-integration/compare/v0.6.4...v0.7.0
[0.6.4]: https://github.com/eMeF1/ha-cem-monitoring-integration/compare/v0.6.0...v0.6.4
[0.6.0]: https://github.com/eMeF1/ha-cem-monitoring-integration/releases/tag/v0.6.0

