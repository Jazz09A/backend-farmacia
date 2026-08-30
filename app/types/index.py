from enum import Enum


class PaymentMethod(Enum):
    CREDIT = "credit"
    DEBIT = "debit"
    CASH = "cash"
    CHECK = "check"
    OTHER = "other"
class PaymentStatusEnum(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"

class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class StockType(Enum):
    """Tipos de stock en saStockAlmacen"""
    ACT = "ACT"  # Stock actual
    COM = "COM"  # Stock comprometido
    LLE = "LLE"  # Stock por llegar
    DES = "DES"  # Stock por despachar
    SACT = "SACT"  # Stock actual secundario
    SCOM = "SCOM"  # Stock comprometido secundario
    SLLE = "SLLE"  # Stock por llegar secundario
    SDES = "SDES"  # Stock por despachar secundario