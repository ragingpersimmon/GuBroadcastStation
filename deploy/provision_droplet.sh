#!/usr/bin/env bash
# One-time droplet setup for gubs.ca. Run as root on a fresh Ubuntu 24.04 droplet.
#
# Easiest: log in with the GitHub CLI and clone as root, then run this script:
#   apt-get install -y gh && gh auth login -w -p https && gh auth setup-git
#   git clone --recurse-submodules https://github.com/ragingpersimmon/GuBroadcastStation.git /opt/gubroadcast
#   CERT_EMAIL=you@example.com bash /opt/gubroadcast/deploy/provision_droplet.sh
#
# Or let the script clone as the gbs user with GH_TOKEN, a fine-grained GitHub token, read-only "Contents" on ragingpersimmon/GuBroadcastStation
# and ragingpersimmon/5protocol (both private). It is stored in /etc/gitconfig (root:gbs, 0640) so the
# gbs user can clone and pull both repos and the submodule. Re-running the script is safe.
# The droplet should also be on the tailnet (tailscale up) so the market pulse can reach nebulizer:8699.
set -euo pipefail
DOMAIN=${DOMAIN:-gubs.ca}
APP=/opt/gubroadcast
REPO=${REPO:-https://github.com/ragingpersimmon/GuBroadcastStation.git}
: "${CERT_EMAIL:?set CERT_EMAIL=you@example.com for Let Encrypt expiry notices}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3-venv git nginx ffmpeg certbot

# service user; its home is the app dir, created empty so git can clone into it
id gbs >/dev/null 2>&1 || useradd --system --home-dir "$APP" --shell /usr/sbin/nologin gbs
mkdir -p "$APP" && chown gbs: "$APP"

# GitHub read access for private repos (system-wide, so submodules and gbs's pulls work)
if [ -n "${GH_TOKEN:-}" ]; then
  git config --system --replace-all url."https://x-access-token:${GH_TOKEN}@github.com/".insteadOf "https://github.com/"
  git config --system --add url."https://x-access-token:${GH_TOKEN}@github.com/".insteadOf "git@github.com:"
  chown root:gbs /etc/gitconfig && chmod 640 /etc/gitconfig
fi

if [ ! -d "$APP/.git" ]; then
  if [ -n "$(ls -A "$APP")" ]; then
    echo "$APP is not empty and not a git checkout; move its contents away and re-run" >&2; exit 1
  fi
  sudo -u gbs git clone --recurse-submodules "$REPO" "$APP"
fi
chown -R gbs: "$APP"   # also covers a checkout cloned as root
cd "$APP"
sudo -u gbs git pull --ff-only 2>/dev/null || true
sudo -u gbs git submodule update --init || git -c safe.directory="$APP" submodule update --init
chown -R gbs: "$APP"
[ -f vendor/5protocol/news_ingest.py ] || { echo "vendor/5protocol is missing: the GitHub login needs read access to ragingpersimmon/5protocol" >&2; exit 1; }
[ -x .venv/bin/python ] || sudo -u gbs python3 -m venv .venv
sudo -u gbs .venv/bin/pip install -q -r requirements.txt
mkdir -p /var/www/gubroadcast && chown gbs: /var/www/gubroadcast
[ -f .env ] || { cp .env.example .env; chown gbs: .env; chmod 600 .env; echo ">> edit $APP/.env"; }
cp deploy/gubroadcast-{pipeline,studio,newsletter}.{service,timer} deploy/gubroadcast-account.service /etc/systemd/system/

rm -f /etc/nginx/sites-enabled/default
if [ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
  # bootstrap: plain-HTTP server for the ACME challenge, get the cert, then install the real config
  cat > /etc/nginx/sites-available/gubroadcast <<NGX
server { listen 80; listen [::]:80; server_name $DOMAIN www.$DOMAIN; root /var/www/gubroadcast; }
NGX
  ln -sf /etc/nginx/sites-available/gubroadcast /etc/nginx/sites-enabled/gubroadcast
  nginx -t && systemctl reload nginx
  certbot certonly --webroot -w /var/www/gubroadcast -d "$DOMAIN" -d "www.$DOMAIN" \
    --non-interactive --agree-tos -m "$CERT_EMAIL" --deploy-hook "systemctl reload nginx"
fi
cp deploy/nginx_gubroadcast.conf /etc/nginx/sites-available/gubroadcast
ln -sf /etc/nginx/sites-available/gubroadcast /etc/nginx/sites-enabled/gubroadcast
nginx -t && systemctl reload nginx

# first edition now, then every 15 minutes
systemctl daemon-reload
systemctl start gubroadcast-pipeline.service || echo ">> first edition failed: journalctl -u gubroadcast-pipeline -n 50"
grep -q '^GBS_SESSION_SECRET=.\+' .env || { sed -i '/^GBS_SESSION_SECRET=/d' .env
  echo "GBS_SESSION_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')" >> .env; }
systemctl daemon-reload
systemctl enable --now gubroadcast-account.service
systemctl enable --now gubroadcast-pipeline.timer gubroadcast-studio.timer gubroadcast-newsletter.timer
echo ">> done: curl -I https://$DOMAIN"
