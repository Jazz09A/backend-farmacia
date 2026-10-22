"""
Schemas para manejo de roles y permisos.
"""

from enum import Enum

from pydantic import BaseModel, Field, validator


class UserRole(str, Enum):
    """Enum para roles de usuario."""

    USER = "user"
    MANAGER = "manager"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class RoleInfo(BaseModel):
    """Información sobre un rol."""

    name: str
    level: int
    description: str
    permissions: list[str]


class UserRoleUpdate(BaseModel):
    """Schema para actualizar el rol de un usuario."""

    user_id: str = Field(..., description="ID del usuario")
    new_role: UserRole = Field(..., description="Nuevo rol del usuario")
    reason: str | None = Field(None, description="Razón para el cambio de rol")

    @validator("new_role")
    def validate_role(cls, v):
        valid_roles = [role.value for role in UserRole]
        if v not in valid_roles:
            raise ValueError(f"Rol inválido. Roles válidos: {valid_roles}")
        return v


class RolePermissionsResponse(BaseModel):
    """Respuesta con permisos del rol actual."""

    user_id: str
    current_role: str
    role_level: int
    permissions: list[str]
    can_promote_to: list[str]


class UserRoleResponse(BaseModel):
    """Respuesta con información del rol del usuario."""

    user_id: str
    email: str
    name: str
    role: str
    role_level: int
    is_admin: bool
    is_super_admin: bool

    class Config:
        from_attributes = True


class RoleHierarchyResponse(BaseModel):
    """Respuesta con la jerarquía de roles disponible."""

    roles: dict[str, RoleInfo]

    class Config:
        json_schema_extra = {
            "example": {
                "roles": {
                    "user": {
                        "name": "user",
                        "level": 0,
                        "description": "Usuario normal",
                        "permissions": ["read_products", "create_orders", "manage_own_profile"],
                    },
                    "manager": {
                        "name": "manager",
                        "level": 1,
                        "description": "Puede ver reportes",
                        "permissions": [
                            "read_products",
                            "create_orders",
                            "manage_own_profile",
                            "view_reports",
                            "view_analytics",
                        ],
                    },
                    "admin": {
                        "name": "admin",
                        "level": 2,
                        "description": "Puede gestionar usuarios",
                        "permissions": [
                            "all_user_permissions",
                            "manage_users",
                            "manage_products",
                            "manage_orders",
                            "view_admin_dashboard",
                        ],
                    },
                    "super_admin": {
                        "name": "super_admin",
                        "level": 3,
                        "description": "Puede promover a admin",
                        "permissions": ["all_permissions", "promote_to_admin", "system_settings", "manage_roles"],
                    },
                }
            }
        }


class PromotionRequest(BaseModel):
    """Request para promover un usuario."""

    target_user_id: str = Field(..., description="ID del usuario a promover")
    new_role: UserRole = Field(..., description="Nuevo rol")
    justification: str = Field(..., min_length=10, max_length=500, description="Justificación para la promoción")


class PromotionResponse(BaseModel):
    """Respuesta de promoción de usuario."""

    success: bool
    message: str
    user_id: str
    previous_role: str
    new_role: str
    promoted_by: str
    timestamp: str


class UserPermissionsCheck(BaseModel):
    """Schema para verificar permisos específicos."""

    user_id: str
    required_permission: str
    has_permission: bool
    role: str
    message: str
