# DevOps Agent Kubernetes Deployment Guide

## Overview

This directory contains all Kubernetes manifests for deploying the DevOps Agent with:
- **Kubernetes deployments** instead of Docker Compose
- **NetworkPolicies** for network segmentation
- **Redis** for caching and rate-limiting
- **Vault** for secrets management
- **mTLS** for secure service-to-service communication

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   Vault     │  │   Redis     │  │   Agent     │              │
│  │  (Secrets)  │──│ (Cache/RL)  │──│  (API)      │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│         │                │                │                      │
│         │                │                │                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  Postgres   │  │   Neo4j     │  │   Qdrant    │              │
│  │   (DB)      │  │  (Graph)    │  │  (Vector)   │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│                                                                  │
│  All communication secured with mTLS                            │
│  Network Policies restrict traffic flow                         │
└─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

1. Kubernetes cluster (v1.25+)
2. kubectl configured
3. Helm v3.x
4. cert-manager installed
5. CSI Secrets Store Driver installed

## Installation Steps

### 1. Create Namespace

```bash
kubectl apply -f namespaces/devops-agent.yaml
```

### 2. Install cert-manager (if not installed)

```bash
helm repo add jetstack https://charts.jetstack.io
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --set installCRDs=true
```

### 3. Deploy Storage PVCs

```bash
kubectl apply -f storage/pvc.yaml
```

### 4. Deploy Vault

```bash
# Apply Vault manifests
kubectl apply -f vault/vault-deployment.yaml
kubectl apply -f vault/vault-agent-injector.yaml

# Wait for Vault to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=vault -n vault --timeout=300s

# Setup Vault authentication
kubectl apply -f vault/vault-auth-setup.yaml

# Apply mTLS certificates
kubectl apply -f cert-manager/mtls-certificates.yaml

# Apply Secret Provider Class
kubectl apply -f vault/secret-provider-class.yaml
```

### 5. Deploy Redis

```bash
# Apply Redis configuration
kubectl apply -f redis/redis-config.yaml

# Deploy Redis
kubectl apply -f deployments/redis.yaml
kubectl apply -f services/redis.yaml
kubectl apply -f secrets/redis-secrets.yaml
```

### 6. Deploy Databases

```bash
# Postgres
kubectl apply -f deployments/postgres.yaml
kubectl apply -f services/postgres.yaml
kubectl apply -f configmaps/postgres-config.yaml
kubectl apply -f secrets/postgres-secrets.yaml

# Neo4j
kubectl apply -f deployments/neo4j.yaml
kubectl apply -f services/neo4j.yaml
kubectl apply -f configmaps/neo4j-config.yaml
kubectl apply -f secrets/neo4j-secrets.yaml

# Qdrant
kubectl apply -f deployments/qdrant.yaml
kubectl apply -f services/qdrant.yaml
```

### 7. Deploy Application Components

```bash
# Service Account
kubectl apply -f deployments/serviceaccount.yaml
kubectl apply -f deployments/docker-executor-sa.yaml

# Agent
kubectl apply -f deployments/agent.yaml
kubectl apply -f services/agent.yaml
kubectl apply -f configmaps/agent-config.yaml
kubectl apply -f secrets/agent-secrets.yaml

# Worker
kubectl apply -f deployments/worker.yaml

# Docker Executor
kubectl apply -f deployments/docker-executor.yaml
kubectl apply -f services/docker-executor.yaml
```

### 8. Apply Network Policies

```bash
# Default deny all
kubectl apply -f networkpolicies/default-deny-all.yaml

# Allow specific traffic
kubectl apply -f networkpolicies/allow-agent-ingress.yaml
kubectl apply -f networkpolicies/allow-agent-egress.yaml
kubectl apply -f networkpolicies/allow-postgres-ingress.yaml
kubectl apply -f networkpolicies/allow-neo4j-ingress.yaml
kubectl apply -f networkpolicies/allow-qdrant-ingress.yaml
kubectl apply -f networkpolicies/allow-redis-ingress.yaml
kubectl apply -f networkpolicies/allow-vault-ingress.yaml
kubectl apply -f networkpolicies/allow-docker-executor-ingress.yaml
kubectl apply -f networkpolicies/allow-mtls-communication.yaml
```

## Verification

### Check all pods are running

```bash
kubectl get pods -n devops-agent
```

### Verify mTLS certificates

```bash
kubectl get certificates -n devops-agent
kubectl get certificates -n vault
```

### Test Redis connectivity

```bash
kubectl exec -it deploy/redis -n devops-agent -- redis-cli -a $(kubectl get secret redis-secrets -n devops-agent -o jsonpath='{.data.REDIS_PASSWORD}' | base64 -d) ping
```

### Test Vault connectivity

```bash
kubectl exec -it vault-0 -n vault -- vault status
```

### Verify Network Policies

```bash
kubectl get networkpolicies -n devops-agent
```

## Redis Usage

### Caching

Redis is configured for caching frequent requests with LRU eviction:

```python
import redis

redis_client = redis.Redis(
    host='redis.devops-agent.svc.cluster.local',
    port=6379,
    password='your_password',
    decode_responses=True
)

# Cache with TTL
redis_client.setex('key', 300, 'value')  # 5 minutes TTL

# Get cached value
value = redis_client.get('key')
```

### Rate Limiting

Use the Lua script for atomic rate limiting:

```python
RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])

local current = redis.call('GET', key)

if current == false then
    redis.call('SET', key, 1, 'EX', window)
    return {1, 1, window}
end

current = tonumber(current)

if current >= limit then
    local ttl = redis.call('TTL', key)
    return {0, current, ttl}
end

redis.call('INCR', key)
local ttl = redis.call('TTL', key)
return {1, current + 1, ttl}
"""

rate_limit_script = redis_client.register_script(RATE_LIMIT_SCRIPT)

# Check rate limit (100 requests per 60 seconds)
allowed, count, ttl = rate_limit_script(keys=['ratelimit:user123:api'], args=[100, 60])

if allowed == 1:
    # Process request
    pass
else:
    # Rate limited
    pass
```

## Vault Integration

### Accessing Secrets in Pods

Pods annotated with Vault annotations automatically receive secrets:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  template:
    metadata:
      annotations:
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/agent-inject-secret-db-credentials.txt: "secret/data/devops/database"
        vault.hashicorp.com/role: "devops-agent"
    spec:
      containers:
        - name: app
          volumeMounts:
            - name: vault-secrets
              mountPath: /vault/secrets
              readOnly: true
```

### Updating Secrets in Vault

```bash
# Update database password
kubectl exec -it vault-0 -n vault -- vault kv put secret/data/devops/database \
  postgres_password="new_secure_password" \
  neo4j_password="new_neo4j_password" \
  gitlab_token="new_gitlab_token"
```

## Security Features

### mTLS Configuration

All services communicate using mutual TLS:
- Certificates issued by cert-manager
- Automatic certificate rotation
- Client certificate verification

### Network Policies

- Default deny all ingress/egress
- Explicit allow rules for required communication
- Isolation between components

### Secrets Management

- No secrets in environment variables or config files
- Vault Agent automatic injection
- Automatic secret rotation support

## Troubleshooting

### Vault Issues

```bash
# Check Vault logs
kubectl logs vault-0 -n vault

# Verify Vault is unsealed
kubectl exec -it vault-0 -n vault -- vault status

# Check Vault Agent Injector
kubectl logs -l app.kubernetes.io/name=vault-agent-injector -n vault
```

### Redis Issues

```bash
# Check Redis logs
kubectl logs deploy/redis -n devops-agent

# Test Redis connection
kubectl exec -it deploy/redis -n devops-agent -- redis-cli ping
```

### mTLS Issues

```bash
# Check certificate status
kubectl get certificates -A

# Describe certificate for errors
kubectl describe certificate devops-agent-mtls -n devops-agent
```

### Network Policy Issues

```bash
# Test connectivity between pods
kubectl exec -it agent-pod -n devops-agent -- curl -v https://redis.devops-agent.svc.cluster.local:6379

# Check network policy applied
kubectl get networkpolicy allow-redis-ingress -n devops-agent -o yaml
```

## Maintenance

### Backup Vault

```bash
kubectl exec -it vault-0 -n vault -- vault operator raft snapshot save /tmp/snapshot.snap
kubectl cp vault-0:/tmp/snapshot.snap ./vault-snapshot.snap -n vault
```

### Rotate Certificates

```bash
# Delete certificate secret to trigger renewal
kubectl delete secret devops-agent-mtls -n devops-agent
```

### Scale Redis

For read-heavy workloads, consider adding Redis replicas:

```bash
kubectl scale deployment redis --replicas=3 -n devops-agent
```

## Monitoring

All components expose Prometheus metrics:
- Vault: `/v1/sys/metrics`
- Redis: Enable via redis-exporter sidecar
- Application: `/metrics` endpoint

Configure ServiceMonitors for Prometheus discovery.
