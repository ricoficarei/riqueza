#!/usr/bin/env bash
set -euo pipefail
project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
(cd "$project/backend" && .venv/bin/python -m pytest "$@")
(cd "$project/frontend" && npm run build)
