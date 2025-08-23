"""
Endpoints protegidos para usuarios autenticados.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.core.dependencies import get_current_active_user
from app.models.user import User
from app.models.address import Address
from app.schemas.user import UserResponse, UserStats, UserUpdate
from app.schemas.address import AddressResponse, AddressCreate, AddressUpdate
from app.schemas.cart import CartResponse, CartItemCreate, CartItemUpdate
from app.schemas.order import OrderResponse, OrderCreate, OrderSummary
from app.services.cart_service import CartService
from app.services.order_service import OrderService
from app.services.user_service import UserService

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
    cart_service.add_item(
        user_id=current_user.id,
        product_id=item.product_id,
        quantity=item.quantity,
        selected_presentation=item.selected_presentation
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
        new_order = order_service.create_order_from_cart(current_user.id, order_data)
        return new_order
    except Exception as e:
        print(f"Error al crear la orden: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/orders", response_model=List[OrderSummary], summary="Get user's order history")
async def get_user_orders(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    📦 **Mis órdenes**: Obtiene un listado de todas las órdenes del usuario.
    """
    order_service = OrderService(db)
    orders = order_service.get_user_orders(current_user.id)
    return orders

@router.get("/orders/{order_id}", response_model=OrderResponse, summary="Get order details")
async def get_order_detail(
    order_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    📋 **Detalle de orden**: Obtiene información detallada de una orden específica.
    """
    order_service = OrderService(db)
    order = order_service.get_order_by_id(order_id, current_user.id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order

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
    
    new_address = Address(**address_data.dict(), user_id=current_user.id)
    db.add(new_address)
    db.commit()
    db.refresh(new_address)
    return new_address

@router.get("/addresses", response_model=List[AddressResponse])
def get_addresses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    **Mis direcciones**: Obtiene todas las direcciones de envío del usuario.
    """
    return db.query(Address).filter(Address.user_id == current_user.id).all()

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
    **Estadísticas del usuario**: Obtiene estadísticas del usuario.
    """
    user_service = UserService(db)
    return user_service.get_user_stats_by_id(current_user.id)