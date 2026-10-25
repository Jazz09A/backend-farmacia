# Models package
# Import all models to ensure SQLAlchemy relationships work correctly

from .address import Address, UserPreferences
from .blog import BlogCategory, BlogImage, BlogPost
from .cart import CartItem

# ShippingZone eliminado - no se usa con Profit Plus
# from .shipping import ShippingZone
from .category import Brand, Category
from .favorites import UserFavorite
from .product import Product
from .product_image import ProductImage

# Order models eliminados - Order no se usa con Profit Plus
# from .order import Order, OrderItem, OrderAddress
# from .order_discount import OrderDiscount, DiscountType as OrderDiscountType
from .promotion import (
    DiscountType,
    FlashOffer,
    Promotion,
    PromotionalCode,
    PromotionUsage,
)
from .types import ArrayType
from .user import User

__all__ = [
    "Address",
    "ArrayType",
    "BlogCategory",
    "BlogImage",
    "BlogPost",
    "Brand",
    "CartItem",
    # "ShippingZone",  # Eliminado - no se usa con Profit Plus
    "Category",
    "DiscountType",
    "FlashOffer",
    "Product",
    "ProductImage",
    # Order models eliminados
    # "Order",
    # "OrderItem", 
    # "OrderAddress",
    # "OrderDiscount",
    # "OrderDiscountType",
    "Promotion",
    "PromotionUsage",
    "PromotionalCode",
    "User",
    "UserFavorite",
    "UserPreferences",
] 