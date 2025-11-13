"""
Endpoints protegidos para usuarios autenticados.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from decimal import Decimal
from sqlalchemy.orm import Session, joinedload
from app.config.database import get_db
from app.core.dependencies import get_current_active_user
from app.models.user import User
from app.models.address import Address
from app.models.cart import CartItem
from app.schemas.user import UserResponse, UserStats, UserUpdate
from app.schemas.address import AddressResponse, AddressCreate, AddressUpdate
from app.schemas.cart import CartResponse, CartItemCreate, CartItemUpdate
from app.schemas.order import OrderResponse, OrderCreate, OrderSummary, CheckoutPreviewRequest, CheckoutPreviewResponse
from app.schemas.demoa_invoice import (
    DEMOAInvoiceResponse,
    DEMOAInvoiceDetails,
    DEMOAInvoiceSummary,
    DEMOAPaymentResponse
)
from app.services.cart_service import CartService
from app.services.order_service import OrderService
from app.services.discount_service import DiscountService
from app.services.user_service import UserService
from app.services.demoa_invoice_service import DEMOAInvoiceService
from app.services.source_system_service import source_system_service
from app.schemas.customer_address import CustomerAddressesResponse
from app.config.logging_config import get_logger, log_error

logger = get_logger("orders")

router = APIRouter(prefix="/user", tags=["User Protected"])

# =============================================================================
# PERFIL DE USUARIO
# =============================================================================

@router.get("/profile", response_model=UserResponse)
async def get_user_profile(current_user: User = Depends(get_current_active_user)):
    """👤 **Mi perfil**: Obtiene información del perfil del usuario actual."""
    return UserResponse.model_validate(current_user)

@router.put("/profile", response_model=UserResponse)
async def update_user_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """✏️ **Actualizar perfil**: Actualiza la información del perfil del usuario."""
    for field, value in user_update.dict(exclude_unset=True).items():
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
    item: CartItemCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
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
        selected_presentation=item.selected_presentation
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
    db: Session = Depends(get_db)
):
    """✏️ **Actualizar item del carrito**: Actualiza la cantidad de un item."""
    cart_service = CartService(db)
    cart_service.update_item_quantity(user_id=current_user.id, item_id=item_id, new_quantity=item_update.quantity)
    return cart_service.get_user_cart(current_user.id)

@router.delete("/cart/item/{item_id}", summary="Remove item from cart", response_model=CartResponse)
async def remove_from_cart(
    item_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
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
# ÓRDENES Y COMPRAS
# =============================================================================

@router.post("/orders", response_model=OrderResponse, summary="Create a new order from cart")
async def create_order(
    order_data: OrderCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    📋 **Crear orden**: Crea una nueva orden a partir del carrito de compras.

    Este proceso valida el carrito, crea la orden con todos sus detalles,
    actualiza el stock de productos y limpia el carrito.
    """
    try:
        order_service = OrderService(db)
        new_order = await order_service.create_order_from_cart(current_user.id, order_data)
        
        # Formatear información de descuentos según el schema OrderDiscountSummary
        discount_info = order_service._calculate_order_discount_info(new_order)
        
        # Manually construct the response data to match the OrderResponse schema.
        # This avoids the validation error caused by the mismatch between the
        # Order model's `discounts` relationship (a list) and the
        # OrderResponse schema's `discounts` field (an object).
        response_data = {
            'id': new_order.id,
            'user_id': new_order.user_id,
            'order_number': new_order.order_number,
            'status': new_order.status,
            'subtotal': new_order.subtotal,
            'shipping_cost': new_order.shipping_cost,
            'taxes': new_order.taxes,
            'total': new_order.total,
            'payment_currency': new_order.payment_currency,
            'exchange_rate': new_order.exchange_rate,
            'payment_method': new_order.payment_method,
            'payment_status': new_order.payment_status,
            'payment_reference': new_order.payment_reference,
            'tracking_number': new_order.tracking_number,
            'estimated_delivery': new_order.estimated_delivery,
            'delivered_at': new_order.delivered_at,
            'customer_notes': new_order.customer_notes,
            'created_at': new_order.created_at,
            'updated_at': new_order.updated_at,
            'items': new_order.items,
            'shipping_address': new_order.shipping_address,
            'item_count': len(new_order.items),
            'payment_capture_url': new_order.payment_capture_url,
            'is_credit_order': new_order.is_credit_order,
            'credit_amount': new_order.credit_amount,
            'credit_remaining': new_order.credit_remaining,
            'credit_paid_total': new_order.credit_paid_total,
            'payment_due_date': new_order.payment_due_date,
            'credit_paid': new_order.credit_paid,
            'credit_payment_date': new_order.credit_payment_date,
            'quantity_discount': new_order.quantity_discount,
            'quantity_discount_amount': new_order.quantity_discount_amount,
        }
        
        from app.schemas.order_discount import OrderDiscountSummary

        if discount_info and discount_info.get("total_discounts", 0) > 0:
            response_data['discounts'] = OrderDiscountSummary(
                total_discounts=discount_info["total_discounts"],
                total_discount_amount=discount_info["total_discount_amount"],
                discount_breakdown=discount_info["discount_breakdown"],
                savings_percentage=discount_info["savings_percentage"]
            )
        else:
            response_data['discounts'] = None

        response_data['original_subtotal'] = discount_info.get("original_subtotal", new_order.subtotal)
        response_data['total_savings'] = discount_info.get("total_savings", Decimal('0.00'))

        # Crear la respuesta de la orden
        order_response = OrderResponse.model_validate(response_data)
        
        # Limpiar el carrito SOLO después de que TODO el proceso sea exitoso
        # Hacer commit explícito y expunge para evitar problemas de sesión
        try:
            # Almacenar user_id ANTES de expunge_all() para evitar error de sesión
            user_id = current_user.id
            
            db.commit()  # Asegurar que todo esté confirmado
            db.expunge_all()  # Desconectar objetos de la sesión
            
            cart_service = CartService(db)
            cart_service.clear_cart(user_id)  # Usar user_id almacenado
        except Exception as cart_error:
            # Log pero no fallar si no se puede limpiar el carrito
            logger.warning(
                "No se pudo limpiar el carrito tras crear la orden",
                extra={
                    "user_id": current_user.id,
                    "order_id": order_response.id if hasattr(order_response, "id") else None,
                    "error": str(cart_error),
                },
            )
        
        return order_response
    except Exception as e:
        log_error(
            logger,
            e,
            context={
                "user_id": current_user.id,
                "endpoint": "create_order",
            },
        )
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/checkout/preview", response_model=CheckoutPreviewResponse, summary="Preview checkout totals")
async def preview_checkout(
    preview_data: CheckoutPreviewRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    🧮 **Preview de checkout**: Calcula el desglose completo de costos (productos + envío + impuestos) 
    antes de crear la orden. Permite al usuario ver el total real que pagará.
    """
    try:
        order_service = OrderService(db)
        totals = await order_service.calculate_checkout_totals(
            user_id=current_user.id,
            shipping_address_id=preview_data.shipping_address_id,
            payment_currency=preview_data.payment_currency
        )
        return CheckoutPreviewResponse(**totals)
    except Exception as e:
        log_error(
            logger,
            e,
            context={
                "user_id": current_user.id,
                "endpoint": "preview_checkout",
            },
        )
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/orders", response_model=List[OrderSummary], summary="Get user's order history")
async def get_user_orders(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    📦 **Mis órdenes**: Obtiene un listado de todas las órdenes del usuario.
    Incluye información de descuentos aplicados.
    """
    order_service = OrderService(db)
    orders = await order_service.get_user_orders(current_user.id)
    
    # Agregar información de descuentos a cada orden
    for order in orders:
        discount_info = order_service._calculate_order_discount_info(order)
        order.total_savings = discount_info["total_savings"]
        order.has_discounts = discount_info["total_discounts"] > 0
    
    return orders

@router.get("/orders/{order_id}", response_model=OrderResponse, summary="Get order details")
async def get_order_detail(
    order_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    📋 **Detalle de orden**: Obtiene información detallada de una orden específica.
    Incluye información completa de descuentos aplicados.
    """
    order_service = OrderService(db)
    order = order_service.get_order_by_id(order_id, current_user.id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    
    # Calcular información de descuentos
    discount_info = order_service._calculate_order_discount_info(order)
    
    # Manually construct the response data to match the OrderResponse schema.
    response_data = order.__dict__
    response_data['items'] = order.items
    response_data['shipping_address'] = order.shipping_address
    response_data['item_count'] = len(order.items)
    
    from app.schemas.order_discount import OrderDiscountSummary

    if discount_info and discount_info.get("total_discounts", 0) > 0:
        response_data['discounts'] = OrderDiscountSummary(
            total_discounts=discount_info["total_discounts"],
            total_discount_amount=discount_info["total_discount_amount"],
            discount_breakdown=discount_info["discount_breakdown"],
            savings_percentage=discount_info["savings_percentage"]
        )
    else:
        response_data['discounts'] = None

    response_data['original_subtotal'] = discount_info.get("original_subtotal", order.subtotal)
    response_data['total_savings'] = discount_info.get("total_savings", Decimal('0.00'))

    order_response = OrderResponse.model_validate(response_data)
    
    return order_response

@router.get("/orders/discounts/stats", summary="Get user's discount statistics")
async def get_user_discount_stats(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    💰 **Estadísticas de descuentos**: Obtiene estadísticas de descuentos del usuario.
    """
    order_service = OrderService(db)
    orders = await order_service.get_user_orders(current_user.id)
    
    # Calcular estadísticas de descuentos
    total_orders = len(orders)
    orders_with_discounts = 0
    total_savings = Decimal('0.00')
    discount_breakdown = {}
    
    for order in orders:
        discount_info = order_service._calculate_order_discount_info(order)
        
        if discount_info["total_discounts"] > 0:
            orders_with_discounts += 1
            total_savings += discount_info["total_savings"]
            
            # Contar tipos de descuentos
            for discount in order.discounts:
                discount_type = discount.discount_type.value
                if discount_type not in discount_breakdown:
                    discount_breakdown[discount_type] = {
                        "count": 0,
                        "total_amount": Decimal('0.00')
                    }
                discount_breakdown[discount_type]["count"] += 1
                discount_breakdown[discount_type]["total_amount"] += discount.discount_amount
    
    # Calcular porcentajes
    discount_usage_percentage = (orders_with_discounts / total_orders * 100) if total_orders > 0 else 0
    average_savings_per_order = (total_savings / orders_with_discounts) if orders_with_discounts > 0 else Decimal('0.00')
    
    return {
        "total_orders": total_orders,
        "orders_with_discounts": orders_with_discounts,
        "discount_usage_percentage": round(discount_usage_percentage, 2),
        "total_savings": total_savings,
        "average_savings_per_order": average_savings_per_order,
        "discount_breakdown": discount_breakdown,
        "most_used_discount_type": max(discount_breakdown.keys(), key=lambda k: discount_breakdown[k]["count"]) if discount_breakdown else None
    }

# =============================================================================
# DIRECCIONES DE ENVÍO
# =============================================================================

@router.post("/addresses", response_model=AddressResponse, status_code=status.HTTP_201_CREATED)
def create_address(
    address_data: AddressCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    **Crear nueva dirección**: Añade una nueva dirección de envío para el usuario.
    """
    if address_data.is_default:
        # Si esta se marca como predeterminada, quitar la marca de las otras
        db.query(Address).filter(Address.user_id == current_user.id).update({Address.is_default: False})
    
    new_address = Address(**address_data.model_dump(), user_id=current_user.id)
    db.add(new_address)
    db.commit()
    db.refresh(new_address)
    return new_address

@router.get("/addresses")
async def get_addresses(
    include_checkout_preview: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    **Mis direcciones**: Obtiene todas las direcciones de envío del usuario.
    
    Args:
        include_checkout_preview: Si True, incluye cálculo de costos para cada dirección
    """
    # 1. Obtener direcciones del usuario
    addresses = db.query(Address).filter(Address.user_id == current_user.id).all()
    
    if not include_checkout_preview:
        return {"addresses": addresses}
    
    # 2. Validar y obtener carrito
    cart_service = CartService(db)
    cart = cart_service.get_user_cart(current_user.id)
    
    if not cart or cart.total == 0:
        return {
            "addresses": addresses,
            "checkout_preview": None,
            "message": "Carrito vacío - no se puede calcular preview de costos"
        }
    
    # 3. Validar que el carrito tenga productos disponibles
    cart_items = db.query(CartItem).options(joinedload(CartItem.product)).filter(CartItem.user_id == current_user.id).all()
    
    unavailable_products = []
    for item in cart_items:
        product = item.product
        if not product or not product.is_available or product.stock < item.quantity:
            unavailable_products.append({
                "product_name": product.name if product else "Producto no encontrado",
                "required_quantity": item.quantity,
                "available_stock": product.stock if product else 0
            })
    
    if unavailable_products:
        return {
            "addresses": addresses,
            "checkout_preview": None,
            "message": "Algunos productos no están disponibles",
            "unavailable_products": unavailable_products
        }
    
    # 4. Calcular preview para cada dirección
    order_service = OrderService(db)
    checkout_previews = {}
    
    for address in addresses:
        try:
            # Calcular totales usando el servicio existente
            preview = await order_service.calculate_checkout_totals(
                user_id=current_user.id,
                shipping_address_id=address.id,
                payment_currency="USD"
            )
            
            # Obtener información de descuentos del carrito
            cart_items = db.query(CartItem).options(joinedload(CartItem.product)).filter(CartItem.user_id == current_user.id).all()
            discount_service = DiscountService(db)
            discounts_info = discount_service.calculate_cart_discounts(cart_items)
            
            # Calcular precios originales y con descuento
            original_subtotal = float(discounts_info.get('subtotal_original', preview['subtotal']))
            discounted_subtotal = float(preview['subtotal'])
            shipping_cost = float(preview['shipping_cost'])
            
            # Calcular impuestos correctamente
            original_taxes = float(original_subtotal * 0.16)  # Impuestos sobre subtotal original
            discounted_taxes = float(discounted_subtotal * 0.16)  # Impuestos sobre subtotal con descuento
            
            # Calcular totales
            original_total = float(original_subtotal + original_taxes + shipping_cost)
            discounted_total = float(discounted_subtotal + discounted_taxes + shipping_cost)
            
            # Calcular ahorro del descuento (SOLO en productos)
            product_savings = original_subtotal - discounted_subtotal
            tax_savings = original_taxes - discounted_taxes  # Diferencia en impuestos (no es ahorro del descuento)
            total_savings = product_savings  # El ahorro real es SOLO el descuento en productos
            
            checkout_previews[address.id] = {
                # Precios originales (sin descuentos) - SOLO PRODUCTOS + IMPUESTOS + ENVÍO
                "original_subtotal": original_subtotal,
                "original_taxes": original_taxes,
                "original_total": original_total,
                
                # Precios finales (con descuentos)
                "subtotal": discounted_subtotal,
                "shipping_cost": shipping_cost,
                "taxes": discounted_taxes,  # Usar impuestos calculados correctamente
                "total": discounted_total,  # Usar total calculado correctamente
                
                # Información detallada de ahorro
                "product_savings": product_savings,  # Descuento aplicado en productos
                "tax_savings": tax_savings,  # Diferencia en impuestos (consecuencia del descuento)
                "total_savings": total_savings,  # Descuento real (solo productos)
                "savings_percentage": round((product_savings / original_subtotal * 100), 2) if original_subtotal > 0 else 0,
                
                # Información de envío y moneda
                "shipping_zone": preview['shipping_zone'],
                "payment_currency": preview['payment_currency'],
                "exchange_rate": float(preview['exchange_rate']) if preview['exchange_rate'] else None,
                
                # Información detallada de descuentos
                "quantity_discount": preview.get('quantity_discount'),
                "quantity_discount_amount": float(preview.get('quantity_discount_amount', 0)),
                "flash_discounts": preview.get('flash_discounts', []),
                "total_discount": float(preview.get('total_discount', 0))
            }
            
        except HTTPException as e:
            # Error específico (dirección no válida, etc.)
            cart_total = float(cart.total)
            original_taxes = float(cart_total * 0.16)
            original_total = float(cart_total + original_taxes)
            
            checkout_previews[address.id] = {
                "error": e.detail,
                # Precios originales (sin descuentos)
                "original_subtotal": cart_total,
                "original_taxes": original_taxes,
                "original_total": original_total,
                # Precios finales (sin descuentos en caso de error)
                "subtotal": cart_total,
                "shipping_cost": 0,
                "taxes": original_taxes,
                "total": original_total,
                # Información de ahorro (sin ahorro en caso de error)
                "product_savings": 0,
                "tax_savings": 0,
                "total_savings": 0,
                "savings_percentage": 0,
                # Información de envío y moneda
                "shipping_zone": "error",
                "payment_currency": "USD",
                "exchange_rate": None,
                # Información de descuentos (sin descuentos en caso de error)
                "quantity_discount": None,
                "quantity_discount_amount": 0,
                "flash_discounts": [],
                "total_discount": 0
            }
        except Exception as e:
            # Error inesperado
            cart_total = float(cart.total)
            original_taxes = float(cart_total * 0.16)
            original_total = float(cart_total + original_taxes)
            
            checkout_previews[address.id] = {
                "error": f"Error calculando costos: {str(e)}",
                # Precios originales (sin descuentos) - SOLO PRODUCTOS + IMPUESTOS
                "original_subtotal": cart_total,
                "original_taxes": original_taxes,
                "original_total": original_total,
                # Precios finales (sin descuentos en caso de error)
                "subtotal": cart_total,
                "shipping_cost": 0,
                "taxes": original_taxes,
                "total": original_total,
                # Información de ahorro (sin ahorro en caso de error)
                "product_savings": 0,
                "tax_savings": 0,
                "total_savings": 0,
                "savings_percentage": 0,
                # Información de envío y moneda
                "shipping_zone": "error",
                "payment_currency": "USD",
                "exchange_rate": None,
                # Información de descuentos (sin descuentos en caso de error)
                "quantity_discount": None,
                "quantity_discount_amount": 0,
                "flash_discounts": [],
                "total_discount": 0
            }
    
    # 5. Calcular resumen general
    valid_previews = {k: v for k, v in checkout_previews.items() if 'error' not in v}
    
    if valid_previews:
        min_total = min(preview['total'] for preview in valid_previews.values())
        max_total = max(preview['total'] for preview in valid_previews.values())
        avg_total = sum(preview['total'] for preview in valid_previews.values()) / len(valid_previews)
    else:
        min_total = max_total = avg_total = 0
    
    # Calcular resumen de precios originales
    if valid_previews:
        original_totals = [preview['original_total'] for preview in valid_previews.values()]
        min_original = min(original_totals)
        max_original = max(original_totals)
        avg_original = sum(original_totals) / len(original_totals)
        
        # Calcular ahorro promedio
        savings = [preview['total_savings'] for preview in valid_previews.values()]
        avg_savings = sum(savings) / len(savings) if savings else 0
    else:
        min_original = max_original = avg_original = avg_savings = 0

    cart_total = float(cart.total)
    original_taxes = float(cart_total * 0.16)
    original_total = float(cart_total + original_taxes)
    
    return {
        "addresses": addresses,
        "checkout_preview": {
            # Precios originales (sin descuentos) - SOLO PRODUCTOS + IMPUESTOS
            "original_subtotal": cart_total,
            "original_taxes": original_taxes,
            "original_total": original_total,
            
            # Precios finales (con descuentos)
            "subtotal": cart_total,  # Este será actualizado por el primer preview válido
            "tax_rate": 0.16,
            "previews_by_address": checkout_previews,
            
            # Resumen general
            "summary": {
                # Totales originales
                "min_original_total": min_original,
                "max_original_total": max_original,
                "avg_original_total": round(avg_original, 2),
                
                # Totales con descuentos
                "min_total": min_total,
                "max_total": max_total,
                "avg_total": round(avg_total, 2),
                
                # Ahorro promedio
                "avg_savings": round(avg_savings, 2),
                "avg_savings_percentage": round((avg_savings / avg_original * 100), 2) if avg_original > 0 else 0,
                
                # Información de direcciones
                "total_addresses": len(addresses),
                "valid_addresses": len(valid_previews)
            }
        }
    }

@router.put("/addresses/{address_id}", response_model=AddressResponse)
def update_address(
    address_id: str,
    address_data: AddressUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    **Actualizar dirección**: Modifica una dirección de envío existente.
    """
    address = db.query(Address).filter(Address.id == address_id, Address.user_id == current_user.id).first()
    if not address:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")

    if address_data.is_default:
        # Si esta se marca como predeterminada, quitar la marca de las otras
        db.query(Address).filter(Address.user_id == current_user.id).update({Address.is_default: False})

    update_data = address_data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(address, key, value)
    
    db.commit()
    db.refresh(address)
    return address

@router.delete("/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_address(
    address_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    **Eliminar dirección**: Elimina una dirección de envío.
    """
    address = db.query(Address).filter(Address.id == address_id, Address.user_id == current_user.id).first()
    if not address:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
    
    db.delete(address)
    db.commit()
    return

@router.post("/addresses/{address_id}/set-default", response_model=AddressResponse)
def set_default_address(
    address_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    **Marcar como predeterminada**: Establece una dirección como la de envío por defecto.
    """
    address = db.query(Address).filter(Address.id == address_id, Address.user_id == current_user.id).first()
    if not address:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")

    # Quitar la marca de predeterminada de cualquier otra dirección
    db.query(Address).filter(Address.user_id == current_user.id).update({Address.is_default: False})
    
    # Marcar la nueva como predeterminada
    address.is_default = True
    db.commit()
    db.refresh(address)
    return address

@router.get("/stats", response_model=UserStats, summary="Obtiene estadísticas del usuario")
async def get_user_stats(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    **Estadísticas del usuario**: Obtiene estadísticas del usuario desde source_system (DEMOA).
    Incluye total de órdenes, total gastado y total de productos comprados.
    """
    user_service = UserService(db)
    return user_service.get_user_stats_by_id(current_user.id, user_email=current_user.email)

# =============================================================================
# FACTURAS DEMOA
# =============================================================================

@router.get("/invoices/summary", response_model=DEMOAInvoiceSummary)
async def get_invoices_summary(
    current_user: User = Depends(get_current_active_user)
):
    """
    📊 **Resumen de Facturas**: Obtiene un resumen de facturas del usuario
    desde el sistema DEMOA.
    """
    demoa_service = DEMOAInvoiceService()
    
    # Obtener código de cliente en DEMOA
    customer_code = demoa_service.get_customer_code_by_email(current_user.email)
    
    if not customer_code:
        return DEMOAInvoiceSummary(
            total_invoices=0,
            pending_invoices=0,
            paid_invoices=0,
            total_pending_amount=Decimal('0.00'),
            total_invoiced=Decimal('0.00')
        )
    
    # Obtener resumen
    summary = demoa_service.get_invoices_summary(customer_code)
    return DEMOAInvoiceSummary(**summary)

@router.get("/invoices", response_model=List[DEMOAInvoiceResponse])
async def get_all_invoices(
    status_filter: Optional[str] = Query(None, description="Filtrar por estado: 'pending', 'paid', 'all'"),
    current_user: User = Depends(get_current_active_user)
):
    """
    📄 **Mis Facturas**: Obtiene todas las facturas del usuario desde DEMOA.
    
    Filtros disponibles:
    - `pending`: Solo facturas pendientes
    - `paid`: Solo facturas pagadas
    - `all` o sin filtro: Todas las facturas
    """
    demoa_service = DEMOAInvoiceService()
    customer_code = demoa_service.get_customer_code_by_email(current_user.email)
    
    if not customer_code:
        return []
    
    if status_filter == 'pending':
        invoices = demoa_service.get_pending_invoices(customer_code)
    elif status_filter == 'paid':
        invoices = demoa_service.get_paid_invoices(customer_code)
    else:
        invoices = demoa_service.get_all_invoices(customer_code)
    
    # Convertir a respuesta
    return [DEMOAInvoiceResponse(**inv) for inv in invoices]

@router.get("/invoices/pending", response_model=List[DEMOAInvoiceResponse])
async def get_pending_invoices(
    current_user: User = Depends(get_current_active_user)
):
    """
    ⏳ **Facturas Pendientes**: Obtiene facturas con pago pendiente.
    """
    demoa_service = DEMOAInvoiceService()
    customer_code = demoa_service.get_customer_code_by_email(current_user.email)
    
    if not customer_code:
        return []
    
    invoices = demoa_service.get_pending_invoices(customer_code)
    return [DEMOAInvoiceResponse(**inv) for inv in invoices]

@router.get("/invoices/paid", response_model=List[DEMOAInvoiceResponse])
async def get_paid_invoices(
    current_user: User = Depends(get_current_active_user)
):
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
async def get_invoice_details(
    invoice_number: str,
    current_user: User = Depends(get_current_active_user)
):
    """
    📋 **Detalles de Factura**: Obtiene detalles completos de una factura,
    incluyendo items y productos.
    """
    demoa_service = DEMOAInvoiceService()
    customer_code = demoa_service.get_customer_code_by_email(current_user.email)
    
    if not customer_code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado en DEMOA"
        )
    
    invoice = demoa_service.get_invoice_details(invoice_number, customer_code)
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Factura no encontrada o no pertenece al usuario"
        )
    
    return DEMOAInvoiceDetails(**invoice)

@router.get("/invoices/payments", response_model=List[DEMOAPaymentResponse])
async def get_payment_history(
    current_user: User = Depends(get_current_active_user)
):
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
async def get_customer_addresses(
    current_user: User = Depends(get_current_active_user)
):
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
    
    if not customer or not customer.get('customer_code'):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado en Profit Plus"
        )
    
    customer_code = customer.get('customer_code')
    
    # Obtener direcciones desde Profit Plus
    addresses = source_system_service.get_customer_addresses(customer_code)
    
    return CustomerAddressesResponse(
        customer_code=customer_code,
        addresses=addresses
    )