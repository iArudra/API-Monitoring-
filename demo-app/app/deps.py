"""FastAPI dependencies (dependency injection and authentication)."""

from fastapi import Depends, Header, HTTPException, Request

from .services import Container


def get_container(request: Request) -> Container:
    """Return the application's service container (created once at startup)."""
    return request.app.state.container


def get_bearer_token(authorization: str = Header(default="")) -> str:
    """Extract the raw bearer token from the Authorization header."""
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return token


def require_auth(token: str = Depends(get_bearer_token), container: Container = Depends(get_container)) -> str:
    """Require a valid bearer token for a route (or an entire router).

    Uses the existing HMAC-signed token mechanism: ``AuthService.get_profile``
    verifies the signature and expiry and resolves the user (401 on failure).
    Public endpoints (register/login/health) must NOT use this dependency.
    """
    container.auth.get_profile(token)
    return token
