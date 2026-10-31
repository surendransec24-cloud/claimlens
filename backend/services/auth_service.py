import time
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, List
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.user import User
from backend.models.revoked_token import RevokedToken

# Production Note: In a production multi-node deployment, replace in-memory rate limiting
# with Redis, integrate enterprise SSO (SAML 2.0 / OIDC / OAuth2), enforce hardware MFA
# (WebAuthn/TOTP), and store cryptographic secrets in AWS Secrets Manager or HashiCorp Vault.

hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16
)

# Reject very common or trivial passwords
COMMON_PASSWORDS = {
    "password123", "password1234", "password12345", "1234567890", "admin12345",
    "claimlens123", "insurance123", "qwertyuiop", "letmein1234",
    "welcome1234", "changeme123", "password1", "passw0rd1", "abc123456789",
    "iloveyou123", "monkey12345", "dragon12345", "master12345", "hello12345"
}

# In-memory IP rate limiter: ip -> list of attempt timestamps
_ip_attempts: Dict[str, List[float]] = {}
IP_RATE_LIMIT_WINDOW = 60.0  # 1 minute
IP_MAX_ATTEMPTS = 10         # max 10 login requests per minute per IP


def validate_password_strength(password: str) -> Tuple[bool, Optional[str]]:
    """Enforces minimum length of 10 and checks against common passwords."""
    if not password or len(password) < 10:
        return False, "Password must be at least 10 characters in length."
    if password.lower() in COMMON_PASSWORDS:
        return False, "Password is too common and easily guessed. Please choose a stronger password."
    return True, None


def hash_password(password: str) -> str:
    """Hashes a plaintext password using Argon2id."""
    return hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Verifies a plaintext password against an Argon2id hash in constant time."""
    try:
        return hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def check_ip_rate_limit(ip: str) -> bool:
    """Returns True if within rate limit, False if rate-limited."""
    now = time.time()
    attempts = _ip_attempts.get(ip, [])
    # Filter attempts within window
    attempts = [t for t in attempts if now - t < IP_RATE_LIMIT_WINDOW]
    if len(attempts) >= IP_MAX_ATTEMPTS:
        _ip_attempts[ip] = attempts
        return False
    attempts.append(now)
    _ip_attempts[ip] = attempts
    return True


def create_access_token(user: User) -> str:
    """Creates a short-lived 15-minute access JWT."""
    now = datetime.utcnow()
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "name": user.full_name,
        "type": "access",
        "jti": secrets.token_hex(16),
        "iat": now,
        "exp": expire
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user: User) -> Tuple[str, str, datetime]:
    """Creates a 7-day refresh JWT with unique JTI for rotation."""
    now = datetime.utcnow()
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    jti = secrets.token_hex(16)
    payload = {
        "sub": user.id,
        "type": "refresh",
        "jti": jti,
        "iat": now,
        "exp": expire
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, jti, expire


def decode_token(token: str) -> Optional[dict]:
    """Decodes and validates a JWT token."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


def is_token_revoked(db: Session, jti: str) -> bool:
    """Checks if a token JTI has been revoked."""
    return db.query(RevokedToken).filter(RevokedToken.jti == jti).first() is not None


def revoke_token(db: Session, jti: str, expires_at: datetime):
    """Adds a token JTI to the revocation blacklist."""
    if not is_token_revoked(db, jti):
        revoked = RevokedToken(jti=jti, expires_at=expires_at)
        db.add(revoked)
        db.commit()


def generate_csrf_token() -> str:
    """Generates a secure random CSRF token for double-submit cookie validation."""
    return secrets.token_urlsafe(32)

