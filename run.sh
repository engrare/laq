#!/usr/bin/env bash
# Uygulamayi baslatir (127.0.0.1:$LAQ_PORT). Ayarlar .env dosyasindan okunur.
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && { set -a; . ./.env; set +a; }
[ -d .venv ] || { echo "Once kurulum: README.md"; exit 1; }
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${LAQ_PORT:-8101}" --workers 1 --proxy-headers --forwarded-allow-ips='*'
