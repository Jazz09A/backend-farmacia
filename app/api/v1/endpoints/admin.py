"""
Endpoints de administración para gestión de usuarios y roles.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.core.auth import require_admin, require_super_admin, get_admin_user, get_super_admin_user
from app.models.user import User
from app.services.role_service import RoleService
from app.schemas.role import (
    UserRoleResponse, RolePermissionsResponse, RoleHierarchyResponse,
    PromotionRequest, PromotionResponse, UserRole
)
from app.schemas.user import UserResponse
from app.core.dependencies import PaginationParams, get_pagination_params

router = APIRouter(prefix="/admin", tags=["Admin"])

# =============================================================================
# ENDPOINTS DE INFORMACIÓN DE ROLES
# =============================================================================

@router.get("/roles/hierarchy", response_model=RoleHierarchyResponse)
async def get_role_hierarchy(
    current_user: User = Depends(get_admin_user)
):
    """
    📋 **Obtener jerarquía de roles**
    
    Obtiene la estructura completa de roles y permisos del sistema.
    Requiere rol de admin o superior.
    """
    return RoleService.get_role_hierarchy()

@router.get("/roles/my-permissions", response_model=RolePermissionsResponse)
async def get_my_permissions(
    current_user: User = Depends(get_admin_user)
):
    """
    🔑 **Obtener mis permisos**
    
    Obtiene los permisos del usuario actual.
    """
    return RoleService.get_user_permissions(current_user)

# =============================================================================
# GESTIÓN DE USUARIOS
# =============================================================================

@router.get("/users", response_model=List[UserRoleResponse])
async def get_all_users(
    pagination: PaginationParams = Depends(get_pagination_params),
    role_filter: str = Query(None, description="Filtrar por rol específico"),
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    👥 **Listar todos los usuarios**
    
    Obtiene lista paginada de usuarios con información de roles.
    Opcionalmente filtrar por rol específico.
    """
    if role_filter:
        users = RoleService.get_users_by_role(
            db, role_filter, pagination.skip, pagination.limit
        )
    else:
        db_users = db.query(User).offset(pagination.skip).limit(pagination.limit).all()
        users = [
            UserRoleResponse(
                user_id=user.id,
                email=user.email,
                name=user.name,
                role=user.role,
                role_level=user.get_role_level(),
                is_admin=user.is_admin(),
                is_super_admin=user.is_super_admin()
            ) for user in db_users
        ]
    
    return users

@router.get("/users/{user_id}", response_model=UserRoleResponse)
async def get_user_details(
    user_id: str,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    👤 **Obtener detalles de usuario**
    
    Obtiene información detallada de un usuario específico.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    return UserRoleResponse(
        user_id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        role_level=user.get_role_level(),
        is_admin=user.is_admin(),
        is_super_admin=user.is_super_admin()
    )

@router.put("/users/{user_id}/ban")
async def ban_user(
    user_id: str,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    🚫 **Banear usuario**
    
    Desactiva la cuenta de un usuario.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes banearte a ti mismo"
        )
    
    # No permitir banear usuarios de nivel igual o superior
    if user.get_role_level() >= current_user.get_role_level():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes banear usuarios de tu mismo nivel o superior"
        )
    
    user.is_active = False
    db.commit()
    
    return {"message": f"Usuario {user.email} ha sido baneado"}

@router.put("/users/{user_id}/unban")
async def unban_user(
    user_id: str,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    ✅ **Desbanear usuario**
    
    Reactiva la cuenta de un usuario baneado.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    user.is_active = True
    db.commit()
    
    return {"message": f"Usuario {user.email} ha sido desbaneado"}

# =============================================================================
# GESTIÓN DE ROLES (SOLO SUPER_ADMIN)
# =============================================================================

@router.post("/users/{user_id}/promote", response_model=UserRoleResponse)
async def promote_user(
    user_id: str,
    new_role: UserRole,
    justification: str = Query(..., min_length=10, description="Justificación para la promoción"),
    current_user: User = Depends(get_super_admin_user),
    db: Session = Depends(get_db)
):
    """
    🚀 **Promover usuario**
    
    Promover un usuario a un rol superior.
    Solo disponible para super_admin.
    """
    return RoleService.promote_user(
        db=db,
        promoter=current_user,
        target_user_id=user_id,
        new_role=new_role.value,
        justification=justification
    )

@router.post("/users/{user_id}/demote", response_model=UserRoleResponse)
async def demote_user(
    user_id: str,
    new_role: UserRole = UserRole.USER,
    reason: str = Query(None, description="Razón para la degradación"),
    current_user: User = Depends(get_super_admin_user),
    db: Session = Depends(get_db)
):
    """
    ⬇️ **Degradar usuario**
    
    Degradar un usuario a un rol inferior.
    Solo disponible para super_admin.
    """
    return RoleService.demote_user(
        db=db,
        demoter=current_user,
        target_user_id=user_id,
        new_role=new_role.value,
        reason=reason
    )

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    confirmation: str = Query(..., description="Escribe 'CONFIRMAR' para proceder"),
    current_user: User = Depends(get_super_admin_user),
    db: Session = Depends(get_db)
):
    """
    🗑️ **Eliminar usuario**
    
    Eliminar permanentemente un usuario del sistema.
    ⚠️ **ACCIÓN IRREVERSIBLE** - Solo para super_admin.
    """
    if confirmation != "CONFIRMAR":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe escribir 'CONFIRMAR' para proceder con la eliminación"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes eliminarte a ti mismo"
        )
    
    # No permitir eliminar otros super_admins
    if user.is_super_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se pueden eliminar super administradores"
        )
    
    email = user.email
    db.delete(user)
    db.commit()
    
    return {"message": f"Usuario {email} ha sido eliminado permanentemente"}

# =============================================================================
# ESTADÍSTICAS Y REPORTES
# =============================================================================

@router.get("/stats/users-by-role")
async def get_users_stats_by_role(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    📊 **Estadísticas de usuarios por rol**
    
    Obtiene conteo de usuarios agrupados por rol.
    """
    stats = {}
    for role in User.ROLE_HIERARCHY.keys():
        count = db.query(User).filter(User.role == role).count()
        stats[role] = count
    
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    verified_users = db.query(User).filter(User.is_verified == True).count()
    
    return {
        "users_by_role": stats,
        "total_users": total_users,
        "active_users": active_users,
        "verified_users": verified_users,
        "inactive_users": total_users - active_users,
        "unverified_users": total_users - verified_users
    }

@router.get("/dashboard")
async def get_admin_dashboard(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    📈 **Dashboard de administración**
    
    Obtiene información general del dashboard de admin.
    """
    # Estadísticas básicas
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    admin_users = db.query(User).filter(User.role.in_(["admin", "super_admin"])).count()
    
    # Usuarios recientes (últimos 7 días)
    from datetime import datetime, timedelta
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_users = db.query(User).filter(User.created_at >= week_ago).count()
    
    return {
        "summary": {
            "total_users": total_users,
            "active_users": active_users,
            "admin_users": admin_users,
            "recent_users": recent_users
        },
        "current_user": {
            "id": current_user.id,
            "email": current_user.email,
            "role": current_user.role,
            "permissions": RoleService.get_user_permissions(current_user).permissions
        }
    } 