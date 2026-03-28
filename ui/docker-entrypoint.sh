#!/bin/sh
set -e

# Replace K8s DNS resolver in nginx config if KUBE_DNS_IP is set
if [ -n "$KUBE_DNS_IP" ]; then
    sed -i "s/# resolver/resolver $KUBE_DNS_IP valid=10s;/" /etc/nginx/conf.d/default.conf
fi

exec "$@"
