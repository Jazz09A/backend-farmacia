from decimal import Decimal

from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_revenue: Decimal
    total_orders: int
    new_customers: int
    conversion_rate: Decimal

    # Discount statistics
    total_discounts_given: Decimal = Decimal("0.00")
    orders_with_discounts: int = 0
    discount_usage_percentage: float = 0.0
    average_discount_per_order: Decimal = Decimal("0.00")


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
    total: Decimal
    status: str


class DiscountBreakdown(BaseModel):
    quantity_discounts: int = 0
    flash_discounts: int = 0
    coupon_discounts: int = 0
    promotional_discounts: int = 0
    total_amount_by_type: dict[str, Decimal] = {}


class DashboardData(BaseModel):
    stats: DashboardStats
    order_status_summary: OrderStatusSummary
    recent_orders: list[RecentOrder]
    discount_breakdown: DiscountBreakdown = DiscountBreakdown()
