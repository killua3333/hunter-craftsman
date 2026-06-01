#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${1:-/opt/hunter-agent}"
SITE_NAME="${2:-craftsman}"
NGINX_TARGET="/etc/nginx/sites-available/${SITE_NAME}"
NGINX_LINK="/etc/nginx/sites-enabled/${SITE_NAME}"

sudo mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
sudo cp "${REPO_ROOT}/docker/nginx/craftsman.conf.example" "${NGINX_TARGET}"

if [[ ! -L "${NGINX_LINK}" ]]; then
  sudo ln -s "${NGINX_TARGET}" "${NGINX_LINK}"
fi

sudo nginx -t
sudo systemctl reload nginx
echo "installed nginx site at ${NGINX_TARGET}"
