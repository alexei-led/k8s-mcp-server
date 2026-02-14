# Multi-stage build with platform-specific configuration
ARG PYTHON_VERSION=3.13-slim

# =========== BUILDER STAGE ===========
FROM --platform=${TARGETPLATFORM} python:${PYTHON_VERSION} AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory
WORKDIR /build

# Copy package definition files
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

# Install package and dependencies with pip wheel
RUN pip install --no-cache-dir wheel && \
    pip wheel --no-cache-dir --wheel-dir=/wheels -e .

# =========== FINAL STAGE ===========
FROM --platform=${TARGETPLATFORM} python:${PYTHON_VERSION}

# Set target architecture argument
ARG TARGETPLATFORM
ARG TARGETARCH

# Step 1: Install system packages - keeping all original packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    unzip \
    curl \
    wget \
    less \
    groff \
    jq \
    gnupg \
    tar \
    gzip \
    zip \
    vim \
    net-tools \
    dnsutils \
    openssh-client \
    grep \
    sed \
    gawk \
    findutils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Step 2: Install kubectl based on architecture
# Use specific kubectl version (e.g., v1.33.0)
ARG KUBECTL_VERSION=v1.33.0
RUN if [ "${TARGETARCH}" = "arm64" ]; then \
        curl -LO "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/arm64/kubectl"; \
    else \
        curl -LO "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl"; \
    fi \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/

# Step 3: Install Helm
# Use specific Helm version

ARG HELM_VERSION=v3.17.3
RUN if [ "${TARGETARCH}" = "arm64" ]; then \
        curl -LO "https://get.helm.sh/helm-${HELM_VERSION}-linux-arm64.tar.gz" && \
        tar -zxvf helm-${HELM_VERSION}-linux-arm64.tar.gz && \
        mv linux-arm64/helm /usr/local/bin/helm && \
        rm -rf linux-arm64 helm-${HELM_VERSION}-linux-arm64.tar.gz; \
    else \
        curl -LO "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz" && \
        tar -zxvf helm-${HELM_VERSION}-linux-amd64.tar.gz && \
        mv linux-amd64/helm /usr/local/bin/helm && \
        rm -rf linux-amd64 helm-${HELM_VERSION}-linux-amd64.tar.gz; \
    fi && chmod +x /usr/local/bin/helm

# Step 4: Install istioctl
# Use specific Istio version
ARG ISTIO_VERSION=1.25.2
RUN if [ "${TARGETARCH}" = "arm64" ]; then \
        ISTIO_ARCH="arm64"; \
    else \
        ISTIO_ARCH="amd64"; \
    fi \
    && curl -L https://istio.io/downloadIstio | ISTIO_VERSION=${ISTIO_VERSION} TARGET_ARCH=${ISTIO_ARCH} sh - \
    && mv istio-*/bin/istioctl /usr/local/bin/ \
    && rm -rf istio-*

# Step 5: Install ArgoCD CLI
# Use specific ArgoCD version
ARG ARGOCD_VERSION=v2.14.11
RUN if [ "${TARGETARCH}" = "arm64" ]; then \
        curl -sSL -o argocd https://github.com/argoproj/argo-cd/releases/download/${ARGOCD_VERSION}/argocd-linux-arm64; \
    else \
        curl -sSL -o argocd https://github.com/argoproj/argo-cd/releases/download/${ARGOCD_VERSION}/argocd-linux-amd64; \
    fi \
    && chmod +x argocd \
    && mv argocd /usr/local/bin/

# Step 6: Install AWS CLI for EKS authentication
ARG AWS_CLI_VERSION=1.32.0
RUN pip install --no-cache-dir awscli==${AWS_CLI_VERSION} && \
    aws --version

# Step 7: Install minimal Google Cloud SDK for GKE authentication
ARG GCLOUD_VERSION=519.0.0
RUN if [ "${TARGETARCH}" = "arm64" ]; then \
        curl -O https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-linux-arm.tar.gz && \
        tar -xzf google-cloud-cli-linux-arm.tar.gz -C /opt && \
        rm google-cloud-cli-linux-arm.tar.gz; \
    else \
        curl -O https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-linux-x86_64.tar.gz && \
        tar -xzf google-cloud-cli-linux-x86_64.tar.gz -C /opt && \
        rm google-cloud-cli-linux-x86_64.tar.gz; \
    fi && \
    /opt/google-cloud-sdk/install.sh --quiet --usage-reporting=false --path-update=false \
        --additional-components gke-gcloud-auth-plugin && \
    ln -s /opt/google-cloud-sdk/bin/gcloud /usr/local/bin/gcloud && \
    ln -s /opt/google-cloud-sdk/bin/gke-gcloud-auth-plugin /usr/local/bin/gke-gcloud-auth-plugin && \
    # Set up GKE authentication plugin
    echo "export USE_GKE_GCLOUD_AUTH_PLUGIN=True" >> /etc/profile.d/gke_auth.sh && \
    gcloud --version

# Step 8: Install Azure CLI for AKS authentication
ARG AZURE_CLI_VERSION=2.71.0
RUN pip install --no-cache-dir azure-cli==${AZURE_CLI_VERSION} && \
    az --version

# Set up application directory, user, and permissions
RUN mkdir -p /app/logs && chmod 750 /app/logs \
    && groupadd -g 10001 appgroup \
    && useradd -m -s /bin/bash -u 10001 -g appgroup appuser \
    && mkdir -p /home/appuser/.kube \
    && mkdir -p /home/appuser/.aws \
    && mkdir -p /home/appuser/.config/gcloud \
    && mkdir -p /home/appuser/.azure \
    && chmod 700 /home/appuser/.kube \
    && chmod 700 /home/appuser/.aws \
    && chmod 700 /home/appuser/.config/gcloud \
    && chmod 700 /home/appuser/.azure

WORKDIR /app

# Copy application code
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
COPY deploy/docker/security_config.yaml ./security_config.yaml
# Copy wheels from builder and install
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels k8s-mcp-server && \
    rm -rf /wheels

# Set ownership after all files have been copied
RUN chown -R appuser:appgroup /app \
    && chown -R appuser:appgroup /home/appuser \
    && chmod -R o-rwx /app /home/appuser \
    && chmod 644 /app/security_config.yaml

# Switch to non-root user
USER appuser

# Set all environment variables in one layer
ENV HOME="/home/appuser" \
    PATH="/usr/local/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    K8S_MCP_TRANSPORT=stdio \
    K8S_MCP_SECURITY_MODE=strict \
    K8S_MCP_SECURITY_CONFIG=/app/security_config.yaml \
    USE_GKE_GCLOUD_AUTH_PLUGIN=True

# Add metadata following OCI Image Specification
LABEL maintainer="Alexei Ledenev" \
      description="Kubernetes Multi-Command Proxy Server" \
      org.opencontainers.image.title="K8s MCP Server" \
      org.opencontainers.image.description="Kubernetes Multi-Command Proxy Server for Anthropic's MCP" \
      org.opencontainers.image.authors="Alexei Ledenev" \
      org.opencontainers.image.vendor="Alexei Ledenev" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/alexei-led/k8s-mcp-server" \
      org.opencontainers.image.documentation="https://github.com/alexei-led/k8s-mcp-server/README.md" \
      org.opencontainers.image.version="1.3.0" \
      org.opencontainers.image.created="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# Expose the service port (only needed for HTTP transports: streamable-http or sse)
EXPOSE 8080

# Set command to run the server with proper signal handling
# The ENTRYPOINT format ensures proper signal forwarding to the Python process
ENTRYPOINT ["python", "-m", "k8s_mcp_server"]
