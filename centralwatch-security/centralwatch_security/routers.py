import os
import subprocess
from asyncio import to_thread
from fastapi import APIRouter, Header, HTTPException
import logging

security_router = APIRouter(tags=["Security"])
logger = logging.getLogger("centralwatch_security")

@security_router.post("/security-scan")
async def trigger_security_scan(target_url: str, authorization: str = Header(default="")):
    """
    Trigger an OWASP ASTF security scan on the specified target.
    The caller's validated bearer token is forwarded to ASTF for authenticated checks.
    """
    script_path = os.environ.get("ASTF_SCRIPT_PATH", "/scripts/security_scan.sh")
    if not os.path.exists(script_path):
        raise HTTPException(status_code=500, detail="Security scan script not configured on the server.")

    token = authorization.removeprefix("Bearer ").strip()
    logger.info("Security scan started: target_url=%s script=%s", target_url, script_path)
    try:
        cmd = [script_path, target_url, token]
        result = await to_thread(
            subprocess.run,
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=int(os.environ.get("ASTF_SCAN_TIMEOUT_SECONDS", "1800")),
        )
    except subprocess.TimeoutExpired:
        logger.exception("Security scan timed out: target_url=%s", target_url)
        raise HTTPException(status_code=504, detail="Security scan timed out.")
    except OSError as exc:
        logger.exception("Security scan could not be executed: target_url=%s", target_url)
        raise HTTPException(status_code=500, detail=f"Failed to execute security scan: {exc}") from exc

    output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    if output:
        logger.info("ASTF scan output:\n%s", output)
    if result.returncode not in (0, 1):
        logger.error("Security scan failed: target_url=%s exit_code=%d", target_url, result.returncode)
        raise HTTPException(
            status_code=502,
            detail=f"ASTF security scan failed with exit code {result.returncode}.",
        )
    if result.returncode == 1:
        logger.warning("ASTF scan completed with findings: target_url=%s", target_url)

    report_path = os.environ.get("ASTF_REPORT_PATH", "/app/reports/security-report.html")
    try:
        report_size = os.path.getsize(report_path)
    except OSError as exc:
        logger.error("Security scan did not produce report: path=%s error=%s", report_path, exc)
        raise HTTPException(status_code=502, detail="ASTF scan completed without generating a report.") from exc
    if report_size == 0:
        logger.error("Security scan produced an empty report: path=%s", report_path)
        raise HTTPException(status_code=502, detail="ASTF scan generated an empty report.")

    logger.info("Security scan complete: target_url=%s report=%s bytes=%d", target_url, report_path, report_size)
    return {
        "status": "Scan complete",
        "target": target_url,
        "report": report_path,
        "report_bytes": report_size,
        "findings_detected": result.returncode == 1,
    }
