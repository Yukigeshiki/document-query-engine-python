#!/bin/sh
set -e

# Replace K8s DNS resolver in nginx config if KUBE_DNS_IP is set
if [ -n "$KUBE_DNS_IP" ]; then
    sed -i "s/# resolver/resolver $KUBE_DNS_IP valid=10s;/" /etc/nginx/conf.d/default.conf
fi

# Override API backend URL and resolver for Docker Compose or other non-K8s environments
if [ -n "$API_URL" ]; then
    sed -i "s|http://query-engine-api.query-engine.svc.cluster.local:8000|$API_URL|" /etc/nginx/conf.d/default.conf
    sed -i "s|kube-dns.kube-system.svc.cluster.local|127.0.0.11|" /etc/nginx/conf.d/default.conf
fi

exec "$@"
