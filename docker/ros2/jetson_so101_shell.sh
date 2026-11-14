#!/usr/bin/env bash
set -euo pipefail

port="${SO101_BRIDGE_PORT:-54321}"
device="/tmp/so101"

socat -d -d "PTY,link=${device},raw,echo=0" "TCP:host.docker.internal:${port},nodelay" &
bridge_pid=$!
trap 'kill "$bridge_pid" 2>/dev/null || true' EXIT

for _ in {1..30}; do
    if ! kill -0 "$bridge_pid" 2>/dev/null; then
        echo "SO-101 bridge failed. Start the Mac host bridge first." >&2
        exit 1
    fi
    if [[ -e "$device" ]]; then
        echo "SO-101 serial device available at $device"
        bash -i
        exit
    fi
    sleep 0.1
done

echo "SO-101 bridge did not create $device" >&2
exit 1
