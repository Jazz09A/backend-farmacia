from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.schemas.dashboard import DashboardData
from app.services.dashboard_service import get_dashboard_data, get_order_by_id, update_order_status, get_all_customers
from app.core.dependencies import get_db, get_current_user
from app.models.user import User
from app.schemas.user import UserResponse
from app.schemas.order import OrderResponse, OrderStatusUpdate, OrderDashboardResponse
from app.services.dashboard_service import get_all_orders as get_all_orders_service

router = APIRouter()

@router.get("/dashboard", response_model=DashboardData)
def read_dashboard_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    days_filter: int = 7
):
    """
    Retrieve all data for the admin dashboard.
    """
    dashboard_data = get_dashboard_data(db, days_filter)
    return dashboard_data

@router.get("/order/{id}", response_model=OrderResponse)
def read_order(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve a single order by its ID.
    """
    order = get_order_by_id(db, id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@router.put("/order/{id}/status", response_model=OrderResponse)
def update_order_status_endpoint(
    id: str,
    status: OrderStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Actualizar el estado de un pedido.
    """
    order = update_order_status(db, id, status.status   )
    return order

@router.get("/orders", response_model=List[OrderDashboardResponse])
def get_all_orders_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Obtener todos los pedidos con información del usuario.
    """
    orders = get_all_orders_service(db)
    orders_with_user = []
    
    for order in orders:
        # Create OrderDashboardResponse manually to ensure all fields are properly mapped
        order_data = {
            'id': order.id,
            'user_id': order.user_id,
            'order_number': order.order_number,
            'status': order.status,
            'subtotal': order.subtotal,
            'shipping_cost': order.shipping_cost,
            'taxes': order.taxes,
            'total': order.total,
            'currency': order.currency,
            'payment_method': order.payment_method,
            'payment_status': order.payment_status,
            'payment_reference': order.payment_reference,
            'tracking_number': order.tracking_number,
            'estimated_delivery': order.estimated_delivery,
            'delivered_at': order.delivered_at,
            'customer_notes': order.customer_notes,
            'created_at': order.created_at,
            'updated_at': order.updated_at,
            'items': order.items if order.items else [],
            'shipping_address': order.shipping_address,
            'item_count': order.item_count,
            'payment_capture_url': order.payment_capture_url,
            'user': order.user.full_name if order.user else "Usuario desconocido"
        }
        orders_with_user.append(OrderDashboardResponse(**order_data))
    
    return orders_with_user

@router.get("/customers", response_model=List[UserResponse])
def get_all_customers_endpoint(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customers = get_all_customers(db)
    return list(customers)