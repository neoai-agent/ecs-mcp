"""
AWS ECS client implementation for MCP server.
"""

from typing import Dict, List, Any
import boto3
from botocore.exceptions import ClientError
import logging
import json
from datetime import datetime, timezone
from litellm import completion
from dataclasses import dataclass

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

    def get_ecs_client(self, region_name=None):
        """Get or create ECS client."""
        if not self._ecs:
            try:
                access_key, secret_key = self.get_aws_credentials()
                client_kwargs = {
                    'region_name': region_name or self.config.region_name
                }
                
                # Only add credentials if they are explicitly provided
                if access_key and secret_key:
                    client_kwargs.update({
                        'aws_access_key_id': access_key,
                        'aws_secret_access_key': secret_key
                    })
                else:
                    client_kwargs.update({
                        'config': boto3.session.Config(
                            user_agent_extra='ecs-mcp/1.0',
                            connect_timeout=10,
                            read_timeout=30
                        )
                    })
                
                self._ecs = boto3.client('ecs', **client_kwargs)
            except Exception as e:
                logger.error(f"Failed to create ECS client: {str(e)}")
                raise
        return self._ecs

    def get_elbv2_client(self, region_name=None):
        """Get or create ELBv2 client."""
        if not self._elbv2:
            try:
                access_key, secret_key = self.get_aws_credentials()
                client_kwargs = {
                    'region_name': region_name or self.config.region_name
                }
                
                # Only add credentials if they are explicitly provided
                if access_key and secret_key:
                    client_kwargs.update({
                        'aws_access_key_id': access_key,
                        'aws_secret_access_key': secret_key
                    })
                else:
                    client_kwargs.update({
                        'config': boto3.session.Config(
                            user_agent_extra='ecs-mcp/1.0',
                            connect_timeout=10,
                            read_timeout=30
                        )
                    })
                
                self._elbv2 = boto3.client('elbv2', **client_kwargs)
            except Exception as e:
                logger.error(f"Failed to create ELBv2 client: {str(e)}")
                raise
        return self._elbv2

    def get_cloudwatch_client(self, region_name=None):
        """Get or create CloudWatch client."""
        if not self._cloudwatch:
            try:
                access_key, secret_key = self.get_aws_credentials()
                client_kwargs = {
                    'region_name': region_name or self.config.region_name
                }
                
                # Only add credentials if they are explicitly provided
                if access_key and secret_key:
                    client_kwargs.update({
                        'aws_access_key_id': access_key,
                        'aws_secret_access_key': secret_key
                    })
                else:
                    client_kwargs.update({
                        'config': boto3.session.Config(
                            user_agent_extra='ecs-mcp/1.0',
                            connect_timeout=10,
                            read_timeout=30
                        )
                    })
                
                self._cloudwatch = boto3.client('cloudwatch', **client_kwargs)
            except Exception as e:
                logger.error(f"Failed to create CloudWatch client: {str(e)}")
                raise
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
        if (self._clusters_services_cache["data"] is not None and 
            self._clusters_services_cache["timestamp"] is not None and
            (current_time - self._clusters_services_cache["timestamp"]).total_seconds() < self._clusters_services_cache["cache_ttl"]):
            logger.info("Returning cached clusters and services data")
            return self._clusters_services_cache["data"]

        try:
            # Get all clusters
            clusters_response = self.ecs_client.list_clusters()
            cluster_arns = clusters_response['clusterArns']
            
            # Get cluster names from ARNs
            cluster_names = [arn.split('/')[-1] for arn in cluster_arns]
            print(f"Cluster names: {cluster_names}")
            # Get services for each cluster
            cluster_services = {}
            for cluster_name in cluster_names:
                service_arns = []
                next_token = None
                
                while True:
                    if next_token:
                        services_response = self.ecs_client.list_services(cluster=cluster_name, nextToken=next_token)
                    else:
                        services_response = self.ecs_client.list_services(cluster=cluster_name)
                    
                    service_arns.extend(services_response['serviceArns'])
                    next_token = services_response.get('nextToken')
                    
                    if not next_token:
                        break
                        
                service_names = [arn.split('/')[-1] for arn in service_arns]
                cluster_services[cluster_name] = service_names
            
            print(f"Cluster services: {cluster_services}")
            
            # Format the response for LLM feedback
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
            self._clusters_services_cache["data"] = formatted_response
            self._clusters_services_cache["timestamp"] = current_time
            
            return formatted_response
            
        except Exception as e:
            logger.error(f"Error getting clusters and services: {str(e)}")
            return {
                "error": f"Failed to get clusters and services: {str(e)}",
                "status": "error"
            }

    async def find_matching_names(self, cluster_name: str = None, service_name: str = None):
        """
        Find the correct cluster and service names using GPT4-mini for intelligent matching.
        Results are cached in memory to improve performance for repeated lookups.
        """
        # Create a cache key based on the input parameters
        cache_key = f"{cluster_name}:{service_name}"
        
        # Check if we have a cached result
        if cache_key in self._name_matching_cache:
            logger.info(f"Cache hit (using cached name matching result for cache_key: {cache_key})")

            return self._name_matching_cache[cache_key]
        """
        Find the correct cluster and service names using GPT4-mini for intelligent matching.
        This utility function is designed to be used by other tools to validate and correct cluster/service names.
        
        Args:
            cluster_name (str, optional): The cluster name to match
            service_name (str, optional): The service name to match
            
        Returns:
            dict: A dictionary containing:
                - cluster_name: The best matching cluster name
                - service_name: The best matching service name
                - status: Success or error status
        """
        try:
            # Get all clusters and services
            all_info = self.get_all_clusters_and_services()
            if "error" in all_info:
                return all_info

            # Create a mapping of all clusters and their services
            cluster_service_map = {
                cluster["name"]: cluster["services"]
                for cluster in all_info["clusters"]
            }

            # Initialize response structure
            response = {
                "status": "success",
                "cluster_name": None,
                "service_name": None
            }

            # Prepare the prompt for GPT4-mini
            prompt = "Given the following ECS clusters and their services, find the best matching names:\n\n"
            
            # Add clusters and services information
            prompt += "Available clusters and services:\n"
            for cluster, services in cluster_service_map.items():
                prompt += f"- Cluster: {cluster}\n"
                prompt += "  Services:\n"
                for service in services:
                    prompt += f"  - {service}\n"
                prompt += "\n"

            # Add the search criteria
            prompt += "\nSearch criteria:\n"
            if cluster_name:
                logger.info(f"Cluster name: {cluster_name}")
                prompt += f"- Looking for cluster similar to: {cluster_name}\n"
            if service_name:
                logger.info(f"Service name: {service_name}")
                prompt += f"- Looking for service similar to: {service_name}\n"

            # Add instructions for the LLM
            prompt += """
    Please analyze the above information and provide:
    1. The best matching cluster name (if cluster search was provided)
    2. The best matching service name (if service search was provided)
    3. Consider:
    - Exact matches
    - Partial matches
    - Common naming patterns
    - Environment prefixes/suffixes
    - Service type indicators
    4. The service name should be part of the cluster name you are finding.

    Format your response as a JSON object with:
    {
        "cluster_name": "best matching cluster name or null",
        "service_name": "best matching service name or null"
    }
    """

            # Call GPT4-mini using LiteLLM
            try:
                response_content = await self.call_llm(prompt)
                
                # Parse the LLM response
                matches = json.loads(response_content)
                
                # Update the response with the LLM's matches
                response["cluster_name"] = matches.get("cluster_name")
                response["service_name"] = matches.get("service_name")
                
                # If we got a service match but no cluster match, and we have a service-to-cluster mapping
                if response["service_name"] and not response["cluster_name"]:
                    response["cluster_name"] = cluster_service_map.get(response["service_name"])
                
                # If we got a cluster match but no service match, and we have a service name to search for
                if response["cluster_name"] and service_name and not response["service_name"]:
                    # Get services for the matched cluster
                    cluster_services = cluster_service_map.get(response["cluster_name"], [])
                    # Create a new prompt for service matching within the cluster
                    service_prompt = f"""
    Given the following services in cluster {response["cluster_name"]}, find the best matching service for "{service_name}":

    Available services:
    {json.dumps(cluster_services, indent=2)}

    Format your response as a JSON object with:
    {{
        "service_name": "best matching service name or null"
    }}
    """
                    # Call GPT4-mini again for service matching
                    service_llm_response = await self.call_llm(service_prompt)
                    service_matches = json.loads(service_llm_response)
                    response["service_name"] = service_matches.get("service_name")
                
                # Cache the result
                self._name_matching_cache[cache_key] = response
                
            except Exception as e:
                logger.error(f"Error in LLM processing: {str(e)}")
                # Fall back to basic matching if LLM fails
                if cluster_name:
                    response["cluster_name"] = self.find_best_match_basic(cluster_name, list(cluster_service_map.keys()))
                if service_name:
                    if response["cluster_name"]:
                        services_to_search = cluster_service_map[response["cluster_name"]]
                    else:
                        services_to_search = list(cluster_service_map.keys())
                    response["service_name"] = self.find_best_match_basic(service_name, services_to_search)

            return response

        except Exception as e:
            logger.error(f"Error finding matching names: {str(e)}")
            return {
                "status": "error",
                "message": f"Failed to find matching names: {str(e)}"
            }

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
        Call GPT4-mini using LiteLLM to find matching names.
        
        Args:
            prompt (str): The prompt to send to the LLM
            
        Returns:
            str: JSON string containing the LLM's response with cluster_name and service_name
        """
        try:
            # Note: completion is synchronous, so we don't await it
            response = completion(
                model=self.model,
                api_key=self.openai_api_key,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that finds the best matching ECS cluster and service names. Always respond with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            response_content = response.choices[0].message.content
            
            try:
                json.loads(response_content)
                return response_content
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON response from LLM: {str(e)}")
                return json.dumps({
                    "cluster_name": None,
                    "service_name": None
                })
                
        except Exception as e:
            logger.error(f"Error calling LLM: {str(e)}")
            return json.dumps({
                "cluster_name": None,
                "service_name": None
            })