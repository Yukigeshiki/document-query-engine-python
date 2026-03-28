# Deployment Guide

## Architecture

```
Internet → Cloudflare (DNS) → Traefik (LoadBalancer, port 443)
         → IngressRoute → query-engine-ui (Nginx, port 8080)
                          ├── /        → static Vue app
                          ├── /api/    → query-engine-api:8000
                          └── /health  → 200 ok

In-cluster (query-engine namespace):
  query-engine-api     FastAPI (port 8000)
  query-engine-worker  Celery worker
  query-engine-beat    Celery beat scheduler
  neo4j                Neo4j 5.26 (ports 7474, 7687)
  postgres             PostgreSQL 16 + pgvector (port 5432)
  redis                Redis 7 (port 6379)
```

TLS is terminated at Traefik using a Let's Encrypt certificate issued via cert-manager with Cloudflare DNS-01 challenge. Cloudflare is used for DNS only (grey cloud / no proxy) because the deep subdomain isn't covered by Cloudflare's universal SSL.

## Prerequisites

- `gcloud` CLI authenticated with `agent-playground-491316`
- `kubectl` and `helm` installed
- `docker` running (for building images)
- Environment variables exported in your shell:
  - `OPENAI_API_KEY`
  - `GCS_CREDENTIALS_JSON`
  - `NEO4J_PASSWORD`
  - `POSTGRES_PASSWORD`
  - `CLOUDFLARE_API_TOKEN`

## Deployment from Scratch

### 1. Configure

```bash
cp infra/.env.example infra/.env
# Fill in non-secret values (domain, email, GCS bucket, etc.)
# Secrets come from exported shell env vars (see Prerequisites)
```

### 2. Create GKE Cluster

```bash
./infra/scripts/create-k8s-cluster.sh
```

Optional: set `USE_SPOT_VMS=true` for ~60-70% cost savings, `RESERVE_STATIC_IP=true` for a static IP.

### 3. Set Up Infrastructure

```bash
./infra/scripts/setup-infra.sh
```

Enables GCP APIs, creates Artifact Registry, installs cert-manager and Traefik, deploys the platform chart (certificate, ingress route, Cloudflare DNS secret).

After this step, get the Traefik external IP and create a Cloudflare DNS record:

```bash
kubectl get svc -n traefik
```

Create an **A record** in Cloudflare pointing the domain to the external IP. **Important:** set the record to **DNS only** (grey cloud), not Proxied.

### 4. Create ConfigMaps and Secrets

```bash
./infra/scripts/create-k8s-maps.sh
```

Creates ConfigMaps for app config, Secrets for API keys and credentials, and auth Secrets for Neo4j and PostgreSQL.

### 5. Deploy Infrastructure Services

```bash
./infra/scripts/helm-deploy.sh neo4j
./infra/scripts/helm-deploy.sh postgres
./infra/scripts/helm-deploy.sh redis
```

Wait for all pods to be ready:

```bash
kubectl get pods -n query-engine -w
```

### 6. Deploy Application

```bash
./infra/scripts/helm-deploy.sh api
./infra/scripts/helm-deploy.sh ui
```

### 7. Verify

```bash
kubectl get pods -n query-engine
curl https://queryengine.alreadyhadthisdomainhandy.acses.ai/health
```

## Updating a Service

```bash
./infra/scripts/helm-deploy.sh api       # rebuilds + redeploys API, worker, and beat
./infra/scripts/helm-deploy.sh ui        # rebuilds + redeploys UI
```

## Teardown

```bash
./infra/scripts/delete-k8s-cluster.sh
```

Set `RESERVE_STATIC_IP=true` to also release the reserved static IP.
