import os
import subprocess
from fastapi import APIRouter, HTTPException

security_router = APIRouter(tags=["Security"])

@security_router.post("/security-scan")
async def trigger_security_scan(target_url: str, token: str = ""):
    """
    Trigger an OWASP ASTF security scan on the specified target.
    Requires astf JAR to be available in the environment or a container service to handle it.
    """
    # This is a basic implementation that expects astf.jar to exist, or delegates to a script.
    script_path = os.environ.get("ASTF_SCRIPT_PATH", "/scripts/security_scan.sh")
    if not os.path.exists(script_path):
        raise HTTPException(status_code=500, detail="Security scan script not configured on the server.")
        
    try:
        # In a real environment, this should be dispatched asynchronously via Celery/BackgroundTasks
        # For demo purposes, we trigger the shell script.
        cmd = [script_path, target_url, token]
        # We start the process and return immediately
        subprocess.Popen(cmd, start_new_session=True)
        return {"status": "Scan initiated", "target": target_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start scan: {str(e)}")
