#!/usr/bin/env bash
systemctl restart hosting-bridge hosting-panel 2>/dev/null || true
systemctl reload caddy 2>/dev/null || true
echo "[post-deploy] $(date) services restarted"
