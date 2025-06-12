"""
Endpoints públicos que no requieren autenticación.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.models.product import Product
from app.models.user import User
from app.core.dependencies import PaginationParams, get_pagination_params
from app.schemas.product import ProductResponse
from app.core.dependencies import get_optional_current_user

router = APIRouter(prefix="/public", tags=["Public"])

# =============================================================================
# CATÁLOGO Y PRODUCTOS - PÚBLICO
# =============================================================================

@router.get("/products", response_model=List[ProductResponse])
async def get_public_products(
    pagination: PaginationParams = Depends(get_pagination_params),
    category_id: Optional[str] = Query(None, description="Filtrar por categoría"),
    search: Optional[str] = Query(None, description="Buscar productos"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    🛍️ **Catálogo de productos (Público)**
    
    Lista todos los productos disponibles sin necesidad de autenticación.
    Soporte para filtros y búsqueda.
    """
    query = db.query(Product).filter(Product.is_active == True)
    
    if category_id:
        query = query.filter(Product.category_id == category_id)
    
    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))
    
    products = query.offset(pagination.skip).limit(pagination.limit).all()
    
    return [ProductResponse.from_orm(product) for product in products]

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
        Product.is_active == True
    ).first()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado"
        )
    
    return ProductResponse.from_orm(product)

@router.get("/products/search")
async def search_public_products(
    q: str = Query(..., min_length=2, description="Término de búsqueda"),
    pagination: PaginationParams = Depends(get_pagination_params),
    db: Session = Depends(get_db)
):
    """
    🔍 **Búsqueda de productos (Público)**
    
    Busca productos por nombre o descripción.
    """
    products = db.query(Product).filter(
        Product.is_active == True,
        Product.name.ilike(f"%{q}%") | Product.description.ilike(f"%{q}%")
    ).offset(pagination.skip).limit(pagination.limit).all()
    
    return {
        "query": q,
        "results": [ProductResponse.from_orm(product) for product in products],
        "total": len(products)
    }

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