#!/usr/bin/env python3
"""
Script to run ECS MCP client tests.
"""

import os
import sys
import pytest
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_test_environment():
    """Set up test environment variables."""
    # Set test AWS credentials
    os.environ["AWS_ACCESS_KEY_ID"] = "test-access-key"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test-secret-key"
    os.environ["AWS_REGION"] = "us-west-2"
    
    # Set test OpenAI API key
    os.environ["OPENAI_API_KEY"] = "test-api-key"

def main():
    """Run the test suite."""
    logger.info("Setting up test environment...")
    setup_test_environment()
    
    logger.info("Starting test suite...")
    
    # Run pytest with specific options
    args = [
        "tests/",  # Test directory
        "-v",      # Verbose output
        "--tb=short",  # Shorter traceback format
        "--cov=ecs_mcp",  # Enable coverage reporting
        "--cov-report=term-missing",  # Show missing lines in coverage
        "--cov-report=html",  # Generate HTML coverage report
        "-W", "ignore::DeprecationWarning",  # Ignore deprecation warnings
    ]
    
    # Add any additional pytest arguments from command line
    args.extend(sys.argv[1:])
    
    # Run the tests
    exit_code = pytest.main(args)
    
    if exit_code == 0:
        logger.info("All tests passed successfully!")
    else:
        logger.error(f"Tests failed with exit code: {exit_code}")
    
    sys.exit(exit_code)

if __name__ == "__main__":
    main() 