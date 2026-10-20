#!/usr/bin/env bash
set -euo pipefail
[ "$EUID" -ne 0 ] && { echo "Запусти от root"; exit 1; }
echo "== Хостинг: установка =="
apt-get update -qq
apt-get install -y -qq git curl sqlite3 dnsutils >/dev/null
command -v docker >/dev/null || curl -fsSL https://get.docker.com | bash
systemctl enable --now docker
if ! command -v caddy >/dev/null; then
  curl -fsSL -o /tmp/caddy.tgz https://github.com/caddyserver/caddy/releases/download/v2.8.4/caddy_2.8.4_linux_amd64.tar.gz
  tar -xzf /tmp/caddy.tgz -C /usr/local/bin caddy
fi
mkdir -p /opt/hosting/{sites,apps,backup} /etc/caddy/sites
cat > /etc/caddy/Caddyfile <<'CADDY'
{
admin localhost:2017
on_demand_tls {
ask http://127.0.0.1:8098/caddy/allow
interval 60s
burst 10
}
}
import /etc/caddy/sites/*.caddy
CADDY
cat > /etc/systemd/system/caddy.service <<'UNIT'
[Unit]
Description=Caddy
After=network.target
[Service]
Type=simple
ExecStart=/usr/local/bin/caddy run --environ --config /etc/caddy/Caddyfile --adapter caddyfile
ExecReload=/usr/local/bin/caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now caddy
docker pull nginx:alpine >/dev/null
bash bridge/install_bridge.sh
echo "== Готово. Мост: curl http://127.0.0.1:8098/ping =="
