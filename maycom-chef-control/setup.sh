#!/usr/bin/env bash
set -euo pipefail
umask 077
project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
for tool in python3 uv node npm ffmpeg ffprobe; do
  command -v "$tool" >/dev/null || { echo "Dependência ausente: $tool. Consulte README.md." >&2; exit 1; }
done
mkdir -p "$project/.data/cache/uv" "$project/.data/cache/npm"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$project/.data/cache/uv}"
export npm_config_cache="${npm_config_cache:-$project/.data/cache/npm}"
(cd "$project/backend" && uv sync --frozen --system-certs)
(cd "$project/frontend" && npm ci --no-audit --no-fund && npm run build)
echo 'Instalação concluída. Execute bash start.sh para abrir o estúdio local.'
