#!/bin/bash
# Authenticate rmapi with your reMarkable account.
# Run this ONCE after first deploy (or if you need to re-auth).
#
# Usage: ./auth-remarkable.sh
set -e

cd "$(dirname "$0")"

# Make sure the container is running
if ! docker compose ps --services --filter status=running | grep -q "^newspapersync$"; then
    echo "Container is not running. Starting it first..."
    mkdir -p rmapi output config
    docker compose up -d --build
    echo "Waiting for container to be ready..."
    sleep 3
fi

echo ""
echo "Opening rmapi inside the running container."
echo "1. Go to: https://my.remarkable.com/device/browser/connect"
echo "2. Log in, copy the one-time code shown on the page."
echo "3. Paste it here and press Enter."
echo "4. Once you see [/]> type: exit  (then press Enter) — do NOT Ctrl+C."
echo ""

docker exec -it newspapersync rmapi

echo ""
echo "Verifying auth..."
if docker exec newspapersync rmapi -ni ls / > /dev/null 2>&1; then
    echo "Auth successful! reMarkable sync is ready."
else
    echo "Auth check failed. Check the output above for errors and try again."
    exit 1
fi
