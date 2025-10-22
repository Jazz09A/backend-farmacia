from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from typing import List

from app.config.database import get_db
from app.core.dependencies import get_current_active_user, get_admin_user
from app.models.user import User
from app.schemas.credit import (
    CreditInfo, CreditPaymentCreate, CreditPaymentResponse, 
    PaymentApproval, CreditOrderCreate, CreditDashboard, CreditOrderResponse
)
from app.services.credit_service import CreditService
from app.services.credit_payment_service import CreditPaymentService

router = APIRouter()

# =============================================================================
# ENDPOINTS DE USUARIO
# =============================================================================

@router.get("/credit/info", response_model=CreditInfo)
async def get_credit_info(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtener información de crédito del usuario"""
    credit_service = CreditService(db)
    return credit_service.get_user_credit(current_user.id)

@router.post("/orders/credit", response_model=dict)
async def create_credit_order(
    order_data: CreditOrderCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Crear orden con crédito"""
    credit_service = CreditService(db)
    
    # Preparar datos para la orden
    order_data_dict = {
        "shipping_address_id": order_data.shipping_address_id,
        "customer_notes": order_data.customer_notes,
        "total": 0  # Se calculará en el servicio
    }
    
    try:
        order = await credit_service.create_credit_order(current_user.id, order_data_dict)
        return {
            "message": "Orden de crédito creada exitosamente",
            "order_id": order.id,
            "order_number": order.order_number,
            "total": order.total,
            "credit_remaining": order.credit_remaining
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/payments", response_model=CreditPaymentResponse)
async def create_payment(
    payment_data: CreditPaymentCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Crear un pago parcial para una orden"""
    payment_service = CreditPaymentService(db)
    
    try:
        payment = await payment_service.create_payment(
            current_user.id, 
            payment_data.order_id, 
            payment_data.dict()
        )
        return payment
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/orders/{order_id}/payments", response_model=List[CreditPaymentResponse])
async def get_order_payments(
    order_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtener todos los pagos de una orden"""
    payment_service = CreditPaymentService(db)
    
    # Verificar que la orden pertenece al usuario
    from app.models.order import Order
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.user_id == current_user.id
    ).first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    
    return payment_service.get_order_payments(order_id)

@router.get("/orders/credit", response_model=List[CreditOrderResponse])
async def get_credit_orders(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtener todas las órdenes con crédito del usuario"""
    from app.models.order import Order
    from sqlalchemy.orm import joinedload
    
    # Obtener órdenes con crédito del usuario
    from sqlalchemy import or_

    # Construir condiciones dinámicas según columnas disponibles
    credit_conditions = [Order.payment_method == "credit"]
    if hasattr(Order, "is_credit_order"):
        credit_conditions.append(Order.is_credit_order == True)
    if hasattr(Order, "is_credit"):
        credit_conditions.append(getattr(Order, "is_credit") == True)

    credit_orders = db.query(Order).options(
        joinedload(Order.items),
        joinedload(Order.shipping_address),
        joinedload(Order.credit_payments)
    ).filter(
        Order.user_id == current_user.id,
        or_(*credit_conditions)
    ).order_by(Order.created_at.desc()).all()
    
    # Convertir a schema de respuesta
    return [CreditOrderResponse.model_validate(order) for order in credit_orders]

@router.get("/orders/credit/{order_id}", response_model=CreditOrderResponse)
async def get_credit_order_by_id(
    order_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtener una orden específica con crédito del usuario"""
    from app.models.order import Order
    from sqlalchemy.orm import joinedload
    
    # Obtener la orden con crédito del usuario
    from sqlalchemy import or_

    credit_conditions = [Order.payment_method == "credit"]
    if hasattr(Order, "is_credit_order"):
        credit_conditions.append(Order.is_credit_order == True)
    if hasattr(Order, "is_credit"):
        credit_conditions.append(getattr(Order, "is_credit") == True)

    credit_order = db.query(Order).options(
        joinedload(Order.items),
        joinedload(Order.shipping_address),
        joinedload(Order.credit_payments)
    ).filter(
        Order.id == order_id,
        Order.user_id == current_user.id,
        or_(*credit_conditions)
    ).first()
    
    if not credit_order:
        raise HTTPException(
            status_code=404, 
            detail="Orden con crédito no encontrada"
        )
    
    return CreditOrderResponse.model_validate(credit_order)

@router.get("/payments/my-payments", response_model=List[CreditPaymentResponse])
async def get_my_payments(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtener todos mis pagos"""
    payment_service = CreditPaymentService(db)
    return payment_service.get_user_payments(current_user.id)

@router.get("/credit/dashboard", response_model=CreditDashboard)
async def get_credit_dashboard(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Dashboard de crédito para usuario"""
    from app.services.dashboard_service import get_user_credit_dashboard
    
    dashboard_data = get_user_credit_dashboard(current_user.id, db)
    return dashboard_data

# =============================================================================
# ENDPOINTS DE ADMIN
# =============================================================================

@router.post("/admin/users/{user_id}/assign-credit")
async def assign_credit(
    user_id: str,
    amount: float,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Asignar crédito a un usuario (solo admin)"""
    credit_service = CreditService(db)
    
    if amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")
    
    success = credit_service.assign_credit(user_id, amount)
    if success:
        return {"message": f"Crédito de {amount} asignado exitosamente"}
    raise HTTPException(status_code=400, detail="Error al asignar crédito")

@router.get("/admin/credit/payments/pending", response_model=List[CreditPaymentResponse])
async def get_pending_payments(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Obtener pagos pendientes de aprobación"""
    payment_service = CreditPaymentService(db)
    return payment_service.get_pending_payments()

@router.post("/admin/credit/payments/{payment_id}/approve")
async def approve_payment(
    payment_id: str,
    approval_data: PaymentApproval,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Aprobar o rechazar un pago"""
    payment_service = CreditPaymentService(db)
    
    if approval_data.action == "approve":
        success = payment_service.approve_payment(
            payment_id, 
            current_user.id, 
            approval_data.admin_notes
        )
    else:
        success = payment_service.reject_payment(
            payment_id, 
            current_user.id, 
            approval_data.admin_notes
        )
    
    if success:
        return {"message": f"Pago {approval_data.action} exitosamente"}
    raise HTTPException(status_code=400, detail="Error al procesar la solicitud")

@router.get("/admin/credit/dashboard")
async def get_admin_credit_dashboard(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Dashboard de crédito para admin"""
    from app.services.dashboard_service import get_credit_payments_dashboard
    
    dashboard_data = get_credit_payments_dashboard(db)
    return dashboard_data

@router.get("/admin/credit/payments", response_model=List[CreditPaymentResponse])
async def admin_list_credit_payments(
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    order_id: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Listar pagos de crédito con filtros opcionales (solo admin)."""
    from decimal import Decimal

    payment_service = CreditPaymentService(db)

    payments = payment_service.get_payments_filtered(
        status=status,
        user_id=user_id,
        order_id=order_id,
        min_amount=Decimal(str(min_amount)) if min_amount is not None else None,
        max_amount=Decimal(str(max_amount)) if max_amount is not None else None,
        start_date=start_date,
        end_date=end_date,
    )

    return payments

@router.get("/admin/payment/{payment_id}/details")
async def get_payment_details(
    payment_id: str,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Detalles de un pago específico"""
    from app.services.dashboard_service import get_payment_details
    
    details = get_payment_details(payment_id, db)
    if not details:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    return details
