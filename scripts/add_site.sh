#!/usr/bin/env bash
set -euo pipefail
KIND=${1:-static}; DOMAIN=${2:-}; SRC=${3:-}; FORCE=${4:-0}
TOKEN=$(grep BRIDGE_TOKEN /opt/hosting/.bridge_env | cut -d= -f2)
[ -n "$DOMAIN" ] || { echo "Укажи домен"; exit 1; }
SID=$(curl -s -X POST http://127.0.0.1:8098/create_service -H "X-Bridge-Token: $TOKEN" -H 'Content-Type: application/json' -d "{\"kind\":\"$KIND\"}" | python3 -c 'import sys,json;print(json.load(sys.stdin)["service_id"])')
echo "Услуга #$SID создана"
VOL=/opt/hosting/sites/$SID
if [ -n "$SRC" ] && [ -d "$SRC" ]; then cp -r "$SRC"/. "$VOL"/; echo "Файлы скопированы в $VOL"; fi
curl -s -X POST http://127.0.0.1:8098/attach_domain -H "X-Bridge-Token: $TOKEN" -H 'Content-Type: application/json' -d "{\"service_id\":$SID,\"domain\":\"$DOMAIN\",\"force\":$([ "$FORCE" = 1 ] && echo true || echo false)}"
echo; echo "Готово: https://$DOMAIN"
