"""
Authentication endpoints and security dependencies for MY PERSONAL AI.

Provides:
- User registration (/api/v1/auth/register)
- User login (/api/v1/auth/login)
- User logout (/api/v1/auth/logout)
- Current user profile (/api/v1/auth/me)
- FastAPI dependencies: get_current_user, require_owner
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from core.auth import authenticate_user, create_user
from core.audit import log_audit_event
from core.config import settings
from core.logging import logger
from core.sessions import create_session, revoke_session, validate_session

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


# --- Pydantic Schemas ---

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=30, description="Alphanumeric username")
    password: str = Field(..., min_length=8, description="Password (min 8 chars, letter + number/special)")


class LoginRequest(BaseModel):
    username: str = Field(..., description="Registered username")
    password: str = Field(..., description="Account password")


class UserResponse(BaseModel):
    id: str
    username: str
    role: str
    is_active: bool = True


class AuthResponse(BaseModel):
    token: str
    user: UserResponse
    expires_at: str


class MessageResponse(BaseModel):
    message: str


# --- Helper: Extract Token from Request ---

def _extract_token(request: Request) -> Optional[str]:
    """Extract session token from Authorization header or session cookie."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    cookie_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if cookie_token:
        return cookie_token.strip()

    return None


# --- FastAPI Dependencies ---

async def get_current_user(request: Request) -> Dict[str, Any]:
    """Dependency that authenticates the caller via Bearer token or cookie.

    Raises HTTP 401 if token is missing, invalid, or expired.
    """
    token = _extract_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid session token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = validate_session(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def require_owner(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Dependency that restricts an endpoint to users with the 'OWNER' role."""
    if current_user.get("role") != "OWNER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Owner role required.",
        )
    return current_user


# --- Endpoints ---

@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(req: RegisterRequest, response: Response):
    """Register a new user and establish an active authenticated session."""
    if not settings.ALLOW_REGISTRATION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User registration is currently disabled.",
        )

    try:
        # Strictly assign 'USER' role — public API registration can NEVER create an OWNER account
        user_record = create_user(username=req.username, password=req.password, role="USER")
    except ValueError as ve:
        err_msg = str(ve)
        status_code = status.HTTP_409_CONFLICT if "already registered" in err_msg else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=err_msg)

    # Establish session immediately upon registration
    token, session_data = create_session(user_id=user_record["id"])

    log_audit_event(
        event_type="AUTH_REGISTER",
        action="register_user",
        user_id=user_record["id"],
        details={"username": user_record["username"], "role": user_record["role"]},
    )

    # Set secure HTTP-only cookie
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_TTL_SECONDS,
        httponly=True,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        secure=settings.SESSION_COOKIE_SECURE,
        path="/",
    )

    return AuthResponse(
        token=token,
        user=UserResponse(
            id=user_record["id"],
            username=user_record["username"],
            role=user_record["role"],
            is_active=user_record["is_active"],
        ),
        expires_at=session_data["expires_at"],
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate credentials and obtain session token",
)
async def login(req: LoginRequest, response: Response):
    """Validate username and password, return session token, and set session cookie."""
    user = authenticate_user(username=req.username, password=req.password)
    if not user:
        log_audit_event(
            event_type="AUTH_FAILED",
            action="login",
            status="DENIED",
            severity="WARNING",
            details={"username": req.username},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token, session_data = create_session(user_id=user["id"])

    log_audit_event(
        event_type="AUTH_LOGIN",
        action="login",
        user_id=user["id"],
        details={"username": user["username"], "role": user["role"]},
    )

    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_TTL_SECONDS,
        httponly=True,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        secure=settings.SESSION_COOKIE_SECURE,
        path="/",
    )

    return AuthResponse(
        token=token,
        user=UserResponse(
            id=user["id"],
            username=user["username"],
            role=user["role"],
            is_active=user["is_active"],
        ),
        expires_at=session_data["expires_at"],
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke active session token",
)
async def logout(request: Request, response: Response):
    """Revoke the current session token and clear the session cookie."""
    token = _extract_token(request)
    if token:
        user = validate_session(token)
        revoke_session(token)
        log_audit_event(
            event_type="AUTH_LOGOUT",
            action="logout",
            user_id=user["user_id"] if user else None,
            details={"revoked": True},
        )

    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/",
        samesite=settings.SESSION_COOKIE_SAMESITE,
    )
    return MessageResponse(message="Successfully logged out.")


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get profile of current authenticated user",
)
async def get_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return UserResponse(
        id=current_user["user_id"],
        username=current_user["username"],
        role=current_user["role"],
        is_active=True,
    )


@router.get(
    "/users",
    response_model=List[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="List all registered system users (Owner only)",
)
async def list_all_users(owner_user: Dict[str, Any] = Depends(require_owner)):
    """Administrative endpoint restricted exclusively to system OWNER."""
    from data.db import db
    rows = db.fetch_all("SELECT id, username, role, is_active FROM users ORDER BY created_at ASC;")
    return [
        UserResponse(
            id=row["id"],
            username=row["username"],
            role=row["role"],
            is_active=bool(row["is_active"]),
        )
        for row in rows
    ]

