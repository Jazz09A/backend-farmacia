"""
Endpoints de administración para gestión de usuarios, roles y productos.
"""
from datetime import timedelta
from app.utils.timezone import get_ve_now
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.auth import get_admin_user, get_super_admin_user

from app.models.user import User
from app.services.role_service import RoleService
from app.schemas.role import (
    UserRoleResponse
)
from app.schemas.dashboard import DashboardData

from app.schemas.user import (
    CustomerDetailedStats, CustomerStats,
    UserResponse
)
from app.core.dependencies import PaginationParams, get_pagination_params
from app.services import dashboard_service
from app.services.imges_service import ImageService

from app.config.logging_config import get_logger


# SourceSystem imports y endpoints
from app.services.source_system_service import source_system_service
from app.services.source_system_user_creation_service import SourceSystemUserCreationService
from pydantic import BaseModel

# Schemas para endpoints
class SourceSystemCustomerResponse(BaseModel):
    customer_code: str
    customer_name: str
    email: Optional[str]
    alternate_email: Optional[str]
    rif: Optional[str]
    phones: Optional[str]
    inactive: bool
    is_juridico: bool

class SourceSystemCustomerListResponse(BaseModel):
    success: bool = True  # Nuevo campo
    customers: List[SourceSystemCustomerResponse]
    total: int
    page: int
    limit: int

class CreateUsersFromSourceSystemRequest(BaseModel):
    customer_codes: List[str]
    use_alternate_emails: bool = False

class UserCreationResult(BaseModel):
    success: bool
    customer_code: str
    customer_name: Optional[str]
    email: Optional[str]
    user_id: Optional[str]
    error: Optional[str]
    email_sent: Optional[bool]
    email_error: Optional[str]

class CreateUsersResponse(BaseModel):
    success: bool = True  # Nuevo campo
    total: int
    successful: List[UserCreationResult]
    failed: List[UserCreationResult]
    summary: dict

router = APIRouter(prefix="/admin")
image_service = ImageService()
logger = get_logger("app")
# =============================================================================
# INDEX ADMIN PAGE
# =============================================================================

@router.get("/dashboard", response_model=DashboardData)
async def get_admin_dashboard(
    time_range: int = Query(7, ge=1, le=365, description="Número de días para el rango de fechas (1-365)"),
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get aggregated data for the admin dashboard.
    
    Args:
        time_range: Número de días hacia atrás para calcular las estadísticas (por defecto 7 días)
    """
    dashboard_data = dashboard_service.get_dashboard_data(db=db, days_filter=time_range)
    return dashboard_data


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

# @router.put("/users/{user_id}/ban")
# async def ban_user(
#     user_id: str,
#     current_user: User = Depends(get_admin_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     🚫 **Banear usuario**
    
#     Desactiva la cuenta de un usuario.
#     """
#     user = db.query(User).filter(User.id == user_id).first()
#     if not user:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Usuario no encontrado"
#         )
    
#     if user.id == current_user.id:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="No puedes banearte a ti mismo"
#         )
    
#     # No permitir banear usuarios de nivel igual o superior
#     if user.get_role_level() >= current_user.get_role_level():
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="No puedes banear usuarios de tu mismo nivel o superior"
#         )
    
#     user.is_active = False
#     db.commit()
    
#     return {"message": f"Usuario {user.email} ha sido baneado"}

# @router.put("/users/{user_id}/unban")
# async def unban_user(
#     user_id: str,
#     current_user: User = Depends(get_admin_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     ✅ **Desbanear usuario**
    
#     Reactiva la cuenta de un usuario baneado.
#     """
#     user = db.query(User).filter(User.id == user_id).first()
#     if not user:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Usuario no encontrado"
#         )
    
#     user.is_active = True
#     db.commit()
    
#     return {"message": f"Usuario {user.email} ha sido desbaneado"}

# =============================================================================
# GESTIÓN DE ROLES (SOLO SUPER_ADMIN)
# =============================================================================

# @router.post("/users/{user_id}/promote", response_model=UserRoleResponse)
# async def promote_user(
#     user_id: str,
#     new_role: UserRole,
#     justification: str = Query(..., min_length=10, description="Justificación para la promoción"),
#     current_user: User = Depends(get_super_admin_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     🚀 **Promover usuario**
    
#     Promover un usuario a un rol superior.
#     Solo disponible para super_admin.
#     """
#     return RoleService.promote_user(
#         db=db,
#         promoter=current_user,
#         target_user_id=user_id,
#         new_role=new_role.value,
#         justification=justification
#     )

# @router.post("/users/{user_id}/demote", response_model=UserRoleResponse)
# async def demote_user(
#     user_id: str,
#     new_role: UserRole = UserRole.USER,
#     reason: str = Query(None, description="Razón para la degradación"),
#     current_user: User = Depends(get_super_admin_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     ⬇️ **Degradar usuario**
    
#     Degradar un usuario a un rol inferior.
#     Solo disponible para super_admin.
#     """
#     return RoleService.demote_user(
#         db=db,
#         demoter=current_user,
#         target_user_id=user_id,
#         new_role=new_role.value,
#         reason=reason
#     )

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
# ESTADÍSTICAS DETALLADAS DE CLIENTES
# =============================================================================

@router.get("/customers/{customer_id}/stats", response_model=CustomerDetailedStats)
async def get_customer_statistics(
    customer_id: str,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    📊 **Obtener estadísticas detalladas de un cliente**
    
    Obtiene información completa y estadísticas de compra de un cliente específico.
    Incluye:
    - Información general del cliente
    - Estadísticas de compras
    - Productos más comprados
    - Distribución de estados de pedidos
    - Tendencias mensuales
    - Categorías favoritas
    """
    # Verificar que el cliente existe
    customer = db.query(User).filter(User.id == customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado"
        )
    
    # Obtener todas las órdenes del cliente - ELIMINADO (Order no se usa con Profit Plus)
    # Las cotizaciones se manejan a través de Profit Plus directamente
    # from app.models.order import OrderItem
    # orders = db.query(Order).filter(Order.user_id == customer_id).all()
    orders = []  # Order no existe, usar cotizaciones de Profit Plus en el futuro
    
    if not orders:
        # Si no hay órdenes, devolver estadísticas vacías
        return CustomerDetailedStats(
            user_info=UserResponse.model_validate(customer),
            general_stats=CustomerStats(
                total_orders=0,
                total_spent=0.0,
                average_order_value=0.0,
                first_order_date=None,
                last_order_date=None,
                days_as_customer=0,
                order_frequency_days=None,
                preferred_payment_method=None,
                most_used_shipping_zone=None
            ),
            top_purchased_products=[],
            order_status_distribution=[],
            monthly_stats=[],
            favorite_categories=[],
            purchase_trends={}
        )
    
    # Código de estadísticas eliminado - Order no se usa con Profit Plus
    # Las estadísticas deben obtenerse de las cotizaciones en Profit Plus
    # TODO: Implementar estadísticas usando cotizaciones de Profit Plus
    
    # Días como cliente
    days_as_customer = (get_ve_now() - customer.created_at).days
    
    general_stats = CustomerStats(
        total_orders=0,  # TODO: Obtener de cotizaciones de Profit Plus
        total_spent=0.0,  # TODO: Obtener de cotizaciones de Profit Plus
        average_order_value=0.0,
        first_order_date=None,  # TODO: Obtener de cotizaciones de Profit Plus
        last_order_date=None,  # TODO: Obtener de cotizaciones de Profit Plus
        days_as_customer=days_as_customer,
        order_frequency_days=None,
        preferred_payment_method=None,
        most_used_shipping_zone=None
    )
    
    top_purchased_products = []
    order_status_distribution = []
    
    # Estadísticas mensuales - ELIMINADO (Order no existe)
    monthly_stats = []
    
    # Categorías favoritas - ELIMINADO (Order no existe)
    favorite_categories = []
    
    # Tendencias de compra - ELIMINADO (Order no existe)
    purchase_trends = {
        'most_active_month': None,
        'average_monthly_orders': 0,
        'average_monthly_spend': 0,
        'is_recurring_customer': False,
        'customer_type': 'Ocasional'
    }
    
    # Construir respuesta
    return CustomerDetailedStats(
        user_info=UserResponse.model_validate(customer),
        general_stats=general_stats,
        top_purchased_products=top_purchased_products,
        order_status_distribution=order_status_distribution,
        monthly_stats=monthly_stats,
        favorite_categories=favorite_categories,
        purchase_trends=purchase_trends
    )

# =============================================================================
# ESTADÍSTICAS Y REPORTES
# =============================================================================

# @router.get("/stats/users-by-role")
# async def get_users_stats_by_role(
#     current_user: User = Depends(get_admin_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     📊 **Estadísticas de usuarios por rol**
    
#     Obtiene conteo de usuarios agrupados por rol.
#     """
#     stats = {}
#     for role in User.ROLE_HIERARCHY.keys():
#         count = db.query(User).filter(User.role == role).count()
#         stats[role] = count
    
#     total_users = db.query(User).count()
#     active_users = db.query(User).filter(User.is_active == True).count()
#     verified_users = db.query(User).filter(User.is_verified == True).count()
    
#     stats = {
#         "users_by_role": stats,
#         "total_users": total_users,
#         "active_users": active_users,
#         "verified_users": verified_users,
#         "inactive_users": total_users - active_users,
#         "unverified_users": total_users - verified_users
#     }
    
#     return stats

@router.get("/stats/dashboard")
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
    week_ago = get_ve_now() - timedelta(days=7)
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
    
# =============================================================================
# GESTIÓN DE IMÁGENES
# =============================================================================
# Endpoints de imágenes de productos locales eliminados - Los artículos vienen de Profit Plus
# @router.post("/products/{product_id}/images") - ELIMINADO
# @router.delete("/products/{product_id}/images/{image_url}") - ELIMINADO

# Endpoint update_payment_status eliminado - Order no se usa con Profit Plus

# SourceSystem imports y endpoints
@router.get("/source-system/customers", response_model=SourceSystemCustomerListResponse)
async def get_source_system_customers(
    pagination: PaginationParams = Depends(get_pagination_params),
    include_inactive: bool = Query(False, description="Incluir clientes inactivos"),
    only_with_email: bool = Query(True, description="Solo clientes con email"),
    search: Optional[str] = Query(None, description="Buscar por nombre o código"),
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    try:
        # Obtener clientes paginados con búsqueda en SQL
        customers = source_system_service.get_all_customers(
            include_inactive=include_inactive,
            only_with_email=only_with_email,
            limit=pagination.limit,
            offset=pagination.skip,
            search=search  # Búsqueda ahora se hace en SQL
        )
        
        # Obtener total usando COUNT(*) eficiente (no trae todos los registros)
        total = source_system_service.count_customers(
            include_inactive=include_inactive,
            only_with_email=only_with_email,
            search=search  # Búsqueda ahora se hace en SQL
        )
        
        customer_responses = [
            SourceSystemCustomerResponse(**customer)
            for customer in customers
        ]
        return SourceSystemCustomerListResponse(
            customers=customer_responses,
            total=total,
            page=pagination.page,
            limit=pagination.limit
        )
    except Exception as e:
        logger.error(f"Error obteniendo clientes SourceSystem: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener clientes de SourceSystem: {str(e)}"
        )

@router.post("/source-system/create-users", response_model=CreateUsersResponse)
async def create_users_from_source_system(
    request: CreateUsersFromSourceSystemRequest,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    try:
        service = SourceSystemUserCreationService(db)
        results = await service.create_multiple_users_from_source_system(
            customer_codes=request.customer_codes,
            use_alternate_emails=request.use_alternate_emails
        )
        successful = [UserCreationResult(**r) for r in results["successful"]]
        failed = [UserCreationResult(**r) for r in results["failed"]]
        total_attempted = results["total"]
        total_successful = len(successful)
        total_failed = len(failed)
        emails_sent_count = sum(1 for r in successful if r.email_sent)
        emails_failed_count = sum(1 for r in successful if not r.email_sent) + total_failed
        summary = {
            "total_attempted": total_attempted,
            "users_created": total_successful,
            "users_failed": total_failed,
            "emails_sent": emails_sent_count,
            "emails_failed": emails_failed_count,
            "success_rate": round((total_successful / total_attempted * 100) if total_attempted > 0 else 0, 2)
        }
        
        # Si todos los usuarios fallaron, devolver error HTTP
        if total_successful == 0 and total_attempted > 0:
            error_messages = [f.error for f in failed if f.error]
            if not error_messages:
                error_messages = ["Error desconocido"]
            
            error_detail = f"No se pudieron crear/actualizar usuarios. Errores: {'; '.join(error_messages[:3])}"
            if len(error_messages) > 3:
                error_detail += f" y {len(error_messages) - 3} más..."
            
            logger.error(f"Todos los usuarios fallaron al crear: {error_detail}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail
            )
        
        # Si algunos usuarios fallaron pero otros tuvieron éxito, devolver 200 con información
        # Si todos tuvieron éxito, devolver 200 OK
        return CreateUsersResponse(
            total=total_attempted,
            successful=successful,
            failed=failed,
            summary=summary
        )
    except HTTPException:
        # Re-lanzar HTTPException sin modificar
        raise
    except Exception as e:
        logger.error(f"Error creando usuarios desde SourceSystem: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear usuarios: {str(e)}"
        )