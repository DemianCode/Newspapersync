# syntax=docker/dockerfile:1
FROM python:3.12-slim

# System deps for WeasyPrint + rmapi
# Cache mount keeps apt packages across rebuilds — only re-downloads on first build
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    curl \
    ca-certificates \
    fonts-liberation \
    fonts-dejavu-core \
    fonts-opendyslexic

# Install rmapi binary (pinned version).
# v0.0.32 uses XDG config dir: $HOME/.local/share/rmapi/
# We bind-mount ./rmapi to that path so auth persists across container recreates.
# The -c flag was removed in v0.0.32; config path is controlled via the volume mount.
RUN --mount=type=cache,target=/tmp/rmapi-cache \
    RMAPI_VERSION="0.0.32" && \
    RMAPI_URL="https://github.com/ddvk/rmapi/releases/download/v${RMAPI_VERSION}/rmapi-linux-amd64.tar.gz" && \
    if [ ! -f /tmp/rmapi-cache/rmapi.tar.gz ] || ! tar -tzf /tmp/rmapi-cache/rmapi.tar.gz > /dev/null 2>&1; then \
        curl -fsSL "$RMAPI_URL" -o /tmp/rmapi-cache/rmapi.tar.gz; \
    fi && \
    tar -xz -C /usr/local/bin -f /tmp/rmapi-cache/rmapi.tar.gz && \
    mkdir -p /root/.local/share/rmapi

WORKDIR /app

COPY requirements.txt .

# Cache mount keeps downloaded wheels — only re-downloads when requirements.txt changes
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY app/ ./app/

RUN mkdir -p /app/output /app/config

CMD ["python", "-m", "app.main"]
