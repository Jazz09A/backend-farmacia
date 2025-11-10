from fastapi import APIRouter, Depends, Header, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.config.database import get_db
from app.core.dependencies import get_current_active_user
from app.models.user import User
from app.schemas.quote import (
    QuoteCreate,
    QuoteCreatedResponse,
    QuoteListResponse,
    QuoteDetailResponse,
)
from app.services.quote_service import QuoteService

# Router for /api/v1/quotes
router = APIRouter()


@router.post("/", response_model=QuoteCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_quote(
    data: QuoteCreate,
    x_source_system: str = Header(..., alias="X-Source-System"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Create a new Quote in Profit Plus from the user's checkout/cart.
    Also sends a confirmation email with the quote.
    """
    try:
        service = QuoteService(db)
        created = service.create_quote(current_user.id, data, x_source_system)
        return created
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo registrar la cotización en Profit Plus",
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
    print(
        f"[quotes] list_user_quotes user_id={current_user.id} "
        f"email={current_user.email} source_system={x_source_system} "
        f"status={status} from_date={from_date} to_date={to_date} "
        f"page={page} page_size={page_size}"
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
    print(
        f"[quotes] list_user_quotes success user_id={current_user.id} "
        f"total_items={result.pagination.total_items}"
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
