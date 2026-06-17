#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${1:-/home/admin/hunter-craftsman}"
DOMAIN="${2:-your-domain.com}"

NGINX_TEMPLATE="${REPO_ROOT}/docker/nginx/dashboard.conf.example"
NGINX_AVAILABLE="/etc/nginx/sites-available/dashboard"
NGINX_ENABLED="/etc/nginx/sites-enabled/dashboard"

if [[ ! -f "${NGINX_TEMPLATE}" ]]; then
  echo "ERROR: ${NGINX_TEMPLATE} not found"
  exit 1
fi

echo "== generating nginx config for ${DOMAIN} =="
sed "s/your-domain.com/${DOMAIN}/g" "${NGINX_TEMPLATE}" | sudo tee "${NGINX_AVAILABLE}" > /dev/null

# enable the site
if [[ ! -L "${NGINX_ENABLED}" ]]; then
  sudo ln -sf "${NGINX_AVAILABLE}" "${NGINX_ENABLED}"
fi

# remove default site if present
if [[ -f "/etc/nginx/sites-enabled/default" ]]; then
  sudo rm -f "/etc/nginx/sites-enabled/default"
fi

echo "== testing nginx config =="
sudo nginx -t

echo "== reloading nginx =="
sudo systemctl reload nginx

echo "== nginx configured for https://${DOMAIN} =="
