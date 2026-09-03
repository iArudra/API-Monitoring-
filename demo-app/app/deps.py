import ipaddress
from fastapi import Depends, Header, HTTPException, Request

from .services import Container
from .telemetry.logging import get_logger

logger = get_logger(__name__)


def get_container(request: Request) -> Container:
    """Return the application's service container (created once at startup)."""
    return request.app.state.container


def get_bearer_token(authorization: str = Header(default="")) -> str:
    """Extract the raw bearer token from the Authorization header."""
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return token


def require_auth(
    request: Request,
    token: str = Depends(get_bearer_token), 
    container: Container = Depends(get_container)
) -> str:
    """Require a valid bearer token and enforce security policies."""
    user = container.auth.get_profile(token)
    
    if user.status == "REVOKED":
        logger.warning("API Key revoked", extra={
            "security_event": "TOKEN_REVOKED",
            "user_id": user.user_id,
            "status_code": 403,
            "action": "BLOCKED"
        })
        raise HTTPException(status_code=403, detail="API Key has been revoked")

    client_ip_str = request.client.host if request.client else "127.0.0.1"
    try:
        client_ip = ipaddress.ip_address(client_ip_str)
    except ValueError:
        client_ip = ipaddress.ip_address("127.0.0.1")

    is_allowed = False
    for cidr in user.allowed_cidrs:
        try:
            if client_ip in ipaddress.ip_network(cidr, strict=False):
                is_allowed = True
                break
        except ValueError:
            pass
            
    if not is_allowed:
        logger.warning("API Key leakage suspected from unauthorized IP %s", client_ip, extra={
            "security_event": "IP_SUBNET_VIOLATION",
            "client_ip": str(client_ip),
            "user_id": user.user_id,
            "status_code": 403,
            "action": "BLOCKED"
        })
        raise HTTPException(status_code=403, detail="Access denied: IP outside allowed subnet")
        
    return token
