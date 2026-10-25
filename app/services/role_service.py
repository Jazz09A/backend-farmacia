"""
Servicio para manejo de roles y permisos.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.role import (
    RoleHierarchyResponse,
    RoleInfo,
    RolePermissionsResponse,
    UserRoleResponse,
)
from app.utils.timezone import get_ve_now


class RoleService:
    """Servicio para gestión de roles y permisos."""

    # Definición de permisos por rol
    ROLE_PERMISSIONS = {
        "user": [
            "read_products",
            "create_orders",
            "manage_own_profile",
            "view_own_orders",
            "manage_cart",
            "write_reviews",
        ],
        "manager": [
            "read_products",
            "create_orders",
            "manage_own_profile",
            "view_own_orders",
            "manage_cart",
            "write_reviews",
            "view_reports",
            "view_analytics",
            "view_all_orders",
            "export_data",
        ],
        "admin": [
            "read_products",
            "create_orders",
            "manage_own_profile",
            "view_own_orders",
            "manage_cart",
            "write_reviews",
            "view_reports",
            "view_analytics",
            "view_all_orders",
            "export_data",
            "manage_users",
            "manage_products",
            "manage_orders",
            "view_admin_dashboard",
            "manage_inventory",
            "configure_settings",
        ],
        "super_admin": [
            "all_permissions",
            "promote_to_admin",
            "system_settings",
            "manage_roles",
            "database_backup",
            "maintenance_mode",
            "audit_logs",
            "security_settings",
        ],
    }

    @staticmethod
    def get_role_hierarchy() -> RoleHierarchyResponse:
        """Obtiene la jerarquía completa de roles."""
        roles = {}

        for role_name, level in User.ROLE_HIERARCHY.items():
            permissions = RoleService.ROLE_PERMISSIONS.get(role_name, [])
            description = RoleService._get_role_description(role_name)

            roles[role_name] = RoleInfo(name=role_name, level=level, description=description, permissions=permissions)

        return RoleHierarchyResponse(roles=roles)

    @staticmethod
    def _get_role_description(role: str) -> str:
        """Obtiene descripción del rol."""
        descriptions = {
            "user": "Usuario normal con permisos básicos",
            "manager": "Puede ver reportes y analíticas",
            "admin": "Puede gestionar usuarios y productos",
            "super_admin": "Acceso completo al sistema",
        }
        return descriptions.get(role, "Rol desconocido")

    @staticmethod
    def get_user_permissions(user: User) -> RolePermissionsResponse:
        """Obtiene permisos del usuario actual."""
        permissions = RoleService.ROLE_PERMISSIONS.get(user.role, [])

        # Si es super_admin, tiene todos los permisos
        if user.role == "super_admin":
            all_permissions = set()
            for role_perms in RoleService.ROLE_PERMISSIONS.values():
                all_permissions.update(role_perms)
            permissions = list(all_permissions)

        # Determinar a qué roles puede promover
        can_promote_to = []
        if user.role == "super_admin":
            can_promote_to = ["user", "manager", "admin"]
        elif user.role == "admin":
            can_promote_to = ["user", "manager"]

        return RolePermissionsResponse(
            user_id=user.id,
            current_role=user.role,
            role_level=user.get_role_level(),
            permissions=permissions,
            can_promote_to=can_promote_to,
        )

    @staticmethod
    def can_access_endpoint(user: User, required_role: str) -> bool:
        """Verifica si el usuario puede acceder a un endpoint."""
        return user.has_role_level(required_role)

    @staticmethod
    def promote_user(
        db: Session, promoter: User, target_user_id: str, new_role: str, justification: str | None = None
    ) -> UserRoleResponse:
        """Promover un usuario a un nuevo rol."""

        # Verificar que el usuario objetivo existe
        target_user = db.query(User).filter(User.id == target_user_id).first()
        if not target_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

        # Verificar que el rol es válido
        if new_role not in User.ROLE_HIERARCHY:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Rol inválido: {new_role}")

        # Verificar permisos del promotor
        if not promoter.can_promote_to(new_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f"No tienes permisos para promover a {new_role}"
            )

        # No permitir auto-promoción
        if promoter.id == target_user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes cambiar tu propio rol")

        # Guardar rol anterior para logging

        # Actualizar rol
        target_user.role = new_role
        target_user.updated_at = get_ve_now()

        try:
            db.commit()
            db.refresh(target_user)

            # TODO: Aquí podrías agregar logging/auditoría
            # log_role_change(promoter.id, target_user_id, previous_role, new_role, justification)

            return UserRoleResponse(
                user_id=target_user.id,
                email=target_user.email,
                name=target_user.name,
                role=target_user.role,
                role_level=target_user.get_role_level(),
                is_admin=target_user.is_admin(),
                is_super_admin=target_user.is_super_admin(),
            )

        except Exception:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al actualizar el rol del usuario"
            )

    @staticmethod
    def demote_user(
        db: Session, demoter: User, target_user_id: str, new_role: str = "user", reason: str | None = None
    ) -> UserRoleResponse:
        """Degradar un usuario a un rol menor."""

        target_user = db.query(User).filter(User.id == target_user_id).first()
        if not target_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

        # Solo super_admin puede degradar admins
        if target_user.role == "admin" and not demoter.is_super_admin():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Solo super_admin puede degradar administradores"
            )

        # Verificar que el nuevo rol es menor al actual
        current_level = target_user.get_role_level()
        new_level = User.ROLE_HIERARCHY.get(new_role, 0)

        if new_level >= current_level:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="El nuevo rol debe ser de menor nivel que el actual"
            )

        # No permitir auto-degradación
        if demoter.id == target_user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes cambiar tu propio rol")

        target_user.role = new_role
        target_user.updated_at = get_ve_now()

        try:
            db.commit()
            db.refresh(target_user)

            return UserRoleResponse(
                user_id=target_user.id,
                email=target_user.email,
                name=target_user.name,
                role=target_user.role,
                role_level=target_user.get_role_level(),
                is_admin=target_user.is_admin(),
                is_super_admin=target_user.is_super_admin(),
            )

        except Exception:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al actualizar el rol del usuario"
            )

    @staticmethod
    def get_users_by_role(db: Session, role: str, skip: int = 0, limit: int = 100) -> list[UserRoleResponse]:
        """Obtiene usuarios filtrados por rol."""
        users = db.query(User).filter(User.role == role).offset(skip).limit(limit).all()

        return [
            UserRoleResponse(
                user_id=user.id,
                email=user.email,
                name=user.full_name,  # el modelo no tiene .name (mismo bug que /admin/users)
                role=user.role,
                role_level=user.get_role_level(),
                is_admin=user.is_admin(),
                is_super_admin=user.is_super_admin(),
            )
            for user in users
        ]

    @staticmethod
    def check_specific_permission(user: User, permission: str) -> bool:
        """Verifica si el usuario tiene un permiso específico."""
        user_permissions = RoleService.ROLE_PERMISSIONS.get(user.role, [])

        # Super admin tiene todos los permisos
        if user.role == "super_admin":
            return True

        return permission in user_permissions
