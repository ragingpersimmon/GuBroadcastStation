#!/usr/bin/env bash
# One-time hardening for the gubs.ca droplet. Run it yourself (it changes security settings):
#   sudo bash /opt/gubroadcast/deploy/harden.sh
# Safe to re-run. Keeps SSH open (key login only), web on 80/443, everything else closed
# except Tailscale. Vantage's Docker ports aren't touched (Docker manages its own iptables;
# keep its services bound to 127.0.0.1).
set -euo pipefail
[ -s /root/.ssh/authorized_keys ] || { echo "No SSH key in /root/.ssh/authorized_keys: add yours first or you'll be locked out of SSH (console still works)."; exit 1; }

apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get -yq upgrade
DEBIAN_FRONTEND=noninteractive apt-get -yq install ufw fail2ban unattended-upgrades

# automatic security updates
printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' > /etc/apt/apt.conf.d/20auto-upgrades

# SSH: keys only
install -d /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/60-gubs-hardening.conf <<'C'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
MaxAuthTries 4
X11Forwarding no
C
sshd -t && systemctl reload ssh

# firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow in on tailscale0
ufw --force enable

# fail2ban: SSH brute force + repeated 429s on sign-in/checkout
cat > /etc/fail2ban/jail.d/gubs.local <<'C'
[sshd]
enabled = true
maxretry = 5
bantime = 1h
[nginx-limit-req]
enabled = true
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 10
bantime = 1h
C
systemctl enable --now fail2ban
systemctl restart fail2ban

echo "Done. Re-check with: sudo bash /opt/gubroadcast/deploy/doctor.sh"
[ -f /var/run/reboot-required ] && echo "A reboot is required to finish kernel updates: sudo reboot"
