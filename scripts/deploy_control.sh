#!/usr/bin/env bash
# Deploy the Keysmith web app on the control VM (run as root, on keysmith-control).
# Serves FastAPI (uvicorn :8000) behind Caddy with automatic HTTPS on an
# <ip-dashed>.sslip.io host, so no domain is needed.
#
# Expects:
#   /root/keysmith              the repo (git archive is fine)
#   /root/keysmith/.env         VULTR_API_KEY + VULTR_INFERENCE_KEY
#   /root/ks                    the SSH private key for job VMs
#   env: KEYSMITH_SNAPSHOT_ID, KEYSMITH_SSHKEY_ID
set -euo pipefail
cd /root/keysmith
: "${KEYSMITH_SNAPSHOT_ID:?set KEYSMITH_SNAPSHOT_ID}"
: "${KEYSMITH_SSHKEY_ID:?set KEYSMITH_SSHKEY_ID}"
export DEBIAN_FRONTEND=noninteractive

echo "== [1/6] python venv + deps =="
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip >/dev/null
python3 -m venv .venv
. .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt cryptography mnemonic ecdsa

echo "== [2/6] demo wallets =="
python scripts/make_demo_wallets.py

echo "== [3/6] env file =="
set -a; . /root/keysmith/.env; set +a
cat > /etc/keysmith.env <<ENV
VULTR_API_KEY=${VULTR_API_KEY}
VULTR_INFERENCE_KEY=${VULTR_INFERENCE_KEY}
KEYSMITH_SNAPSHOT_ID=${KEYSMITH_SNAPSHOT_ID}
KEYSMITH_SSHKEY_ID=${KEYSMITH_SSHKEY_ID}
KEYSMITH_SSH_KEY=/root/ks
KEYSMITH_DATA_DIR=/root/keysmith/data
KEYSMITH_WEB_DIST=/root/keysmith/web/dist
PYTHONPATH=/root/keysmith/src
ENV
chmod 600 /etc/keysmith.env

echo "== [4/6] systemd service =="
cat > /etc/systemd/system/keysmith.service <<UNIT
[Unit]
Description=Keysmith backend (FastAPI + sealed-VM runner)
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
WorkingDirectory=/root/keysmith
EnvironmentFile=/etc/keysmith.env
ExecStart=/root/keysmith/.venv/bin/uvicorn keysmith.api:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now keysmith
sleep 3
echo -n "health: "; curl -s http://127.0.0.1:8000/api/health; echo

echo "== [5/6] caddy (auto-HTTPS) =="
if ! command -v caddy >/dev/null 2>&1; then
  apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl gnupg >/dev/null
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq && apt-get install -y -qq caddy >/dev/null
fi
IP=$(curl -s http://127.0.0.1:8000/api/health >/dev/null && hostname -I | awk '{print $1}')
DOMAIN="${IP//./-}.sslip.io"
cat > /etc/caddy/Caddyfile <<CADDY
${DOMAIN} {
	reverse_proxy 127.0.0.1:8000 {
		flush_interval -1
	}
	encode gzip
}
CADDY
systemctl restart caddy

echo "== [6/6] done =="
echo "URL: https://${DOMAIN}"
echo "(Caddy fetches a certificate on first visit; give it ~15s, then open the URL.)"
