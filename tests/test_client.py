"""Test cases for the ECS client implementation."""

import pytest
from unittest.mock import MagicMock, patch, Mock
from datetime import datetime, timezone, timedelta
import json
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from ecs_mcp.client import ECSClient, ECSClientConfig, AWSClientManager

# Test data
MOCK_CLUSTERS = {
    "clusterArns": [
        "arn:aws:ecs:us-west-2:123456789012:cluster/test-cluster-1",
        "arn:aws:ecs:us-west-2:123456789012:cluster/test-cluster-2"
    ]
}

MOCK_CLUSTER_DETAILS = {
    "clusters": [{
        "clusterName": "test-cluster-1",
        "status": "ACTIVE",
        "runningTasksCount": 5,
        "pendingTasksCount": 0,
        "activeServicesCount": 2
    }]
}

MOCK_SERVICES = {
    "serviceArns": [
        "arn:aws:ecs:us-west-2:123456789012:service/test-cluster-1/test-service-1",
        "arn:aws:ecs:us-west-2:123456789012:service/test-cluster-1/test-service-2"
    ]
}

MOCK_SERVICE_DETAILS = {
    "services": [{
        "serviceName": "test-service-1",
        "status": "ACTIVE",
        "desiredCount": 2,
        "runningCount": 2,
        "pendingCount": 0
    }]
}

MOCK_LLM_RESPONSE = {
    "choices": [{
        "message": {
            "content": json.dumps({
                "cluster_name": "test-cluster-1",
                "service_name": "test-service-1"
            })
        }
    }]
}

@pytest.fixture
def mock_config():
    """Create a mock ECS client configuration."""
    return ECSClientConfig(
        access_key="test-access-key",
        secret_access_key="test-secret-key",
        region_name="us-west-2"
    )

@pytest.fixture
def mock_aws_clients():
    """Mock AWS service clients."""
    with patch("boto3.client") as mock_client:
        # Create mock clients
        mock_ecs = MagicMock()
        mock_elbv2 = MagicMock()
        mock_cloudwatch = MagicMock()
        
        # Configure mock responses
        mock_ecs.list_clusters.return_value = MOCK_CLUSTERS
        mock_ecs.describe_clusters.return_value = MOCK_CLUSTER_DETAILS
        mock_ecs.list_services.return_value = MOCK_SERVICES
        mock_ecs.describe_services.return_value = MOCK_SERVICE_DETAILS
        
        # Configure mock client to return different clients based on service name
        mock_client.side_effect = lambda service, **kwargs: {
            "ecs": mock_ecs,
            "elbv2": mock_elbv2,
            "cloudwatch": mock_cloudwatch
        }.get(service)
        
        yield {
            "ecs": mock_ecs,
            "elbv2": mock_elbv2,
            "cloudwatch": mock_cloudwatch
        }

@pytest.fixture(autouse=True)
def mock_llm(monkeypatch):
    """Automatically mock ECSClient.call_llm for all tests."""
    with patch.object(ECSClient, 'call_llm', return_value='{"cluster_name": "test-cluster-1", "service_name": "test-service-1"}') as mock:
        yield mock

@pytest.fixture
def client(mock_config, mock_aws_clients, mock_llm):
    """Create a test client instance."""
    aws_client_manager = AWSClientManager(mock_config)
    return ECSClient(
        model="gpt-4-mini",
        openai_api_key="test-api-key",
        aws_client_manager=aws_client_manager
    )

class TestECSClient:
    """Test cases for ECSClient class."""

    def test_init(self, mock_config):
        """Test client initialization."""
        aws_client_manager = AWSClientManager(mock_config)
        client = ECSClient(
            model="gpt-4-mini",
            openai_api_key="test-api-key",
            aws_client_manager=aws_client_manager
        )
        assert client.aws_client_manager == aws_client_manager
        assert client.model == "gpt-4-mini"
        assert client.openai_api_key == "test-api-key"
        assert isinstance(client._name_matching_cache, dict)
        assert isinstance(client._clusters_services_cache, dict)

    def test_get_aws_credentials(self, client):
        """Test AWS credentials retrieval."""
        access_key, secret_key = client.aws_client_manager.get_aws_credentials()
        assert access_key == "test-access-key"
        assert secret_key == "test-secret-key"

    def test_get_aws_credentials_missing(self, mock_config):
        """Test AWS credentials retrieval with missing credentials."""
        config = ECSClientConfig(
            access_key="",
            secret_access_key="",
            region_name="us-west-2"
        )
        aws_client_manager = AWSClientManager(config)
        client = ECSClient(
            model="gpt-4-mini",
            openai_api_key="test-api-key",
            aws_client_manager=aws_client_manager
        )
        
        # Test that it returns None, None when no credentials are provided
        access_key, secret_key = client.aws_client_manager.get_aws_credentials()
        assert access_key is None
        assert secret_key is None

    def test_list_clusters(self, client, mock_aws_clients):
        """Test listing clusters."""
        clusters = client.list_clusters()
        assert clusters == MOCK_CLUSTERS["clusterArns"]
        mock_aws_clients["ecs"].list_clusters.assert_called_once()

    def test_describe_cluster(self, client, mock_aws_clients):
        """Test describing a cluster."""
        cluster = client.describe_cluster("test-cluster-1")
        assert cluster == MOCK_CLUSTER_DETAILS["clusters"][0]
        mock_aws_clients["ecs"].describe_clusters.assert_called_once_with(
            clusters=["test-cluster-1"]
        )

    def test_list_services(self, client, mock_aws_clients):
        """Test listing services."""
        services = client.list_services("test-cluster-1")
        assert services == MOCK_SERVICES["serviceArns"]
        mock_aws_clients["ecs"].list_services.assert_called_once_with(
            cluster="test-cluster-1"
        )

    def test_describe_service(self, client, mock_aws_clients):
        """Test describing a service."""
        service = client.describe_service("test-cluster-1", "test-service-1")
        assert service == MOCK_SERVICE_DETAILS["services"][0]
        mock_aws_clients["ecs"].describe_services.assert_called_once_with(
            cluster="test-cluster-1",
            services=["test-service-1"]
        )

    def test_get_all_clusters_and_services(self, client, mock_aws_clients):
        """Test getting all clusters and services."""
        result = client.get_all_clusters_and_services()
        
        # Verify the structure of the response
        assert "clusters" in result
        assert "total_clusters" in result
        assert "total_services" in result
        
        # Verify cluster data
        clusters = result["clusters"]
        assert len(clusters) == 2  # Based on MOCK_CLUSTERS
        assert clusters[0]["name"] == "test-cluster-1"
        assert "services" in clusters[0]
        assert "service_count" in clusters[0]

    @pytest.mark.asyncio
    async def test_find_matching_names(self, client, mock_aws_clients, mock_llm):
        """Test finding matching names using LLM."""
        result = await client.find_matching_names(
            cluster_name="test-cluster",
            service_name="test-service"
        )
        
        assert result["status"] == "success"
        assert result["cluster_name"] == "test-cluster-1"
        assert result["service_name"] == "test-service-1"
        
        # Verify LLM was called
        mock_llm.assert_called()

    @pytest.mark.asyncio
    @patch("ecs_mcp.client.ECSClient.call_llm")
    async def test_find_matching_names_cache(self, mock_llm, client):
        # Reset (clear) the name matching cache so that the first call is a cache miss.
        client._name_matching_cache.clear()
        print("Cleared name matching cache (so that first call is a cache miss).")
        mock_llm.return_value = json.dumps({"cluster_name": "test-cluster-1", "service_name": "test-service-1"})
        cluster_name = "test-cluster"
        service_name = "test-service"
        # First call (cache miss) should call the LLM.
        first_result = await client.find_matching_names(cluster_name, service_name)
        assert first_result["status"] == "success"
        assert first_result["cluster_name"] == "test-cluster-1"
        assert first_result["service_name"] == "test-service-1"
        assert mock_llm.call_count == 1, "LLM (call_llm) should be called once on first invocation (cache miss)."
        # Second call (with the same cluster/service name) should hit the cache (i.e. not call the LLM again).
        second_result = await client.find_matching_names(cluster_name, service_name)
        assert second_result["status"] == "success"
        assert second_result["cluster_name"] == "test-cluster-1"
        assert second_result["service_name"] == "test-service-1"
        assert mock_llm.call_count == 1, "LLM (call_llm) should not be called again on second invocation (cache hit)."

    def test_find_best_match_basic(self, client):
        """Test basic name matching fallback."""
        candidates = ["test-cluster-1", "test-cluster-2", "other-cluster"]
        
        # Test exact match
        assert client.find_best_match_basic("test-cluster-1", candidates) == "test-cluster-1"
        
        # Test partial match
        assert client.find_best_match_basic("test", candidates) == "test-cluster-1"
        
        # Test no match
        assert client.find_best_match_basic("nonexistent", candidates) is None

    def test_error_handling(self, client, mock_aws_clients):
        """Test error handling in client methods."""
        # Mock an AWS API error
        mock_aws_clients["ecs"].list_clusters.side_effect = ClientError(
            error_response={"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            operation_name="ListClusters"
        )
        
        # Test that the error is properly propagated
        with pytest.raises(ClientError):
            client.list_clusters()

    @pytest.mark.asyncio
    async def test_llm_error_handling(self, client, mock_aws_clients, mock_llm):
        """Test error handling in LLM calls."""
        # Mock LLM error
        mock_llm.side_effect = Exception("LLM API Error")
        
        # Test that the system falls back to basic matching
        result = await client.find_matching_names(
            cluster_name="test-cluster",
            service_name="test-service"
        )
        
        assert result["status"] == "success"
        # Should use basic matching when LLM fails
        assert result["cluster_name"] is not None or result["service_name"] is not None

    @pytest.mark.asyncio
    async def test_invalid_json_handling(self, client, mock_aws_clients, mock_llm):
        """Test handling of invalid JSON from LLM."""
        # Mock LLM returning invalid JSON
        mock_llm.return_value = {
            "choices": [{
                "message": {
                    "content": "invalid json"
                }
            }]
        }
        
        result = await client.find_matching_names(
            cluster_name="test-cluster",
            service_name="test-service"
        )
        
        assert result["status"] == "success"
        # Should fall back to basic matching
        assert result["cluster_name"] is not None or result["service_name"] is not None 