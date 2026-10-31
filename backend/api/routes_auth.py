import time
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.user import User
from backend.models.audit_log import AuditLog
from backend.config import settings
from backend.services.auth_service import (
    validate_password_strength,
    hash_password,
    verify_password,
    check_ip_rate_limit,
    create_access_token,
    create_refresh_token,
    decode_token,
    is_token_revoked,
    revoke_token,
    generate_csrf_token,
)
from backend.api.deps import get_current_user, require_role, verify_csrf

router = APIRouter(prefix="/api/auth", tags=["authentication"])

# Pydantic Request Schemas
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    role: str = "adjuster"


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str, csrf_token: str):
    """Sets secure HttpOnly session cookies."""
    # Access token cookie (15 mins)
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        path="/"
    )
    # Refresh token cookie (7 days)
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        path="/"
    )
    # CSRF token cookie (accessible by JavaScript for setting X-CSRF-Token header)
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=False,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        path="/"
    )


def _clear_auth_cookies(response: Response):
    """Clears all session cookies."""
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")
    response.delete_cookie(key="csrf_token", path="/")


@router.post("/login")
def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    client_ip = request.client.host if request.client else "unknown"

    # 1. IP Rate Limiting Defense
    if not check_ip_rate_limit(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts from this IP address. Please wait 1 minute before trying again."
        )

    # 2. User Lookup
    email_clean = req.email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()

    # 3. Account Lockout Check
    if user and user.locked_until:
        if user.locked_until > datetime.utcnow():
            remaining_mins = max(1, int((user.locked_until - datetime.utcnow()).total_seconds() / 60) + 1)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account locked due to multiple failed login attempts. Please try again after {remaining_mins} minutes."
            )
        else:
            # Lockout expired
            user.locked_until = None
            user.failed_attempts = 0
            db.commit()

    # 4. Password Verification (constant generic error message)
    GENERIC_AUTH_ERROR = "Incorrect email or password."

    if not user or not user.is_active or not verify_password(user.password_hash, req.password):
        if user and user.is_active:
            user.failed_attempts += 1
            newly_locked = False
            if user.failed_attempts >= 5:
                user.locked_until = datetime.utcnow() + timedelta(minutes=15)
                newly_locked = True
                # Audit log lockout
                log_lock = AuditLog(
                    event_type="account_locked",
                    user_id=user.id,
                    user_role=user.role,
                    input_summary=f"5 consecutive failed login attempts from IP {client_ip}",
                    output_summary="Account locked for 15 minutes"
                )
                db.add(log_lock)

            # Audit log failed attempt
            log_fail = AuditLog(
                event_type="login_failed",
                user_id=user.id,
                user_role=user.role,
                input_summary=f"Failed login attempt for {email_clean} from IP {client_ip}",
                output_summary=f"Attempt {user.failed_attempts}/5"
            )
            db.add(log_fail)
            db.commit()

            # If this attempt triggered the lockout, raise 403 immediately
            if newly_locked:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account locked due to multiple failed login attempts. Please try again after 15 minutes."
                )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=GENERIC_AUTH_ERROR
        )

    # 5. Successful Authentication
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.utcnow()

    access_token = create_access_token(user)
    refresh_token, _, _ = create_refresh_token(user)
    csrf_token = generate_csrf_token()

    _set_auth_cookies(response, access_token, refresh_token, csrf_token)

    # Audit log login success
    log_success = AuditLog(
        event_type="login_success",
        user_id=user.id,
        user_role=user.role,
        input_summary=f"User signed in successfully from IP {client_ip}",
        output_summary=f"Role: {user.role}"
    )
    db.add(log_success)
    db.commit()

    return {
        "status": "success",
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role
        },
        "csrf_token": csrf_token
    }


@router.post("/refresh")
def refresh_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """Silent token refresh endpoint using HttpOnly refresh cookie."""
    token = request.cookies.get("refresh_token")
    if not token:
        _clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token. Please sign in again."
        )

    payload = decode_token(token)
    if not payload or payload.get("type") != "refresh":
        _clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token."
        )

    jti = payload.get("jti")
    if not jti or is_token_revoked(db, jti):
        _clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked or already rotated."
        )

    # Invalidate previous refresh token (rotation!)
    exp_ts = payload.get("exp", time.time() + 86400)
    revoke_token(db, jti, datetime.utcfromtimestamp(exp_ts))

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        _clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account inactive or not found."
        )

    # Issue new access + refresh pair
    new_access_token = create_access_token(user)
    new_refresh_token, _, _ = create_refresh_token(user)
    csrf_token = generate_csrf_token()

    _set_auth_cookies(response, new_access_token, new_refresh_token, csrf_token)

    return {
        "status": "refreshed",
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role
        },
        "csrf_token": csrf_token
    }


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """Invalidates session and clears all authentication cookies."""
    # Revoke refresh token if present
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        payload = decode_token(refresh_token)
        if payload and payload.get("jti"):
            exp_ts = payload.get("exp", time.time() + 86400)
            revoke_token(db, payload["jti"], datetime.utcfromtimestamp(exp_ts))

    # Log logout if access token valid
    access_token = request.cookies.get("access_token")
    if access_token:
        payload = decode_token(access_token)
        if payload and payload.get("sub"):
            log_out = AuditLog(
                event_type="logout",
                user_id=payload["sub"],
                user_role=payload.get("role", "adjuster"),
                input_summary="User signed out",
                output_summary="Session invalidated"
            )
            db.add(log_out)
            db.commit()

    _clear_auth_cookies(response)
    return {"status": "success", "message": "Signed out successfully."}


@router.get("/me")
def get_current_user_profile(
    current_user: User = Depends(get_current_user)
):
    """Returns profile for currently authenticated user."""
    return {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "email": current_user.email,
        "role": current_user.role,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        "last_login_at": current_user.last_login_at.isoformat() if current_user.last_login_at else None
    }


@router.post("/change-password", dependencies=[Depends(verify_csrf)])
def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Authenticated user changes their password."""
    if not verify_password(current_user.password_hash, req.current_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password verification failed."
        )

    valid, err_msg = validate_password_strength(req.new_password)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg
        )

    current_user.password_hash = hash_password(req.new_password)
    db.commit()

    # Log to audit log
    log = AuditLog(
        event_type="password_changed",
        user_id=current_user.id,
        user_role=current_user.role,
        input_summary="Password change request",
        output_summary="Password updated successfully"
    )
    db.add(log)
    db.commit()

    return {"status": "success", "message": "Password changed successfully."}


@router.post("/register", dependencies=[Depends(verify_csrf)])
def register_staff_user(
    req: RegisterRequest,
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    """Admin-only endpoint to create new staff accounts."""
    role_clean = req.role.strip().lower()
    if role_clean not in ["adjuster", "supervisor", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role. Must be one of: adjuster, supervisor, admin."
        )

    valid, err_msg = validate_password_strength(req.password)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg
        )

    email_clean = req.email.strip().lower()
    existing = db.query(User).filter(User.email == email_clean).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address is already registered."
        )

    new_user = User(
        full_name=req.full_name.strip(),
        email=email_clean,
        password_hash=hash_password(req.password),
        role=role_clean,
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Log to audit log
    log = AuditLog(
        event_type="user_created",
        user_id=current_user.id,
        user_role=current_user.role,
        input_summary=f"Admin created new staff user: {new_user.email}",
        output_summary=f"Assigned Role: {new_user.role}"
    )
    db.add(log)
    db.commit()

    return {
        "status": "success",
        "user": {
            "id": new_user.id,
            "full_name": new_user.full_name,
            "email": new_user.email,
            "role": new_user.role
        }
    }

