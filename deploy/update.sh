#!/usr/bin/env bash
# One-command deploy on the droplet:  sudo bash /opt/gubroadcast/deploy/update.sh
# Pulls main, installs units + nginx config, fills a session secret if missing,
# restarts the account service and rebuilds the site.
set -euo pipefail
APP=/opt/gubroadcast
cd "$APP"
git pull -q --ff-only
git submodule update --init -q || true
.venv/bin/pip install -q -r requirements.txt
grep -q '^GBS_SESSION_SECRET=.\+' .env || {
  sed -i '/^GBS_SESSION_SECRET=/d' .env
  echo "GBS_SESSION_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')" >> .env
}
# new keys from .env.example that .env doesn't have yet (values as in the template)
while IFS= read -r line; do
  k=${line%%=*}
  [[ $line =~ ^[A-Z_]+= ]] && ! grep -q "^$k=" .env && echo "$line" >> .env
done < .env.example
# rewriter: if LLM_BASE_URL is empty, use the first OpenAI-compatible server that answers on the tailnet
# (Ric's kwon9000 Ollama first). Nothing new publishes without it.
if ! grep -q '^LLM_BASE_URL=.\+' .env; then
  for u in ${GBS_LLM_CANDIDATES:-http://100.111.143.71:11434/v1 http://kwon9000:11434/v1 http://kwon9000:8080/v1}; do
    if curl -s -m 5 "$u/models" | grep -q '"data"'; then
      sed -i '/^LLM_BASE_URL=/d;/^LLM_MODEL=/d' .env
      printf 'LLM_BASE_URL=%s\nLLM_MODEL=auto\n' "$u" >> .env
      echo "rewriter: $u"; break
    fi
  done
  grep -q '^LLM_BASE_URL=.\+' .env || echo "WARNING: no rewriter reachable; nothing new will publish until LLM_BASE_URL is set"
fi
chown -R gbs: "$APP"
chmod 600 .env
cp deploy/gubroadcast-*.service deploy/gubroadcast-*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable -q --now gubroadcast-account.service gubroadcast-images.timer
systemctl restart gubroadcast-account.service
install -D -m 644 deploy/nginx_security_headers.conf /etc/nginx/snippets/gubs-security-headers.conf
install -D -m 644 deploy/nginx_http_hardening.conf /etc/nginx/conf.d/gubs-hardening.conf
cp deploy/nginx_gubroadcast.conf /etc/nginx/sites-available/gubroadcast
nginx -t -q && systemctl reload nginx
systemctl start gubroadcast-pipeline.service
echo "account: $(curl -s http://127.0.0.1:${GBS_ACCOUNT_PORT:-8710}/auth/health)"
echo "site: $(curl -s -o /dev/null -w '%{http_code}' https://gubs.ca/)"
