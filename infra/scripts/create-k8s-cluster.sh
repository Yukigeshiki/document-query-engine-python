#!/bin/bash
set -euo pipefail

# Create a GKE cluster for the Query Engine.
#
# Required env vars:
#   GCP_PROJECT    — GCP project ID
#   GCP_ZONE       — GCP zone (e.g. africa-south1-a)
#
# Optional env vars:
#   GKE_CLUSTER_NAME   — cluster name (default: query-engine)
#   GKE_MACHINE_TYPE   — machine type (default: e2-medium)
#   USE_SPOT_VMS       — set to "true" for spot VMs (~60-70% cost savings)
#   RESERVE_STATIC_IP  — set to "true" to reserve a static IP for Traefik

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${1:-$SCRIPT_DIR/../.env}"

if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

: "${GCP_PROJECT:?GCP_PROJECT is required}"
: "${GCP_ZONE:?GCP_ZONE is required}"

CLUSTER_NAME="${GKE_CLUSTER_NAME:-query-engine}"
MACHINE_TYPE="${GKE_MACHINE_TYPE:-e2-medium}"

echo "Enabling required GCP APIs..."
gcloud services enable container.googleapis.com --project "$GCP_PROJECT" --quiet
gcloud services enable artifactregistry.googleapis.com --project "$GCP_PROJECT" --quiet

echo "Creating GKE cluster '$CLUSTER_NAME' in $GCP_ZONE..."

SPOT_FLAG=""
if [ "${USE_SPOT_VMS:-false}" = "true" ]; then
    SPOT_FLAG="--spot"
    echo "  Using spot VMs for cost savings"
fi

gcloud container clusters create "$CLUSTER_NAME" \
    --project "$GCP_PROJECT" \
    --zone "$GCP_ZONE" \
    --num-nodes 2 \
    --machine-type "$MACHINE_TYPE" \
    --enable-autoscaling --min-nodes 1 --max-nodes 5 \
    --release-channel regular \
    $SPOT_FLAG

echo "Fetching kubectl credentials..."
gcloud container clusters get-credentials "$CLUSTER_NAME" \
    --project "$GCP_PROJECT" \
    --zone "$GCP_ZONE"

if [ "${RESERVE_STATIC_IP:-false}" = "true" ]; then
    REGION="${GCP_ZONE%-*}"
    echo "Reserving static IP 'query-engine-ip' in $REGION..."
    gcloud compute addresses create query-engine-ip \
        --project "$GCP_PROJECT" \
        --region "$REGION"
    STATIC_IP=$(gcloud compute addresses describe query-engine-ip \
        --project "$GCP_PROJECT" \
        --region "$REGION" \
        --format='get(address)')
    echo "Static IP reserved: $STATIC_IP"
    echo "Set TRAEFIK_STATIC_IP=$STATIC_IP in your .env"
fi

echo "Cluster '$CLUSTER_NAME' is ready."
kubectl cluster-info
