# Models package
# Import all models to ensure SQLAlchemy relationships work correctly

from .address import Address, UserPreferences
from .blog import BlogCategory, BlogImage, BlogPost
from .cart import CartItem

# ShippingZone eliminado - no se usa con Profit Plus
# from .shipping import ShippingZone
from .category import Brand, Category
from .credit_payment import CreditPayment
from .favorites import UserFavorite
from .product import Product
from .product_image import ProductImage

# Order models eliminados - Order no se usa con Profit Plus
# from .order import Order, OrderItem, OrderAddress
# from .order_discount import OrderDiscount, DiscountType as OrderDiscountType
from .promotion import DiscountType, FlashOffer, Promotion, PromotionalCode, PromotionUsage
from .user import User

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
    "BlogImage",
    "ProductImage",
]
