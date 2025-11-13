from fastapi import APIRouter, Depends, Header, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from app.config.database import get_db
from app.core.dependencies import get_current_active_user
from app.models.user import User
from app.schemas.quote import (
    QuoteCreate,
    QuoteCreatedResponse,
    QuoteListResponse,
    QuoteDetailResponse,
    QuoteVerifyRequest,
    QuoteVerifyResponse,
    CartValidationRequest,
    CartValidationResponse,
)
from app.services.quote_service import QuoteService
from app.config.logging_config import get_logger, log_error

logger = get_logger("orders")

# Router for /api/v1/quotes
router = APIRouter()

@router.post("/verify", response_model=QuoteVerifyResponse)
async def verify_quote(
    data: QuoteVerifyRequest,
    x_source_system: str = Header(..., alias="X-Source-System"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Verifica artículos y totales estimados para una cotización sin escribir en Profit Plus.
    (Endpoint legacy - usar /verificar para validación de carrito)
    """
    service = QuoteService(db)
    return service.verify_quote_payload(data)


@router.post("/verificar", response_model=CartValidationResponse)
async def verificar_carrito(
    data: CartValidationRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    price_code: Optional[str] = Query("01", description="Código de lista de precios"),
    warehouse_code: Optional[str] = Query("001", description="Código de almacén para verificar stock"),
):
    """
    Valida un carrito de compras enviado por el frontend.
    
    Este endpoint NO guarda nada en la base de datos. Su único propósito es validar
    el carrito enviado por el cliente y devolver un resumen verificado con precios
    reales para que el usuario dé su confirmación final.
    
    Principio: Desconfianza absoluta. Solo se confía en co_art y cantidad.
    Todos los demás datos (precio, descripción, impuestos, disponibilidad) se
    obtienen y calculan desde la base de datos.
    
    El frontend debe enviar únicamente:
    - co_art: Código del artículo
    - cantidad: Cantidad deseada
    
    Todos los demás campos enviados por el frontend serán ignorados.
    """
    service = QuoteService(db)
    return service.validate_cart(
        cart_request=data,
        user_email=current_user.email,
        price_code=price_code or "01",
        warehouse_code=warehouse_code or "001",
    )


@router.post("/", response_model=QuoteCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_quote(
    request: Request,
    data: QuoteCreate,
    x_source_system: str = Header(..., alias="X-Source-System"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Create a new Quote in Profit Plus from the user's checkout/cart.
    Also sends a confirmation email with the quote.
    """
    logger.info(
        "Inicio de creación de cotización",
        extra={
            "path": request.url.path,
            "method": request.method,
            "source_system": x_source_system,
            "user_id": current_user.id if current_user else None,
            "user_email": current_user.email if current_user else None,
            "user_active": current_user.is_active if current_user else None,
            "items_count": len(data.items) if data.items else 0,
            "payment_terms": data.payment_terms,
            "customer_code": getattr(data.customer, "code", None) if data.customer else None,
        },
    )
    
    try:
        service = QuoteService(db)
        logger.debug("Instancia de QuoteService creada, iniciando proceso de persistencia")
        created = service.create_quote(
            current_user.id, 
            data, 
            x_source_system,
            user_email=current_user.email
        )
        logger.info(
            "Cotización creada exitosamente",
            extra={
                "quote_id": created.quote_id,
                "user_id": current_user.id,
                "user_email": current_user.email,
                "items_count": len(data.items) if data.items else 0,
            },
        )
        return created
    except HTTPException as e:
        logger.warning(
            "HTTPException durante creación de cotización",
            extra={
                "status_code": e.status_code,
                "detail": e.detail,
                "user_id": current_user.id,
                "user_email": current_user.email,
            },
        )
        raise
    except Exception as e:
        log_error(
            logger,
            e,
            context={
                "user_id": current_user.id,
                "user_email": current_user.email,
                "items_count": len(data.items) if data.items else 0,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo registrar la cotización en Profit Plus: {str(e)}",
        ) from e


# Router for /api/v1/user/quotes
user_quotes_router = APIRouter()


@user_quotes_router.get("/statuses")
async def get_quote_statuses(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get list of available quote statuses.
    """
    service = QuoteService(db)
    return service.get_statuses()


@user_quotes_router.get("", response_model=QuoteListResponse)
async def list_user_quotes(
    status: Optional[str] = Query(None, description="pending|accepted|expired|cancelled|converted"),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    x_source_system: str = Header(..., alias="X-Source-System"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    List quotes for the current user with optional filters and pagination.
    """
    logger.info(
        "Listando cotizaciones de usuario",
        extra={
            "user_id": current_user.id,
            "user_email": current_user.email,
            "source_system": x_source_system,
            "status_filter": status,
            "from_date": from_date,
            "to_date": to_date,
            "page": page,
            "page_size": page_size,
        },
    )
    service = QuoteService(db)
    result = service.list_user_quotes(
        user_id=current_user.id,
        source_system=x_source_system,
        status_filter=status,
        date_range=(from_date, to_date),
        page=page,
        page_size=page_size,
    )
    logger.info(
        "Listado de cotizaciones completado",
        extra={
            "user_id": current_user.id,
            "user_email": current_user.email,
            "total_items": result.pagination.total_items,
        },
    )
    return result


@user_quotes_router.get("/{quote_id}", response_model=QuoteDetailResponse)
async def get_quote_detail(
    quote_id: str,
    x_source_system: str = Header(..., alias="X-Source-System"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get full details of a specific quote for the current user.
    """
    # Validar que no sea "statuses" para evitar conflictos
    if quote_id == "statuses":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cotización no encontrada")
    
    service = QuoteService(db)
    detail = service.get_quote_detail(current_user.id, quote_id, x_source_system)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cotización no encontrada")
    return detail
