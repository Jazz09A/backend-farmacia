from datetime import datetime, timezone, timedelta
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.user import User
from app.models.order import Order
from app.models.order_discount import OrderDiscount
from app.config.logging_config import get_logger
from app.schemas.dashboard import DashboardStats, OrderStatusSummary, RecentOrder, DashboardData, DiscountBreakdown
from app.schemas.order import OrderStatus  # Import from schema, not model
from fastapi import HTTPException
from app.schemas.order import PaymentStatusEnum
from app.schemas.order import UpdatePaymentStatus
from decimal import Decimal

from app.schemas.order_discount import OrderDiscountSummary, OrderDiscountResponse

def _calculate_order_discount_info(order: Order) -> dict:
    """
    Calculates discount information for an order.
    
    Args:
        order: Order with loaded discounts
        
    Returns:
        dict with discount information
    """
    if not order.discounts:
        return {
            "total_discounts": 0,
            "total_discount_amount": Decimal('0.00'),
            "discount_breakdown": [],
            "savings_percentage": 0.0,
            "original_subtotal": order.subtotal,
            "total_savings": Decimal('0.00')
        }
    
    total_discount_amount = sum(discount.discount_amount for discount in order.discounts)
    original_subtotal = order.subtotal + total_discount_amount
    savings_percentage = (total_discount_amount / original_subtotal * 100) if original_subtotal > 0 else 0.0
    
    discount_breakdown = [
        OrderDiscountResponse.model_validate(discount) for discount in order.discounts
    ]
    
    return {
        "total_discounts": len(order.discounts),
        "total_discount_amount": total_discount_amount,
        "discount_breakdown": discount_breakdown,
        "savings_percentage": round(float(savings_percentage), 2),
        "original_subtotal": original_subtotal,
        "total_savings": total_discount_amount
    }

def get_dashboard_data(db: Session, days_filter: int = 7) -> DashboardData:
    """
    Retrieves and computes all data required for the admin dashboard.
    """
    perf_logger = get_logger("performance")
    error_logger = get_logger("errors")
    
    perf_logger.info(
        f"Dashboard data calculation started",
        extra={
            'days_filter': days_filter, 
            'event': 'dashboard_calculation_started',
            'user_email': 'admin@farmaplus.com'  # Dashboard es accedido por admin
        }
    )
    
    # 1. Calculate date range for filtering
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days_filter)

    # 2. Basic Stats
    total_revenue_query = db.query(func.sum(Order.total)).filter(
    Order.created_at >= start_date,
    Order.status.in_(['pending', 'confirmed', 'processing', 'shipped', 'delivered'])
    ).scalar() or Decimal('0.00')
    
    total_orders = db.query(Order).filter(Order.created_at >= start_date).count()
    new_customers = db.query(User).filter(User.created_at >= start_date).count()
    
    # Placeholder for conversion rate logic
    conversion_rate = Decimal('0.00') 
    
    # 2.1. Calculate discount statistics
    total_discounts_given = db.query(func.sum(OrderDiscount.discount_amount)).filter(
        OrderDiscount.created_at >= start_date
    ).scalar() or Decimal('0.00')
    
    orders_with_discounts = db.query(func.count(func.distinct(OrderDiscount.order_id))).filter(
        OrderDiscount.created_at >= start_date
    ).scalar() or 0
    
    discount_usage_percentage = (orders_with_discounts / total_orders * 100) if total_orders > 0 else 0.0
    average_discount_per_order = (total_discounts_given / orders_with_discounts) if orders_with_discounts > 0 else Decimal('0.00')
    
    # Calculate discount breakdown by type
    discount_type_counts = db.query(
        OrderDiscount.discount_type, 
        func.count(OrderDiscount.id),
        func.sum(OrderDiscount.discount_amount)
    ).filter(
        OrderDiscount.created_at >= start_date
    ).group_by(OrderDiscount.discount_type).all()
    
    discount_breakdown = DiscountBreakdown()
    total_amount_by_type = {}
    
    for discount_type, count, total_amount in discount_type_counts:
        type_name = discount_type.value
        total_amount_by_type[type_name] = total_amount or Decimal('0.00')
        
        if type_name == 'quantity':
            discount_breakdown.quantity_discounts = count
        elif type_name == 'flash':
            discount_breakdown.flash_discounts = count
        elif type_name == 'coupon':
            discount_breakdown.coupon_discounts = count
        elif type_name == 'promotional':
            discount_breakdown.promotional_discounts = count
    
    discount_breakdown.total_amount_by_type = total_amount_by_type

    stats = DashboardStats(
        total_revenue=total_revenue_query,
        total_orders=total_orders,
        new_customers=new_customers,
        conversion_rate=conversion_rate,
        total_discounts_given=total_discounts_given,
        orders_with_discounts=orders_with_discounts,
        discount_usage_percentage=round(discount_usage_percentage, 2),
        average_discount_per_order=average_discount_per_order,
    )

    # 3. Order Status Summary
    # Using a more efficient single query with GROUP BY
    status_counts = db.query(Order.status, func.count(Order.id)).group_by(Order.status).all()
    status_map = dict(status_counts)

    order_status_summary = OrderStatusSummary(
        pending=status_map.get('pending', 0),
        confirmed=status_map.get('confirmed', 0),
        processing=status_map.get('processing', 0),
        shipped=status_map.get('shipped', 0),
        delivered=status_map.get('delivered', 0),
        cancelled=status_map.get('cancelled', 0),
    )

    # 4. Recent Orders
    recent_orders_query = db.query(Order).order_by(Order.created_at.desc()).limit(5).all()
    
    recent_orders = [
        RecentOrder(
            id=str(order.id),
            customer_name=order.user.full_name, # Using the model property
            date=order.created_at.strftime("%Y-%m-%d"),
            total=order.total,
            status=order.status,
        ) for order in recent_orders_query
    ]

    perf_logger.info(
        f"Dashboard data calculated successfully",
        extra={
            'days_filter': days_filter,
            'total_revenue': total_revenue_query,
            'total_orders': total_orders,
            'new_customers': new_customers,
            'conversion_rate': conversion_rate,
            'status_counts': len(status_counts),
            'recent_orders_count': len(recent_orders),
            'event': 'dashboard_calculation_completed',
            'user_email': 'admin@farmaplus.com'  # Dashboard es accedido por admin
        }
    )

    return DashboardData(
        stats=stats,
        order_status_summary=order_status_summary,
        recent_orders=recent_orders,
        discount_breakdown=discount_breakdown,
    ) 
    
def get_order_by_id(db: Session, id: str) -> Order:
    return db.query(Order).filter(Order.id == id).first()


def update_order_status(db: Session, id: str, status: str) -> Order:
    order = db.query(Order).filter(Order.id == id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Validate status against the schema enum (English values)
    valid_statuses = [status.value for status in OrderStatus]
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid status. Valid statuses are: {valid_statuses}"
        )
    
    order.status = status
    db.commit()
    db.refresh(order)
    
    # Manually construct the response to match OrderResponse schema
    discount_info = _calculate_order_discount_info(order)
    
    response_data = order.__dict__
    response_data['items'] = order.items
    response_data['shipping_address'] = order.shipping_address
    response_data['item_count'] = len(order.items)
    # Formatear exchange_rate a 2 decimales
    if response_data.get('exchange_rate'):
        response_data['exchange_rate'] = response_data['exchange_rate'].quantize(Decimal('0.01'))
    
    if discount_info and discount_info["total_discounts"] > 0:
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
    
    from app.schemas.order import OrderResponse
    return OrderResponse.model_validate(response_data)

def get_orders_by_status(db: Session, status: str) -> List[Order]:
    orders = db.query(Order).filter(Order.status == status).all()
    if not orders:
        raise HTTPException(status_code=404, detail="No orders found")
    return orders

def get_orders_by_user(db: Session, user_id: str) -> List[Order]:
    orders = db.query(Order).filter(Order.user_id == user_id).all()
    if not orders:
        raise HTTPException(status_code=404, detail="No orders found")
    return orders

def get_orders_by_date(db: Session, date: str) -> List[Order]:
    orders = db.query(Order).filter(Order.created_at == date).all()
    if not orders:
        raise HTTPException(status_code=404, detail="No orders found")
    return orders

def get_all_orders(db: Session) -> List[Order]:
    # Use eager loading to avoid N+1 queries when accessing user, items, and shipping address data
    from sqlalchemy.orm import joinedload
    orders = db.query(Order).options(
        joinedload(Order.user),
        joinedload(Order.items),
        joinedload(Order.shipping_address)
    ).all()
    return orders

def get_all_customers(db: Session) -> List[User]:
    customers_without_admin_users = []
    customers = db.query(User).all()
    for customer in customers:
        if customer.role != 'admin' and customer.role != 'super_admin':
            customers_without_admin_users.append(customer)
    if not customers_without_admin_users:
        return []
    return customers_without_admin_users

def update_payment_status(db: Session, order_id: str, status: PaymentStatusEnum) -> Order:
    print("STATUS", status)
    print("ORDER_ID", order_id)
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Validar que el status sea válido para pagos
    valid_payment_statuses = [status.value for status in PaymentStatusEnum]
    if status not in valid_payment_statuses:
        raise HTTPException(
            status_code=400, 
            detail=f"Status de pago inválido. Valores válidos: {valid_payment_statuses}"
        )
    
    order.payment_status = status.value
    db.commit()
    db.refresh(order)
    return order

# =============================================================================
# FUNCIONES DE CRÉDITO PARA DASHBOARD
# =============================================================================

def get_credit_payments_dashboard(db: Session) -> dict:
    """Dashboard de pagos de crédito para admin"""
    from app.models.credit_payment import CreditPayment
    from app.models.order import Order
    from sqlalchemy import func
    from datetime import datetime, timezone
    
    
    # Pagos pendientes
    pending_payments = db.query(CreditPayment).filter(
        CreditPayment.status == "pending"
    ).count()
    
    # Pagos aprobados hoy
    today = datetime.now(timezone.utc).date()
    approved_today = db.query(CreditPayment).filter(
        CreditPayment.status == "approved",
        func.date(CreditPayment.approved_at) == today
    ).count()
    
    # Monto total pendiente
    total_pending_amount = db.query(func.sum(CreditPayment.amount)).filter(
        CreditPayment.status == "pending"
    ).scalar() or 0
    
    # Órdenes con pagos pendientes
    orders_with_pending = db.query(Order).filter(
        Order.is_credit_order == True,
        Order.credit_remaining > 0
    ).count()
    
    return {
        "pending_payments": pending_payments,
        "approved_today": approved_today,
        "total_pending_amount": total_pending_amount,
        "orders_with_pending": orders_with_pending
    }

def get_user_credit_dashboard(user_id: str, db: Session) -> dict:
    """Dashboard de crédito para usuario"""
    from app.models.user import User
    from app.models.order import Order
    from app.models.credit_payment import CreditPayment
    from sqlalchemy import func
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {}
    
    # Órdenes del usuario
    orders = db.query(Order).filter(
        Order.user_id == user_id,
        Order.is_credit_order == True
    ).all()
    
    # Pagos pendientes de aprobación
    pending_payments = db.query(CreditPayment).filter(
        CreditPayment.user_id == user_id,
        CreditPayment.status == "pending"
    ).all()
    
    # Pagos aprobados recientes
    recent_approved = db.query(CreditPayment).filter(
        CreditPayment.user_id == user_id,
        CreditPayment.status == "approved"
    ).order_by(CreditPayment.approved_at.desc()).limit(5).all()
    
    # Estadísticas
    total_credit_used = sum(order.credit_amount for order in orders)
    total_paid = sum(order.credit_paid_total for order in orders)
    total_remaining = sum(order.credit_remaining for order in orders)
    
    # Convert ORM payments to serializable dicts
    from app.schemas.credit import CreditPaymentResponse
    recent_approved_serialized = [
        CreditPaymentResponse.model_validate(p).model_dump()
        for p in recent_approved
    ]

    return {
        "user_credit": {
            "available_credit": user.available_credit,
            "credit_limit": user.credit_limit,
            "credit_status": user.credit_status
        },
        "orders": {
            "total_orders": len(orders),
            "total_credit_used": total_credit_used,
            "total_paid": total_paid,
            "total_remaining": total_remaining
        },
        "payments": {
            "pending_count": len(pending_payments),
            "pending_amount": sum(p.amount for p in pending_payments),
            "recent_approved": recent_approved_serialized
        }
    }

def get_payment_details(payment_id: str, db: Session) -> dict:
    """Detalles completos de un pago"""
    from app.models.credit_payment import CreditPayment
    from app.models.order import Order
    from app.models.user import User
    
    payment = db.query(CreditPayment).filter(CreditPayment.id == payment_id).first()
    if not payment:
        return None
    
    order = payment.order
    user = payment.user
    
    from app.schemas.credit import CreditPaymentResponse
    payment_serialized = CreditPaymentResponse.model_validate(payment).model_dump()

    return {
        "payment": payment_serialized,
        "order": {
            "id": order.id,
            "order_number": order.order_number,
            "total": order.total,
            "credit_remaining": order.credit_remaining,
            "credit_paid_total": order.credit_paid_total
        },
        "user": {
            "id": user.id,
            "email": user.email,
            "company_name": user.company_name
        }
    }