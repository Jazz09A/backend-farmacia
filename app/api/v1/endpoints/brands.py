"""
Endpoints para manejo de marcas.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config.database import get_db
from app.models.category import Brand
from app.models.product import Product
from app.schemas.category import (
    BrandCreate, BrandUpdate, BrandResponse, BrandListResponse, BrandSimple
)
from app.core.dependencies import get_current_admin_user, PaginationParams, get_pagination_params
from app.models.user import User

router = APIRouter(prefix="/brands", tags=["Brands"])

# =============================================================================
# RUTAS PÚBLICAS - MARCAS
# =============================================================================

@router.get("/", response_model=BrandListResponse)
async def get_brands(
    pagination: PaginationParams = Depends(get_pagination_params),
    featured_only: bool = Query(False, description="Solo marcas destacadas"),
    active_only: bool = Query(True, description="Solo marcas activas"),
    search: Optional[str] = Query(None, description="Buscar por nombre"),
    db: Session = Depends(get_db)
):
    """
    🏷️ **Listar marcas**
    
    Obtiene todas las marcas con soporte para paginación y filtros.
    """
    query = db.query(Brand)
    
    if active_only:
        query = query.filter(Brand.is_active == True)
    
    if featured_only:
        query = query.filter(Brand.is_featured == True)
    
    if search:
        query = query.filter(Brand.name.ilike(f"%{search}%"))
    
    # Ordenar por nombre
    query = query.order_by(Brand.name)
    
    # Contar total
    total = query.count()
    
    # Aplicar paginación
    brands = query.offset(pagination.skip).limit(pagination.limit).all()
    
    # Agregar conteo de productos para cada marca
    brands_with_count = []
    for brand in brands:
        product_count = db.query(func.count(Product.id)).filter(
            Product.brand_id == brand.id,
            Product.is_active == True
        ).scalar()
        
        brand_dict = brand.__dict__.copy()
        brand_dict['product_count'] = product_count
        brands_with_count.append(BrandResponse(**brand_dict))
    
    pages = (total + pagination.limit - 1) // pagination.limit
    
    return BrandListResponse(
        brands=brands_with_count,
        total=total,
        page=pagination.page,
        pages=pages
    )

@router.get("/featured", response_model=List[BrandResponse])
async def get_featured_brands(
    limit: int = Query(10, le=50, description="Número máximo de marcas"),
    db: Session = Depends(get_db)
):
    """
    🏷️ **Marcas destacadas**
    
    Obtiene las marcas marcadas como destacadas.
    """
    brands = db.query(Brand).filter(
        Brand.is_featured == True,
        Brand.is_active == True
    ).order_by(Brand.name).limit(limit).all()
    
    # Agregar conteo de productos para cada marca
    brands_with_count = []
    for brand in brands:
        product_count = db.query(func.count(Product.id)).filter(
            Product.brand_id == brand.id,
            Product.is_active == True
        ).scalar()
        
        brand_dict = brand.__dict__.copy()
        brand_dict['product_count'] = product_count
        brands_with_count.append(BrandResponse(**brand_dict))
    
    return brands_with_count

@router.get("/{brand_id}", response_model=BrandResponse)
async def get_brand(
    brand_id: str,
    db: Session = Depends(get_db)
):
    """
    🏷️ **Obtener marca específica**
    
    Obtiene información detallada de una marca por su ID.
    """
    brand = db.query(Brand).filter(
        Brand.id == brand_id,
        Brand.is_active == True
    ).first()
    
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Marca no encontrada"
        )
    
    # Agregar conteo de productos
    product_count = db.query(func.count(Product.id)).filter(
        Product.brand_id == brand.id,
        Product.is_active == True
    ).scalar()
    
    brand_dict = brand.__dict__.copy()
    brand_dict['product_count'] = product_count
    
    return BrandResponse(**brand_dict)

@router.get("/simple/list", response_model=List[BrandSimple])
async def get_brands_simple(
    db: Session = Depends(get_db)
):
    """
    🏷️ **Lista simple de marcas**
    
    Obtiene una lista simple de marcas para usar en dropdowns.
    """
    brands = db.query(Brand).filter(
        Brand.is_active == True
    ).order_by(Brand.name).all()
    
    return [
        BrandSimple(
            id=brand.id,
            name=brand.name,
            slug=brand.slug
        )
        for brand in brands
    ]

# =============================================================================
# RUTAS DE ADMINISTRADOR - MARCAS
# =============================================================================

@router.post("/", response_model=BrandResponse)
async def create_brand(
    brand_data: BrandCreate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    👑 **Crear marca**
    
    Crea una nueva marca. Solo para administradores.
    """
    # Verificar que el slug no exista
    existing_brand = db.query(Brand).filter(Brand.slug == brand_data.slug).first()
    if existing_brand:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe una marca con ese slug"
        )
    
    # Crear marca
    brand = Brand(**brand_data.dict())
    db.add(brand)
    db.commit()
    db.refresh(brand)
    
    return BrandResponse(**brand.__dict__)

@router.put("/{brand_id}", response_model=BrandResponse)
async def update_brand(
    brand_id: str,
    brand_data: BrandUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    👑 **Actualizar marca**
    
    Actualiza una marca existente. Solo para administradores.
    """
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Marca no encontrada"
        )
    
    # Verificar slug único si se está actualizando
    if brand_data.slug and brand_data.slug != brand.slug:
        existing_brand = db.query(Brand).filter(Brand.slug == brand_data.slug).first()
        if existing_brand:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe una marca con ese slug"
            )
    
    # Actualizar campos
    update_data = brand_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(brand, field, value)
    
    db.commit()
    db.refresh(brand)
    
    return BrandResponse(**brand.__dict__)

@router.delete("/{brand_id}")
async def delete_brand(
    brand_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    👑 **Eliminar marca**
    
    Elimina una marca. Solo para administradores.
    """
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Marca no encontrada"
        )
    
    # Verificar que no tenga productos asociados
    product_count = db.query(func.count(Product.id)).filter(Product.brand_id == brand_id).scalar()
    if product_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se puede eliminar la marca porque tiene {product_count} productos asociados"
        )
    
    db.delete(brand)
    db.commit()
    
    return {"message": "Marca eliminada exitosamente"} 