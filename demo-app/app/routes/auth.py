"""Authentication routes (backed by DynamoDB via LocalStack)."""

from fastapi import APIRouter, Depends, Header, HTTPException

from ..deps import get_container, require_auth
from ..schemas.auth import LoginRequest, LoginResponse, RegisterRequest, UserOut
from ..services import Container

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201, summary="Register a new user (DynamoDB)")
def register(body: RegisterRequest, container: Container = Depends(get_container)) -> UserOut:
    return container.auth.register(body.email, body.password, body.name, body.allowed_cidrs)


@router.post("/login", response_model=LoginResponse, summary="Login and get a bearer token (DynamoDB)")
def login(body: LoginRequest, container: Container = Depends(get_container)) -> LoginResponse:
    return container.auth.login(body.email, body.password)


@router.get("/profile", response_model=UserOut, summary="Get the current user profile (DynamoDB)")
def profile(
    token: str = Depends(require_auth),
    container: Container = Depends(get_container),
) -> UserOut:
    return container.auth.get_profile(token)
