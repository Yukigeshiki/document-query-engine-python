#!/bin/bash
set -euo pipefail

# Build, push, and deploy a service to GKE.
#
# Usage: ./helm-deploy.sh <service> [options]
#
# Services: api, ui, neo4j, postgres, redis
#
# Options:
#   --namespace       Kubernetes namespace (default: query-engine)
#   --version         Image tag (default: git short SHA)
#   --cpu-request     CPU request override
#   --memory-request  Memory request override
#   --cpu-limit       CPU limit override
#   --memory-limit    Memory limit override

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env"

if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

: "${GCP_PROJECT:?GCP_PROJECT is required}"
: "${GCP_ZONE:?GCP_ZONE is required}"

# Ensure kubectl is connected to the correct cluster
CLUSTER_NAME="${GKE_CLUSTER_NAME:-query-engine}"
EXPECTED_CONTEXT="gke_${GCP_PROJECT}_${GCP_ZONE}_${CLUSTER_NAME}"
CURRENT_CONTEXT=$(kubectl config current-context 2>/dev/null || echo "none")
if [ "$CURRENT_CONTEXT" != "$EXPECTED_CONTEXT" ]; then
    echo "Switching kubectl context to $EXPECTED_CONTEXT..."
    gcloud container clusters get-credentials "$CLUSTER_NAME" \
        --project "$GCP_PROJECT" \
        --zone "$GCP_ZONE"
fi

SERVICE="${1:?Usage: helm-deploy.sh <service> [options]}"
shift

NAMESPACE="query-engine"
VERSION=$(git -C "$ROOT_DIR" rev-parse --short HEAD 2>/dev/null || echo "latest")
CPU_REQUEST=""
MEMORY_REQUEST=""
CPU_LIMIT=""
MEMORY_LIMIT=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --namespace) NAMESPACE="$2"; shift 2 ;;
        --version) VERSION="$2"; shift 2 ;;
        --cpu-request) CPU_REQUEST="$2"; shift 2 ;;
        --memory-request) MEMORY_REQUEST="$2"; shift 2 ;;
        --cpu-limit) CPU_LIMIT="$2"; shift 2 ;;
        --memory-limit) MEMORY_LIMIT="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

REGION="${GCP_ZONE%-*}"
REGISTRY="${REGION}-docker.pkg.dev/${GCP_PROJECT}/query-engine"

# Authenticate Docker with GCP
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet 2>/dev/null

deploy_api() {
    local IMAGE="${REGISTRY}/query-engine-api:${VERSION}"
    echo "Building query-engine-api..."
    docker build --platform linux/amd64 \
        -t "$IMAGE" \
        "$ROOT_DIR/services/query-engine"

    echo "Pushing $IMAGE..."
    docker push "$IMAGE"

    echo "Deploying query-engine (api + worker + beat)..."
    local ARGS="--set image.repository=${REGISTRY}/query-engine-api --set image.tag=${VERSION}"
    [ -n "$CPU_REQUEST" ] && ARGS="$ARGS --set api.resources.requests.cpu=$CPU_REQUEST"
    [ -n "$MEMORY_REQUEST" ] && ARGS="$ARGS --set api.resources.requests.memory=$MEMORY_REQUEST"
    [ -n "$CPU_LIMIT" ] && ARGS="$ARGS --set api.resources.limits.cpu=$CPU_LIMIT"
    [ -n "$MEMORY_LIMIT" ] && ARGS="$ARGS --set api.resources.limits.memory=$MEMORY_LIMIT"

    helm upgrade --install query-engine "$ROOT_DIR/services/query-engine/chart" \
        --namespace "$NAMESPACE" $ARGS

    echo "Deployed: $IMAGE"
}

deploy_ui() {
    local IMAGE="${REGISTRY}/query-engine-ui:${VERSION}"
    echo "Building query-engine-ui..."
    docker build --platform linux/amd64 \
        -t "$IMAGE" \
        "$ROOT_DIR/ui"

    echo "Pushing $IMAGE..."
    docker push "$IMAGE"

    echo "Deploying query-engine-ui..."
    helm upgrade --install query-engine-ui "$ROOT_DIR/ui/chart" \
        --namespace "$NAMESPACE" \
        --set "image.repository=${REGISTRY}/query-engine-ui" \
        --set "image.tag=${VERSION}"

    echo "Deployed: $IMAGE"
}

deploy_infra() {
    local NAME="$1"
    local CHART_DIR="$ROOT_DIR/infra/k8s/${NAME}/chart"

    if [ ! -d "$CHART_DIR" ]; then
        echo "Error: chart not found at $CHART_DIR"
        exit 1
    fi

    echo "Deploying $NAME..."
    helm upgrade --install "$NAME" "$CHART_DIR" \
        --namespace "$NAMESPACE"

    echo "Deployed: $NAME"
}

case "$SERVICE" in
    api)      deploy_api ;;
    ui)       deploy_ui ;;
    neo4j)    deploy_infra neo4j ;;
    postgres) deploy_infra postgres ;;
    redis)    deploy_infra redis ;;
    *)
        echo "Unknown service: $SERVICE"
        echo "Available: api, ui, neo4j, postgres, redis"
        exit 1
        ;;
esac
