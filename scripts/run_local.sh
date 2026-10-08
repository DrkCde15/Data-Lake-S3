#!/usr/bin/env bash
# End-to-end local: seed + promote raw->bronze->silver->gold no LocalStack.
# Autocontido: tudo a partir desta pasta. Pré-reqs: python3, aws cli, podman.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -x .venv/bin/python ] || {
  echo "Crie o venv primeiro:" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
}
export AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL:-http://127.0.0.1:4566}"
export AWS_PROFILE="${AWS_PROFILE:-local}" LAKE_BUCKET="${LAKE_BUCKET:-data-engineer-lab-local}"
export PYTHONPATH="src:${PYTHONPATH:-}"

ensure_localstack() {
  if podman ps --format '{{.Names}}' 2>/dev/null | grep -qx localstack; then return 0; fi
  [ -S "/run/user/$(id -u)/podman/podman.sock" ] || {
    echo "Ative o socket podman: systemctl --user enable --now podman.socket" >&2; return 1; }
  podman rm -f localstack >/dev/null 2>&1 || true
  podman run -d --name localstack -p 4566:4566 \
    -e SERVICES="s3,sqs,kinesis,lambda,stepfunctions,events,logs,sts,iam,cloudwatch" \
    -v "/run/user/$(id -u)/podman/podman.sock:/var/run/docker.sock" \
    localstack/localstack:3.8.1 >/dev/null
  for _try in $(seq 1 24); do
    curl -s -m 3 http://127.0.0.1:4566/_localstack/health | grep -q '"s3"' && return 0
    sleep 5
  done
  echo "LocalStack não subiu (ver: podman logs localstack)" >&2; return 1
}
ensure_localstack >/dev/null

.venv/bin/python -m lake.run --date "${1:-2026-10-08}" --transactions "${2:-2000}" --seed 42
