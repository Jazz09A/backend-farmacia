"""
Endpoints protegidos para usuarios autenticados.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.config.logging_config import get_logger
from app.core.dependencies import get_current_active_user
from app.models.user import User
from app.schemas.article import ArticleSummary
from app.schemas.user import UserResponse, UserStats, UserUpdate
from app.services.article_service import article_service
from app.services.recommendation_service import RecommendationService
from app.services.source_system_service import source_system_service

logger = get_logger(__name__)
from app.config.logging_config import get_logger
from app.schemas.cart import CartItemCreate, CartItemUpdate, CartResponse
from app.schemas.customer_address import CustomerAddressesResponse

# Order schemas eliminados - Order no se usa con Profit Plus
from app.schemas.demoa_invoice import (
    DEMOAInvoiceDetails,
    DEMOAInvoiceResponse,
    DEMOAInvoiceSummary,
    DEMOAPaymentResponse,
)
from app.services.cart_service import CartService
from app.services.demoa_invoice_service import DEMOAInvoiceService

# OrderService eliminado - Order no se usa con Profit Plus
from app.services.user_service import UserService

logger = get_logger("orders")

router = APIRouter(prefix="/user")

# =============================================================================
# PERFIL DE USUARIO
# =============================================================================


@router.get("/profile", response_model=UserResponse)
async def get_user_profile(current_user: User = Depends(get_current_active_user)):
    """👤 **Mi perfil**: Obtiene información del perfil del usuario actual."""
    return UserResponse.model_validate(current_user)


@router.put("/profile", response_model=UserResponse)
async def update_user_profile(
    user_update: UserUpdate, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)
):
    """✏️ **Actualizar perfil**: Actualiza la información del perfil del usuario."""
    for field, value in user_update.model_dump(exclude_unset=True).items():
        if hasattr(current_user, field):
            setattr(current_user, field, value)
    db.commit()
    db.refresh(current_user)
    return UserResponse.model_validate(current_user)


# ... (otros endpoints de perfil sin cambios)

# =============================================================================
# CARRITO DE COMPRAS
# =============================================================================


@router.get("/cart", response_model=CartResponse, summary="Get user's shopping cart")
async def get_user_cart(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """🛒 **Mi carrito**: Obtiene el carrito de compras del usuario actual."""
    cart_service = CartService(db)
    return cart_service.get_user_cart(current_user.id)


@router.post("/cart/add", summary="Add item to cart", response_model=CartResponse)
async def add_to_cart(
    item: CartItemCreate, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)
):
    """➕ **Agregar al carrito**: Agrega un producto al carrito del usuario."""
    cart_service = CartService(db)
    logger.info(
        "Agregando producto al carrito",
        extra={
            "user_id": current_user.id,
            "product_id": item.product_id,
            "quantity": item.quantity,
            "selected_presentation": item.selected_presentation,
        },
    )
    cart_service.add_item(
        user_id=current_user.id,
        product_id=item.product_id,
        quantity=item.quantity,
        selected_presentation=item.selected_presentation,
    )
    logger.info(
        "Producto agregado correctamente al carrito",
        extra={
            "user_id": current_user.id,
            "product_id": item.product_id,
            "quantity": item.quantity,
        },
    )
    return cart_service.get_user_cart(current_user.id)


@router.put("/cart/item/{item_id}", summary="Update cart item quantity", response_model=CartResponse)
async def update_cart_item(
    item_id: str,
    item_update: CartItemUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """✏️ **Actualizar item del carrito**: Actualiza la cantidad de un item."""
    cart_service = CartService(db)
    cart_service.update_item_quantity(user_id=current_user.id, item_id=item_id, new_quantity=item_update.quantity)
    return cart_service.get_user_cart(current_user.id)


@router.delete("/cart/item/{item_id}", summary="Remove item from cart", response_model=CartResponse)
async def remove_from_cart(
    item_id: str, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)
):
    """❌ **Eliminar del carrito**: Elimina un item específico del carrito."""
    cart_service = CartService(db)
    cart_service.remove_item(user_id=current_user.id, item_id=item_id)
    return cart_service.get_user_cart(current_user.id)


@router.delete("/cart/clear", summary="Clear entire cart", response_model=CartResponse)
async def clear_cart(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """🗑️ **Vaciar carrito**: Elimina todos los items del carrito."""
    cart_service = CartService(db)
    cart_service.clear_cart(user_id=current_user.id)
    return cart_service.get_user_cart(current_user.id)


# =============================================================================
# ÓRDENES Y COMPRAS - ELIMINADAS
# =============================================================================
# Los endpoints de Order fueron eliminados porque Order no se usa con Profit Plus.
# Las cotizaciones se manejan a través de /quotes que se conecta directamente a Profit Plus.

# =============================================================================
# DIRECCIONES DE ENVÍO
# =============================================================================

# @router.post("/addresses", response_model=AddressResponse, status_code=status.HTTP_201_CREATED)
# def create_address(
#     address_data: AddressCreate,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_active_user)
# ):
#     """
#     **Crear nueva dirección**: Añade una nueva dirección de envío para el usuario.
#     """
#     if address_data.is_default:
#         # Si esta se marca como predeterminada, quitar la marca de las otras
#         db.query(Address).filter(Address.user_id == current_user.id).update({Address.is_default: False})

#     new_address = Address(**address_data.model_dump(), user_id=current_user.id)
#     db.add(new_address)
#     db.commit()
#     db.refresh(new_address)
#     return new_address

# @router.get("/addresses")
# async def get_addresses(
#     include_checkout_preview: bool = False,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_active_user)
# ):
#     """
#     **Mis direcciones**: Obtiene todas las direcciones de envío del usuario.

#     Args:
#         include_checkout_preview: Si True, incluye cálculo de costos para cada dirección
#     """
#     # 1. Obtener direcciones del usuario
#     addresses = db.query(Address).filter(Address.user_id == current_user.id).all()

#     if not include_checkout_preview:
#         return {"addresses": addresses}

#     # 2. Validar y obtener carrito
#     cart_service = CartService(db)
#     cart = cart_service.get_user_cart(current_user.id)

#     if not cart or cart.total == 0:
#         return {
#             "addresses": addresses,
#             "checkout_preview": None,
#             "message": "Carrito vacío - no se puede calcular preview de costos"
#         }

#     # 3. Validar que el carrito tenga productos disponibles
#     cart_items = db.query(CartItem).options(joinedload(CartItem.product)).filter(CartItem.user_id == current_user.id).all()

#     unavailable_products = []
#     for item in cart_items:
#         product = item.product
#         if not product or not product.is_available or product.stock < item.quantity:
#             unavailable_products.append({
#                 "product_name": product.name if product else "Producto no encontrado",
#                 "required_quantity": item.quantity,
#                 "available_stock": product.stock if product else 0
#             })

#     if unavailable_products:
#         return {
#             "addresses": addresses,
#             "checkout_preview": None,
#             "message": "Algunos productos no están disponibles",
#             "unavailable_products": unavailable_products
#         }

#     # 4. Calcular preview para cada dirección
#     order_service = OrderService(db)
#     checkout_previews = {}

#     for address in addresses:
#         try:
#             # Calcular totales usando el servicio existente
#             preview = await order_service.calculate_checkout_totals(
#                 user_id=current_user.id,
#                 shipping_address_id=address.id,
#                 payment_currency="USD"
#             )

#             # Obtener información de descuentos del carrito
#             cart_items = db.query(CartItem).options(joinedload(CartItem.product)).filter(CartItem.user_id == current_user.id).all()
#             discount_service = DiscountService(db)
#             discounts_info = discount_service.calculate_cart_discounts(cart_items)

#             # Calcular precios originales y con descuento
#             original_subtotal = float(discounts_info.get('subtotal_original', preview['subtotal']))
#             discounted_subtotal = float(preview['subtotal'])
#             shipping_cost = float(preview['shipping_cost'])

#             # Calcular impuestos correctamente
#             original_taxes = float(original_subtotal * 0.16)  # Impuestos sobre subtotal original
#             discounted_taxes = float(discounted_subtotal * 0.16)  # Impuestos sobre subtotal con descuento

#             # Calcular totales
#             original_total = float(original_subtotal + original_taxes + shipping_cost)
#             discounted_total = float(discounted_subtotal + discounted_taxes + shipping_cost)

#             # Calcular ahorro del descuento (SOLO en productos)
#             product_savings = original_subtotal - discounted_subtotal
#             tax_savings = original_taxes - discounted_taxes  # Diferencia en impuestos (no es ahorro del descuento)
#             total_savings = product_savings  # El ahorro real es SOLO el descuento en productos

#             checkout_previews[address.id] = {
#                 # Precios originales (sin descuentos) - SOLO PRODUCTOS + IMPUESTOS + ENVÍO
#                 "original_subtotal": original_subtotal,
#                 "original_taxes": original_taxes,
#                 "original_total": original_total,

#                 # Precios finales (con descuentos)
#                 "subtotal": discounted_subtotal,
#                 "shipping_cost": shipping_cost,
#                 "taxes": discounted_taxes,  # Usar impuestos calculados correctamente
#                 "total": discounted_total,  # Usar total calculado correctamente

#                 # Información detallada de ahorro
#                 "product_savings": product_savings,  # Descuento aplicado en productos
#                 "tax_savings": tax_savings,  # Diferencia en impuestos (consecuencia del descuento)
#                 "total_savings": total_savings,  # Descuento real (solo productos)
#                 "savings_percentage": round((product_savings / original_subtotal * 100), 2) if original_subtotal > 0 else 0,

#                 # Información de envío y moneda
#                 "shipping_zone": preview['shipping_zone'],
#                 "payment_currency": preview['payment_currency'],
#                 "exchange_rate": float(preview['exchange_rate']) if preview['exchange_rate'] else None,

#                 # Información detallada de descuentos
#                 "quantity_discount": preview.get('quantity_discount'),
#                 "quantity_discount_amount": float(preview.get('quantity_discount_amount', 0)),
#                 "flash_discounts": preview.get('flash_discounts', []),
#                 "total_discount": float(preview.get('total_discount', 0))
#             }

#         except HTTPException as e:
#             # Error específico (dirección no válida, etc.)
#             cart_total = float(cart.total)
#             original_taxes = float(cart_total * 0.16)
#             original_total = float(cart_total + original_taxes)

#             checkout_previews[address.id] = {
#                 "error": e.detail,
#                 # Precios originales (sin descuentos)
#                 "original_subtotal": cart_total,
#                 "original_taxes": original_taxes,
#                 "original_total": original_total,
#                 # Precios finales (sin descuentos en caso de error)
#                 "subtotal": cart_total,
#                 "shipping_cost": 0,
#                 "taxes": original_taxes,
#                 "total": original_total,
#                 # Información de ahorro (sin ahorro en caso de error)
#                 "product_savings": 0,
#                 "tax_savings": 0,
#                 "total_savings": 0,
#                 "savings_percentage": 0,
#                 # Información de envío y moneda
#                 "shipping_zone": "error",
#                 "payment_currency": "USD",
#                 "exchange_rate": None,
#                 # Información de descuentos (sin descuentos en caso de error)
#                 "quantity_discount": None,
#                 "quantity_discount_amount": 0,
#                 "flash_discounts": [],
#                 "total_discount": 0
#             }
#         except Exception as e:
#             # Error inesperado
#             cart_total = float(cart.total)
#             original_taxes = float(cart_total * 0.16)
#             original_total = float(cart_total + original_taxes)

#             checkout_previews[address.id] = {
#                 "error": f"Error calculando costos: {str(e)}",
#                 # Precios originales (sin descuentos) - SOLO PRODUCTOS + IMPUESTOS
#                 "original_subtotal": cart_total,
#                 "original_taxes": original_taxes,
#                 "original_total": original_total,
#                 # Precios finales (sin descuentos en caso de error)
#                 "subtotal": cart_total,
#                 "shipping_cost": 0,
#                 "taxes": original_taxes,
#                 "total": original_total,
#                 # Información de ahorro (sin ahorro en caso de error)
#                 "product_savings": 0,
#                 "tax_savings": 0,
#                 "total_savings": 0,
#                 "savings_percentage": 0,
#                 # Información de envío y moneda
#                 "shipping_zone": "error",
#                 "payment_currency": "USD",
#                 "exchange_rate": None,
#                 # Información de descuentos (sin descuentos en caso de error)
#                 "quantity_discount": None,
#                 "quantity_discount_amount": 0,
#                 "flash_discounts": [],
#                 "total_discount": 0
#             }

#     # 5. Calcular resumen general
#     valid_previews = {k: v for k, v in checkout_previews.items() if 'error' not in v}

#     if valid_previews:
#         min_total = min(preview['total'] for preview in valid_previews.values())
#         max_total = max(preview['total'] for preview in valid_previews.values())
#         avg_total = sum(preview['total'] for preview in valid_previews.values()) / len(valid_previews)
#     else:
#         min_total = max_total = avg_total = 0

#     # Calcular resumen de precios originales
#     if valid_previews:
#         original_totals = [preview['original_total'] for preview in valid_previews.values()]
#         min_original = min(original_totals)
#         max_original = max(original_totals)
#         avg_original = sum(original_totals) / len(original_totals)

#         # Calcular ahorro promedio
#         savings = [preview['total_savings'] for preview in valid_previews.values()]
#         avg_savings = sum(savings) / len(savings) if savings else 0
#     else:
#         min_original = max_original = avg_original = avg_savings = 0

#     cart_total = float(cart.total)
#     original_taxes = float(cart_total * 0.16)
#     original_total = float(cart_total + original_taxes)

#     return {
#         "addresses": addresses,
#         "checkout_preview": {
#             # Precios originales (sin descuentos) - SOLO PRODUCTOS + IMPUESTOS
#             "original_subtotal": cart_total,
#             "original_taxes": original_taxes,
#             "original_total": original_total,

#             # Precios finales (con descuentos)
#             "subtotal": cart_total,  # Este será actualizado por el primer preview válido
#             "tax_rate": 0.16,
#             "previews_by_address": checkout_previews,

#             # Resumen general
#             "summary": {
#                 # Totales originales
#                 "min_original_total": min_original,
#                 "max_original_total": max_original,
#                 "avg_original_total": round(avg_original, 2),

#                 # Totales con descuentos
#                 "min_total": min_total,
#                 "max_total": max_total,
#                 "avg_total": round(avg_total, 2),

#                 # Ahorro promedio
#                 "avg_savings": round(avg_savings, 2),
#                 "avg_savings_percentage": round((avg_savings / avg_original * 100), 2) if avg_original > 0 else 0,

#                 # Información de direcciones
#                 "total_addresses": len(addresses),
#                 "valid_addresses": len(valid_previews)
#             }
#         }
#     }

# @router.put("/addresses/{address_id}", response_model=AddressResponse)
# def update_address(
#     address_id: str,
#     address_data: AddressUpdate,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_active_user)
# ):
#     """
#     **Actualizar dirección**: Modifica una dirección de envío existente.
#     """
#     address = db.query(Address).filter(Address.id == address_id, Address.user_id == current_user.id).first()
#     if not address:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")

#     if address_data.is_default:
#         # Si esta se marca como predeterminada, quitar la marca de las otras
#         db.query(Address).filter(Address.user_id == current_user.id).update({Address.is_default: False})

#     update_data = address_data.dict(exclude_unset=True)
#     for key, value in update_data.items():
#         setattr(address, key, value)

#     db.commit()
#     db.refresh(address)
#     return address

# @router.delete("/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
# def delete_address(
#     address_id: str,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_active_user)
# ):
#     """
#     **Eliminar dirección**: Elimina una dirección de envío.
#     """
#     address = db.query(Address).filter(Address.id == address_id, Address.user_id == current_user.id).first()
#     if not address:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")

#     db.delete(address)
#     db.commit()
#     return

# @router.post("/addresses/{address_id}/set-default", response_model=AddressResponse)
# def set_default_address(
#     address_id: str,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_active_user)
# ):
#     """
#     **Marcar como predeterminada**: Establece una dirección como la de envío por defecto.
#     """
#     address = db.query(Address).filter(Address.id == address_id, Address.user_id == current_user.id).first()
#     if not address:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")

#     # Quitar la marca de predeterminada de cualquier otra dirección
#     db.query(Address).filter(Address.user_id == current_user.id).update({Address.is_default: False})

#     # Marcar la nueva como predeterminada
#     address.is_default = True
#     db.commit()
#     db.refresh(address)
#     return address


@router.get("/stats", response_model=UserStats, summary="Obtiene estadísticas del usuario")
async def get_user_stats(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """
    **Estadísticas del usuario**: Obtiene estadísticas del usuario desde source_system (DEMOA).
    Incluye total de órdenes, total gastado y total de productos comprados.
    """
    user_service = UserService(db)
    return user_service.get_user_stats_by_id(current_user.id, user_email=current_user.email)


@router.get(
    "/recommendations", response_model=list[ArticleSummary], summary="Obtiene artículos recomendados para el usuario"
)
async def get_user_recommendations(
    limit: int = Query(12, ge=1, le=50, description="Número máximo de artículos recomendados"),
    price_code: str = Query("01", description="Lista de precio de referencia"),
    warehouse_code: str = Query("001", description="Almacén principal para stock"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    🎯 **Artículos recomendados para ti**

    Obtiene artículos recomendados basados en tu historial de compras desde source_system (DEMOA).
    Incluye artículos de categorías que has comprado, artículos populares y mejor valorados.
    """
    recommendation_service = RecommendationService()

    # Obtener código de cliente desde source_system
    customer_code = None
    try:
        customer = source_system_service.get_customer_by_email(current_user.email)
        if customer:
            customer_code = customer.get("customer_code")
    except Exception as e:
        logger.error(f"No se pudo obtener código de cliente para recomendaciones: {e}")

    recommended = recommendation_service.get_recommended_articles(
        customer_code=customer_code, limit=limit, price_code=price_code, warehouse_code=warehouse_code
    )

    # Convertir a ArticleSummary
    def row_to_summary(row):
        image_guid = row.get("image_guid")
        image_guid_normalized = None
        if image_guid:
            image_guid_normalized = str(image_guid).strip().upper().replace("{", "").replace("}", "")

        image_url = article_service._build_image_url(image_guid_normalized)

        return ArticleSummary(
            co_art=(row.get("co_art") or "").strip(),
            art_des=row.get("art_des") or "",
            category_code=(row.get("category_code") or "").strip() if row.get("category_code") else None,
            category_name=row.get("category_name"),
            price=article_service._to_decimal(row.get("price")),
            currency=(row.get("currency") or "VES").strip(),
            stock=article_service._to_decimal(row.get("stock")),
            warehouse_code=(row.get("warehouse_code") or "").strip() if row.get("warehouse_code") else None,
            image_url=image_url,
            has_image=bool(image_guid_normalized),
        )

    return [row_to_summary(row) for row in recommended]


# =============================================================================
# FACTURAS PROFIT PLUS
# =============================================================================


@router.get("/invoices/summary", response_model=DEMOAInvoiceSummary)
async def get_invoices_summary(current_user: User = Depends(get_current_active_user)):
    """
    📊 **Resumen de Facturas**: Obtiene un resumen de facturas del usuario
    desde el sistema Profit Plus.
    """
    demoa_service = DEMOAInvoiceService()

    # Obtener código de cliente en DEMOA
    customer_code = demoa_service.get_customer_code_by_email(current_user.email)

    if not customer_code:
        return DEMOAInvoiceSummary(
            total_invoices=0,
            pending_invoices=0,
            paid_invoices=0,
            total_pending_amount=Decimal("0.00"),
            total_invoiced=Decimal("0.00"),
        )

    # Obtener resumen
    summary = demoa_service.get_invoices_summary(customer_code)
    return DEMOAInvoiceSummary(**summary)


@router.get("/invoices", response_model=list[DEMOAInvoiceResponse])
async def get_all_invoices(
    status_filter: str | None = Query(None, description="Filtrar por estado: 'pending', 'paid', 'all'"),
    current_user: User = Depends(get_current_active_user),
):
    """
    📄 **Mis Facturas**: Obtiene todas las facturas del usuario desde Profit Plus.

    Filtros disponibles:
    - `pending`: Solo facturas pendientes
    - `paid`: Solo facturas pagadas
    - `all` o sin filtro: Todas las facturas
    """
    demoa_service = DEMOAInvoiceService()
    customer_code = demoa_service.get_customer_code_by_email(current_user.email)

    if not customer_code:
        return []

    if status_filter == "pending":
        invoices = demoa_service.get_pending_invoices(customer_code)
    elif status_filter == "paid":
        invoices = demoa_service.get_paid_invoices(customer_code)
    else:
        invoices = demoa_service.get_all_invoices(customer_code)

    # Convertir a respuesta
    return [DEMOAInvoiceResponse(**inv) for inv in invoices]


@router.get("/invoices/pending", response_model=list[DEMOAInvoiceResponse])
async def get_pending_invoices(current_user: User = Depends(get_current_active_user)):
    """
    ⏳ **Facturas Pendientes**: Obtiene facturas con pago pendiente.
    """
    demoa_service = DEMOAInvoiceService()
    customer_code = demoa_service.get_customer_code_by_email(current_user.email)

    if not customer_code:
        return []

    invoices = demoa_service.get_pending_invoices(customer_code)
    return [DEMOAInvoiceResponse(**inv) for inv in invoices]


@router.get("/invoices/paid", response_model=list[DEMOAInvoiceResponse])
async def get_paid_invoices(current_user: User = Depends(get_current_active_user)):
    """
    ✅ **Facturas Pagadas**: Obtiene historial de facturas pagadas.
    """
    demoa_service = DEMOAInvoiceService()
    customer_code = demoa_service.get_customer_code_by_email(current_user.email)

    if not customer_code:
        return []

    invoices = demoa_service.get_paid_invoices(customer_code)
    return [DEMOAInvoiceResponse(**inv) for inv in invoices]


@router.get("/invoices/{invoice_number}", response_model=DEMOAInvoiceDetails)
async def get_invoice_details(invoice_number: str, current_user: User = Depends(get_current_active_user)):
    """
    📋 **Detalles de Factura**: Obtiene detalles completos de una factura,
    incluyendo items y productos.
    """
    demoa_service = DEMOAInvoiceService()
    customer_code = demoa_service.get_customer_code_by_email(current_user.email)

    if not customer_code:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado en Profit Plus")

    invoice = demoa_service.get_invoice_details(invoice_number, customer_code)

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Factura no encontrada o no pertenece al usuario"
        )

    return DEMOAInvoiceDetails(**invoice)


@router.get("/invoices/payments", response_model=list[DEMOAPaymentResponse])
async def get_payment_history(current_user: User = Depends(get_current_active_user)):
    """
    💳 **Historial de Pagos**: Obtiene el historial completo de pagos
    aplicados a facturas.
    """
    demoa_service = DEMOAInvoiceService()
    customer_code = demoa_service.get_customer_code_by_email(current_user.email)

    if not customer_code:
        return []

    payments = demoa_service.get_payment_history(customer_code)
    return [DEMOAPaymentResponse(**payment) for payment in payments]


@router.get("/customer-addresses", response_model=CustomerAddressesResponse)
async def get_customer_addresses(current_user: User = Depends(get_current_active_user)):
    """
    📍 **Direcciones del Cliente**: Obtiene las direcciones del cliente desde Profit Plus
    usando su código de cliente (co_cli).

    Retorna las direcciones almacenadas en Profit Plus:
    - direc1: Dirección principal
    - dir_ent2: Dirección de entrega
    - direc2: Dirección secundaria
    """
    # Obtener código de cliente por email
    customer = source_system_service.get_customer_by_email(current_user.email)

    if not customer or not customer.get("customer_code"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado en Profit Plus")

    # customer viene de la búsqueda en saCliente (SIEMPRE incluye 'customer_code');
    # el dict está tipado como Dict[str, Any], mypy no puede saberlo.
    customer_code = customer.get("customer_code")

    # Obtener direcciones desde Profit Plus
    addresses = source_system_service.get_customer_addresses(customer_code)  # type: ignore[arg-type]

    return CustomerAddressesResponse(customer_code=customer_code, addresses=addresses)
