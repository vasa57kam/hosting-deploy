#!/usr/bin/env bash
set -e
NEW=${1:-$(openssl rand -hex 12)}
ENVF=/opt/hosting/.panel_env
if [ ! -f "$ENVF" ]; then
  echo "❌ Файл $ENVF не найден — панель не установлена"
  exit 1
fi
sed -i "s/^PANEL_PASSWORD=.*/PANEL_PASSWORD=$NEW/" "$ENVF"
chmod 600 "$ENVF"
systemctl restart hosting-panel
sleep 2
echo "✓ Новый пароль панели хостинга: $NEW"
echo "  Панель: http://192.168.0.172:8097"
