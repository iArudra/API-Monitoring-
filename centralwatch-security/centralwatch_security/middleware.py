import ipaddress
import logging
from typing import Callable, Awaitable, Optional, Dict, Any
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from opentelemetry import trace

logger = logging.getLogger("centralwatch_security")
tracer = trace.get_tracer(__name__)

class SecurityEnforcementMiddleware(BaseHTTPMiddleware):
    """
    Hybrid Security Gateway Middleware for FastAPI.
    Validates IPs against allowed CIDRs and checks API key status via a callback.
    """
    def __init__(
        self,
        app,
        get_policy_callback: Callable[[Request], Awaitable[Optional[Dict[str, Any]]]]
    ):
        super().__init__(app)
        self.get_policy_callback = get_policy_callback

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        try:
            # The callback should return a dict like:
            # {"status": "ACTIVE", "allowed_cidrs": ["10.0.0.0/8"], "user_id": "usr_123"}
            # or None if the route doesn't require auth or token is missing.
            policy = await self.get_policy_callback(request)
        except Exception:
            policy = None

        if policy:
            user_id = policy.get("user_id", "unknown")
            status = policy.get("status", "ACTIVE")
            allowed_cidrs = policy.get("allowed_cidrs", ["0.0.0.0/0"])

            if status == "REVOKED":
                self._log_security_event("TOKEN_REVOKED", request, user_id)
                return Response(content='{"detail": "API Key has been revoked"}', status_code=403, media_type="application/json")

            client_ip_str = request.client.host if request.client else "127.0.0.1"
            try:
                client_ip = ipaddress.ip_address(client_ip_str)
            except ValueError:
                client_ip = ipaddress.ip_address("127.0.0.1")

            is_allowed = False
            for cidr in allowed_cidrs:
                try:
                    if client_ip in ipaddress.ip_network(cidr, strict=False):
                        is_allowed = True
                        break
                except ValueError:
                    pass

            if not is_allowed:
                self._log_security_event("IP_SUBNET_VIOLATION", request, user_id, str(client_ip))
                return Response(content='{"detail": "Access denied: IP outside allowed subnet"}', status_code=403, media_type="application/json")

        return await call_next(request)

    def _log_security_event(self, event_type: str, request: Request, user_id: str, client_ip: str = ""):
        extra = {
            "security_event": event_type,
            "user_id": user_id,
            "status_code": 403,
            "action": "BLOCKED"
        }
        if client_ip:
            extra["client_ip"] = client_ip

        logger.warning(f"Security event triggered: {event_type}", extra=extra)
        
        span = trace.get_current_span()
        if span.is_recording():
            span.set_attribute("security.event_type", event_type)
            span.set_attribute("security.user_id", user_id)
            if client_ip:
                span.set_attribute("security.client_ip", client_ip)
            span.set_attribute("security.action", "BLOCKED")
