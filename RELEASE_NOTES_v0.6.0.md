Release v0.6.0

Major feature release with improved configuration flow and new capabilities:

- Hierarchical counter selection during setup with intuitive UI showing objects → meters → counters
- Configurable update intervals for counter readings (default: 30 minutes, range: 1-1440 minutes)
- Options flow for reconfiguring counter selection and update intervals after initial setup
- New get_raw service for debugging and inspecting raw CEM API responses
- Enhanced config flow with better user experience
- Automatic integration reload when options are changed
- Improved object name resolution using parent hierarchy
- Better counter type filtering (excludes state counters like door/contact sensors)
- Comprehensive unit test coverage for all coordinator classes
- Code cleanup: removed unused coordinator classes
- Fixed Python 3.9 and 3.11 compatibility issues in tests
- Updated README with comprehensive documentation of all new features
