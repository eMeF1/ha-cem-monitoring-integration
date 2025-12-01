Release v0.6.0

Major feature release with improved configuration flow and new capabilities.

✨ **New Features**

- Hierarchical counter selection during setup - Choose which counters to expose with an intuitive UI showing objects → meters → counters
- Configurable update intervals - Control how often counter readings are refreshed (default: 30 minutes, range: 1-1440 minutes)
- Options flow for reconfiguration - Change counter selection and update intervals after initial setup without removing the integration
- Debug service (get_raw) - New service for inspecting raw CEM API responses to help with troubleshooting

🔧 **Improvements**

- Enhanced config flow with better user experience for counter selection
- Automatic integration reload when options are changed
- Improved object name resolution using parent hierarchy
- Better counter type filtering - Excludes state counters like door/contact sensors
- Comprehensive unit test coverage for all coordinator classes
- Code cleanup - Removed unused coordinator classes

🐛 **Bug Fixes**

- Fixed Python 3.9 and 3.11 compatibility issues in tests
- Improved error handling across coordinators

📚 **Documentation**

- Updated README with comprehensive documentation of all new features
- Added Services section documenting the get_raw service
- Enhanced troubleshooting section with counter selection and update interval tips
