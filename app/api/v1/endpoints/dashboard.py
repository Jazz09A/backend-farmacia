from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.schemas.dashboard import DashboardData
from app.services.dashboard_service import get_dashboard_data, get_order_by_id, update_order_status
from app.core.dependencies import get_db, get_current_user
from app.schemas.order import OrderResponse, OrderStatusUpdate

router = APIRouter()

@router.get("/dashboard", response_model=DashboardData)
def read_dashboard_data(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
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
    current_user: dict = Depends(get_current_user),
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
    current_user: dict = Depends(get_current_user),
):
    """
    Actualizar el estado de un pedido.
    """
    order = update_order_status(db, id, status.status   )
    return order