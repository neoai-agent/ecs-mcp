# AWS ECS MCP Server

A Model Context Protocol (MCP) server for monitoring and analyzing AWS ECS (Elastic Container Service) metrics and services.

## Features

- **ECS Service Monitoring**: Check service status, health, and deployment information
- **CloudWatch Metrics**: Get CPU, memory, and custom metrics for ECS services
- **Load Balancer Integration**: Monitor target group health and response times
- **IAM Role Support**: Works seamlessly with EC2 instance roles and ECS task roles
- **Intelligent Name Matching**: Uses AI to find the correct cluster and service names

## Installation

Install directly from GitHub using pipx:

```bash
# Install
pipx install git+https://github.com/neoai-agent/ecs-mcp.git

# Or run without installation
pipx run git+https://github.com/neoai-agent/ecs-mcp.git
```

## Quick Start

### On EC2 with IAM Role (Recommended)
```bash
ecs-mcp --openai-api-key "YOUR_OPENAI_API_KEY" --region "YOUR_AWS_REGION"
```

### With Explicit AWS Credentials
```bash
ecs-mcp --openai-api-key "YOUR_OPENAI_API_KEY" --access-key "YOUR_AWS_ACCESS_KEY" --secret-access-key "YOUR_AWS_SECRET_KEY" --region "YOUR_AWS_REGION"
```

## Available Tools

The server provides the following tools for AWS ECS analysis:

1. **check_ecs_service_status**: Get comprehensive service status including:
   - Running vs desired task count
   - Deployment status
   - Container images
   - Target group health
   - Unhealthy tasks

2. **get_service_metrics**: Get CloudWatch metrics for ECS services:
   - CPU utilization
   - Memory utilization
   - Custom metrics

3. **get_ecs_target_group_response_time**: Monitor load balancer response times

4. **get_ecs_target_group_request_metrics**: Get request count and error metrics

5. **get_ecs_services**: List all services in a cluster

## IAM Permissions

For EC2 instance role or ECS task role:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ecs:ListClusters",
                "ecs:DescribeClusters",
                "ecs:ListServices",
                "ecs:DescribeServices",
                "ecs:ListTasks",
                "ecs:DescribeTasks",
                "ecs:DescribeTaskDefinition",
                "elasticloadbalancing:DescribeTargetHealth",
                "cloudwatch:GetMetricData",
                "cloudwatch:GetMetricStatistics"
            ],
            "Resource": "*"
        }
    ]
}
```

## Development

For development setup:
```bash
git clone https://github.com/neoai-agent/ecs-mcp.git
cd ecs-mcp
python -m venv ecs-venv
source ecs-venv/bin/activate  # On Windows: ecs-venv\Scripts\activate
pip install -e ".[dev]"
```

## License

MIT License - See [LICENSE](LICENSE) file for details
