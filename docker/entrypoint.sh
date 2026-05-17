#!/usr/bin/env bash
# CacheCrow Docker entrypoint
# Starts Xvfb, launches Discord briefly to populate cache, runs cache-crow stats.

set -euo pipefail

DISPLAY_NUM=":99"
DISCORD_WAIT="${DISCORD_WAIT:-18}"
CACHE_DIR="${CACHE_DIR:-/root/.config/discord/Cache/Cache_Data}"

echo "[entrypoint] Starting Xvfb on display ${DISPLAY_NUM}"
Xvfb "${DISPLAY_NUM}" -screen 0 1280x800x24 &
XVFB_PID=$!
export DISPLAY="${DISPLAY_NUM}"

# Give Xvfb a moment to initialise
sleep 2

echo "[entrypoint] Launching Discord (headless via Xvfb) for ${DISCORD_WAIT}s to warm cache..."
# --no-sandbox required inside Docker (no user namespace support)
# --disable-gpu avoids mesa fallback failures in a virtual framebuffer
discord \
    --no-sandbox \
    --disable-gpu \
    --disable-software-rasterizer \
    --disable-dev-shm-usage \
    &>/tmp/discord.log &
DISCORD_PID=$!

sleep "${DISCORD_WAIT}"

echo "[entrypoint] Stopping Discord (PID ${DISCORD_PID})"
kill "${DISCORD_PID}" 2>/dev/null || true
wait "${DISCORD_PID}" 2>/dev/null || true

echo "[entrypoint] Discord log tail:"
tail -20 /tmp/discord.log || true

# Check if cache was populated
if [ ! -d "${CACHE_DIR}" ]; then
    echo "[entrypoint] WARNING: Cache directory not found at ${CACHE_DIR}"
    echo "[entrypoint] Listing ~/.config/discord/ if it exists:"
    ls -la /root/.config/discord/ 2>/dev/null || echo "  (no discord config dir)"
    echo ""
    echo "[entrypoint] Discord requires login before it writes a media cache."
    echo "             The cache dir is only created after a successful login session."
    echo "             To pre-seed: mount a host Discord cache via -v or bind-mount."
    echo "             Exiting with diagnostic info — not a build failure."
    kill "${XVFB_PID}" 2>/dev/null || true
    exit 0
fi

echo "[entrypoint] Running cache-crow on ${CACHE_DIR}"
cache-crow --stats --cache-dir "${CACHE_DIR}"

echo "[entrypoint] Done."
kill "${XVFB_PID}" 2>/dev/null || true
