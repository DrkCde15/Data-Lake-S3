#!/usr/bin/env bash
# End-to-end local: seed + promote raw->bronze->silver->gold no MinIO.
# Autocontido: tudo a partir desta pasta. Pré-reqs: python3, aws cli, podman.
# Console web: http://127.0.0.1:9001 (minioadmin/minioadmin).
set -euo pipefail
cd "$(dirname "$0")/.."
[ -x .venv/bin/python ] || {
  echo "Crie o venv primeiro:" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
}
export AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL:-http://127.0.0.1:9000}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-minioadmin}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-minioadmin}"
export AWS_PROFILE="${AWS_PROFILE:-local}" LAKE_BUCKET="${LAKE_BUCKET:-data-engineer-lab-local}"
export PYTHONPATH="src:${PYTHONPATH:-}"

ensure_minio() {
  if podman ps --format '{{.Names}}' 2>/dev/null | grep -qx minio; then return 0; fi
  # minio/minio saiu do Docker Hub; Chainguard é a alternativa mantida.
  podman rm -f minio >/dev/null 2>&1 || true
  podman run -d --name minio -p 9000:9000 -p 9001:9001 \
    -e MINIO_ROOT_USER="${AWS_ACCESS_KEY_ID}" \
    -e MINIO_ROOT_PASSWORD="${AWS_SECRET_ACCESS_KEY}" \
    -v minio-data:/data \
    cgr.dev/chainguard/minio:latest server /data --console-address ":9001" >/dev/null
  for _try in $(seq 1 24); do
    curl -s -m 3 http://127.0.0.1:9000/minio/health/live >/dev/null && return 0
    sleep 2
  done
  echo "MinIO não subiu (ver: podman logs minio)" >&2; return 1
}
ensure_minio >/dev/null

.venv/bin/python -m lake.run --date "${1:-2026-10-08}" --transactions "${2:-2000}" --seed 42
