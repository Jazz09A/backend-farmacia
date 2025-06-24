# Models package
# Import all models to ensure SQLAlchemy relationships work correctly

from .user import User
from .product import Product
from .cart import CartItem
from .address import Address, UserPreferences
from .order import Order, OrderItem, OrderAddress
from .review import Review
from .support import SupportTicket, SupportResponse
from .promotion import Promotion, PromotionUsage
from .notification import UserNotification
from .blog import BlogCategory, BlogPost
from .shipping import ShippingZone

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
    "UserNotification",
    "BlogCategory",
    "BlogPost",
    "ShippingZone"
] 