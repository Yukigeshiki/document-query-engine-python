#!/bin/bash
set -euo pipefail

# Delete the GKE cluster.
#
# Required env vars:
#   GCP_PROJECT    — GCP project ID
#   GCP_ZONE       — GCP zone

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

echo "Deleting GKE cluster '$CLUSTER_NAME'..."
gcloud container clusters delete "$CLUSTER_NAME" \
    --project "$GCP_PROJECT" \
    --zone "$GCP_ZONE" \
    --quiet

if [ "${RESERVE_STATIC_IP:-false}" = "true" ]; then
    REGION="${GCP_ZONE%-*}"
    echo "Releasing static IP 'query-engine-ip'..."
    gcloud compute addresses delete query-engine-ip \
        --project "$GCP_PROJECT" \
        --region "$REGION" \
        --quiet
fi

echo "Cluster deleted."
