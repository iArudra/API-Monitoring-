#!/usr/bin/env bash
# healthcheck.sh - Deep health verification for CentralWatch monitoring stack.
# Checks container status, HTTP readiness, and Prometheus target scrape status.

set -eo pipefail

echo "=================================================="
echo "Starting CentralWatch Health Check..."
echo "=================================================="

# Check if curl is installed
if ! command -v curl &> /dev/null; then
  echo "Error: curl is required but not installed." >&2
  exit 1
fi

# 1. Verify Docker containers are running
echo "Checking Docker containers..."
CONTAINERS=("centralwatch-otel-collector" "centralwatch-prometheus")
ALL_RUNNING=true

for container in "${CONTAINERS[@]}"; do
  STATUS=$(docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null || echo "not found")
  if [ "$STATUS" = "running" ]; then
    echo "  [PASS] $container is running."
  else
    echo "  [FAIL] $container status is: $STATUS"
    ALL_RUNNING=false
  fi
done

if [ "$ALL_RUNNING" = false ]; then
  echo "Error: One or more containers are not running." >&2
  exit 1
fi

# 2. Check OTel Collector metrics endpoint readiness
echo "Checking OTel Collector metrics endpoint (http://localhost:8889/metrics)..."
MAX_RETRIES=6
RETRY_INTERVAL=5
COLLECTOR_READY=false

for ((i=1; i<=MAX_RETRIES; i++)); do
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8889/metrics || echo "000")
  if [ "$HTTP_CODE" = "200" ]; then
    echo "  [PASS] OTel Collector metrics endpoint responded with HTTP 200."
    COLLECTOR_READY=true
    break
  fi
  echo "  [RETRY $i/$MAX_RETRIES] Collector not ready yet (HTTP $HTTP_CODE). Retrying in ${RETRY_INTERVAL}s..."
  sleep $RETRY_INTERVAL
done

if [ "$COLLECTOR_READY" = false ]; then
  echo "Error: OTel Collector metrics endpoint is not reachable." >&2
  exit 1
fi

# 3. Check Prometheus server readiness
echo "Checking Prometheus readiness (http://localhost:9090/-/healthy)..."
PROM_READY=false

for ((i=1; i<=MAX_RETRIES; i++)); do
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9090/-/healthy || echo "000")
  if [ "$HTTP_CODE" = "200" ]; then
    echo "  [PASS] Prometheus is healthy (HTTP 200)."
    PROM_READY=true
    break
  fi
  echo "  [RETRY $i/$MAX_RETRIES] Prometheus not ready yet (HTTP $HTTP_CODE). Retrying in ${RETRY_INTERVAL}s..."
  sleep $RETRY_INTERVAL
done

if [ "$PROM_READY" = false ]; then
  echo "Error: Prometheus is not reachable." >&2
  exit 1
fi

# 4. Deep Scrape Verification: Check Prometheus target health
echo "Verifying Prometheus target scrape status for 'otel-collector'..."
TARGET_UP=false

# Wait for Prometheus to complete its initial scrape and mark target as up
for ((i=1; i<=MAX_RETRIES; i++)); do
  TARGETS_JSON=$(curl -s http://localhost:9090/api/v1/targets || echo "")
  
  # Simple grep checks to ensure target is up
  # It looks for "otel-collector" and verifies "health":"up" is nearby.
  # We extract activeTargets section and match our job.
  if echo "$TARGETS_JSON" | grep -q '"job":"otel-collector"' && \
     echo "$TARGETS_JSON" | grep -q '"health":"up"'; then
    echo "  [PASS] Prometheus target 'otel-collector' is successfully scraped and health status is UP."
    TARGET_UP=true
    break
  fi
  
  echo "  [RETRY $i/$MAX_RETRIES] Scrape target 'otel-collector' not verified as UP yet. Retrying in ${RETRY_INTERVAL}s..."
  sleep $RETRY_INTERVAL
done

if [ "$TARGET_UP" = false ]; then
  echo "Warning: Scrape target 'otel-collector' is not reported as UP by Prometheus."
  echo "Full target status payload:"
  curl -s http://localhost:9090/api/v1/targets | grep -o '"job":"otel-collector"[^}]*' || true
  exit 1
fi

echo "=================================================="
echo "SUCCESS: CentralWatch monitoring stack is fully healthy!"
echo "=================================================="
exit 0
