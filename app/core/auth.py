"""
Sistema de autorización y control de acceso basado en roles.
"""
from functools import wraps

from fastapi import Depends, HTTPException, status

from app.core.dependencies import get_current_active_user
from app.models.user import User


class RoleChecker:
    """Verificador de roles para endpoints."""
    
    def __init__(self, required_roles: list[str]):
        self.required_roles = required_roles
    
    def __call__(self, current_user: User = Depends(get_current_active_user)):
        if not any(current_user.has_role_level(role) for role in self.required_roles):
            roles_str = ", ".join(self.required_roles)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado. Se requiere uno de los siguientes roles: {roles_str}"
            )
        return current_user

# Dependencias específicas para roles
def require_auth():
    """Requiere usuario autenticado."""
    return Depends(get_current_active_user)

def require_manager():
    """Requiere rol manager o superior."""
    return Depends(RoleChecker(["manager", "admin", "super_admin"]))

def require_admin():
    """Requiere rol admin o superior."""
    return Depends(RoleChecker(["admin", "super_admin"]))

def require_super_admin():
    """Requiere rol super_admin."""
    return Depends(RoleChecker(["super_admin"]))

# Funciones utilitarias para verificación de roles
def check_role_permission(current_user: User, required_role: str) -> bool:
    """Verifica si el usuario tiene el rol requerido o superior."""
    return current_user.has_role_level(required_role)

def check_promotion_permission(current_user: User, target_role: str) -> bool:
    """Verifica si el usuario puede promover a otro usuario al rol objetivo."""
    return current_user.can_promote_to(target_role)

# Middleware de roles para endpoints específicos
async def get_manager_user(current_user: User = Depends(get_current_active_user)) -> User:
    """Obtiene usuario con rol manager o superior."""
    if not current_user.has_role_level("manager"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de manager o superior"
        )
    return current_user

async def get_admin_user(current_user: User = Depends(get_current_active_user)) -> User:
    """Obtiene usuario con rol admin o superior."""
    if not current_user.has_role_level("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de administrador o superior"
        )
    return current_user

async def get_super_admin_user(current_user: User = Depends(get_current_active_user)) -> User:
    """Obtiene usuario con rol super_admin."""
    if not current_user.is_super_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de super administrador"
        )
    return current_user

# Verificadores de permisos específicos
class PermissionChecker:
    """Verificador de permisos específicos."""
    
    @staticmethod
    def can_manage_users(user: User) -> bool:
        """Verifica si puede gestionar usuarios."""
        return user.has_role_level("admin")
    
    @staticmethod
    def can_view_reports(user: User) -> bool:
        """Verifica si puede ver reportes."""
        return user.has_role_level("manager")
    
    @staticmethod
    def can_manage_products(user: User) -> bool:
        """Verifica si puede gestionar productos."""
        return user.has_role_level("admin")
    
    @staticmethod
    def can_manage_orders(user: User) -> bool:
        """Verifica si puede gestionar órdenes."""
        return user.has_role_level("admin")
    
    @staticmethod
    def can_access_system_settings(user: User) -> bool:
        """Verifica si puede acceder a configuraciones del sistema."""
        return user.is_super_admin()
    
    @staticmethod
    def can_promote_users(user: User, target_role: str) -> bool:
        """Verifica si puede promover usuarios a un rol específico."""
        return user.can_promote_to(target_role)

# Decorador para verificar permisos en funciones
def require_permission(permission_check):
    """Decorador para verificar permisos específicos."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Buscar el parámetro current_user en kwargs
            current_user = kwargs.get('current_user')
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Usuario no autenticado"
                )
            
            if not permission_check(current_user):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Permisos insuficientes"
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator 