# CentralWatch Demo App — reproducible container image.
# Builds from this directory only; no pre-existing image is required.
#
#   docker compose build demo-app
#   docker compose up -d demo-app
#
# The application is a passive telemetry GENERATOR for the CentralWatch
# observability stack. It never proxies anything — it calls AWS (LocalStack in
# dev, real AWS in production) and emits OpenTelemetry over OTLP to the
# collector. All environment configuration (AWS endpoint, OTLP endpoint,
# resource names, auth secret) is supplied at runtime via environment
# variables — see .env.example and the root README.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so layer caching stays effective across source edits.
RUN apt-get update && \
    apt-get install -y wget apt-transport-https gnupg curl && \
    wget -qO - https://packages.adoptium.net/artifactory/api/gpg/key/public | apt-key add - && \
    echo "deb https://packages.adoptium.net/artifactory/deb bookworm main" > /etc/apt/sources.list.d/adoptium.list && \
    apt-get update && \
    apt-get install -y temurin-21-jre && \
    rm -rf /var/lib/apt/lists/*

COPY demo-app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy centralwatch-security plugin and install it
COPY centralwatch-security /centralwatch-security
RUN pip install -e /centralwatch-security

# Application source + startup script.
COPY demo-app/app ./app
COPY demo-app/entrypoint.sh .
COPY scripts/security_scan.sh /scripts/security_scan.sh
RUN chmod +x /app/entrypoint.sh && chmod +x /scripts/security_scan.sh

EXPOSE 8000

# entrypoint.sh waits for LocalStack (when AWS_ENDPOINT_URL is set), then
# starts uvicorn. OpenTelemetry env vars (OTEL_EXPORTER_OTLP_ENDPOINT, ...)
# are passed through from the container environment unchanged.
ENTRYPOINT ["/app/entrypoint.sh"]
