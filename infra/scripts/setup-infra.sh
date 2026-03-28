#!/bin/bash
set -euo pipefail

# Set up cluster infrastructure: Artifact Registry, cert-manager, Traefik, platform chart.
#
# Required env vars:
#   GCP_PROJECT          — GCP project ID
#   CLOUDFLARE_API_TOKEN — Cloudflare API token for DNS-01 challenge
#   QE_DOMAIN            — Domain for the query engine
#   QE_EMAIL             — Email for Let's Encrypt registration

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$SCRIPT_DIR/.."
ENV_FILE="${1:-$INFRA_DIR/.env}"

if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

: "${GCP_PROJECT:?GCP_PROJECT is required}"
: "${GCP_ZONE:?GCP_ZONE is required}"
: "${CLOUDFLARE_API_TOKEN:?CLOUDFLARE_API_TOKEN is required}"
: "${QE_DOMAIN:?QE_DOMAIN is required}"
: "${QE_EMAIL:?QE_EMAIL is required}"

CLUSTER_NAME="${GKE_CLUSTER_NAME:-query-engine}"
REGION="${GCP_ZONE%-*}"

# Ensure kubectl is connected to the correct cluster
EXPECTED_CONTEXT="gke_${GCP_PROJECT}_${GCP_ZONE}_${CLUSTER_NAME}"
CURRENT_CONTEXT=$(kubectl config current-context 2>/dev/null || echo "none")
if [ "$CURRENT_CONTEXT" != "$EXPECTED_CONTEXT" ]; then
    echo "Switching kubectl context to $EXPECTED_CONTEXT..."
    gcloud container clusters get-credentials "$CLUSTER_NAME" \
        --project "$GCP_PROJECT" \
        --zone "$GCP_ZONE"
fi
NAMESPACE="${QE_NAMESPACE:-query-engine}"

# 1. Artifact Registry
echo "Creating Artifact Registry repository..."
gcloud artifacts repositories create query-engine \
    --repository-format=docker \
    --location="$REGION" \
    --project="$GCP_PROJECT" \
    --quiet 2>/dev/null || echo "  Repository already exists"

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# 2. Namespace
echo "Creating namespace '$NAMESPACE'..."
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# 3. Helm repos
echo "Adding Helm repositories..."
helm repo add traefik https://traefik.github.io/charts 2>/dev/null || true
helm repo add jetstack https://charts.jetstack.io 2>/dev/null || true
helm repo update

# 4. cert-manager
echo "Installing cert-manager..."
helm upgrade --install cert-manager jetstack/cert-manager \
    --namespace cert-manager --create-namespace \
    --set crds.enabled=true \
    --wait

# 5. Traefik
echo "Installing Traefik..."
TRAEFIK_ARGS="--namespace traefik --create-namespace"
TRAEFIK_ARGS="$TRAEFIK_ARGS --set service.type=LoadBalancer"
TRAEFIK_ARGS="$TRAEFIK_ARGS --set ports.web.http.redirections.entryPoint.to=websecure"
TRAEFIK_ARGS="$TRAEFIK_ARGS --set ports.web.http.redirections.entryPoint.scheme=https"
TRAEFIK_ARGS="$TRAEFIK_ARGS --set providers.kubernetesCRD.enabled=true"
TRAEFIK_ARGS="$TRAEFIK_ARGS --set providers.kubernetesCRD.allowCrossNamespace=true"

if [ -n "${TRAEFIK_STATIC_IP:-}" ]; then
    TRAEFIK_ARGS="$TRAEFIK_ARGS --set service.spec.loadBalancerIP=$TRAEFIK_STATIC_IP"
fi

helm upgrade --install traefik traefik/traefik $TRAEFIK_ARGS --wait

# 6. Platform chart
echo "Installing platform chart..."
helm upgrade --install query-engine-platform "$INFRA_DIR/k8s/platform/chart" \
    --namespace "$NAMESPACE" \
    --set "cloudflare.apiToken=$CLOUDFLARE_API_TOKEN" \
    --set "domain=$QE_DOMAIN" \
    --set "email=$QE_EMAIL"

echo ""
echo "Infrastructure setup complete."
echo "  Namespace: $NAMESPACE"
echo "  Domain: $QE_DOMAIN"
echo ""
echo "Next steps:"
echo "  1. Get the Traefik external IP: kubectl get svc -n traefik"
echo "  2. Create a Cloudflare A record pointing $QE_DOMAIN to that IP"
echo "  3. Run create-k8s-maps.sh to create ConfigMaps and Secrets"
echo "  4. Deploy services with helm-deploy.sh"
