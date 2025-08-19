from pydantic import BaseModel
from typing import List, Dict

class DashboardStats(BaseModel):
    total_revenue: float
    total_orders: int
    new_customers: int
    conversion_rate: float
    
class OrderStatusSummary(BaseModel):
    pending: int
    confirmed: int
    processing: int
    shipped: int
    delivered: int
    cancelled: int
    
class RecentOrder(BaseModel):
    id: str
    customer_name: str
    date: str
    total: float
    status: str
    
class DashboardData(BaseModel):
    stats: DashboardStats
    order_status_summary: OrderStatusSummary
    recent_orders: List[RecentOrder] 