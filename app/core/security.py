import secrets
from datetime import timedelta

import jwt
from fastapi import HTTPException, status
from jwt import ExpiredSignatureError, InvalidTokenError
from passlib.context import CryptContext

from app.config.logging_config import get_logger
from app.config.settings import Settings
from app.core.exceptions import FarmaException
from app.utils.timezone import get_ve_now

logger = get_logger("auth")

settings = Settings()

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Generate password hash."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = get_ve_now() + expires_delta
    else:
        expire = get_ve_now() + timedelta(minutes=settings.jwt.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.jwt.SECRET_KEY, algorithm=settings.jwt.ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict) -> str:
    """Create JWT refresh token."""
    to_encode = data.copy()
    expire = get_ve_now() + timedelta(days=settings.jwt.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.jwt.SECRET_KEY, algorithm=settings.jwt.ALGORITHM)
    return encoded_jwt


class TokenExpiredException(FarmaException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado",
        )


class InvalidTokenException(FarmaException):
    def __init__(self, detail: str = "Token inválido") -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )


def verify_token(token: str, token_type: str = "access") -> str:
    """Verify and decode JWT token.

    Returns the subject (email) embedded in the token, or raises an
    HTTPException. Implementation now uses PyJWT instead of python-jose.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido: token vacío",
        )

    token = token.strip()

    try:
        payload = jwt.decode(
            token,
            settings.jwt.SECRET_KEY,
            algorithms=[settings.jwt.ALGORITHM],
        )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
        )

    email: str | None = payload.get("sub")
    token_type_check: str | None = payload.get("type")

    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido: email no encontrado",
        )

    if token_type_check != token_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido: tipo esperado {token_type}",
        )

    return email

def generate_verification_token() -> str:
    """Generate a unique verification token."""
    return secrets.token_urlsafe(32)

def generate_reset_token() -> str:
    """Generate a unique password reset token."""
    return secrets.token_urlsafe(32)

def create_url_safe_token(data: dict, expires_hours: int = 24) -> str:
    """Create a URL-safe token for email verification and password reset."""
    to_encode = data.copy()
    expire = get_ve_now() + timedelta(hours=expires_hours)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt.SECRET_KEY, algorithm=settings.jwt.ALGORITHM)
    return encoded_jwt

def verify_url_safe_token(token: str) -> dict | None:
    """Verify URL-safe token and return payload.

    Returns None on any decoding error (expired or invalid). The caller is
    responsible for distinguishing the two cases; we keep the original
    public contract of this function (no exception raised) intact.
    """
    try:
        payload = jwt.decode(token, settings.jwt.SECRET_KEY, algorithms=[settings.jwt.ALGORITHM])
        return payload
    except (ExpiredSignatureError, InvalidTokenError):
        return None