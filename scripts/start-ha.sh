#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Pull the latest :stable image first — compose only fetches it when
# creating a fresh container, so without this an existing container
# would keep restarting an outdated Home Assistant forever.
docker compose pull
docker compose up -d
echo "Home Assistant starting at http://localhost:8123"
echo "Logs: docker compose logs -f"
echo "Stop: docker compose down"
