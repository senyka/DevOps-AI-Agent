# Vault Configuration for DevOps Agent

## Overview
This directory contains HashiCorp Vault configuration for managing secrets in the DevOps Agent Kubernetes deployment.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Agent Pod     │────▶│  Vault Server   │────▶│  Secret Store   │
│  (with Vault    │     │  (dev mode for  │     │  (KV v2)        │
│   Agent)        │     │   production)   │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Components

### 1. Vault Server Deployment
- Runs in dev mode for development (NOT for production)
- For production, use HA mode with Consul/Raft storage
- Exposes port 8200 for API access

### 2. Vault Agent Injector
- Automatically injects secrets into pods
- Uses annotations on pod specifications
- Renders secrets as files or environment variables

### 3. Authentication Methods
- **Kubernetes Auth**: Pods authenticate using service account tokens
- **AppRole**: For external applications

## Setup Instructions

### 1. Install Vault Helm Chart
```bash
helm repo add hashicorp https://helm.releases.hashicorp.com
helm install vault hashicorp/vault -n devops-agent -f vault-values.yaml
```

### 2. Initialize Vault (Dev Mode)
```bash
kubectl exec -it vault-0 -n devops-agent -- vault operator init -key-shares=5 -key-threshold=3
kubectl exec -it vault-0 -n devops-agent -- vault operator unseal <key1>
kubectl exec -it vault-0 -n devops-agent -- vault operator unseal <key2>
kubectl exec -it vault-0 -n devops-agent -- vault operator unseal <key3>
```

### 3. Enable KV Secrets Engine
```bash
kubectl exec -it vault-0 -n devops-agent -- vault secrets enable -path=secret kv-v2
```

### 4. Configure Kubernetes Auth Method
```bash
# Enable Kubernetes auth method
kubectl exec -it vault-0 -n devops-agent -- vault auth enable kubernetes

# Configure Kubernetes auth
kubectl exec -it vault-0 -n devops-agent -- vault write auth/kubernetes/config \
  kubernetes_host="https://$KUBERNETES_PORT_443_TCP_ADDR:443" \
  kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt

# Create role for devops-agent
kubectl exec -it vault-0 -n devops-agent -- vault write auth/kubernetes/role/devops-agent \
  bound_service_account_names=devops-agent-sa \
  bound_service_account_namespaces=devops-agent \
  policies=devops-agent-policy \
  ttl=24h
```

### 5. Store Secrets
```bash
# Database credentials
kubectl exec -it vault-0 -n devops-agent -- vault kv put secret/data/devops/database \
  password="secure_password_change_me" \
  neo4j_password="neo4j_secure_password" \
  gitlab_token="gitlab_token_here"

# Redis credentials
kubectl exec -it vault-0 -n devops-agent -- vault kv put secret/data/devops/redis \
  password="redis_secure_password"
```

### 6. Create Policy
```bash
kubectl exec -it vault-0 -n devops-agent -- vault policy write devops-agent-policy - <<EOF
path "secret/data/devops/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/devops/*" {
  capabilities = ["list"]
}
EOF
```

## Security Considerations

### Production Checklist
- [ ] Use HA mode with Raft storage backend
- [ ] Enable TLS for all Vault communications
- [ ] Configure auto-unseal (AWS KMS, GCP KMS, Azure Key Vault)
- [ ] Enable audit logging
- [ ] Implement secret rotation
- [ ] Set up monitoring and alerting
- [ ] Regular backup strategy
- [ ] Network policies to restrict Vault access

### mTLS Configuration
For mutual TLS between components:
1. Generate certificates using cert-manager
2. Configure Vault with TLS certificates
3. Update all deployments to use TLS volumes
4. Enable TLS verification in application code

## Monitoring
- Prometheus metrics endpoint: `/v1/sys/metrics`
- Audit logs location: `/vault/logs/audit.log`

## Troubleshooting

### Common Issues
1. **Pod cannot authenticate**: Check service account binding
2. **Secret injection fails**: Verify annotations and role configuration
3. **Vault sealed**: Ensure unseal keys are provided

### Logs
```bash
kubectl logs vault-0 -n devops-agent
kubectl logs -l app=vault-agent-injector -n devops-agent
```
