#!/usr/bin/env bash
# OWASP ASTF Security Scan Trigger Script
# Downloads the scanner if missing, and runs it against the target.

TARGET_URL=${1:-"http://127.0.0.1:8000"}
TOKEN=${2:-""}

ASTF_JAR="/app/astf-v2.0.1.jar"
REPORT_DIR="/app/reports"

mkdir -p "$REPORT_DIR"

if [ ! -f "$ASTF_JAR" ]; then
    echo "Downloading OWASP ASTF..."
    curl -sSL "https://github.com/OWASP/www-project-api-security-testing-framework/releases/latest/download/astf-v2.0.1.jar" -o "$ASTF_JAR"
fi

echo "Running security scan against $TARGET_URL..."

# Note: In a real scenario, you'd pass the auth token. 
# We output the report to the reports directory which can be served or inspected.
if [ -n "$TOKEN" ]; then
    java -jar "$ASTF_JAR" -u "$TARGET_URL" --token "$TOKEN" -f HTML -o "$REPORT_DIR/security-report.html"
else
    java -jar "$ASTF_JAR" -u "$TARGET_URL" -f HTML -o "$REPORT_DIR/security-report.html"
fi

echo "Scan complete. Report generated at $REPORT_DIR/security-report.html"
