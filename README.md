# AWS ECS MCP Server

A command-line tool for monitoring and analyzing AWS ECS (Elastic Container Service) metrics using MCP (Model Control Protocol).

## Installation

Install directly from GitHub using pipx:

```bash
# Install
pipx install git+https://github.com/yourusername/ecs-mcp.git

# Or run without installation
pipx run git+https://github.com/yourusername/ecs-mcp.git
```

## Quick Start

1. Set up your environment variables:

   **Method: Using .env file**
   ```bash
   # Create a .env file in your project directory
   cat > .env << EOL
   # AWS Credentials
   AWS_ACCESS_KEY_ID=your-aws-access-key-here
   AWS_SECRET_ACCESS_KEY=your-aws-secret-key-here
   AWS_REGION=your-aws-region-here
   
   # OpenAI Credentials
   OPENAI_API_KEY=your-openai-api-key-here
   
   # Optional: Model Configuration
   MODEL=openai/gpt-4o-mini
   EOL
   ```

2. Create `agent.yaml`:
```yaml
- name: "AWS ECS Agent"
  description: "Agent to monitor and analyze AWS ECS clusters and services"
  mcp_servers: 
    - name: "ECS MCP Server"
      args: ["--access-key=${AWS_ACCESS_KEY_ID}", "--secret-access-key=${AWS_SECRET_ACCESS_KEY}", "--region=${AWS_REGION}", "--openai-api-key=${OPENAI_API_KEY}"]
      command: "ecs-mcp"
  system_prompt: "You are a DevOps engineer specializing in AWS ECS monitoring and optimization. You can use the provided tools to analyze ECS clusters, services, and tasks. Use the tools precisely to gather valuable insights about cluster performance, service health, and resource utilization."
```

3. Run the server:
```bash
ecs-mcp --access-key "YOUR_AWS_ACCESS_KEY" --secret-access-key "YOUR_AWS_SECRET_KEY" --region "YOUR_AWS_REGION" --openai-api-key "YOUR_OPENAI_API_KEY"
```

## Available Tools

The server provides the following tools for AWS ECS analysis:

1. Get cluster details:
```python
await get_cluster_details(
    cluster_name="your-cluster-name"
)
```

2. Get service metrics:
```python
await get_service_metrics(
    cluster_name="your-cluster-name",
    service_name="your-service-name",
    time_range_minutes=30
)
```

3. Get task metrics:
```python
await get_task_metrics(
    cluster_name="your-cluster-name",
    service_name="your-service-name",
    time_range_minutes=30
)
```

4. Get container insights:
```python
await get_container_insights(
    cluster_name="your-cluster-name",
    service_name="your-service-name",
    time_range_minutes=30
)
```

5. Get load balancer metrics:
```python
await get_load_balancer_metrics(
    load_balancer_arn="your-load-balancer-arn",
    time_range_minutes=30
)
```

6. Get auto scaling metrics:
```python
await get_auto_scaling_metrics(
    cluster_name="your-cluster-name",
    service_name="your-service-name",
    time_range_minutes=30
)
```

## Development

For development setup:
```bash
git clone https://github.com/yourusername/ecs-mcp.git
cd ecs-mcp
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

## License

MIT License - See [LICENSE](LICENSE) file for details