from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.config.database import get_db
from app.core.dependencies import get_current_active_user
from app.models.user import User
from app.models.order import Order
from app.schemas.order import OrderCreate, OrderResponse
from app.services.order_service import OrderService

router = APIRouter()

@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    order_data: OrderCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a new order from the user's current cart.
    """
    try:
        order_service = OrderService(db)
        new_order = order_service.create_order_from_cart(current_user.id, order_data)
        
        # Convert to response schema
        return OrderResponse.model_validate(new_order)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating order: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al crear la orden"
        )

@router.get("/", response_model=List[OrderResponse])
async def get_user_orders(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get all orders for the current authenticated user.
    """
    try:
        order_service = OrderService(db)
        orders = order_service.get_user_orders(current_user.id)
        return [OrderResponse.model_validate(order) for order in orders]
        
    except Exception as e:
        print(f"Error getting user orders: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al obtener las órdenes"
        )

@router.get("/{order_id}", response_model=OrderResponse)
async def get_order_by_id(
    order_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific order by ID for the current authenticated user.
    """
    try:
        order_service = OrderService(db)
        order = order_service.get_order_by_id(order_id, current_user.id)
        
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Orden no encontrada"
            )
        
        return OrderResponse.model_validate(order)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting order: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al obtener la orden"
        )

@router.get("/{order_id}/tracking")
async def get_order_tracking(
    order_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get tracking information for a specific order.
    This endpoint returns tracking details and current status.
    """
    try:
        order_service = OrderService(db)
        order = order_service.get_order_by_id(order_id, current_user.id)
        
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Orden no encontrada"
            )
        
        # Prepare tracking information
        tracking_info = {
            "order_id": order.id,
            "order_number": order.order_number,
            "status": order.status,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
            "payment_status": order.payment_status,
            "shipping_address": {
                "street": order.shipping_address.street if order.shipping_address else None,
                "city": order.shipping_address.city if order.shipping_address else None,
                "state": order.shipping_address.state if order.shipping_address else None,
                "recipient_name": order.shipping_address.recipient_name if order.shipping_address else None,
                "recipient_phone": order.shipping_address.recipient_phone if order.shipping_address else None,
            },
            "items": [
                {
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "total_price": item.total_price
                }
                for item in order.items
            ],
            "totals": {
                "subtotal": order.subtotal,
                "shipping_cost": order.shipping_cost,
                "taxes": order.taxes,
                "total": order.total,
                "currency": order.currency
            }
        }
        
        return {
            "success": True,
            "tracking_info": tracking_info,
            "message": "Información de seguimiento obtenida exitosamente"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting order tracking: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al obtener el seguimiento"
        )
