#!/bin/bash
set -euo pipefail

# Create Kubernetes ConfigMaps and Secrets for the Query Engine.
#
# Required env vars (from .env):
#   NEO4J_PASSWORD, POSTGRES_PASSWORD, OPENAI_API_KEY, GCS_CREDENTIALS_JSON
#
# Optional env vars:
#   GCS_BUCKET, LLM_MODEL, EMBEDDING_MODEL, etc.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${1:-$SCRIPT_DIR/../.env}"

if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

: "${GCP_PROJECT:?GCP_PROJECT is required}"
: "${GCP_ZONE:?GCP_ZONE is required}"
: "${NEO4J_PASSWORD:?NEO4J_PASSWORD is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${OPENAI_API_KEY:?OPENAI_API_KEY is required}"
: "${GCS_CREDENTIALS_JSON:?GCS_CREDENTIALS_JSON is required}"

CLUSTER_NAME="${GKE_CLUSTER_NAME:-query-engine}"
NAMESPACE="${QE_NAMESPACE:-query-engine}"

# Ensure kubectl is connected to the correct cluster
EXPECTED_CONTEXT="gke_${GCP_PROJECT}_${GCP_ZONE}_${CLUSTER_NAME}"
CURRENT_CONTEXT=$(kubectl config current-context 2>/dev/null || echo "none")
if [ "$CURRENT_CONTEXT" != "$EXPECTED_CONTEXT" ]; then
    echo "Switching kubectl context to $EXPECTED_CONTEXT..."
    gcloud container clusters get-credentials "$CLUSTER_NAME" \
        --project "$GCP_PROJECT" \
        --zone "$GCP_ZONE"
fi

echo "Creating ConfigMaps and Secrets in namespace '$NAMESPACE'..."

# --- Query Engine ConfigMap ---
kubectl create configmap query-engine-config \
    --namespace "$NAMESPACE" \
    --from-literal=DEBUG=false \
    --from-literal=LOG_LEVEL=info \
    --from-literal=LLM_MODEL="${LLM_MODEL:-gpt-4o-mini}" \
    --from-literal=LLM_TEMPERATURE="${LLM_TEMPERATURE:-0.0}" \
    --from-literal=EMBEDDING_MODEL="${EMBEDDING_MODEL:-text-embedding-3-small}" \
    --from-literal=MAX_TRIPLETS_PER_CHUNK="${MAX_TRIPLETS_PER_CHUNK:-10}" \
    --from-literal=CHUNK_SIZE="${CHUNK_SIZE:-1024}" \
    --from-literal=NEO4J_URI="bolt://neo4j.${NAMESPACE}.svc.cluster.local:7687" \
    --from-literal=NEO4J_USERNAME=neo4j \
    --from-literal=NEO4J_DATABASE=neo4j \
    --from-literal=NEO4J_ENABLED=true \
    --from-literal=POSTGRES_URI="postgresql://postgres:${POSTGRES_PASSWORD}@postgres.${NAMESPACE}.svc.cluster.local:5432/query_engine" \
    --from-literal=POSTGRES_ENABLED=true \
    --from-literal=EMBED_DIM=1536 \
    --from-literal=CELERY_BROKER_URL="redis://redis.${NAMESPACE}.svc.cluster.local:6379/0" \
    --from-literal=GCS_BUCKET="${GCS_BUCKET:-query-engine-upload-data}" \
    --from-literal=CACHE_TTL_SECONDS="${CACHE_TTL_SECONDS:-86400}" \
    --from-literal=CACHE_SIMILARITY_THRESHOLD="${CACHE_SIMILARITY_THRESHOLD:-0.95}" \
    --from-literal=RATE_LIMIT_DEFAULT="${RATE_LIMIT_DEFAULT:-60/minute}" \
    --from-literal=RATE_LIMIT_QUERY="${RATE_LIMIT_QUERY:-30/minute}" \
    --from-literal=RATE_LIMIT_INGEST="${RATE_LIMIT_INGEST:-10/minute}" \
    --dry-run=client -o yaml | kubectl apply -f -

# --- Query Engine Secrets ---
kubectl create secret generic query-engine-secrets \
    --namespace "$NAMESPACE" \
    --from-literal=NEO4J_PASSWORD="$NEO4J_PASSWORD" \
    --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY" \
    --from-literal=GCS_CREDENTIALS_JSON="$GCS_CREDENTIALS_JSON" \
    --dry-run=client -o yaml | kubectl apply -f -

# --- Neo4j Auth Secret (for StatefulSet) ---
kubectl create secret generic neo4j-auth \
    --namespace "$NAMESPACE" \
    --from-literal=NEO4J_AUTH="neo4j/$NEO4J_PASSWORD" \
    --dry-run=client -o yaml | kubectl apply -f -

# --- Postgres Auth Secret (for StatefulSet) ---
kubectl create secret generic postgres-auth \
    --namespace "$NAMESPACE" \
    --from-literal=POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
    --dry-run=client -o yaml | kubectl apply -f -

# --- UI ConfigMap (empty for now — Nginx proxies API calls) ---
kubectl create configmap query-engine-ui-config \
    --namespace "$NAMESPACE" \
    --dry-run=client -o yaml | kubectl apply -f -

echo "ConfigMaps and Secrets created."
