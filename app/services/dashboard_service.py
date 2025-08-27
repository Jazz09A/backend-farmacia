import datetime
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.user import User
from app.models.order import Order
from app.config.logging_config import get_logger
from app.schemas.dashboard import DashboardStats, OrderStatusSummary, RecentOrder, DashboardData
from app.schemas.order import OrderStatus  # Import from schema, not model
from fastapi import HTTPException
from app.schemas.order import PaymentStatusEnum
from app.schemas.order import UpdatePaymentStatus
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
    end_date = datetime.datetime.now(datetime.timezone.utc)
    start_date = end_date - datetime.timedelta(days=days_filter)

    # 2. Basic Stats
    total_revenue_query = db.query(func.sum(Order.total)).filter(
    Order.created_at >= start_date,
    Order.status.in_(['pending', 'confirmed', 'processing', 'shipped', 'delivered'])
    ).scalar() or 0.0
    
    total_orders = db.query(Order).filter(Order.created_at >= start_date).count()
    new_customers = db.query(User).filter(User.created_at >= start_date).count()
    
    # Placeholder for conversion rate logic
    conversion_rate = 0.0 

    stats = DashboardStats(
        total_revenue=total_revenue_query,
        total_orders=total_orders,
        new_customers=new_customers,
        conversion_rate=conversion_rate,
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
    return order

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
        raise HTTPException(status_code=200, detail="No customers found")
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
