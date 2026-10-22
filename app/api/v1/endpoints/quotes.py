from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.config.logging_config import get_logger, log_error
from app.core.dependencies import get_current_active_user
from app.models.user import User
from app.schemas.quote import (
    CartValidationRequest,
    CartValidationResponse,
    QuoteCreate,
    QuoteCreatedResponse,
    QuoteDetailResponse,
    QuoteListResponse,
    QuoteVerifyRequest,
    QuoteVerifyResponse,
)
from app.services.quote_service import QuoteService

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
    price_code: str | None = Query("01", description="Código de lista de precios"),
    warehouse_code: str | None = Query("001", description="Código de almacén para verificar stock"),
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
        created = service.create_quote(current_user.id, data, x_source_system, user_email=current_user.email)
        logger.info(
            "Cotización creada exitosamente",
            extra={
                "quote_id": created.quote_id,
                "user_id": current_user.id,
                "user_email": current_user.email,
                "items_count": len(data.items) if data.items else 0,
            },
        )

        # Enviar email de confirmación (no bloquear si falla)
        if current_user.email:
            try:
                from app.config.settings import Settings
                from app.services.email_service import EmailService

                settings = Settings()
                email_service = EmailService()

                # Preparar items para el email - usar datos obtenidos en create_quote (ya están en created.items_data)
                email_items = []
                if data.items:
                    # Usar los datos que ya obtuvimos en create_quote antes de cerrar la conexión
                    if created.items_data and len(created.items_data) > 0:
                        logger.info(
                            f"[EMAIL DEBUG] Usando items_data obtenidos en create_quote: {len(created.items_data)} items"
                        )
                        quote_items_list = created.items_data

                        # Mapear items por código de artículo para facilitar la búsqueda
                        quote_items_map = {item["co_art"]: item for item in quote_items_list}
                        logger.info(
                            f"[EMAIL DEBUG] Mapeando items por código. unit_prices: {[(k, v.get('unit_price', 'N/A')) for k, v in quote_items_map.items()]}"
                        )

                        # Construir email_items usando los datos ya obtenidos
                        for item in data.items:
                            product_code = item.product_code
                            if product_code in quote_items_map:
                                quote_item = quote_items_map[product_code]
                                logger.info(
                                    f"[EMAIL DEBUG] Item {product_code} -> unit_price: {quote_item.get('unit_price', 'N/A')}"
                                )
                                email_items.append(
                                    {
                                        "product_code": quote_item["co_art"],
                                        "product_name": quote_item["name"],
                                        "quantity": quote_item["quantity"],
                                        "unit_price": quote_item["unit_price"],
                                        "discount_amount": quote_item["discount_amount"],
                                        "tax_amount": quote_item["tax_amount"],
                                    }
                                )
                            else:
                                # Fallback si no se encuentra en los datos obtenidos
                                logger.warning(
                                    f"[EMAIL DEBUG] Item {product_code} no encontrado en items_data, usando fallback"
                                )
                                email_items.append(
                                    {
                                        "product_code": product_code,
                                        "product_name": item.product_name or product_code,
                                        "quantity": str(item.quantity),
                                        "unit_price": item.unit_price
                                        if item.unit_price and item.unit_price != "None"
                                        else "N/A",
                                        "discount_amount": item.discount_amount
                                        if item.discount_amount and item.discount_amount != "None"
                                        else "0.00",
                                        "tax_amount": item.tax_amount
                                        if item.tax_amount and item.tax_amount != "None"
                                        else "0.00",
                                    }
                                )
                    else:
                        # Fallback: usar datos del payload si no hay items_data (no debería pasar normalmente)
                        logger.warning("[EMAIL DEBUG] No hay items_data disponible, usando fallback con data.items")
                        for item in data.items:
                            unit_price_fallback = (
                                item.unit_price if item.unit_price and item.unit_price != "None" else "N/A"
                            )
                            logger.warning(
                                f"[EMAIL DEBUG] Fallback - Item {item.product_code} -> unit_price: {unit_price_fallback}"
                            )
                            email_items.append(
                                {
                                    "product_code": item.product_code,
                                    "product_name": item.product_name or item.product_code,
                                    "quantity": str(item.quantity),
                                    "unit_price": unit_price_fallback,
                                    "discount_amount": item.discount_amount
                                    if item.discount_amount and item.discount_amount != "None"
                                    else "0.00",
                                    "tax_amount": item.tax_amount
                                    if item.tax_amount and item.tax_amount != "None"
                                    else "0.00",
                                }
                            )

                # Log final de email_items antes de enviar
                logger.info(
                    f"[EMAIL DEBUG] email_items FINAL antes de enviar: {[{'product_code': item.get('product_code'), 'product_name': item.get('product_name'), 'quantity': item.get('quantity'), 'unit_price': item.get('unit_price')} for item in email_items]}"
                )

                # Contexto para el template
                customer_name = (
                    data.customer.name
                    if data.customer and data.customer.name
                    else current_user.company_name or "Cliente"
                )

                # Formatear fechas
                from datetime import datetime as dt

                created_at_str = dt.now().strftime("%d/%m/%Y %H:%M")
                expires_at_str = ""
                if created.expires_at:
                    try:
                        expires_dt = dt.fromisoformat(created.expires_at.replace("Z", "+00:00"))
                        expires_at_str = expires_dt.strftime("%d/%m/%Y")
                    except Exception:
                        expires_at_str = (
                            created.expires_at.split("T")[0] if "T" in created.expires_at else created.expires_at
                        )

                email_context = {
                    "customer_name": customer_name,
                    "quote_id": created.quote_id,
                    "created_at": created_at_str,
                    "expires_at": expires_at_str,
                    "currency": created.currency,
                    "total_net": created.total_net,
                    "total_tax": created.total_tax,
                    "total_gross": created.total_gross,
                    "items": email_items,
                    "frontend_url": settings.FRONTEND_URL or "https://farmaplus.com",
                    "year": datetime.now().year,
                }

                # Enviar email de forma asíncrona
                await email_service.send_email(
                    to_email=current_user.email,
                    subject=f"Tu Cotización {created.quote_id} ha sido Creada - FarmaPlus",
                    template_name="quote_created.html",
                    context=email_context,
                )

                # Actualizar email_sent_at en la respuesta
                created.email_sent_at = datetime.now().isoformat()
                logger.info(f"Email de cotización enviado exitosamente a {current_user.email}")

            except Exception as email_error:
                # No fallar la respuesta si el email falla
                logger.warning(
                    f"Error enviando email de cotización a {current_user.email}: {email_error!s}. "
                    f"La cotización fue creada exitosamente pero el email no se pudo enviar.",
                    exc_info=True,
                )
                # email_sent_at permanece como None

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
            detail=f"No se pudo registrar la cotización en Profit Plus: {e!s}",
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
    status: str | None = Query(None, description="pending|accepted|expired|cancelled|converted"),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
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
