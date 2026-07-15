#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
docker compose up -d
echo "Home Assistant starting at http://localhost:8123"
echo "Logs: docker compose logs -f"
echo "Stop: docker compose down"
