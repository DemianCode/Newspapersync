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
    ca-certificates

# Install rmapi binary (pinned version) and wrap it so config always lives at
# /root/rmapi-config/.rmapi (the bind-mount path) instead of ~/.rmapi.
# ddvk/rmapi v0.0.32 does not honour RMAPI_CONFIG, so we use the -c flag via wrapper.
RUN --mount=type=cache,target=/tmp/rmapi-cache \
    RMAPI_VERSION="0.0.32" && \
    RMAPI_URL="https://github.com/ddvk/rmapi/releases/download/v${RMAPI_VERSION}/rmapi-linux-amd64.tar.gz" && \
    if [ ! -f /tmp/rmapi-cache/rmapi.tar.gz ] || ! tar -tzf /tmp/rmapi-cache/rmapi.tar.gz > /dev/null 2>&1; then \
        curl -fsSL "$RMAPI_URL" -o /tmp/rmapi-cache/rmapi.tar.gz; \
    fi && \
    tar -xz -C /usr/local/bin -f /tmp/rmapi-cache/rmapi.tar.gz && \
    mv /usr/local/bin/rmapi /usr/local/bin/rmapi-bin && \
    printf '#!/bin/sh\nexec /usr/local/bin/rmapi-bin -c /root/rmapi-config/.rmapi "$@"\n' \
        > /usr/local/bin/rmapi && \
    chmod +x /usr/local/bin/rmapi-bin /usr/local/bin/rmapi

WORKDIR /app

COPY requirements.txt .

# Cache mount keeps downloaded wheels — only re-downloads when requirements.txt changes
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY app/ ./app/

RUN mkdir -p /app/output /app/config

CMD ["python", "-m", "app.main"]
