import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from ecs_mcp.cli import main, perform_async_initialization
from ecs_mcp.server import ECSMCPServer

@pytest.fixture
def mock_env_vars():
    """Fixture to set up test environment variables."""
    env_vars = {
        'AWS_ACCESS_KEY_ID': 'test-access-key',
        'AWS_SECRET_ACCESS_KEY': 'test-secret-key',
        'AWS_REGION': 'us-west-2',
        'OPENAI_API_KEY': 'test-openai-key',
        'MODEL': 'test-model'
    }
    with patch.dict(os.environ, env_vars):
        yield env_vars

@pytest.fixture
def mock_server():
    """Fixture to create a mock server instance."""
    server = MagicMock(spec=ECSMCPServer)
    server.client = AsyncMock()
    server.run_mcp_blocking = MagicMock()
    return server

def test_perform_async_initialization_noop(mock_server):
    import anyio
    anyio.run(perform_async_initialization, mock_server)

@pytest.mark.parametrize("args,expected_exit,clear_env", [
    (['--openai-api-key', 'test-key', '--region', 'us-east-1'], 0, False),
    (['--openai-api-key', 'test-key', '--access-key', 'cli-access-key', 
      '--secret-access-key', 'cli-secret-key',
      '--region', 'us-east-1'], 0, False),
    (['--openai-api-key', 'test-key', '--region', 'us-east-1'], 0, True),
    (['--openai-api-key', 'test-key', '--access-key', 'cli-access-key'], 2, True),
    (['--openai-api-key', 'test-key', '--secret-access-key', 'cli-secret-key'], 2, True),
])
def test_main_with_args(args, expected_exit, clear_env, mock_env_vars, mock_server):
    env_patch = patch.dict(os.environ, {}, clear=True) if clear_env else patch.dict(os.environ, mock_env_vars)
    with env_patch, \
         patch('sys.argv', ['cli.py'] + args), \
         patch('ecs_mcp.cli.ECSMCPServer', return_value=mock_server), \
         patch('ecs_mcp.cli.anyio.run') as mock_anyio_run:
        if expected_exit == 0:
            assert main() == 0
            mock_anyio_run.assert_called_once()
            mock_server.run_mcp_blocking.assert_called_once()
        else:
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == expected_exit
            mock_anyio_run.assert_not_called()
            mock_server.run_mcp_blocking.assert_not_called()

def test_main_with_custom_model(mock_env_vars, mock_server):
    with patch('sys.argv', ['cli.py', '--openai-api-key', 'test-key', '--region', 'us-east-1', '--model', 'custom-model']), \
         patch('ecs_mcp.cli.ECSMCPServer', return_value=mock_server) as mock_server_class, \
         patch('ecs_mcp.cli.anyio.run') as mock_anyio_run:
        assert main() == 0
        mock_server_class.assert_called_once()
        call_args = mock_server_class.call_args[1]
        assert call_args['model'] == 'custom-model'
        mock_anyio_run.assert_called_once()
        mock_server.run_mcp_blocking.assert_called_once()

def test_main_with_custom_host_port(mock_env_vars, mock_server):
    with patch('sys.argv', ['cli.py', '--openai-api-key', 'test-key', '--region', 'us-east-1', '--host', '127.0.0.1', '--port', '9000']), \
         patch('ecs_mcp.cli.ECSMCPServer', return_value=mock_server) as mock_server_class, \
         patch('ecs_mcp.cli.anyio.run') as mock_anyio_run:
        assert main() == 0
        mock_server_class.assert_called_once()
        mock_anyio_run.assert_called_once()
        mock_server.run_mcp_blocking.assert_called_once()