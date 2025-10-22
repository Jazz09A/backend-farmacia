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