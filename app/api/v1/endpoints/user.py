"""
Endpoints protegidos para usuarios autenticados.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.core.dependencies import get_current_active_user
from app.models.user import User
from app.models.cart import CartItem
from app.models.order import Order
from app.schemas.user import UserResponse, UserUpdate
from app.schemas.cart import CartResponse, CartItemCreate, CartItemUpdate
# from app.schemas.order import OrderResponse, OrderCreate
from app.services.cart_service import CartService

router = APIRouter(prefix="/user", tags=["User Protected"])

# =============================================================================
# PERFIL DE USUARIO
# =============================================================================

@router.get("/profile", response_model=UserResponse)
async def get_user_profile(
    current_user: User = Depends(get_current_active_user)
):
    """
    👤 **Mi perfil**
    
    Obtiene información del perfil del usuario actual.
    Requiere autenticación.
    """
    return UserResponse.model_validate(current_user)

@router.put("/profile", response_model=UserResponse)
async def update_user_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    ✏️ **Actualizar perfil**
    
    Actualiza la información del perfil del usuario.
    """
    # Actualizar campos permitidos
    for field, value in user_update.dict(exclude_unset=True).items():
        if hasattr(current_user, field):
            setattr(current_user, field, value)
    
    db.commit()
    db.refresh(current_user)
    
    return UserResponse.model_validate(current_user)

@router.post("/change-password")
async def change_password(
    old_password: str,
    new_password: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    🔐 **Cambiar contraseña**
    
    Cambia la contraseña del usuario actual.
    """
    from app.core.security import verify_password, get_password_hash
    
    # Verificar contraseña actual
    if not verify_password(old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contraseña actual incorrecta"
        )
    
    # Actualizar contraseña
    current_user.hashed_password = get_password_hash(new_password)
    db.commit()
    
    return {"message": "Contraseña actualizada exitosamente"}

@router.delete("/account")
async def delete_user_account(
    password: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    🗑️ **Eliminar cuenta**
    
    Elimina permanentemente la cuenta del usuario.
    ⚠️ **ACCIÓN IRREVERSIBLE**
    """
    from app.core.security import verify_password
    
    # Verificar contraseña para confirmación
    if not verify_password(password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contraseña incorrecta"
        )
    
    # Eliminar usuario (esto debería también eliminar datos relacionados)
    db.delete(current_user)
    db.commit()
    
    return {"message": "Cuenta eliminada exitosamente"}

# =============================================================================
# CARRITO DE COMPRAS
# =============================================================================

@router.get("/cart", response_model=CartResponse, summary="Get user's shopping cart")
async def get_user_cart(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    🛒 **Mi carrito**
    
    Obtiene el carrito de compras del usuario actual con todos los detalles y totales.
    """
    cart_service = CartService(db)
    return cart_service.get_user_cart(current_user.id)

@router.post("/cart/add", summary="Add item to cart", response_model=CartResponse)
async def add_to_cart(
    item: CartItemCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> CartResponse:
    """
    Adds a product to the user's shopping cart. If the item already exists,
    the quantity is updated. Otherwise, a new item is created.
    """
    cart_service = CartService(db)
    cart_service.add_item(
        user_id=current_user.id,
        product_id=item.product_id,
        quantity=item.quantity,
        selected_presentation=item.selected_presentation
    )
    
    updated_cart = cart_service.get_user_cart(current_user.id)
    if not updated_cart:
        raise HTTPException(status_code=404, detail="Cart not found after update.")
        
    return updated_cart

@router.put("/cart/item/{item_id}", summary="Update cart item quantity", response_model=CartResponse)
async def update_cart_item(
    item_id: str,
    item_update: CartItemUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> CartResponse:
    """
    Updates the quantity of a specific item in the user's cart.
    """
    cart_service = CartService(db)
    cart_service.update_item_quantity(
        user_id=current_user.id,
        item_id=item_id,
        new_quantity=item_update.quantity
    )
    
    updated_cart = cart_service.get_user_cart(current_user.id)
    if not updated_cart:
        raise HTTPException(status_code=404, detail="Cart not found after update.")
        
    return updated_cart

@router.delete("/cart/item/{item_id}", summary="Remove item from cart", response_model=CartResponse)
async def remove_from_cart(
    item_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> CartResponse:
    """
    Removes a specific item from the user's shopping cart.
    """
    cart_service = CartService(db)
    cart_service.remove_item(user_id=current_user.id, item_id=item_id)
    
    updated_cart = cart_service.get_user_cart(current_user.id)
    return updated_cart

@router.delete("/cart/clear", summary="Clear entire cart", response_model=CartResponse)
async def clear_cart(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> CartResponse:
    """
    Removes all items from the user's shopping cart.
    """
    cart_service = CartService(db)
    cart_service.clear_cart(user_id=current_user.id)
    
    cleared_cart = cart_service.get_user_cart(current_user.id)
    # After clearing, the cart should be empty.
    return cleared_cart

# =============================================================================
# ÓRDENES Y COMPRAS
# =============================================================================

@router.post("/orders")
async def create_order(
    shipping_address_id: str,
    payment_method: str = "cash",
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    📋 **Crear orden**
    
    Crea una nueva orden de compra.
    """
    # Verificar que el carrito no esté vacío
    cart_items = db.query(CartItem).filter(CartItem.user_id == current_user.id).all()
    
    if not cart_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No hay items en el carrito"
        )
    
    # Calcular total
    total = sum(item.quantity * (item.product.price_ves if item.product else 0) for item in cart_items)
    
    # Crear orden
    import uuid
    new_order = Order(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        status="pending",
        total_amount=total,
        payment_method=payment_method
        # ... otros campos según tu modelo
    )
    
    db.add(new_order)
    db.commit()
    db.refresh(new_order)
    
    # Limpiar carrito después de crear orden
    db.query(CartItem).filter(CartItem.user_id == current_user.id).delete()
    db.commit()
    
    return {
        "order_id": new_order.id,
        "total": total,
        "status": new_order.status,
        "message": "Orden creada exitosamente"
    }

@router.get("/orders")
async def get_user_orders(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    📦 **Mis órdenes**
    
    Obtiene todas las órdenes del usuario.
    """
    orders = db.query(Order).filter(Order.user_id == current_user.id).all()
    
    return [
        {
            "id": order.id,
            "status": order.status,
            "total_amount": order.total_amount,
            "created_at": order.created_at,
            "payment_method": getattr(order, 'payment_method', 'cash')
        } for order in orders
    ]

@router.get("/orders/{order_id}")
async def get_order_detail(
    order_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    📋 **Detalle de orden**
    
    Obtiene información detallada de una orden específica.
    """
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.user_id == current_user.id
    ).first()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Orden no encontrada"
        )
    
    return {
        "id": order.id,
        "status": order.status,
        "total_amount": order.total_amount,
        "created_at": order.created_at,
        "payment_method": getattr(order, 'payment_method', 'cash'),
        "items": []  # Aquí deberías incluir los items de la orden
    }

@router.put("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    ❌ **Cancelar orden**
    
    Cancela una orden que esté en estado "pending".
    """
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.user_id == current_user.id
    ).first()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Orden no encontrada"
        )
    
    if order.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se pueden cancelar órdenes pendientes"
        )
    
    order.status = "cancelled"
    db.commit()
    
    return {"message": "Orden cancelada exitosamente"}

# =============================================================================
# CHECKOUT Y PAGOS
# =============================================================================

@router.post("/checkout/calculate")
async def calculate_checkout(
    shipping_zone: str = "caracas",
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    🧮 **Calcular checkout**
    
    Calcula el total del checkout incluyendo envío.
    """
    cart_items = db.query(CartItem).filter(CartItem.user_id == current_user.id).all()
    
    if not cart_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No hay items en el carrito"
        )
    
    subtotal = sum(item.quantity * (item.product.price_ves if item.product else 0) for item in cart_items)
    
    # Calcular envío basado en zona
    shipping_rates = {
        "caracas": 5.00,
        "miranda": 7.50,
        "vargas": 10.00,
        "nacional": 15.00
    }
    
    shipping_cost = shipping_rates.get(shipping_zone, 15.00)
    total = subtotal + shipping_cost
    
    return {
        "subtotal": subtotal,
        "shipping_cost": shipping_cost,
        "total": total,
        "item_count": len(cart_items)
    }

@router.post("/checkout/process")
async def process_checkout(
    payment_method: str = "cash",
    shipping_address_id: str = "default",
    shipping_zone: str = "caracas",
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    💳 **Procesar checkout**
    
    Procesa el checkout y crea la orden final.
    """
    # Verificar carrito
    cart_items = db.query(CartItem).filter(CartItem.user_id == current_user.id).all()
    
    if not cart_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No hay items en el carrito"
        )
    
    # Calcular totales
    subtotal = sum(item.quantity * (item.product.price_ves if item.product else 0) for item in cart_items)
    shipping_rates = {"caracas": 5.00, "miranda": 7.50, "vargas": 10.00, "nacional": 15.00}
    shipping_cost = shipping_rates.get(shipping_zone, 15.00)
    total = subtotal + shipping_cost
    
    # Crear orden
    import uuid
    new_order = Order(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        status="confirmed",
        total_amount=total,
        payment_method=payment_method
    )
    
    db.add(new_order)
    
    # Limpiar carrito
    db.query(CartItem).filter(CartItem.user_id == current_user.id).delete()
    
    db.commit()
    db.refresh(new_order)
    
    return {
        "message": "Checkout procesado exitosamente",
        "order_id": new_order.id,
        "payment_method": payment_method,
        "status": "confirmed",
        "total": total
    }
