# Contributing to CEM Monitoring Integration

Thank you for your interest in contributing to the CEM Monitoring Integration! This document provides guidelines and instructions for contributing.

## Code of Conduct

- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on constructive feedback
- Respect different viewpoints and experiences

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in [Issues](https://github.com/eMeF1/ha-cem-monitoring-integration/issues)
2. If not, create a new issue using the bug report template
3. Include:
   - Home Assistant version
   - Integration version
   - Steps to reproduce
   - Expected vs. actual behavior
   - Relevant logs (with sensitive information removed)

### Suggesting Features

1. Check if the feature has already been suggested
2. Create a new issue using the feature request template
3. Describe the use case and benefits
4. Consider implementation complexity

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Ensure all tests pass (`pytest`)
5. Run linting and formatting (`ruff check --fix` and `ruff format`)
6. Run type checking (`mypy custom_components`)
7. Update documentation if needed
8. Commit your changes with clear messages
9. Push to your fork (`git push origin feature/amazing-feature`)
10. Open a Pull Request

## Development Setup

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for detailed setup instructions.

### Quick Start

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/ha-cem-monitoring-integration.git
cd ha-cem-monitoring-integration

# Install dependencies
pip install -r requirements-test.txt
pip install pre-commit
pre-commit install

# Run tests
pytest
```

## Code Style

- Follow PEP 8
- Use type hints for all functions
- Maximum line length: 100 characters
- Use `ruff` for linting and formatting
- Use `mypy` for type checking

### Pre-commit Hooks

The project uses pre-commit hooks to ensure code quality. They will run automatically on commit, or you can run them manually:

```bash
pre-commit run --all-files
```

## Testing

- Write tests for new features
- Ensure all existing tests pass
- Aim for high test coverage
- Test both success and error cases

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=custom_components.cem_monitor --cov-report=html

# Specific test file
pytest tests/unit/test_api.py
```

## Commit Messages

Use clear, descriptive commit messages:

- Use present tense ("Add feature" not "Added feature")
- Start with a capital letter
- Keep the first line under 72 characters
- Reference issues when applicable: "Fix #123: Description"

Examples:
- `Add batch API support for counter readings`
- `Fix token refresh on 401 errors`
- `Update documentation for new architecture`

## Pull Request Process

1. Ensure your PR addresses a single issue or feature
2. Update documentation if needed
3. Add tests for new functionality
4. Ensure all CI checks pass
5. Request review from maintainers
6. Address review feedback
7. Once approved, maintainers will merge

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
└── utils/                   # Utility modules

tests/
├── unit/                    # Unit tests
├── integration/             # Integration tests
└── coordinators/            # Coordinator tests
```

## Questions?

- Open an issue for questions
- Check existing documentation in `docs/`
- Review [Home Assistant Developer Documentation](https://developers.home-assistant.io/)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

