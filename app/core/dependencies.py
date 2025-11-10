from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional
from app.config.database import get_db
from app.config.settings import Settings
from app.core.security import verify_token
from app.models.user import User

settings = Settings()
# HTTP Bearer security scheme
security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        print(
            "[auth] get_current_user called",
            f"scheme={credentials.scheme if credentials else 'None'}",
        )
        # Verify token
        email = verify_token(credentials.credentials, "access")
        print("[auth] token verified", f"email={email}")
        
        # Get user from database
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            print("[auth] user not found in database", f"email={email}")
            raise credentials_exception
        print(
            "[auth] user fetched",
            f"id={user.id}",
            f"is_active={user.is_active}",
            f"is_verified={getattr(user, 'is_verified', None)}",
        )
        return user
    except Exception as e:
        print("[auth] get_current_user error", repr(e))
        raise credentials_exception

async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current active user."""
    if not current_user.is_active:
        print(
            "[auth] inactive user attempted access",
            f"id={current_user.id}",
            f"email={current_user.email}",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Usuario inactivo"
        )
    print(
        "[auth] current active user",
        f"id={current_user.id}",
        f"email={current_user.email}",
    )
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