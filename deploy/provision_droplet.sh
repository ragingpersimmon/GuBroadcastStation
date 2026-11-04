#!/usr/bin/env bash
# One-time droplet setup. Run as root. Droplet must already be on the tailnet
# (it is, for the flowerseekingbee relay) so market pulse can reach nebulizer:8699.
set -euo pipefail
REPO=${REPO:-git@github.com:ragingpersimmon/GuBroadcastStation.git}
id gbs >/dev/null 2>&1 || useradd --system --create-home --home-dir /opt/gubroadcast gbs
apt-get install -y python3-venv git nginx
[ -d /opt/gubroadcast/.git ] || sudo -u gbs git clone --recurse-submodules "$REPO" /opt/gubroadcast
cd /opt/gubroadcast && sudo -u gbs git submodule update --init
sudo -u gbs python3 -m venv .venv && sudo -u gbs .venv/bin/pip install -r requirements.txt
mkdir -p /var/www/gubroadcast && chown gbs: /var/www/gubroadcast
[ -f .env ] || { cp .env.example .env; chown gbs: .env; chmod 600 .env; echo "edit /opt/gubroadcast/.env"; }
cp deploy/gubroadcast-pipeline.{service,timer} /etc/systemd/system/
cp deploy/nginx_gubroadcast.conf /etc/nginx/sites-available/gubroadcast
ln -sf /etc/nginx/sites-available/gubroadcast /etc/nginx/sites-enabled/gubroadcast
systemctl daemon-reload && systemctl enable --now gubroadcast-pipeline.timer
nginx -t && systemctl reload nginx
