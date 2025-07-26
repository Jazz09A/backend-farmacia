"""
Endpoints públicos que no requieren autenticación.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc, asc
from app.config.database import get_db
from app.models.product import Product
from app.models.user import User
from app.core.dependencies import PaginationParams, get_pagination_params
from app.schemas.product import ProductResponse, ProductListResponse, ProductSummary
from app.core.dependencies import get_optional_current_user

router = APIRouter(prefix="/public")

# =============================================================================
# CATÁLOGO Y PRODUCTOS - PÚBLICO
# =============================================================================

@router.get("/products", response_model=ProductListResponse)
async def get_public_products(
    pagination: PaginationParams = Depends(get_pagination_params),
    category_id: Optional[str] = Query(None, description="Filtrar por categoría"),
    brand_id: Optional[str] = Query(None, description="Filtrar por marca"),
    search: Optional[str] = Query(None, description="Buscar productos"),
    min_price: Optional[float] = Query(None, ge=0, description="Precio mínimo"),
    max_price: Optional[float] = Query(None, ge=0, description="Precio máximo"),
    prescription_required: Optional[bool] = Query(None, description="Solo productos con/sin receta"),
    featured_only: Optional[bool] = Query(False, description="Solo productos destacados"),
    on_offer: Optional[bool] = Query(None, description="Solo productos en oferta"),
    sort_by: str = Query("name", description="Ordenar por: name, price_asc, price_desc, rating, newest"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    🛍️ **Catálogo de productos (Público) - Mejorado**
    
    Lista todos los productos disponibles con paginación completa, filtros avanzados y optimización de consultas.
    """
    # Base query with optimized filtering
    query = db.query(Product).filter(Product.in_stock == True)
    
    # Build filters dictionary for response
    applied_filters = {}
    
    # Apply filters
    if category_id:
        query = query.filter(Product.category_id == category_id)
        applied_filters["category_id"] = category_id
    
    if brand_id:
        query = query.filter(Product.brand_id == brand_id)
        applied_filters["brand_id"] = brand_id
    
    if search:
        search_filter = or_(
            Product.name.ilike(f"%{search}%"),
            Product.description.ilike(f"%{search}%"),
            Product.brand.ilike(f"%{search}%")
        )
        query = query.filter(search_filter)
        applied_filters["search"] = search
    
    if min_price is not None:
        query = query.filter(Product.price_ves >= min_price)
        applied_filters["min_price"] = min_price
    
    if max_price is not None:
        query = query.filter(Product.price_ves <= max_price)
        applied_filters["max_price"] = max_price
    
    if prescription_required is not None:
        query = query.filter(Product.prescription == prescription_required)
        applied_filters["prescription_required"] = prescription_required
    
    if featured_only:
        query = query.filter(Product.featured == True)
        applied_filters["featured_only"] = featured_only
    
    if on_offer is not None:
        query = query.filter(Product.is_offer == on_offer)
        applied_filters["on_offer"] = on_offer
    
    # Apply sorting
    if sort_by == "price_asc":
        query = query.order_by(asc(Product.price_ves))
    elif sort_by == "price_desc":
        query = query.order_by(desc(Product.price_ves))
    elif sort_by == "rating":
        query = query.order_by(desc(Product.rating))
    elif sort_by == "newest":
        query = query.order_by(desc(Product.created_at))
    else:  # default to name
        query = query.order_by(asc(Product.name))
    
    applied_filters["sort_by"] = sort_by
    
    # Get total count for pagination (optimized)
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
            'is_available': product.in_stock and product.stock > 0
        }
        product_responses.append(ProductResponse.model_validate(product_dict))
    
    return ProductListResponse.create(
        products=product_responses,
        total=total,
        page=pagination.page,
        limit=pagination.limit,
        filters=applied_filters
    )

@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_public_product_detail(
    product_id: str,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    📦 **Detalle de producto (Público)**
    
    Obtiene información detallada de un producto específico.
    """
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.in_stock == True
    ).first()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado"
        )
    
    return ProductResponse.from_orm(product)

@router.get("/products/search", response_model=ProductListResponse)
async def search_public_products(
    q: str = Query(..., min_length=2, description="Término de búsqueda"),
    pagination: PaginationParams = Depends(get_pagination_params),
    category_id: Optional[str] = Query(None, description="Filtrar por categoría"),
    sort_by: str = Query("relevance", description="Ordenar por: relevance, name, price_asc, price_desc, rating"),
    db: Session = Depends(get_db)
):
    """
    🔍 **Búsqueda de productos (Público) - Mejorado**
    
    Busca productos por nombre, descripción o marca con paginación completa y filtros.
    """
    # Base search query
    search_filter = or_(
        Product.name.ilike(f"%{q}%"),
        Product.description.ilike(f"%{q}%"),
        Product.brand.ilike(f"%{q}%"),
        Product.ingredients.ilike(f"%{q}%") if hasattr(Product, 'ingredients') else False
    )
    
    query = db.query(Product).filter(
        Product.in_stock == True,
        search_filter
    )
    
    # Apply category filter if provided
    applied_filters = {"search": q}
    if category_id:
        query = query.filter(Product.category_id == category_id)
        applied_filters["category_id"] = category_id
    
    # Apply sorting
    if sort_by == "price_asc":
        query = query.order_by(asc(Product.price_ves))
    elif sort_by == "price_desc":
        query = query.order_by(desc(Product.price_ves))
    elif sort_by == "rating":
        query = query.order_by(desc(Product.rating))
    elif sort_by == "name":
        query = query.order_by(asc(Product.name))
    else:  # relevance (default)
        # Simple relevance: exact matches first, then partial matches
        query = query.order_by(
            Product.name.ilike(f"{q}").desc(),  # Exact match first
            desc(Product.rating),  # Then by rating
            asc(Product.name)  # Then alphabetically
        )
    
    applied_filters["sort_by"] = sort_by
    
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
            'is_available': product.in_stock and product.stock > 0
        }
        product_responses.append(ProductResponse.model_validate(product_dict))
    
    return ProductListResponse.create(
        products=product_responses,
        total=total,
        page=pagination.page,
        limit=pagination.limit,
        filters=applied_filters
    )

# =============================================================================
# INFORMACIÓN GENERAL - PÚBLICO
# =============================================================================

@router.get("/shipping-zones")
async def get_shipping_zones():
    """
    🚚 **Zonas de envío disponibles**
    
    Obtiene las zonas de envío configuradas en el sistema.
    """
    # Datos estáticos por ahora, puedes mover esto a base de datos
    zones = [
        {"id": "caracas", "name": "Caracas", "price": 5.00, "delivery_days": "1-2"},
        {"id": "miranda", "name": "Miranda", "price": 7.50, "delivery_days": "2-3"},
        {"id": "vargas", "name": "Vargas", "price": 10.00, "delivery_days": "3-4"},
        {"id": "nacional", "name": "Nacional", "price": 15.00, "delivery_days": "5-7"}
    ]
    return {"shipping_zones": zones}

@router.get("/payment-methods")
async def get_payment_methods():
    """
    💳 **Métodos de pago disponibles**
    
    Obtiene los métodos de pago activos en el sistema.
    """
    methods = [
        {
            "id": "cash",
            "name": "Efectivo",
            "description": "Pago en efectivo contra entrega",
            "fee": 0.00,
            "active": True
        },
        {
            "id": "transfer",
            "name": "Transferencia Bancaria", 
            "description": "Transferencia a cuenta bancaria",
            "fee": 0.00,
            "active": True
        },
        {
            "id": "mobile_payment",
            "name": "Pago Móvil",
            "description": "Pago móvil interbancario",
            "fee": 0.00,
            "active": True
        }
    ]
    return {"payment_methods": methods}

@router.get("/categories")
async def get_public_categories(db: Session = Depends(get_db)):
    """
    📂 **Categorías de productos**
    
    Obtiene todas las categorías disponibles.
    """
    # Asumiendo que tienes un modelo Category
    # categories = db.query(Category).filter(Category.is_active == True).all()
    
    # Por ahora datos estáticos
    categories = [
        {"id": "analgesicos", "name": "Analgésicos", "description": "Medicamentos para el dolor"},
        {"id": "antibioticos", "name": "Antibióticos", "description": "Medicamentos antimicrobianos"},
        {"id": "vitaminas", "name": "Vitaminas", "description": "Suplementos vitamínicos"},
        {"id": "cuidado_personal", "name": "Cuidado Personal", "description": "Productos de higiene y cuidado"}
    ]
    
    return {"categories": categories}

@router.get("/brands")
async def get_public_brands(db: Session = Depends(get_db)):
    """
    🏷️ **Marcas de productos**
    
    Obtiene todas las marcas disponibles.
    """
    # Datos estáticos por ahora
    brands = [
        {"id": "bayer", "name": "Bayer", "country": "Alemania"},
        {"id": "pfizer", "name": "Pfizer", "country": "Estados Unidos"},
        {"id": "roche", "name": "Roche", "country": "Suiza"},
        {"id": "novartis", "name": "Novartis", "country": "Suiza"}
    ]
    
    return {"brands": brands}

# =============================================================================
# INFORMACIÓN DEL SISTEMA
# =============================================================================

@router.get("/health")
async def health_check():
    """
    ❤️ **Health Check**
    
    Endpoint para verificar que la API está funcionando.
    """
    return {
        "status": "healthy",
        "service": "Farmacia API",
        "version": "1.0.0"
    }

@router.get("/features")
async def get_public_features():
    """
    ⭐ **Características del sistema**
    
    Obtiene las características públicas del sistema.
    """
    return {
        "features": {
            "user_registration": True,
            "guest_checkout": False,
            "multiple_payment_methods": True,
            "prescription_upload": True,
            "delivery_tracking": True,
            "customer_reviews": True,
            "loyalty_program": False
        },
        "supported_currencies": ["VES", "USD"],
        "supported_languages": ["es"],
        "api_version": "v1"
    } 