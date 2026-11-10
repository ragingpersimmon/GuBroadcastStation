#!/usr/bin/env bash
# Read-only health + security audit of the gubs.ca droplet. Changes nothing.
#   sudo bash /opt/gubroadcast/deploy/doctor.sh            (paste the output to Claude)
APP=/opt/gubroadcast
ok(){ printf '  [ok]   %s\n' "$*"; }
warn(){ printf '  [WARN] %s\n' "$*"; }
bad(){ printf '  [FIX]  %s\n' "$*"; }
echo "== gubs.ca doctor  $(date -u +%FT%TZ)  $(hostname) =="

echo "-- capacity"
read -r _ total used free _ _ avail <<<"$(free -m | awk '/^Mem:/')"
swap_used=$(free -m | awk '/^Swap:/{print $3}')
[ "$avail" -lt 300 ] && bad "RAM: ${avail} MB available of ${total} MB (swap used ${swap_used} MB) - resize to 4 GB or move Vantage" || ok "RAM: ${avail} MB available of ${total} MB, swap used ${swap_used} MB"
disk=$(df -P / | awk 'NR==2{print $5}' | tr -d %)
[ "$disk" -gt 85 ] && bad "disk / ${disk}% full" || ok "disk / ${disk}% used"
ok "load: $(cut -d' ' -f1-3 /proc/loadavg)  uptime: $(uptime -p)"

echo "-- services"
for u in nginx gubroadcast-account; do systemctl is-active -q $u && ok "$u running" || bad "$u NOT running"; done
for t in gubroadcast-pipeline.timer gubroadcast-studio.timer gubroadcast-newsletter.timer gubroadcast-images.timer; do
  systemctl is-active -q $t && ok "$t active" || warn "$t not active"; done
r=$(systemctl show gubroadcast-pipeline -p Result --value); [ "$r" = success ] && ok "last pipeline run: success" || bad "last pipeline run: $r (journalctl -u gubroadcast-pipeline -n 50)"
failed=$(systemctl --failed --no-legend | wc -l); [ "$failed" -eq 0 ] && ok "no failed units" || bad "$failed failed units: $(systemctl --failed --no-legend | awk '{print $2}' | tr '\n' ' ')"
nginx -t -q 2>/dev/null && ok "nginx config valid" || bad "nginx -t fails"

echo "-- TLS"
end=$(openssl x509 -enddate -noout -in /etc/letsencrypt/live/gubs.ca/fullchain.pem 2>/dev/null | cut -d= -f2)
if [ -n "$end" ]; then days=$(( ($(date -d "$end" +%s) - $(date +%s)) / 86400 )); [ $days -lt 20 ] && bad "cert expires in $days days" || ok "cert valid $days more days"; fi
systemctl is-active -q certbot.timer && ok "certbot renew timer active" || warn "certbot.timer inactive"

echo "-- updates"
apt-get -s -o Debug::NoLocking=1 upgrade 2>/dev/null | grep -c '^Inst' | { read n; [ "$n" -gt 0 ] && warn "$n packages upgradable" || ok "packages up to date"; }
sec=$(apt-get -s upgrade 2>/dev/null | grep '^Inst' | grep -ci security); [ "$sec" -gt 0 ] && bad "$sec security updates pending" || ok "no pending security updates"
[ -f /var/run/reboot-required ] && bad "reboot required ($(cat /var/run/reboot-required.pkgs 2>/dev/null | tr '\n' ' '))" || ok "no reboot required"
dpkg -l unattended-upgrades 2>/dev/null | grep -q ^ii && grep -q '"1"' /etc/apt/apt.conf.d/20auto-upgrades 2>/dev/null && ok "unattended security upgrades on" || bad "unattended-upgrades off"

echo "-- access"
sshd -T 2>/dev/null | grep -q '^passwordauthentication no' && ok "SSH password login disabled" || bad "SSH password login allowed"
sshd -T 2>/dev/null | grep -qE '^permitrootlogin (prohibit-password|without-password|no)' && ok "root SSH: keys only" || bad "root SSH allows passwords"
ufw status 2>/dev/null | grep -q 'Status: active' && ok "ufw active: $(ufw status | grep -c ALLOW) allow rules" || bad "firewall (ufw) inactive"
systemctl is-active -q fail2ban && ok "fail2ban running" || bad "fail2ban not installed/running"
echo "   public listeners:"
ss -Htlnp | awk '$4 !~ /^(127\.|\[::1\]|100\.|\[fd7a)/ {print "     "$4"  "$6}' | sort -u
docker ps --format '   docker: {{.Names}} {{.Ports}}' 2>/dev/null
tailscale status --self=true --peers=false 2>/dev/null | sed 's/^/   tailscale: /' | head -1

echo "-- secrets"
[ "$(stat -c %a $APP/.env)" = 600 ] && ok ".env mode 600" || bad ".env readable by others ($(stat -c %a $APP/.env))"
for k in STRIPE_SECRET_KEY STRIPE_WEBHOOK_SECRET GOOGLE_CLIENT_ID LLM_BASE_URL; do grep -q "^$k=." $APP/.env && ok "$k set" || warn "$k empty"; done

echo "-- site"
code=$(curl -s -o /dev/null -w '%{http_code}' https://gubs.ca/); [ "$code" = 200 ] && ok "https://gubs.ca -> 200" || bad "https://gubs.ca -> $code"
for h in content-security-policy x-frame-options referrer-policy; do curl -sI https://gubs.ca/ | grep -qi "^$h:" && ok "header $h" || bad "missing header $h (run deploy/update.sh)"; done
curl -sI https://gubs.ca/ | grep -qi '^server: nginx/' && bad "nginx version exposed" || ok "server version hidden"
age=$(( $(date +%s) - $(stat -c %Y /var/www/gubroadcast/index.html) )); [ $age -gt 3600 ] && bad "front page $((age/60)) min old" || ok "front page rebuilt $((age/60)) min ago"

echo "-- newsroom"
cd $APP && sudo -u gbs bash -c 'set -a; . ./.env; set +a; .venv/bin/python -m gbs doctor' | sed 's/^/   /'
