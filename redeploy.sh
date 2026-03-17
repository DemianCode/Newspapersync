#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Stopping container..."
docker compose down

echo "Rebuilding and starting..."
docker compose up -d --build

echo "Done. Logs (Ctrl+C to exit):"
docker compose logs -f
