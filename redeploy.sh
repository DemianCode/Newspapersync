#!/bin/bash
set -e

cd "$(dirname "$0")"

# Ensure volume directories exist before Docker tries to mount them
mkdir -p rmapi output config

echo "Stopping container..."
docker compose down

echo "Rebuilding and starting..."
docker compose up -d --build

echo "Done. Logs (Ctrl+C to exit):"
docker compose logs -f
