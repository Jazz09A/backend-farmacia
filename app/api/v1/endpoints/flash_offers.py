"""
Endpoints para gestionar Flash Offers
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.auth import get_admin_user
from app.core.dependencies import (
    PaginationParams,
    get_current_user,
    get_pagination_params,
)
from app.models.user import User
from app.schemas.promotion import (
    FlashOfferCreate,
    FlashOfferListResponse,
    FlashOfferResponse,
    FlashOfferUpdate,
)
from app.services.flash_offers_service import FlashOffersService

router = APIRouter()


@router.post("/flash-offers", response_model=FlashOfferResponse, status_code=status.HTTP_201_CREATED)
async def create_flash_offer(
    flash_offer_data: FlashOfferCreate, db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)
):
    """
    Crear una nueva flash offer.

    **Requiere permisos de administrador.**
    """
    service = FlashOffersService(db)
    flash_offer = service.create_flash_offer(flash_offer_data)
    return service.build_flash_offer_response(flash_offer)


@router.get("/flash-offers", response_model=FlashOfferListResponse)
async def get_flash_offers(
    pagination: PaginationParams = Depends(get_pagination_params),
    active_only: bool = Query(False, description="Solo ofertas activas"),
    valid_only: bool = Query(False, description="Solo ofertas válidas (activas y en tiempo)"),
    product_id: str | None = Query(None, description="Filtrar por ID de producto local"),
    article_code: str | None = Query(None, description="Filtrar por código de artículo (co_art)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Obtener lista de flash offers con filtros y paginación.

    **Requiere autenticación.**
    """
    service = FlashOffersService(db)
    flash_offers, total = service.get_flash_offers(
        skip=pagination.skip,
        limit=pagination.limit,
        active_only=active_only,
        valid_only=valid_only,
        product_id=product_id,
        article_code=article_code,
    )

    offers = service.serialize_flash_offers(flash_offers)
    return FlashOfferListResponse(
        offers=offers, total=total, page=pagination.page, pages=(total + pagination.limit - 1) // pagination.limit
    )


@router.get("/flash-offers/public", response_model=FlashOfferListResponse)
async def get_public_flash_offers(
    pagination: PaginationParams = Depends(get_pagination_params),
    product_id: str | None = Query(None, description="Filtrar por ID de producto local"),
    article_code: str | None = Query(None, description="Filtrar por código de artículo (co_art)"),
    db: Session = Depends(get_db),
):
    """
    Obtener flash offers válidas (públicas, sin autenticación).

    Solo muestra ofertas activas y válidas en el tiempo.
    """
    service = FlashOffersService(db)
    flash_offers, total = service.get_flash_offers(
        skip=pagination.skip,
        limit=pagination.limit,
        active_only=True,
        valid_only=True,
        product_id=product_id,
        article_code=article_code,
    )

    offers = service.serialize_flash_offers(flash_offers)
    return FlashOfferListResponse(
        offers=offers, total=total, page=pagination.page, pages=(total + pagination.limit - 1) // pagination.limit
    )


@router.get("/flash-offers/{offer_id}", response_model=FlashOfferResponse)
async def get_flash_offer(offer_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Obtener una flash offer específica por ID.

    **Requiere autenticación.**
    """
    service = FlashOffersService(db)
    flash_offer = service.get_flash_offer(offer_id)

    if not flash_offer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flash offer no encontrada")

    return service.build_flash_offer_response(flash_offer)


@router.put("/flash-offers/{offer_id}", response_model=FlashOfferResponse)
async def update_flash_offer(
    offer_id: str,
    update_data: FlashOfferUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """
    Actualizar una flash offer existente.

    **Requiere permisos de administrador.**
    """
    service = FlashOffersService(db)
    flash_offer = service.update_flash_offer(offer_id, update_data)

    if not flash_offer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flash offer no encontrada")

    return service.build_flash_offer_response(flash_offer)


@router.delete("/flash-offers/{offer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_flash_offer(
    offer_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)
):
    """
    Eliminar una flash offer.

    **Requiere permisos de administrador.**
    """
    service = FlashOffersService(db)
    deleted = service.delete_flash_offer(offer_id)

    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flash offer no encontrada")


@router.patch("/flash-offers/{offer_id}/toggle-status", response_model=FlashOfferResponse)
async def toggle_flash_offer_status(
    offer_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)
):
    """
    Activar/desactivar una flash offer.

    **Requiere permisos de administrador.**
    """
    service = FlashOffersService(db)
    flash_offer = service.toggle_flash_offer_status(offer_id)

    if not flash_offer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flash offer no encontrada")

    return service.build_flash_offer_response(flash_offer)


@router.get("/flash-offers/article/{article_code}/active", response_model=list[FlashOfferResponse])
async def get_active_flash_offers_for_article(article_code: str, db: Session = Depends(get_db)):
    """
    Obtener todas las flash offers activas y válidas para un artículo (co_art) específico.

    **Endpoint público** - No requiere autenticación.
    """
    service = FlashOffersService(db)
    flash_offers = service.get_active_flash_offers_for_article(article_code)
    return service.serialize_flash_offers(flash_offers)


@router.post("/flash-offers/{offer_id}/increment-usage")
async def increment_flash_offer_usage(
    offer_id: str,
    quantity: int = Query(1, ge=1, description="Cantidad a incrementar"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Incrementar el uso de una flash offer.

    Este endpoint se usa internamente cuando se realiza una compra.
    **Requiere autenticación.**
    """
    service = FlashOffersService(db)
    flash_offer = service.increment_usage(offer_id, quantity)

    if not flash_offer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flash offer no encontrada")

    return {
        "message": f"Uso incrementado en {quantity}",
        "used_quantity": flash_offer.used_quantity,
        "max_quantity": flash_offer.max_quantity,
        "remaining": flash_offer.max_quantity - flash_offer.used_quantity if flash_offer.max_quantity else None,
    }


@router.post("/flash-offers/cleanup-expired")
async def cleanup_expired_flash_offers(db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    """
    Desactivar automáticamente flash offers expiradas.

    **Requiere permisos de administrador.**
    Este endpoint puede ser llamado por un cron job o manualmente.
    """
    service = FlashOffersService(db)
    count = service.cleanup_expired_offers()

    return {"message": f"Se desactivaron {count} flash offers expiradas", "count": count}


@router.get("/flash-offers/stats/expired", response_model=list[FlashOfferResponse])
async def get_expired_flash_offers(db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    """
    Obtener lista de flash offers expiradas pero aún activas.

    **Requiere permisos de administrador.**
    Útil para monitoreo y limpieza manual.
    """
    service = FlashOffersService(db)
    expired_offers = service.get_expired_flash_offers()
    return service.serialize_flash_offers(expired_offers)
