#!/usr/bin/env bash
# start.sh - Script to start the CentralWatch monitoring stack in detached mode.

# Exit immediately if a command exits with a non-zero status
set -eo pipefail

# Determine script's directory to ensure relative paths work regardless of execution location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=================================================="
echo "Starting CentralWatch Monitoring Infrastructure..."
echo "Project Root: ${PROJECT_ROOT}"
echo "=================================================="

# Navigate to project root containing docker-compose.yml
cd "${PROJECT_ROOT}"

# Start services using Docker Compose
docker compose up -d

echo "--------------------------------------------------"
echo "Services started successfully!"
echo "OTel Collector Port: 4317 (gRPC) & 4318 (HTTP)"
echo "Prometheus Web UI: http://localhost:9090"
echo "--------------------------------------------------"
echo "Run healthcheck.sh to verify full connectivity."
echo "=================================================="
