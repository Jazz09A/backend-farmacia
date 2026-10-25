
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_admin_user, get_current_user, get_db
from app.models.user import User
from app.schemas.dashboard import DashboardData
from app.schemas.quote import QuoteDetailResponse, QuoteListResponse
from app.schemas.user import UserResponse
from app.services.dashboard_service import (
    get_all_customers,
    get_all_quotes_paginated,
    get_dashboard_data,
    get_quote_detail_for_admin,
)

router = APIRouter()

@router.get("/dashboard", response_model=DashboardData)
def read_dashboard_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user),
    time_range: int = Query(7, ge=1, le=365, description="Número de días para el rango de fechas (1-365)")
):
    """
    Retrieve all data for the admin dashboard.
    
    Args:
        time_range: Número de días hacia atrás para calcular las estadísticas (por defecto 7 días)
    """
    dashboard_data = get_dashboard_data(db, days_filter=time_range)
    return dashboard_data

# Endpoints de Order eliminados - Order no se usa con Profit Plus
# Las cotizaciones se manejan a través de /admin/quotes que se conecta directamente a Profit Plus

@router.get("/customers", response_model=list[UserResponse])
def get_all_customers_endpoint(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customers = get_all_customers(db)
    return list(customers)

@router.get("/quotes", response_model=QuoteListResponse)
def get_all_quotes_endpoint(
    page: int = Query(1, ge=1, description="Número de página (empezando en 1)"),
    page_size: int = Query(20, ge=1, le=100, description="Tamaño de página (máximo 100)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Obtiene todas las cotizaciones desde el sistema fuente con paginación.
    Ordenadas por fecha de emisión descendente (más reciente primero).
    """
    return get_all_quotes_paginated(page=page, page_size=page_size, db=db)

@router.get("/quotes/{quote_id}", response_model=QuoteDetailResponse)
def get_quote_detail_endpoint(
    quote_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Obtiene los detalles completos de una cotización específica desde el sistema fuente.
    Solo disponible para administradores autenticados.
    """
    detail = get_quote_detail_for_admin(quote_id=quote_id, db=db)
    if not detail:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    return detail  