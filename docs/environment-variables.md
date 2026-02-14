# K8s MCP Server Environment Variables

This document details all environment variables that can be configured when running the K8s MCP Server container.

## Core Server Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `K8S_MCP_TIMEOUT` | Default timeout for commands in seconds | `300` | No |
| `K8S_MCP_MAX_OUTPUT` | Maximum output size in characters | `100000` | No |
| `K8S_MCP_TRANSPORT` | Transport protocol: "stdio", "sse" (deprecated), or "streamable-http" | `stdio` | No |
| `K8S_CONTEXT` | Kubernetes context to use | *current context* | No |
| `K8S_NAMESPACE` | Default Kubernetes namespace | `default` | No |
| `K8S_MCP_SECURITY_MODE` | Security mode ("strict" or "permissive") | `strict` | No |
| `K8S_MCP_SECURITY_CONFIG` | Path to security configuration YAML file | `/app/security_config.yaml` | No |

## AWS EKS Configuration

| Variable | Description | Default | Required for EKS |
|----------|-------------|---------|-----------------|
| `AWS_PROFILE` | AWS profile to use for authentication | `default` | No |
| `AWS_REGION` | AWS region for EKS cluster | - | Yes, if not in kubeconfig |
| `AWS_ACCESS_KEY_ID` | AWS access key ID (alternative to profile) | - | Only if not using profile |
| `AWS_SECRET_ACCESS_KEY` | AWS secret access key (alternative to profile) | - | Only if not using profile |
| `AWS_SESSION_TOKEN` | AWS session token for temporary credentials | - | Only if using temporary credentials |

## GCP GKE Configuration

| Variable | Description | Default | Required for GKE |
|----------|-------------|---------|-----------------|
| `CLOUDSDK_CORE_PROJECT` | GCP project ID | - | Yes |
| `CLOUDSDK_COMPUTE_REGION` | GCP region | - | Yes, if not using zone |
| `CLOUDSDK_COMPUTE_ZONE` | GCP zone | - | Yes, if not using region |
| `USE_GKE_GCLOUD_AUTH_PLUGIN` | Enable GKE auth plugin | `True` | No (enabled by default) |

## Azure AKS Configuration

| Variable | Description | Default | Required for AKS |
|----------|-------------|---------|-----------------|
| `AZURE_SUBSCRIPTION` | Azure subscription ID | - | Yes |
| `AZURE_DEFAULTS_LOCATION` | Azure region | - | No |
| `AZURE_TENANT_ID` | Azure tenant ID (alternative to login) | - | Only if not using Azure CLI login |
| `AZURE_CLIENT_ID` | Azure client ID (alternative to login) | - | Only if not using Azure CLI login |
| `AZURE_CLIENT_SECRET` | Azure client secret (alternative to login) | - | Only if not using Azure CLI login |

## Docker Volume Mounts

| Volume | Container Path | Purpose | Required |
|--------|---------------|---------|----------|
| `~/.kube` | `/home/appuser/.kube` | Kubernetes configuration | Yes |
| `~/.aws` | `/home/appuser/.aws` | AWS credentials | Only for EKS |
| `~/.config/gcloud` | `/home/appuser/.config/gcloud` | GCP credentials | Only for GKE |
| `~/.azure` | `/home/appuser/.azure` | Azure credentials | Only for AKS |
| Custom security config | `/app/security_config.yaml` | Custom security rules | No |

## Usage Examples

### Basic Configuration
```bash
docker run -i --rm \
  -v ~/.kube:/home/appuser/.kube:ro \
  -e K8S_NAMESPACE=production \
  -e K8S_MCP_TIMEOUT=600 \
  ghcr.io/alexei-led/k8s-mcp-server:latest
```

### AWS EKS Configuration
```bash
docker run -i --rm \
  -v ~/.kube:/home/appuser/.kube:ro \
  -v ~/.aws:/home/appuser/.aws:ro \
  -e AWS_PROFILE=production \
  -e AWS_REGION=us-west-2 \
  ghcr.io/alexei-led/k8s-mcp-server:latest
```

### GCP GKE Configuration
```bash
docker run -i --rm \
  -v ~/.kube:/home/appuser/.kube:ro \
  -v ~/.config/gcloud:/home/appuser/.config/gcloud:ro \
  -e CLOUDSDK_CORE_PROJECT=my-project \
  -e CLOUDSDK_COMPUTE_REGION=us-central1 \
  ghcr.io/alexei-led/k8s-mcp-server:latest
```

### Azure AKS Configuration
```bash
docker run -i --rm \
  -v ~/.kube:/home/appuser/.kube:ro \
  -v ~/.azure:/home/appuser/.azure:ro \
  -e AZURE_SUBSCRIPTION=my-subscription-id \
  -e AZURE_DEFAULTS_LOCATION=eastus \
  ghcr.io/alexei-led/k8s-mcp-server:latest
```