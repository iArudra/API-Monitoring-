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
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application source + startup script.
COPY app ./app
COPY entrypoint.sh .
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

# entrypoint.sh waits for LocalStack (when AWS_ENDPOINT_URL is set), then
# starts uvicorn. OpenTelemetry env vars (OTEL_EXPORTER_OTLP_ENDPOINT, ...)
# are passed through from the container environment unchanged.
ENTRYPOINT ["/app/entrypoint.sh"]
