#!/usr/bin/env bash
# One-time droplet setup. Run as root. Droplet must already be on the tailnet
# (it is, for the flowerseekingbee relay) so market pulse can reach nebulizer:8699.
set -euo pipefail
REPO=${REPO:-git@github.com:ragingpersimmon/GuBroadcastStation.git}
id gbs >/dev/null 2>&1 || useradd --system --create-home --home-dir /opt/gubroadcast gbs
apt-get install -y python3-venv git nginx ffmpeg certbot
[ -d /opt/gubroadcast/.git ] || sudo -u gbs git clone --recurse-submodules "$REPO" /opt/gubroadcast
cd /opt/gubroadcast && sudo -u gbs git submodule update --init
sudo -u gbs python3 -m venv .venv && sudo -u gbs .venv/bin/pip install -r requirements.txt
mkdir -p /var/www/gubroadcast && chown gbs: /var/www/gubroadcast
[ -f .env ] || { cp .env.example .env; chown gbs: .env; chmod 600 .env; echo "edit /opt/gubroadcast/.env"; }
cp deploy/gubroadcast-{pipeline,studio,newsletter}.{service,timer} /etc/systemd/system/
DOMAIN=${DOMAIN:-gubs.ca}
if [ ! -f /etc/letsencrypt/live/$DOMAIN/fullchain.pem ]; then
  # bootstrap: plain-HTTP server for the ACME challenge, get the cert, then install the real config
  cat > /etc/nginx/sites-available/gubroadcast <<NGX
server { listen 80; listen [::]:80; server_name $DOMAIN www.$DOMAIN; root /var/www/gubroadcast; }
NGX
  ln -sf /etc/nginx/sites-available/gubroadcast /etc/nginx/sites-enabled/gubroadcast
  nginx -t && systemctl reload nginx
  certbot certonly --webroot -w /var/www/gubroadcast -d $DOMAIN -d www.$DOMAIN \
    --non-interactive --agree-tos -m "${CERT_EMAIL:-news@$DOMAIN}" --deploy-hook "systemctl reload nginx"
fi
cp deploy/nginx_gubroadcast.conf /etc/nginx/sites-available/gubroadcast
ln -sf /etc/nginx/sites-available/gubroadcast /etc/nginx/sites-enabled/gubroadcast
systemctl daemon-reload && systemctl enable --now gubroadcast-pipeline.timer gubroadcast-studio.timer gubroadcast-newsletter.timer
nginx -t && systemctl reload nginx
