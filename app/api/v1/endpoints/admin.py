"""
Endpoints de administración para gestión de usuarios, roles y productos.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, File, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc, or_
from app.config.database import get_db
from app.core.auth import get_admin_user, get_super_admin_user
from app.models.order import Order, OrderStatus
from app.models.user import User
from app.models.product import Product
from app.services.role_service import RoleService
from app.schemas.role import (
    UserRoleResponse, RolePermissionsResponse, RoleHierarchyResponse,
    PromotionRequest, PromotionResponse, UserRole
)
from app.schemas.dashboard import DashboardData, DashboardStats, OrderStatusSummary, RecentOrder
from app.schemas.product import (
    ProductResponse, ProductCreate, ProductUpdate, ProductListResponse
)
from app.schemas.user import (
    CustomerDetailedStats, CustomerStats, ProductPurchaseStats,
    OrderStatusDistribution, MonthlyPurchaseStats, UserResponse
)
from app.core.dependencies import PaginationParams, get_pagination_params
from app.services import dashboard_service # Import the new service
from app.services.imges_service import ImageService

router = APIRouter(prefix="/admin", tags=["Admin"])
image_service = ImageService()
# =============================================================================
# INDEX ADMIN PAGE
# =============================================================================

@router.get("/", response_model=DashboardData)
async def get_admin_dashboard(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get aggregated data for the admin dashboard.
    """
    dashboard_data = dashboard_service.get_dashboard_data(db=db, days_filter=7)
    return dashboard_data




# =============================================================================
# GESTIÓN DE PRODUCTOS - ADMIN
# =============================================================================

@router.get("/products", response_model=ProductListResponse)
async def get_admin_products(
    pagination: PaginationParams = Depends(get_pagination_params),
    search: Optional[str] = Query(None, description="Buscar productos"),
    category_id: Optional[str] = Query(None, description="Filtrar por categoría"),
    brand_id: Optional[str] = Query(None, description="Filtrar por marca"),
    in_stock: Optional[bool] = Query(None, description="Filtrar por stock disponible"),
    featured: Optional[bool] = Query(None, description="Solo productos destacados"),
    is_offer: Optional[bool] = Query(None, description="Solo productos en oferta"),
    prescription: Optional[bool] = Query(None, description="Requiere receta"),
    sort_by: str = Query("created_at", description="Ordenar por: name, price, stock, created_at, rating"),
    sort_order: str = Query("desc", description="Orden: asc, desc"),
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    📦 **Gestión de productos (Admin)**
    
    Lista todos los productos del sistema con filtros avanzados y paginación.
    """
    # Base query (include out of stock products for admin)
    query = db.query(Product)
    
    # Build filters
    applied_filters = {}
    
    if search:
        search_filter = or_(
            Product.name.ilike(f"%{search}%"),
            Product.description.ilike(f"%{search}%"),
            Product.brand.ilike(f"%{search}%"),
            Product.sku.ilike(f"%{search}%")
        )
        query = query.filter(search_filter)
        applied_filters["search"] = search
    
    if category_id:
        query = query.filter(Product.category_id == category_id)
        applied_filters["category_id"] = category_id
    
    if brand_id:
        query = query.filter(Product.brand_id == brand_id)
        applied_filters["brand_id"] = brand_id
    
    if in_stock is not None:
        query = query.filter(Product.in_stock == in_stock)
        applied_filters["in_stock"] = in_stock
    
    if featured is not None:
        query = query.filter(Product.featured == featured)
        applied_filters["featured"] = featured
    
    if is_offer is not None:
        query = query.filter(Product.is_offer == is_offer)
        applied_filters["is_offer"] = is_offer
    
    if prescription is not None:
        query = query.filter(Product.prescription == prescription)
        applied_filters["prescription"] = prescription
    
    # Apply sorting
    order_func = desc if sort_order == "desc" else asc
    
    if sort_by == "name":
        query = query.order_by(order_func(Product.name))
    elif sort_by == "price":
        query = query.order_by(order_func(Product.price_ves))
    elif sort_by == "stock":
        query = query.order_by(order_func(Product.stock))
    elif sort_by == "rating":
        query = query.order_by(order_func(Product.rating))
    else:  # created_at (default)
        query = query.order_by(order_func(Product.created_at))
    
    applied_filters.update({"sort_by": sort_by, "sort_order": sort_order})
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    products = query.offset(pagination.skip).limit(pagination.limit).all()
    
    # Convert to response models
    product_responses = []
    for product in products:
        product_dict = {
            **product.__dict__,
            'current_price': product.current_price,
            'discount_percentage': product.discount_percentage,
            'is_available': True if product.in_stock and product.stock > 0 else False
        }
        product_responses.append(ProductResponse.model_validate(product_dict))
    
    return ProductListResponse.create(
        products=product_responses,
        total=total,
        page=pagination.page,
        limit=pagination.limit,
        filters=applied_filters
    )

@router.post("/products", response_model=ProductResponse)
async def create_product(
    product_data: ProductCreate,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    ➕ **Crear producto**
    
    Crea un nuevo producto en el sistema.
    """
    # Generate slug if not provided
    if not product_data.slug:
        import re
        slug_base = re.sub(r'[^a-zA-Z0-9\s-]', '', product_data.name.lower())
        slug_base = re.sub(r'\s+', '-', slug_base.strip())
        product_data.slug = slug_base
    
    # Check if slug already exists
    if db.query(Product).filter(Product.slug == product_data.slug).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un producto con este slug"
        )
    
    # Create product
    db_product = Product(**product_data.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    
    # Convert to response model
    product_dict = {
        **db_product.__dict__,
        'current_price': db_product.current_price,
        'discount_percentage': db_product.discount_percentage,
        'is_available': db_product.is_available
    }
    
    return ProductResponse.model_validate(product_dict)

@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_admin_product(
    product_id: str,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    📋 **Obtener producto (Admin)**
    
    Obtiene detalles completos de un producto (incluye productos fuera de stock).
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado"
        )
    
    product_dict = {
        **product.__dict__,
        'current_price': product.current_price,
        'discount_percentage': product.discount_percentage,
        'is_available': product.is_available
    }
    
    return ProductResponse.model_validate(product_dict)

@router.put("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    product_data: ProductUpdate,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    ✏️ **Actualizar producto**
    
    Actualiza la información de un producto existente.
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado"
        )
    
    # Update only provided fields
    try:
        update_data = product_data.model_dump(exclude_unset=True)
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Error al actualizar el producto"
        )
    
    # Check slug uniqueness if being updated
    if 'slug' in update_data and update_data['slug']:
        existing_slug = db.query(Product).filter(
            Product.slug == update_data['slug'],
            Product.id != product_id
        ).first()
        if existing_slug:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe un producto con este slug"
            )
    
    for field, value in update_data.items():
        setattr(product, field, value)
    
    product.updated_at = func.now()
    db.commit()
    db.refresh(product)
    
    product_dict = {
        **product.__dict__,
        'current_price': product.current_price,
        'discount_percentage': product.discount_percentage,
        'is_available': product.is_available
    }
    
    return ProductResponse.model_validate(product_dict)

@router.delete("/products/{product_id}")
async def delete_product(
    product_id: str,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    🗑️ **Eliminar producto**
    
    Elimina un producto del sistema.
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado"
        )
    
    # Store product name for response
    product_name = product.name
    
    # Delete product
    db.delete(product)
    db.commit()
    
    return {"message": f"Producto '{product_name}' eliminado exitosamente"}

@router.get("/products/stats/summary")
async def get_products_stats(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    📊 **Estadísticas de productos**
    
    Obtiene estadísticas generales de productos.
    """
    total_products = db.query(Product).count()
    in_stock_products = db.query(Product).filter(Product.in_stock == True).count()
    featured_products = db.query(Product).filter(Product.featured == True).count()
    offer_products = db.query(Product).filter(Product.is_offer == True).count()
    low_stock_products = db.query(Product).filter(Product.stock <= 5, Product.in_stock == True).count()
    
    # Average rating
    avg_rating_result = db.query(func.avg(Product.rating)).scalar()
    avg_rating = round(float(avg_rating_result or 0), 2)
    
    # Products by category
    category_stats = db.query(
        Product.category,
        func.count(Product.id)
    ).group_by(Product.category).all()
    
    return {
        "summary": {
            "total_products": total_products,
            "in_stock_products": in_stock_products,
            "out_of_stock_products": total_products - in_stock_products,
            "featured_products": featured_products,
            "offer_products": offer_products,
            "low_stock_products": low_stock_products,
            "avg_rating": avg_rating
        },
        "categories": [{"name": cat, "count": count} for cat, count in category_stats]
    }

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
    
    # Obtener todas las órdenes del cliente
    from app.models.order import OrderItem
    orders = db.query(Order).filter(Order.user_id == customer_id).all()
    
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
    
    # Calcular estadísticas generales
    total_orders = len(orders)
    total_spent = sum(order.total for order in orders)
    average_order_value = total_spent / total_orders if total_orders > 0 else 0
    
    # Fechas de primera y última compra
    sorted_orders = sorted(orders, key=lambda x: x.created_at)
    first_order_date = sorted_orders[0].created_at
    last_order_date = sorted_orders[-1].created_at
    
    # Días como cliente
    # Usar datetime.utcnow() para mantener consistencia con los timestamps de la DB
    days_as_customer = (datetime.utcnow() - customer.created_at).days
    
    # Frecuencia de pedidos (promedio de días entre pedidos)
    order_frequency_days = None
    if total_orders > 1:
        days_between_orders = (last_order_date - first_order_date).days
        order_frequency_days = days_between_orders / (total_orders - 1) if total_orders > 1 else None
    
    # Método de pago preferido
    payment_methods = {}
    for order in orders:
        payment_methods[order.payment_method] = payment_methods.get(order.payment_method, 0) + 1
    preferred_payment_method = max(payment_methods, key=payment_methods.get) if payment_methods else None
    
    # Zona de envío más usada (si tienes shipping_zone en las órdenes)
    # Por ahora lo dejamos como None
    most_used_shipping_zone = None
    
    general_stats = CustomerStats(
        total_orders=total_orders,
        total_spent=total_spent,
        average_order_value=average_order_value,
        first_order_date=first_order_date,
        last_order_date=last_order_date,
        days_as_customer=days_as_customer,
        order_frequency_days=order_frequency_days,
        preferred_payment_method=preferred_payment_method,
        most_used_shipping_zone=most_used_shipping_zone
    )
    
    # Productos más comprados
    product_stats = {}
    for order in orders:
        for item in order.items:
            product_id = item.product_id
            if product_id not in product_stats:
                product_stats[product_id] = {
                    'product_id': product_id,
                    'product_name': item.product_name,
                    'product_brand': item.product_brand,
                    'total_quantity': 0,
                    'times_purchased': 0,
                    'total_spent': 0,
                    'last_purchase_date': None,
                    'purchase_dates': []
                }
            
            product_stats[product_id]['total_quantity'] += item.quantity
            product_stats[product_id]['times_purchased'] += 1
            product_stats[product_id]['total_spent'] += item.total_price
            product_stats[product_id]['purchase_dates'].append(order.created_at)
    
    # Calcular estadísticas de productos
    top_purchased_products = []
    for product_id, stats in product_stats.items():
        stats['last_purchase_date'] = max(stats['purchase_dates'])
        stats['average_quantity_per_order'] = stats['total_quantity'] / stats['times_purchased']
        
        top_purchased_products.append(ProductPurchaseStats(
            product_id=stats['product_id'],
            product_name=stats['product_name'],
            product_brand=stats['product_brand'],
            total_quantity=stats['total_quantity'],
            times_purchased=stats['times_purchased'],
            total_spent=stats['total_spent'],
            last_purchase_date=stats['last_purchase_date'],
            average_quantity_per_order=stats['average_quantity_per_order']
        ))
    
    # Ordenar por cantidad total comprada
    top_purchased_products.sort(key=lambda x: x.total_quantity, reverse=True)
    top_purchased_products = top_purchased_products[:10]  # Top 10 productos
    
    # Distribución de estados de pedidos
    status_distribution = {}
    for order in orders:
        status_distribution[order.status] = status_distribution.get(order.status, 0) + 1
    
    order_status_distribution = []
    for status, count in status_distribution.items():
        percentage = (count / total_orders) * 100 if total_orders > 0 else 0
        order_status_distribution.append(OrderStatusDistribution(
            status=status,
            count=count,
            percentage=percentage
        ))
    
    # Estadísticas mensuales
    monthly_stats_dict = {}
    for order in orders:
        month_key = order.created_at.strftime('%Y-%m')
        
        if month_key not in monthly_stats_dict:
            monthly_stats_dict[month_key] = {
                'month': month_key,
                'order_count': 0,
                'total_spent': 0,
                'total_items': 0
            }
        
        monthly_stats_dict[month_key]['order_count'] += 1
        monthly_stats_dict[month_key]['total_spent'] += order.total
        monthly_stats_dict[month_key]['total_items'] += sum(item.quantity for item in order.items)
    
    monthly_stats = [
        MonthlyPurchaseStats(**stats) 
        for stats in sorted(monthly_stats_dict.values(), key=lambda x: x['month'], reverse=True)
    ][:12]  # Últimos 12 meses
    
    # Categorías favoritas (basado en productos comprados)
    from app.models.product import Product
    category_stats = {}
    for product_id, stats in product_stats.items():
        product = db.query(Product).filter(Product.id == product_id).first()
        if product and product.category:
            if product.category not in category_stats:
                category_stats[product.category] = {
                    'category': product.category,
                    'total_items': 0,
                    'total_spent': 0,
                    'product_count': 0
                }
            
            category_stats[product.category]['total_items'] += stats['total_quantity']
            category_stats[product.category]['total_spent'] += stats['total_spent']
            category_stats[product.category]['product_count'] += 1
    
    favorite_categories = sorted(
        category_stats.values(), 
        key=lambda x: x['total_spent'], 
        reverse=True
    )[:5]  # Top 5 categorías
    
    # Tendencias de compra
    purchase_trends = {
        'most_active_month': max(monthly_stats_dict.keys(), key=lambda k: monthly_stats_dict[k]['order_count']) if monthly_stats_dict else None,
        'average_monthly_orders': sum(m['order_count'] for m in monthly_stats_dict.values()) / len(monthly_stats_dict) if monthly_stats_dict else 0,
        'average_monthly_spend': sum(m['total_spent'] for m in monthly_stats_dict.values()) / len(monthly_stats_dict) if monthly_stats_dict else 0,
        'is_recurring_customer': total_orders > 3,
        'customer_type': 'Frecuente' if total_orders > 10 else 'Regular' if total_orders > 3 else 'Ocasional'
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
    
# =============================================================================
# GESTIÓN DE IMÁGENES
# =============================================================================
@router.post("/products/{product_id}/images")
async def add_product_images(
    product_id: str,
    images: List[str] = Query(...),
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    🖼️ **Agregar imágenes a producto**
    
    Agrega imágenes a un producto existente.
    """
    return image_service.add_images_to_product(product_id, images)

@router.get("/products/{product_id}/images/{image_url}")
async def delete_product_images(
    product_id: str,
    image_url: str,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    🖼️ **Obtener imágenes de producto**
    """
    return image_service.delete_image_from_product(product_id, image_url)