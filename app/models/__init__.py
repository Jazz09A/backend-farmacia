# Models package
# Import all models to ensure SQLAlchemy relationships work correctly

from .user import User
from .product import Product
from .cart import CartItem
from .address import Address, UserPreferences
# Order models eliminados - Order no se usa con Profit Plus
# from .order import Order, OrderItem, OrderAddress
# from .order_discount import OrderDiscount, DiscountType as OrderDiscountType
from .promotion import (
    Promotion, PromotionUsage, FlashOffer, 
    PromotionalCode, DiscountType
)
# ShippingZone eliminado - no se usa con Profit Plus
# from .shipping import ShippingZone
from .category import Category, Brand
from .favorites import UserFavorite
from .credit_payment import CreditPayment
from .blog import BlogPost, BlogCategory, BlogImage

__all__ = [
    "User",
    "Product", 
    "CartItem",
    "Address",
    "UserPreferences",
    # Order models eliminados
    # "Order",
    # "OrderItem", 
    # "OrderAddress",
    # "OrderDiscount",
    # "OrderDiscountType",
    "Promotion",
    "PromotionUsage",
    "FlashOffer",
    "PromotionalCode",
    "DiscountType",
    # "ShippingZone",  # Eliminado - no se usa con Profit Plus
    "Category",
    "Brand",
    "UserFavorite",
    "CreditPayment",
    "BlogPost",
    "BlogCategory",
    "BlogImage"
] 