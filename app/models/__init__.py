# Models package
# Import all models to ensure SQLAlchemy relationships work correctly

from .user import User
from .product import Product
from .cart import CartItem
from .address import Address, UserPreferences
from .order import Order, OrderItem, OrderAddress
from .review import Review
from .support import SupportTicket, SupportResponse
from .promotion import (
    Promotion, PromotionUsage, FlashOffer, 
    PromotionalCode, DiscountType
)
from .notification import UserNotification
from .blog import BlogCategory, BlogPost
from .shipping import ShippingZone
from .category import Category, Brand
from .inventory import InventoryMovement, StockAlert, BatchTracking, MovementType

__all__ = [
    "User",
    "Product", 
    "CartItem",
    "Address",
    "UserPreferences",
    "Order",
    "OrderItem", 
    "OrderAddress",
    "Review",
    "SupportTicket",
    "SupportResponse",
    "Promotion",
    "PromotionUsage",
    "FlashOffer",
    "PromotionalCode",
    "DiscountType",
    "UserNotification",
    "BlogCategory",
    "BlogPost",
    "ShippingZone",
    "Category",
    "Brand",
    "InventoryMovement",
    "StockAlert", 
    "BatchTracking",
    "MovementType"
] 