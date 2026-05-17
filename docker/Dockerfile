# CacheCrow — Discord cache scanner
# Runs Discord headlessly via Xvfb to warm the cache, then scans with cache-crow.
FROM ubuntu:22.04

# Prevent apt from prompting for timezone etc.
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# ── System packages ────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # X virtual framebuffer
    xvfb \
    x11-utils \
    # Python
    python3 \
    python3-pip \
    python3-venv \
    # Discord .deb runtime dependencies
    libc6 \
    libglib2.0-0 \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libgtk-3-0 \
    libgbm1 \
    libasound2 \
    libxss1 \
    libxtst6 \
    libx11-xcb1 \
    libxcb-dri3-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    # Download tool
    wget \
    ca-certificates \
    # Misc utilities
    procps \
    && rm -rf /var/lib/apt/lists/*

# ── Discord ────────────────────────────────────────────────────────────────────
# Pull the latest stable Discord .deb directly from Discord's CDN.
RUN wget -q "https://discord.com/api/download?platform=linux&format=deb" \
        -O /tmp/discord.deb \
    && dpkg -i /tmp/discord.deb || true \
    # dpkg exits non-zero on missing deps; apt-get -f install fixes them
    && apt-get update \
    && apt-get install -f -y --no-install-recommends \
    && rm -f /tmp/discord.deb \
    && rm -rf /var/lib/apt/lists/*

# ── CacheCrow ──────────────────────────────────────────────────────────────────
WORKDIR /app

# Copy the full cache-crow source tree
COPY . /app/cache-crow

# Install in editable mode so the `cache-crow` entry-point is available globally
RUN pip3 install --no-cache-dir -e /app/cache-crow

# ── Entrypoint ─────────────────────────────────────────────────────────────────
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Environment knobs (overridable at runtime)
ENV DISCORD_WAIT=18
ENV CACHE_DIR=/root/.config/discord/Cache/Cache_Data

ENTRYPOINT ["/entrypoint.sh"]
