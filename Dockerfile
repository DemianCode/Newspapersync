FROM python:3.12-slim

# System deps for WeasyPrint + rmapi
RUN apt-get update && apt-get install -y --no-install-recommends \
    # WeasyPrint rendering
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    # rmapi (pre-built binary download needs curl + ca-certs)
    curl \
    ca-certificates \
    # General
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install rmapi binary
RUN curl -sSL \
    "https://github.com/juruen/rmapi/releases/latest/download/rmapi-linux-amd64.tar.gz" \
    | tar -xz -C /usr/local/bin \
    && chmod +x /usr/local/bin/rmapi

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Output dir for generated PDFs
RUN mkdir -p /app/output /app/config

CMD ["python", "-m", "app.main"]
