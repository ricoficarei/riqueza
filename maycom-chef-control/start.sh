#!/usr/bin/env bash
set -euo pipefail
umask 077
project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$project/.env" ]; then
  set -a
  source "$project/.env"
  set +a
fi
if [ ! -x "$project/backend/.venv/bin/python" ] || [ ! -f "$project/frontend/dist/index.html" ]; then
  echo 'Execute bash setup.sh antes de iniciar.' >&2
  exit 1
fi
cd "$project/backend"
# A fila é durável e single-worker. Nunca use --workers > 1 com o mesmo banco.
exec "$project/backend/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port "${MAYCOM_PORT:-8000}"
