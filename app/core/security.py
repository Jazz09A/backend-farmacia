from datetime import timedelta
from typing import Optional, Union
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
from app.config.settings import Settings
import uuid
from app.utils.timezone import get_ve_now
from app.config.logging_config import get_logger, log_error

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

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = get_ve_now() + expires_delta
    else:
        expire = get_ve_now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict) -> str:
    """Create JWT refresh token."""
    to_encode = data.copy()
    expire = get_ve_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_token(token: str, token_type: str = "access") -> str:
    """Verify and decode JWT token."""
    logger.debug(
        "verify_token invocado",
        extra={
            "token_type_expected": token_type,
            "token_length": len(token) if token else 0,
        },
    )
    
    # Validar que el token no esté vacío
    if not token:
        logger.warning("Token vacío recibido")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido: token vacío"
        )
    
    # Limpiar espacios en blanco
    token = token.strip()
    
    # Validar formato JWT: debe tener exactamente 3 segmentos separados por puntos
    segments = token.split(".")
    if len(segments) != 3:
        logger.warning(
            "Token con formato inválido",
            extra={
                "segments_count": len(segments),
                "token_length": len(token),
                "token_preview": token[:50] + "..." if len(token) > 50 else token,
                "token_ends_with": token[-10:] if len(token) > 10 else token,
                "has_spaces": " " in token,
                "has_newlines": "\n" in token or "\r" in token,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido: formato incorrecto"
        )
    
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        logger.debug(
            "Token decodificado correctamente",
            extra={
                "payload_keys": list(payload.keys()),
            },
        )
        
        email: str = payload.get("sub")
        token_type_check: str = payload.get("type")
        
        logger.debug(
            "Datos extraídos del token",
            extra={
                "email_present": bool(email),
                "token_type_from_token": token_type_check,
            },
        )
        
        if email is None:
            logger.warning("Email no encontrado en el token decodificado")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido: email no encontrado"
            )
        
        if token_type_check != token_type:
            logger.warning(
                "Tipo de token inválido",
                extra={
                    "expected_type": token_type,
                    "received_type": token_type_check,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token inválido: tipo esperado {token_type}"
            )
        
        logger.debug("Token verificado correctamente", extra={"email": email})
        return email
    except JWTError as e:
        log_error(logger, e, context={"token_type_expected": token_type})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado"
        )
    except HTTPException:
        raise
    except Exception as e:
        log_error(logger, e, context={"token_type_expected": token_type})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado"
        )

def generate_verification_token() -> str:
    """Generate a unique verification token."""
    return str(uuid.uuid4())

def generate_reset_token() -> str:
    """Generate a unique password reset token."""
    return str(uuid.uuid4())

def create_url_safe_token(data: dict, expires_hours: int = 24) -> str:
    """Create a URL-safe token for email verification and password reset."""
    to_encode = data.copy()
    expire = get_ve_now() + timedelta(hours=expires_hours)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_url_safe_token(token: str) -> Union[dict, None]:
    """Verify URL-safe token and return payload."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None 