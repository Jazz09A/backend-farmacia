"""
Endpoints para gestionar descuentos por cantidad
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import get_current_user, PaginationParams, get_pagination_params
from app.core.auth import get_admin_user
from app.models.user import User
from app.services.discount_service import DiscountService
from app.schemas.promotion import (
    QuantityDiscountCreate,
    QuantityDiscountUpdate,
    QuantityDiscountResponse,
    QuantityDiscountListResponse
)

router = APIRouter()


@router.post("/quantity-discounts", response_model=QuantityDiscountResponse, status_code=status.HTTP_201_CREATED)
async def create_quantity_discount(
    discount_data: QuantityDiscountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Crear un nuevo descuento por cantidad.

    **Requiere permisos de administrador.**
    """
    service = DiscountService(db)
    discount = service.create_quantity_discount(discount_data.dict())
    return discount


@router.get("/quantity-discounts", response_model=QuantityDiscountListResponse)
async def get_quantity_discounts(
    pagination: PaginationParams = Depends(get_pagination_params),
    active_only: bool = Query(False, description="Solo descuentos activos"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Obtener lista de descuentos por cantidad con paginación.

    **Requiere permisos de administrador.**
    """
    service = DiscountService(db)
    discounts, total = service.get_quantity_discounts(
        skip=pagination.skip,
        limit=pagination.limit,
        active_only=active_only
    )

    return QuantityDiscountListResponse(
        discounts=discounts,
        total=total,
        page=pagination.page,
        pages=(total + pagination.limit - 1) // pagination.limit
    )


@router.get("/quantity-discounts/{discount_id}", response_model=QuantityDiscountResponse)
async def get_quantity_discount(
    discount_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Obtener un descuento por cantidad específico por ID.

    **Requiere permisos de administrador.**
    """
    service = DiscountService(db)
    discount = service.get_quantity_discount(discount_id)

    if not discount:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Descuento por cantidad no encontrado"
        )

    return discount


@router.put("/quantity-discounts/{discount_id}", response_model=QuantityDiscountResponse)
async def update_quantity_discount(
    discount_id: str,
    update_data: QuantityDiscountUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Actualizar un descuento por cantidad existente.

    **Requiere permisos de administrador.**
    """
    service = DiscountService(db)
    discount = service.update_quantity_discount(discount_id, update_data.model_dump(exclude_unset=True))

    if not discount:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Descuento por cantidad no encontrado"
        )

    return discount


@router.delete("/quantity-discounts/{discount_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quantity_discount(
    discount_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Eliminar un descuento por cantidad.

    **Requiere permisos de administrador.**
    """
    service = DiscountService(db)
    deleted = service.delete_quantity_discount(discount_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Descuento por cantidad no encontrado"
        )


@router.patch("/quantity-discounts/{discount_id}/toggle-status", response_model=QuantityDiscountResponse)
async def toggle_quantity_discount_status(
    discount_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Activar/desactivar un descuento por cantidad.

    **Requiere permisos de administrador.**
    """
    service = DiscountService(db)
    discount = service.toggle_quantity_discount_status(discount_id)

    if not discount:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Descuento por cantidad no encontrado"
        )

    return discount

