#!/usr/bin/env bash
# One-command deploy on the droplet:  sudo bash /opt/gubroadcast/deploy/update.sh
# Pulls main, installs units + nginx config, fills a session secret if missing,
# restarts the account service and rebuilds the site.
set -euo pipefail
APP=/opt/gubroadcast
cd "$APP"
git pull -q --ff-only
git submodule update --init -q || true
grep -q '^GBS_SESSION_SECRET=.\+' .env || {
  sed -i '/^GBS_SESSION_SECRET=/d' .env
  echo "GBS_SESSION_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')" >> .env
}
# new keys from .env.example that .env doesn't have yet (values as in the template)
while IFS= read -r line; do
  k=${line%%=*}
  [[ $line =~ ^[A-Z_]+= ]] && ! grep -q "^$k=" .env && echo "$line" >> .env
done < .env.example
chown -R gbs: "$APP"
chmod 600 .env
cp deploy/gubroadcast-*.service deploy/gubroadcast-*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable -q --now gubroadcast-account.service gubroadcast-images.timer
systemctl restart gubroadcast-account.service
cp deploy/nginx_gubroadcast.conf /etc/nginx/sites-available/gubroadcast
nginx -t -q && systemctl reload nginx
systemctl start gubroadcast-pipeline.service
echo "account: $(curl -s http://127.0.0.1:${GBS_ACCOUNT_PORT:-8710}/auth/health)"
echo "site: $(curl -s -o /dev/null -w '%{http_code}' https://gubs.ca/)"
