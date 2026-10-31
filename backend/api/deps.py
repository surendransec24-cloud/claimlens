from typing import List, Optional
from fastapi import Request, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.user import User
from backend.services.auth_service import decode_token

# Production Note: For production architectures, replace cookie/token decoding with
# an API Gateway JWT verification layer or OAuth2/OpenID Connect introspection endpoint.


async def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Extracts and validates the current user from cookies or Authorization header without raising 401."""
    token = request.cookies.get("access_token")

    # Fallback to Authorization: Bearer <token> for automated testing / CLI
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]

    if not token:
        return None

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        return None

    return user


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """FastAPI dependency requiring a valid, active user session. Raises 401 if unauthenticated."""
    user = await get_current_user_optional(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return user


def require_role(allowed_roles: List[str]):
    """Returns a dependency that verifies the user has one of the required roles."""
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires one of roles: {', '.join(allowed_roles)}."
            )
        return current_user
    return role_checker


async def verify_csrf(request: Request):
    """
    Validates CSRF double-submit token for state-changing HTTP methods.
    If the client is authenticating via cookies, X-CSRF-Token must match csrf_token cookie.
    """
    if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
        # If authenticated via cookie
        cookie_csrf = request.cookies.get("csrf_token")
        if cookie_csrf:
            header_csrf = request.headers.get("X-CSRF-Token")
            if not header_csrf or header_csrf != cookie_csrf:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="CSRF validation failed. Missing or invalid X-CSRF-Token header."
                )

