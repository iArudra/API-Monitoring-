"""Authentication routes (backed by DynamoDB via LocalStack)."""

from fastapi import APIRouter, Depends, Header, HTTPException

from ..deps import get_container
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
    authorization: str = Header(default=""),
    container: Container = Depends(get_container),
) -> UserOut:
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return container.auth.get_profile(token)
