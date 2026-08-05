#!/usr/bin/env bash
# stop.sh - Script to stop and clean up the CentralWatch monitoring stack.

# Exit immediately if a command exits with a non-zero status
set -eo pipefail

# Determine script's directory to ensure relative paths work regardless of execution location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=================================================="
echo "Stopping CentralWatch Monitoring Infrastructure..."
echo "Project Root: ${PROJECT_ROOT}"
echo "=================================================="

# Navigate to project root containing docker-compose.yml
cd "${PROJECT_ROOT}"

# Stop services and remove containers, networks, and volumes (optional, keeping volumes by default)
docker compose down

echo "--------------------------------------------------"
echo "Services stopped successfully!"
echo "=================================================="
