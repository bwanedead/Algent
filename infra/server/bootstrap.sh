#!/usr/bin/env bash
# First-time (and repeatable) setup of the Ohmega worker server — Ubuntu 24.04, run as root.
#
# Idempotent: every step checks before it acts, so re-running it on a configured server changes nothing and
# rebuilding a fresh server is one command. The server holds nothing irreplaceable (the corpus lives in
# Supabase and the private GitHub archive), so "rebuild from this script" is the recovery plan.
#
#   fresh server:  scp -i ~/.ssh/ohmega_ops infra/server/bootstrap.sh root@HOST:/root/
#                  ssh -i ~/.ssh/ohmega_ops root@HOST bash /root/bootstrap.sh
#   re-run later:  scp it to ohmega@HOST:~ and run `sudo bash ~/bootstrap.sh` (root login is off by then)
#
# After it runs: root login and passwords are off; log in as `ohmega` with the same keys. Don't pipe its output
# through `head`: a closed pipe can kill the run mid-upgrade.
set -euo pipefail

OPS_USER="ohmega"
export DEBIAN_FRONTEND=noninteractive

echo "== packages"
apt-get update -y
apt-get upgrade -y
apt-get install -y ufw fail2ban unattended-upgrades git curl ca-certificates \
    python3-venv python3-pip docker.io docker-compose-v2

echo "== swap (2 GB): breathing room for the headless browser and chart tools on a 4 GB machine"
if ! swapon --show | grep -q /swapfile; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "== ops user '${OPS_USER}' with the same SSH keys as root"
if ! id -u "${OPS_USER}" >/dev/null 2>&1; then
    adduser --disabled-password --gecos "" "${OPS_USER}"
fi
usermod -aG sudo,docker "${OPS_USER}"
echo "${OPS_USER} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/90-${OPS_USER}"
chmod 440 "/etc/sudoers.d/90-${OPS_USER}"
install -d -m 700 -o "${OPS_USER}" -g "${OPS_USER}" "/home/${OPS_USER}/.ssh"
install -m 600 -o "${OPS_USER}" -g "${OPS_USER}" /root/.ssh/authorized_keys "/home/${OPS_USER}/.ssh/authorized_keys"

echo "== SSH: keys only, no root login"
cat > /etc/ssh/sshd_config.d/90-ohmega.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
sshd -t
systemctl reload ssh

echo "== firewall: SSH in, nothing else (services bind to 127.0.0.1; Docker ports are published on localhost only)"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw --force enable

echo "== automatic security updates"
dpkg-reconfigure -f noninteractive unattended-upgrades
systemctl enable --now fail2ban docker

echo "== done: log in as ${OPS_USER}@$(hostname -I | awk '{print $1}')"
