# Contributing to ECS MCP Server

Thank you for your interest in contributing to ECS MCP Server! This document provides guidelines and instructions for contributing.

## Code of Conduct

By participating in this project, you agree to abide by our Code of Conduct. Please read it before contributing.

## Development Setup

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/your-username/ecs-mcp.git
   cd ecs-mcp
   ```
3. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
4. Install development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```
5. Install pre-commit hooks:
   ```bash
   pre-commit install
   ```

## Development Workflow

1. Create a new branch for your feature/fix:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Make your changes
3. Run tests:
   ```bash
   pytest
   ```
4. Run linting:
   ```bash
   black .
   isort .
   flake8
   mypy .
   ```
5. Commit your changes:
   ```bash
   git commit -m "Description of your changes"
   ```
6. Push to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```
7. Create a Pull Request

## Pull Request Process

1. Update the README.md with details of changes if needed
2. Update the documentation if needed
3. The PR will be merged once you have the sign-off of at least one maintainer
4. Make sure all tests pass and code is properly formatted

## Testing

We use pytest for testing. To run tests:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=ecs_mcp

# Run specific test file
pytest tests/test_specific.py
```

## Code Style

We use:
- Black for code formatting
- isort for import sorting
- flake8 for linting
- mypy for type checking

To format your code:
```bash
black .
isort .
```

## Documentation

- Update docstrings for any new functions/classes
- Update README.md if needed
- Update API documentation if needed

## Release Process

1. Update version in pyproject.toml
2. Update CHANGELOG.md
3. Create a new release on GitHub
4. Build and publish to PyPI:
   ```bash
   python -m build
   twine upload dist/*
   ```

## Questions?

Feel free to open an issue for any questions or concerns. 