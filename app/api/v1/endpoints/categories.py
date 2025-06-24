"""
Endpoints para manejo de categorías.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config.database import get_db
from app.models.category import Category, Brand
from app.models.product import Product
from app.schemas.category import (
    CategoryCreate, CategoryUpdate, CategoryResponse, CategoryListResponse,
    CategoryWithSubcategories, CategorySimple
)
from app.core.dependencies import get_current_admin_user, PaginationParams, get_pagination_params
from app.models.user import User

router = APIRouter(prefix="/categories", tags=["Categories"])

# =============================================================================
# RUTAS PÚBLICAS - CATEGORÍAS
# =============================================================================

@router.get("/", response_model=CategoryListResponse)
async def get_categories(
    pagination: PaginationParams = Depends(get_pagination_params),
    parent_id: Optional[str] = Query(None, description="Filtrar por categoría padre"),
    active_only: bool = Query(True, description="Solo categorías activas"),
    db: Session = Depends(get_db)
):
    """
    📂 **Listar categorías**
    
    Obtiene todas las categorías con soporte para paginación y filtros.
    """
    query = db.query(Category)
    
    if active_only:
        query = query.filter(Category.is_active == True)
    
    if parent_id:
        query = query.filter(Category.parent_id == parent_id)
    else:
        # Si no se especifica parent_id, mostrar solo categorías principales
        query = query.filter(Category.parent_id.is_(None))
    
    # Ordenar por sort_order y nombre
    query = query.order_by(Category.sort_order, Category.name)
    
    # Contar total
    total = query.count()
    
    # Aplicar paginación
    categories = query.offset(pagination.skip).limit(pagination.limit).all()
    
    # Agregar conteo de productos para cada categoría
    categories_with_count = []
    for category in categories:
        product_count = db.query(func.count(Product.id)).filter(
            Product.category_id == category.id,
            Product.is_active == True
        ).scalar()
        
        category_dict = category.__dict__.copy()
        category_dict['product_count'] = product_count
        categories_with_count.append(CategoryResponse(**category_dict))
    
    pages = (total + pagination.limit - 1) // pagination.limit
    
    return CategoryListResponse(
        categories=categories_with_count,
        total=total,
        page=pagination.page,
        pages=pages
    )

@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: str,
    db: Session = Depends(get_db)
):
    """
    📂 **Obtener categoría específica**
    
    Obtiene información detallada de una categoría por su ID.
    """
    category = db.query(Category).filter(
        Category.id == category_id,
        Category.is_active == True
    ).first()
    
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Categoría no encontrada"
        )
    
    # Agregar conteo de productos
    product_count = db.query(func.count(Product.id)).filter(
        Product.category_id == category.id,
        Product.is_active == True
    ).scalar()
    
    category_dict = category.__dict__.copy()
    category_dict['product_count'] = product_count
    
    return CategoryResponse(**category_dict)

@router.get("/{category_id}/subcategories", response_model=List[CategoryResponse])
async def get_subcategories(
    category_id: str,
    db: Session = Depends(get_db)
):
    """
    📂 **Obtener subcategorías**
    
    Obtiene todas las subcategorías de una categoría específica.
    """
    parent_category = db.query(Category).filter(
        Category.id == category_id,
        Category.is_active == True
    ).first()
    
    if not parent_category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Categoría padre no encontrada"
        )
    
    subcategories = db.query(Category).filter(
        Category.parent_id == category_id,
        Category.is_active == True
    ).order_by(Category.sort_order, Category.name).all()
    
    # Agregar conteo de productos para cada subcategoría
    subcategories_with_count = []
    for subcategory in subcategories:
        product_count = db.query(func.count(Product.id)).filter(
            Product.category_id == subcategory.id,
            Product.is_active == True
        ).scalar()
        
        subcategory_dict = subcategory.__dict__.copy()
        subcategory_dict['product_count'] = product_count
        subcategories_with_count.append(CategoryResponse(**subcategory_dict))
    
    return subcategories_with_count

@router.get("/simple/list", response_model=List[CategorySimple])
async def get_categories_simple(
    db: Session = Depends(get_db)
):
    """
    📂 **Lista simple de categorías**
    
    Obtiene una lista simple de categorías para usar en dropdowns.
    """
    categories = db.query(Category).filter(
        Category.is_active == True
    ).order_by(Category.sort_order, Category.name).all()
    
    return [
        CategorySimple(
            id=category.id,
            name=category.name,
            slug=category.slug
        )
        for category in categories
    ]

# =============================================================================
# RUTAS DE ADMINISTRADOR - CATEGORÍAS
# =============================================================================

@router.post("/", response_model=CategoryResponse)
async def create_category(
    category_data: CategoryCreate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    👑 **Crear categoría**
    
    Crea una nueva categoría. Solo para administradores.
    """
    # Verificar que el slug no exista
    existing_category = db.query(Category).filter(Category.slug == category_data.slug).first()
    if existing_category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe una categoría con ese slug"
        )
    
    # Si tiene parent_id, verificar que exista
    if category_data.parent_id:
        parent = db.query(Category).filter(Category.id == category_data.parent_id).first()
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Categoría padre no encontrada"
            )
    
    # Crear categoría
    category = Category(**category_data.dict())
    db.add(category)
    db.commit()
    db.refresh(category)
    
    return CategoryResponse(**category.__dict__)

@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: str,
    category_data: CategoryUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    👑 **Actualizar categoría**
    
    Actualiza una categoría existente. Solo para administradores.
    """
    category = db.query(Category).filter(Category.id == category_id).first()
    
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Categoría no encontrada"
        )
    
    # Verificar slug único si se está actualizando
    if category_data.slug and category_data.slug != category.slug:
        existing_category = db.query(Category).filter(Category.slug == category_data.slug).first()
        if existing_category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe una categoría con ese slug"
            )
    
    # Actualizar campos
    update_data = category_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)
    
    db.commit()
    db.refresh(category)
    
    return CategoryResponse(**category.__dict__)

@router.delete("/{category_id}")
async def delete_category(
    category_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    👑 **Eliminar categoría**
    
    Elimina una categoría. Solo para administradores.
    """
    category = db.query(Category).filter(Category.id == category_id).first()
    
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Categoría no encontrada"
        )
    
    # Verificar que no tenga productos asociados
    product_count = db.query(func.count(Product.id)).filter(Product.category_id == category_id).scalar()
    if product_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se puede eliminar la categoría porque tiene {product_count} productos asociados"
        )
    
    # Verificar que no tenga subcategorías
    subcategory_count = db.query(func.count(Category.id)).filter(Category.parent_id == category_id).scalar()
    if subcategory_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se puede eliminar la categoría porque tiene {subcategory_count} subcategorías"
        )
    
    db.delete(category)
    db.commit()
    
    return {"message": "Categoría eliminada exitosamente"} 