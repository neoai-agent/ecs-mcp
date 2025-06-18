from datetime import datetime, timezone, timedelta
from typing import Dict
import logging
from mcp.server.fastmcp import FastMCP
from ecs_mcp.client import ECSClient, AWSClientManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('ecs_mcp')


class ECSMCPServer:
    def __init__(self, model: str, openai_api_key: str, aws_client_manager: AWSClientManager):
        self.mcp = FastMCP("ecs-mcp")
        self.client = ECSClient(model=model, openai_api_key=openai_api_key, aws_client_manager=aws_client_manager)
        self._register_tools()

    def _register_tools(self):
        """Register all MCP tools with the ECS MCP server"""
        self.mcp.tool()(self.check_ecs_service_status)
        self.mcp.tool()(self.get_service_metrics)
        self.mcp.tool()(self.get_ecs_target_group_response_time)
        self.mcp.tool()(self.get_ecs_target_group_request_metrics)
        self.mcp.tool()(self.get_ecs_services)

    def run_mcp_blocking(self):
        """
        Runs the FastMCP server. This method is blocking and should be called
        after any necessary asynchronous initialization (like self.client.initialize_ecs)
        has been completed in a separate AnyIO event loop.
        """
        # self.client.initialize_ecs() is assumed to have been awaited
        # before this synchronous method is called.
        
        # The FastMCP server's run method will internally call anyio.run()
        # and manage its own event loop for stdio transport.
        self.mcp.run(transport='stdio')

    async def check_ecs_service_status(self, service_name: str):
        """Check ECS service status with container images and target group health
        Args:
            service_name: The name of the service to check
        Returns:
            A dictionary containing the service name, cluster name, status, target health, and unhealthy tasks
        """
        try:
            matches = await self.client.find_matching_names(service_name=service_name)
            logger.info(f"Matches: {matches}")
            if not matches.get("cluster_name") or not matches.get("service_name"):
                return {
                    "error": "Invalid names provided",
                    "status": "error"
                }
            
            correct_cluster = matches["cluster_name"]
            correct_service = matches["service_name"]

            logger.info(f"Correct cluster: {correct_cluster}")
            logger.info(f"Correct service: {correct_service}")
            
            service_response = self.client.ecs_client.describe_services(
                cluster=correct_cluster,
                services=[correct_service]
            )
            logger.info(f"Service response: {service_response}")
            
            if not service_response['services']:
                return {
                    "error": f"Service '{correct_service}' not found in cluster '{correct_cluster}'",
                    "status": "not_found"
                }
                
            if service_response['failures']:
                failure = service_response['failures'][0]
                return {
                    "error": f"Service error: {failure.get('reason', 'Unknown error')}",
                    "status": "error"
                }
                
            service = service_response['services'][0]
            
            primary_deployment = next((d for d in service['deployments'] if d['status'] == 'PRIMARY'), None)
            task_def_arn = primary_deployment['taskDefinition'] if primary_deployment else None
            
            container_images = []
            if task_def_arn:
                task_def = self.client.ecs_client.describe_task_definition(
                    taskDefinition=task_def_arn
                )['taskDefinition']
                container_images = [
                    {
                        "name": container['name'],
                        "image": container['image'].replace(
                            container['image'].split('.')[0],
                            '******'
                        ) if container.get('image') else 'Unknown'
                    }
                    for container in task_def['containerDefinitions']
                ]
            
            status = {
                "running_count": service['runningCount'],
                "desired_count": service['desiredCount'],
                "deployment": {
                    "status": primary_deployment['rolloutState'] if primary_deployment else 'No active deployment',
                    "completed": primary_deployment['runningCount'] if primary_deployment else 0,
                    "pending": primary_deployment['pendingCount'] if primary_deployment else 0,
                    "failed": primary_deployment['failedTasks'] if primary_deployment else 0,
                    "task_definition": task_def_arn.split('/')[-1] if task_def_arn else None,
                    "containers": container_images
                }
            }
            
            # Get target group health
            target_health = []
            if 'loadBalancers' in service:
                for lb in service['loadBalancers']:
                    if 'targetGroupArn' in lb:
                        health = self.client.elbv2_client.describe_target_health(
                            TargetGroupArn=lb['targetGroupArn']
                        )['TargetHealthDescriptions']
                        
                        unhealthy = [t for t in health if t['TargetHealth']['State'] != 'healthy']
                        if unhealthy:
                            target_health.append({
                                "healthy_count": len(health) - len(unhealthy),
                                "unhealthy_count": len(unhealthy),
                                "unhealthy_targets": [
                                    {
                                        "id": t['Target']['Id'],
                                        "state": t['TargetHealth']['State'],
                                        "reason": t['TargetHealth'].get('Reason', '')
                                    }
                                    for t in unhealthy
                                ]
                            })
            
            service_healthy = (
                status['running_count'] == status['desired_count'] and
                status['deployment']['status'] in ['COMPLETED', 'IN_PROGRESS'] and
                not target_health
            )
            
            if not service_healthy:
                running_tasks = self.client.ecs_client.list_tasks(
                    cluster=correct_cluster,
                    serviceName=correct_service,
                    desiredStatus='RUNNING'
                )
                
                if running_tasks['taskArns']:
                    tasks = self.client.ecs_client.describe_tasks(
                        cluster=correct_cluster,
                        tasks=running_tasks['taskArns']
                    )['tasks']
                    
                    unhealthy_tasks = [
                        {
                            "task_id": task['taskArn'].split('/')[-1],
                            "status": task['lastStatus'],
                            "unhealthy_containers": [
                                {
                                    "name": c['name'],
                                    "status": c.get('lastStatus'),
                                    "reason": c.get('reason', 'No reason provided')
                                }
                                for c in task['containers']
                                if c.get('lastStatus') != 'RUNNING'
                            ]
                        }
                        for task in tasks
                        if any(c.get('lastStatus') != 'RUNNING' for c in task['containers'])
                    ]
                else:
                    unhealthy_tasks = None
            else:
                unhealthy_tasks = None
            
            return {
                "service": correct_service,
                "cluster": correct_cluster,
                "status": status,
                "target_health": target_health if target_health else None,
                "unhealthy_tasks": unhealthy_tasks if 'unhealthy_tasks' in locals() else None
            }
            
        except Exception as e:
            logger.error(f"Error checking service status: {str(e)}")
            return {
                "error": f"Failed to check service status: {str(e)}",
                "status": "error"
            }

    async def get_service_metrics(self, service_name: str):
        """Get service-level CPU and memory metrics with min/max/avg and health status"""
        try:
            matches = await self.client.find_matching_names(service_name=service_name)
            if not matches.get("cluster_name") or not matches.get("service_name"):
                return {
                    "error": "Invalid service name provided",
                    "status": "error"
                }
            
            correct_cluster = matches["cluster_name"]
            correct_service = matches["service_name"]
            
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(minutes=60)
            
            metrics = {
                'CPUUtilization': ['Average', 'Maximum', 'Minimum'],
                'MemoryUtilization': ['Average', 'Maximum', 'Minimum']
            }
            
            results = {}
            for metric_name, stats in metrics.items():
                response = self.client.cloudwatch_client.get_metric_statistics(
                    Namespace='AWS/ECS',
                    MetricName=metric_name,
                    Dimensions=[
                        {'Name': 'ClusterName', 'Value': correct_cluster},
                        {'Name': 'ServiceName', 'Value': correct_service}
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=300,  # 5-minute periods
                    Statistics=stats
                )
                
                if response['Datapoints']:
                    latest = max(response['Datapoints'], key=lambda x: x['Timestamp'])
                    results[metric_name.lower()] = {
                        'average': round(latest['Average'], 2),
                        'maximum': round(latest['Maximum'], 2),
                        'minimum': round(latest['Minimum'], 2)
                    }
                else:
                    results[metric_name.lower()] = None
            
            cpu_avg = results.get('cpuutilization', {}).get('average') if results.get('cpuutilization') else None
            memory_avg = results.get('memoryutilization', {}).get('average') if results.get('memoryutilization') else None
            
            if cpu_avg is None or memory_avg is None:
                health_status = "Unknown"
            elif cpu_avg > 90 or memory_avg > 90:
                health_status = "Critical"
            elif cpu_avg > 80 or memory_avg > 80:
                health_status = "Warning"
            else:
                health_status = "Healthy"
            
            return {
                "status": "success",
                "service": correct_service,
                "cluster": correct_cluster,
                "metrics": {
                    "cpu": results.get('cpuutilization'),
                    "memory": results.get('memoryutilization')
                },
                "health_status": health_status
            }
            
        except Exception as e:
            logger.error(f"Error getting service metrics: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

    async def get_ecs_target_group_response_time(self, service_name: str, period_minutes: int = 15) -> Dict:
        """Get response time metrics summary for all target groups"""
        try:
            matches = await self.client.find_matching_names(service_name=service_name)
            if not matches.get("cluster_name") or not matches.get("service_name"):
                return {
                    "error": "Invalid service name provided",
                    "status": "error"
                }
            
            correct_cluster = matches["cluster_name"]
            correct_service = matches["service_name"]
            
            service = self.client.ecs_client.describe_services(
                cluster=correct_cluster,
                services=[correct_service]
            )['services'][0]
            
            if 'loadBalancers' not in service or not service['loadBalancers']:
                return {"status": "error", "message": "No target group found for this service"}
                
            target_group_arn = service['loadBalancers'][0]['targetGroupArn']
            target_group_info = self.client.elbv2_client.describe_target_groups(
                TargetGroupArns=[target_group_arn]
            )['TargetGroups'][0]
            
            load_balancer_arn = target_group_info['LoadBalancerArns'][0]
            load_balancer_name = load_balancer_arn.split('loadbalancer/')[-1]
            target_group_name = target_group_arn.split(':')[-1]
            
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(minutes=period_minutes)
            
            health = self.client.elbv2_client.describe_target_health(
                TargetGroupArn=target_group_arn
            )
            
            healthy_count = len([t for t in health['TargetHealthDescriptions'] 
                            if t['TargetHealth']['State'] == 'healthy'])
            total_count = len(health['TargetHealthDescriptions'])

            response = self.client.cloudwatch_client.get_metric_data(
                MetricDataQueries=[
                    {
                        'Id': 'avg',
                        'MetricStat': {
                            'Metric': {
                                'Namespace': 'AWS/ApplicationELB',
                                'MetricName': 'TargetResponseTime',
                                'Dimensions': [
                                    {'Name': 'LoadBalancer', 'Value': load_balancer_name},
                                    {'Name': 'TargetGroup', 'Value': target_group_name}
                                ]
                            },
                            'Period': 300, #5 minutes
                            'Stat': 'Average'
                        }
                    }
                ],
                StartTime=start_time,
                EndTime=end_time
            )
            
            if not response['MetricDataResults'][0]['Values']:
                return {
                    "status": "warning",
                    "message": "No response time data available"
                }
                
            values = response['MetricDataResults'][0]['Values']
            timestamps = response['MetricDataResults'][0]['Timestamps']
            data_points = sorted(zip(timestamps, values), key=lambda x: x[0])
            
            latest = data_points[-1]
            max_point = max(data_points, key=lambda x: x[1])
            min_point = min(data_points, key=lambda x: x[1])
            
            current_avg = round(latest[1] * 1000, 2)
            max_value = round(max_point[1] * 1000, 2)
            min_value = round(min_point[1] * 1000, 2)
            
            return {
                "status": "success",
                "service_name": correct_service,
                "cluster_name": correct_cluster,
                "response_times_ms": {
                    "current_average": current_avg,
                    "maximum": {
                        "value": max_value,
                        "timestamp": max_point[0].strftime("%Y-%m-%d %H:%M:%S UTC"),
                        "time_ago": f"{int((end_time - max_point[0]).total_seconds() / 60)} minutes ago"
                    },
                    "minimum": {
                        "value": min_value,
                        "timestamp": min_point[0].strftime("%Y-%m-%d %H:%M:%S UTC"),
                        "time_ago": f"{int((end_time - min_point[0]).total_seconds() / 60)} minutes ago"
                    }
                },
                "target_health": {
                    "healthy_count": healthy_count,
                    "total_count": total_count,
                    "health_percentage": round((healthy_count/total_count * 100), 1) if total_count > 0 else 0
                },
                "time_range": f"Last {period_minutes} minutes"
            }
            
        except Exception as e:
            print(f"Error getting response time metrics: {e}")
            return {
                "status": "error",
                "message": f"Failed to get response time metrics: {str(e)}"
            }

    #Get overall HTTP status codes count and total request count summary
    async def get_ecs_target_group_request_metrics(self, service_name: str, period_minutes: int = 15) -> Dict:
        """Get overall HTTP status codes count and total request count summary for all target groups"""
        try:
            matches = await self.client.find_matching_names(service_name=service_name)
            if not matches.get("cluster_name") or not matches.get("service_name"):
                return {
                    "error": "Invalid service name provided",
                    "status": "error"
                }
            
            correct_cluster = matches["cluster_name"]
            correct_service = matches["service_name"]
            
            service = self.client.ecs_client.describe_services(
                cluster=correct_cluster,
                services=[correct_service]
            )['services'][0]
            
            if 'loadBalancers' not in service or not service['loadBalancers']:
                return {"status": "error", "message": "No target groups found for this service"}
                
            target_groups_metrics = []
            for load_balancer in service['loadBalancers']:
                target_group_arn = load_balancer['targetGroupArn']
                
                target_group_info = self.client.elbv2_client.describe_target_groups(
                    TargetGroupArns=[target_group_arn]
                )['TargetGroups'][0]
                
                load_balancer_arn = target_group_info['LoadBalancerArns'][0]
                load_balancer_name = load_balancer_arn.split('loadbalancer/')[-1]
                target_group_name = target_group_arn.split(':')[-1]
                
                start_time = datetime.now(timezone.utc) - timedelta(minutes=period_minutes)
                end_time = datetime.now(timezone.utc)
                
                metrics = {
                    '2XX': 'HTTPCode_Target_2XX_Count',
                    '3XX': 'HTTPCode_Target_3XX_Count',
                    '4XX': 'HTTPCode_Target_4XX_Count',
                    '5XX': 'HTTPCode_Target_5XX_Count',
                    'total': 'RequestCount',
                    'request_count_per_target': 'RequestCountPerTarget'
                }
                
                results = {}
                for name, metric in metrics.items():
                    response = self.client.cloudwatch_client.get_metric_statistics(
                        Namespace='AWS/ApplicationELB',
                        MetricName=metric,
                        Dimensions=[
                            {'Name': 'LoadBalancer', 'Value': load_balancer_name},
                            {'Name': 'TargetGroup', 'Value': target_group_name}
                        ],
                        StartTime=start_time,
                        EndTime=end_time,
                        Period=period_minutes * 60,
                        Statistics=['Sum']
                    )
                    
                    total = sum(point['Sum'] for point in response['Datapoints']) if response['Datapoints'] else 0
                    results[name] = int(total)
                
                target_health = self.client.elbv2_client.describe_target_health(
                    TargetGroupArn=target_group_arn
                )['TargetHealthDescriptions']
                
                healthy_count = sum(1 for t in target_health if t['TargetHealth']['State'] == 'healthy')
                total_count = len(target_health)
                
                target_groups_metrics.append({
                    "target_group_name": target_group_name,
                    "metrics": {
                        "status_codes": {
                            "2xx": results['2XX'],
                            "3xx": results['3XX'],
                            "4xx": results['4XX'],
                            "5xx": results['5XX']
                        },
                        "requests": {
                            "total": results['total'],
                            "per_target": results['request_count_per_target']
                        },
                        "target_health": {
                            "healthy_count": healthy_count,
                            "total_count": total_count,
                            "health_percentage": (healthy_count / total_count * 100) if total_count > 0 else 0
                        }
                    }
                })
            
            total_metrics = {
                "2xx": sum(tg["metrics"]["status_codes"]["2xx"] for tg in target_groups_metrics),
                "3xx": sum(tg["metrics"]["status_codes"]["3xx"] for tg in target_groups_metrics),
                "4xx": sum(tg["metrics"]["status_codes"]["4xx"] for tg in target_groups_metrics),
                "5xx": sum(tg["metrics"]["status_codes"]["5xx"] for tg in target_groups_metrics),
                "total_requests": sum(tg["metrics"]["requests"]["total"] for tg in target_groups_metrics)
            }
            
            return {
                "status": "success",
                "service_name": correct_service,
                "cluster_name": correct_cluster,
                "period_minutes": period_minutes,
                "target_groups": target_groups_metrics,
                "aggregated_metrics": total_metrics,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting target group metrics: {str(e)}")
            return {"status": "error", "message": str(e)}

    async def get_ecs_services(self, cluster_name: str):
        """Get all services in an ECS cluster and their names"""
        try:    
            matches = await self.client.find_matching_names(cluster_name=cluster_name)
            if not matches.get("cluster_name"):
                return {
                    "error": "Invalid cluster name provided",
                    "status": "error"
                }
            
            correct_cluster = matches["cluster_name"]
            
            services = []
            next_token = None

            while True:
                if next_token:
                    response = self.client.ecs_client.list_services(cluster=correct_cluster, nextToken=next_token)
                else:
                    response = self.client.ecs_client.list_services(cluster=correct_cluster)
                
                services.extend(response['serviceArns'])
                next_token = response.get('nextToken')
                if not next_token:
                    break

            service_names = [arn.split("/")[-1] for arn in services]
            
            return {
                "status": "success",
                "cluster": correct_cluster,
                "services": service_names,
                "service_count": len(service_names)
            }
            
        except Exception as e:
            logger.error(f"Error getting ECS services: {str(e)}")
            return {
                "error": f"Failed to get ECS services: {str(e)}",
                "status": "error"
            }