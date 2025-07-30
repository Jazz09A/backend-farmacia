import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.user import User
from app.models.order import Order
from app.schemas.dashboard import DashboardStats, OrderStatusSummary, RecentOrder, DashboardData

def get_dashboard_data(db: Session, days_filter: int = 7) -> DashboardData:
    """
    Retrieves and computes all data required for the admin dashboard.
    """
    # 1. Calculate date range for filtering
    end_date = datetime.datetime.now(datetime.timezone.utc)
    start_date = end_date - datetime.timedelta(days=days_filter)

    # 2. Basic Stats
    total_revenue_query = db.query(func.sum(Order.total)).filter(
        Order.created_at >= start_date,
        Order.status == 'delivered' # Assuming revenue is counted on delivered orders
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
        processing=status_map.get('processing', 0),
        shipped=status_map.get('shipped', 0),
        delivered=status_map.get('delivered', 0),
    )

    # 4. Recent Orders
    recent_orders_query = db.query(Order).order_by(Order.created_at.desc()).limit(5).all()
    
    recent_orders = [
        RecentOrder(
            id=str(order.id),
            customer_name=order.user.name, # Using the model property
            date=order.created_at.strftime("%Y-%m-%d"),
            total=order.total,
            status=order.status,
        ) for order in recent_orders_query
    ]

    return DashboardData(
        stats=stats,
        order_status_summary=order_status_summary,
        recent_orders=recent_orders,
    ) 