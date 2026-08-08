#!/bin/sh
set -e

if [ -n "${AWS_ENDPOINT_URL:-}" ]; then
  echo "[entrypoint] AWS_ENDPOINT_URL is set — waiting for LocalStack at ${AWS_ENDPOINT_URL} ..."

  python - <<'PY'
import os
import sys
import time
import urllib.request

endpoint = os.environ.get("AWS_ENDPOINT_URL", "").rstrip("/")
timeout = float(os.environ.get("LOCALSTACK_WAIT_TIMEOUT_SECONDS", "120"))
url = endpoint + "/_localstack/health"
deadline = time.monotonic() + timeout
ready = False

while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            if resp.status == 200:
                ready = True
                break
    except Exception:
        pass
    time.sleep(2)

if ready:
    print("[entrypoint] LocalStack is ready.")
else:
    print("[entrypoint] WARNING: LocalStack not ready in time; the app will retry initialization.")
PY
else
  echo "[entrypoint] No AWS_ENDPOINT_URL configured — using AWS default regional endpoints."
fi

echo "[entrypoint] Starting uvicorn (CentralWatch demo app) ..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --no-access-log
