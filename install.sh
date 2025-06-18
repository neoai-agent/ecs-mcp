#!/bin/bash

# Install ecs-mcp server using pipx
echo "Installing ecs-mcp server..."

# Check if pipx is installed
if ! command -v pipx &> /dev/null; then
    echo "pipx is not installed. Installing pipx first..."
    python3 -m pip install --user pipx
    python3 -m pipx ensurepath
fi

# Install the MCP server
pipx install .

echo "ecs-mcp server installed successfully!"
echo ""
echo "Usage examples:"
echo "  # With IAM role (recommended for EC2)"
echo "  ecs-mcp --openai-api-key YOUR_KEY --region us-east-1"
echo ""
echo "  # With explicit AWS credentials"
echo "  ecs-mcp --openai-api-key YOUR_KEY --access-key YOUR_ACCESS_KEY --secret-access-key YOUR_SECRET_KEY --region us-east-1"
echo ""
echo "  # With custom model"
echo "  ecs-mcp --openai-api-key YOUR_KEY --region us-east-1 --model gpt-4" 