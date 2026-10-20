#!/usr/bin/env bash
set -euo pipefail
ENVF=/opt/hosting/.bridge_env
if [ ! -f "$ENVF" ]; then
  TOK=$(openssl rand -hex 24)
  IP=$(hostname -I | awk '{print $1}')
  cat > "$ENVF" <<EOF
BRIDGE_TOKEN=$TOK
BRIDGE_PORT=8098
HOST_IP=$IP
EOF
  chmod 600 "$ENVF"
fi
cat > /etc/systemd/system/hosting-bridge.service <<'UNIT'
[Unit]
Description=Hosting Bridge API
After=network.target docker.service
[Service]
Type=simple
User=root
WorkingDirectory=/opt/hosting
EnvironmentFile=/opt/hosting/.bridge_env
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/hosting/venv/bin
ExecStart=/opt/hosting/venv/bin/python /opt/hosting/bridge/bridge_server.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
[ -d /opt/hosting/venv ] || python3 -m venv /opt/hosting/venv
/opt/hosting/venv/bin/pip install -q flask
systemctl daemon-reload
systemctl enable --now hosting-bridge
systemctl restart hosting-bridge
sleep 2
curl -s http://127.0.0.1:8098/ping && echo
echo "TOKEN: $(grep BRIDGE_TOKEN "$ENVF" | cut -d= -f2)"
