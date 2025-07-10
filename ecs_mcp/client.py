"""
AWS ECS client implementation for MCP server.
"""

from typing import Dict, List, Any
import boto3
from botocore.exceptions import ClientError
import logging
import json
from datetime import datetime, timezone
from litellm import acompletion
from dataclasses import dataclass
from botocore.config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger('ecs_mcp')

@dataclass
class ECSClientConfig:
    region_name: str
    access_key: str = None
    secret_access_key: str = None

class AWSClientManager:
    """Manages AWS service client connections."""
    
    def __init__(self, config: ECSClientConfig):
        self.config = config
        self._ecs = None
        self._elbv2 = None
        self._cloudwatch = None

    def get_aws_credentials(self):
        """Get AWS credentials with proper error handling"""
        if not self.config.access_key or not self.config.secret_access_key:
            logger.info("No explicit AWS credentials provided. Using default AWS credential chain (IAM roles, environment variables, etc.)")
            return None, None
        return self.config.access_key, self.config.secret_access_key

    def _create_client(self, service_name, region_name=None):
        access_key, secret_key = self.get_aws_credentials()
        client_kwargs = {'region_name': region_name or self.config.region_name}
        if access_key and secret_key:
            client_kwargs.update({
                'aws_access_key_id': access_key,
                'aws_secret_access_key': secret_key
            })
        else:
            client_kwargs['config'] = Config(
                user_agent_extra='ecs-mcp/1.0',
                connect_timeout=10,
                read_timeout=30
            )
        return boto3.client(service_name, **client_kwargs)

    def get_ecs_client(self):
        if not self._ecs:
            self._ecs = self._create_client('ecs')
        return self._ecs

    def get_elbv2_client(self):
        if not self._elbv2:
            self._elbv2 = self._create_client('elbv2')
        return self._elbv2

    def get_cloudwatch_client(self):
        if not self._cloudwatch:
            self._cloudwatch = self._create_client('cloudwatch')
        return self._cloudwatch

class ECSClient:
    """Client for interacting with AWS ECS services and cloudwatch metrics for ecs services"""

    def __init__(self, model: str, openai_api_key: str, aws_client_manager: AWSClientManager):
        """Initialize the ECS client and cloudwatch client.

        Args:
            region_name: AWS region name
            profile_name: Optional AWS profile name
        """
        self.model = model
        self.openai_api_key = openai_api_key
        self._name_matching_cache = {}
        self._clusters_services_cache = {
            "data": None,
            "timestamp": None,
            "cache_ttl": 300  # Cache TTL in seconds (5 minutes)
        }
        self.aws_client_manager = aws_client_manager
        self.initialize_ecs()

    def initialize_ecs(self):
        """Initialize the ECS client."""
        self.ecs_client = self.aws_client_manager.get_ecs_client()
        self.elbv2_client = self.aws_client_manager.get_elbv2_client()
        self.cloudwatch_client = self.aws_client_manager.get_cloudwatch_client()

    def list_clusters(self) -> List[str]:
        """List all ECS clusters."""
        try:
            response = self.ecs_client.list_clusters()
            return response["clusterArns"]
        except ClientError as e:
            logger.error(f"Failed to list clusters: {str(e)}")
            raise

    def describe_cluster(self, cluster_name: str) -> Dict[str, Any]:
        """Get detailed information about a cluster."""
        try:
            response = self.ecs_client.describe_clusters(clusters=[cluster_name])
            return response["clusters"][0]
        except ClientError as e:
            logger.error(f"Failed to describe cluster {cluster_name}: {str(e)}")
            raise

    def list_services(self, cluster_name: str) -> List[str]:
        """List all services in a cluster."""
        try:
            response = self.ecs_client.list_services(cluster=cluster_name)
            return response["serviceArns"]
        except ClientError as e:
            logger.error(f"Failed to list services for cluster {cluster_name}: {str(e)}")
            raise

    def describe_service(self, cluster_name: str, service_name: str) -> Dict[str, Any]:
        """Get detailed information about a service."""
        try:
            response = self.ecs_client.describe_services(
                cluster=cluster_name,
                services=[service_name]
            )
            return response["services"][0]
        except ClientError as e:
            logger.error(f"Failed to describe service {service_name} in cluster {cluster_name}: {str(e)}")
            raise

    def get_all_clusters_and_services(self):
        """Get all ECS clusters and their services in a format suitable for LLM feedback"""
        # Check if we have valid cached data
        current_time = datetime.now(timezone.utc)
        if (self._clusters_services_cache["data"] and 
            self._clusters_services_cache["timestamp"] and
            (current_time - self._clusters_services_cache["timestamp"]).total_seconds() < self._clusters_services_cache["cache_ttl"]):
            logger.info("Returning cached clusters and services data")
            return self._clusters_services_cache["data"]

        try:
            clusters = self.ecs_client.list_clusters()['clusterArns']
            cluster_names = [arn.split('/')[-1] for arn in clusters]
            cluster_services = {}
            
            for cluster_name in cluster_names:
                service_arns = []
                next_token = None
                
                while True:
                    kwargs = {'cluster': cluster_name}
                    if next_token:
                        kwargs['nextToken'] = next_token
                    response = self.ecs_client.list_services(**kwargs)
                    
                    service_arns.extend(response['serviceArns'])
                    next_token = response.get('nextToken')
                    if not next_token:
                        break
                        
                service_names = [arn.split('/')[-1] for arn in service_arns]
                cluster_services[cluster_name] = service_names
            
            formatted_response = {
                "clusters": [
                    {
                        "name": cluster_name,
                        "services": services,
                        "service_count": len(services)
                    }
                    for cluster_name, services in cluster_services.items()
                ],
                "total_clusters": len(cluster_names),
                "total_services": sum(len(services) for services in cluster_services.values())
            }
            
            # Update cache
            self._clusters_services_cache = {
                "data": formatted_response,
                "timestamp": current_time,
                "cache_ttl": 300
            }
            
            return formatted_response
            
        except Exception as e:
            logger.error(f"Error getting clusters and services: {str(e)}")
            return {
                "error": f"Failed to get clusters and services: {str(e)}",
                "status": "error"
            }

    async def find_matching_names(self, cluster_name: str = None, service_name: str = None):
        """
        Find the correct cluster and service names using LLM for intelligent matching.
        Results are cached in memory to improve performance for repeated lookups.

        Args:
            cluster_name (str, optional): The cluster name to match
            service_name (str, optional): The service name to match
            
        Returns:
            dict: A dictionary containing:
                - cluster_name: The best matching cluster name
                - service_name: The best matching service name
                - status: Success or error status
        """
        cache_key = f"{cluster_name}:{service_name}"
        if cache_key in self._name_matching_cache:
            logger.info(f"Cache hit for key: {cache_key}")
            return self._name_matching_cache[cache_key]

        try:
            all_info = self.get_all_clusters_and_services()
            if "error" in all_info:
                return all_info

            cluster_map = {c["name"]: c["services"] for c in all_info["clusters"]}
            prompt = self._build_prompt(cluster_map, cluster_name, service_name)
            response_content = await self.call_llm(prompt)
            matches = json.loads(response_content)

            result = {
                "status": "success",
                "cluster_name": matches.get("cluster_name"),
                "service_name": matches.get("service_name")
            }
            if result["service_name"] and not result["cluster_name"]:
                for c, services in cluster_map.items():
                    if result["service_name"] in services:
                        result["cluster_name"] = c
                        break
            if result["cluster_name"] and service_name and not result["service_name"]:
                cluster_svcs = cluster_map[result["cluster_name"]]
                service_prompt = f"""
Given the following services in cluster {result['cluster_name']}, find the best matching service for "{service_name}":
{json.dumps(cluster_svcs, indent=2)}
Format:
{{"service_name": "..."}}
"""
                svc_response = await self.call_llm(service_prompt)
                svc_match = json.loads(svc_response)
                result["service_name"] = svc_match.get("service_name")

            self._name_matching_cache[cache_key] = result
            return result
        except Exception as e:
            logger.error(f"LLM fallback error: {str(e)}")
            result = {
                "status": "fallback",
                "cluster_name": None,
                "service_name": None
            }
            all_info = self.get_all_clusters_and_services()
            cluster_map = {c['name']: c['services'] for c in all_info.get('clusters', [])}

            if cluster_name:
                result["cluster_name"] = self.find_best_match_basic(cluster_name, list(cluster_map.keys()))

            if service_name:
                services = cluster_map.get(result["cluster_name"], []) if result["cluster_name"] else sum(cluster_map.values(), [])
                result["service_name"] = self.find_best_match_basic(service_name, services)

            return result

    def _build_prompt(self, cluster_map, cluster_name, service_name):
        """Build a prompt for the LLM to find matching names"""
        prompt = "Given the following ECS clusters and services, find the best matching names:\n\n"
        for c, s in cluster_map.items():
            prompt += f"- Cluster: {c}\n  Services:\n  " + "\n  ".join(f"- {svc}" for svc in s) + "\n\n"
        prompt += "\nSearch criteria:\n"
        if cluster_name:
            prompt += f"- Cluster similar to: {cluster_name}\n"
        if service_name:
            prompt += f"- Service similar to: {service_name}\n"
        prompt += """
Important Instructions:
1. Only match a service that exists inside the matched cluster. Do not return a service that is not found within the cluster.
2. Avoid selecting clusters that contain the following terms unless there are no other valid options:
   - "test"
   - "experiment"
   - "dev"
   - "sandbox"
Please provide a JSON response:
{
  "cluster_name": "best matching cluster name or None",
  "service_name": "best matching service name or None"
}
"""
        return prompt

    def find_best_match_basic(self, target: str, candidates: list) -> str:
        """Basic fallback matching function when LLM is not available"""
        if not target or not candidates:
            return None
        
        # Convert to lowercase for case-insensitive matching
        target = target.lower()
        
        # Exact match check
        for candidate in candidates:
            if candidate.lower() == target:
                return candidate
        
        # Partial match check (contains)
        partial_matches = [
            c for c in candidates
            if target in c.lower() or c.lower() in target
        ]
        
        if partial_matches:
            # Sort by length to prefer shorter, more precise matches
            partial_matches.sort(key=len)
            return partial_matches[0]
        
        return None

    async def call_llm(self, prompt: str) -> str:
        """
        Call LLM (default is GPT-4o-mini) using LiteLLM to find matching names and return JSON.
        """
        try:
            response = await acompletion(
                model=self.model,
                api_key=self.openai_api_key,
                messages=[
                    {"role": "system", "content": "You help match ECS cluster/service names in JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM call failed: {str(e)}")
            return json.dumps({"cluster_name": None, "service_name": None})