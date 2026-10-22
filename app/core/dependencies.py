from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional
from app.config.database import get_db
from app.config.settings import Settings
from app.core.security import verify_token
from app.models.user import User
from app.config.logging_config import get_logger, log_error

logger = get_logger("auth")

settings = Settings()
# HTTP Bearer security scheme
security = HTTPBearer() 

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user."""
    logger.info("get_current_user invocado")
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    logger.debug(
        "Credenciales recibidas",
        extra={
            "scheme": credentials.scheme if credentials else None,
            "has_token": bool(credentials and credentials.credentials),
            "token_preview": (credentials.credentials[:5] + "***")
            if credentials and credentials.credentials
            else None,
        },
    )
    
    try:
        if not credentials:
            logger.warning("Solicitud sin credenciales Bearer")
            raise credentials_exception
            
        if not credentials.credentials:
            logger.warning("Bearer token vacío")
            raise credentials_exception
        
        logger.debug("Verificando token de acceso")
        # Verify token
        email = verify_token(credentials.credentials, "access")
        logger.debug("Token de acceso verificado", extra={"email": email})
        
        # Get user from database
        logger.debug("Consultando usuario en base de datos", extra={"email": email})
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            logger.warning("Usuario no encontrado para email autenticado", extra={"email": email})
            raise credentials_exception
        
        logger.info(
            "Usuario autenticado correctamente",
            extra={
                "user_id": user.id,
                "user_email": user.email,
                "is_active": user.is_active,
            },
        )
        return user
    except HTTPException as e:
        logger.warning(
            "HTTPException en get_current_user",
            extra={"status_code": e.status_code, "detail": e.detail},
        )
        raise
    except Exception as e:
        log_error(logger, e, context={"dependency": "get_current_user"})
        raise credentials_exception

async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current active user."""
    logger.debug(
        "Validando usuario activo",
        extra={
            "user_id": current_user.id if current_user else None,
            "user_email": current_user.email if current_user else None,
        },
    )
    
    if not current_user.is_active:
        logger.warning(
            "Usuario inactivo detectado",
            extra={"user_id": current_user.id, "user_email": current_user.email},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Usuario inactivo"
        )
    
    logger.debug("Usuario activo confirmado", extra={"user_id": current_user.id})
    return current_user

async def get_current_verified_user(current_user: User = Depends(get_current_active_user)) -> User:
    """Get current verified user."""
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email no verificado"
        )
    return current_user

async def get_optional_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Get current user if authenticated, otherwise return None."""
    try:
        authorization = request.headers.get("authorization")
        if not authorization:
            return None
            
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            return None
            
        email = verify_token(token, "access")
        user = db.query(User).filter(User.email == email).first()
        return user if user and user.is_active else None
    except Exception:
        return None

# Admin role dependency (Updated for new role system)
async def get_admin_user(current_user: User = Depends(get_current_verified_user)) -> User:
    """Get current admin user."""
    if not current_user.has_role_level("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador"
        )
    return current_user

# Enhanced Pagination dependency with configuration
class PaginationParams:
    def __init__(self, page: int = 1, limit: int = None):
        # Use settings for default values
        if limit is None:
            limit = settings.DEFAULT_PAGE_SIZE
            
        self.page = max(1, page)
        self.limit = min(settings.MAX_PAGE_SIZE, max(settings.MIN_PAGE_SIZE, limit))
        self.skip = (self.page - 1) * self.limit

def get_pagination_params(
    page: int = 1, 
    limit: int = None
) -> PaginationParams:
    """Get pagination parameters with configurable defaults."""
    return PaginationParams(page, limit) 