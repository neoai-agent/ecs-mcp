# ECS MCP Server



A lightweight Management Control Plane (MCP) server for AWS ECS that helps you manage and monitor your ECS clusters with ease. Built with Python and designed for simplicity.

## Features

- Intelligent cluster and service discovery
- Real-time resource monitoring
- Automated scaling recommendations
- Health monitoring and alerts
- AI-powered service name matching

## Installation

```bash
# Using pipx (recommended)
pipx install ecs-mcp

# Using pip
pip install ecs-mcp
```

## Quick Start

```python
from ecs_mcp import MCPServer, ECSClientConfig

# Configure AWS credentials
config = ECSClientConfig(
    access_key="your_access_key",
    secret_access_key="your_secret_key",
    region_name="us-west-2"
)

# Initialize and start the server
server = MCPServer(config=config)
server.start()
```

Or using the CLI:

```bash
# Set environment variables
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_REGION=your_region
export OPENAI_API_KEY=your_openai_key

# Run the server
ecs-mcp --host 0.0.0.0 --port 8000
```

That's it! pipx will:
- Download the package from PyPI
- Create an isolated environment
- Run the command
- Clean up after itself

## Prerequisites

- Python 3.8 or higher
- pipx (for running without installation)

To install pipx if you don't have it:
```bash
# On macOS
brew install pipx
pipx ensurepath

# On Linux
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# On Windows
python -m pip install --user pipx
python -m pipx ensurepath
```