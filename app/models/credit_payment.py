import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.config.database import Base
from app.utils.timezone import get_ve_now


class CreditPayment(Base):
    __tablename__ = "credit_payments"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # order_id eliminado - Order no se usa con Profit Plus
    # order_id = Column(String, ForeignKey("orders.id"), nullable=False, index=True)
    order_id = Column(String, nullable=True, index=True)  # Temporal: mantener para migración
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    
    # Información del pago (TODO EN USD - sistema unificado)
    amount = Column(Numeric(10, 2), nullable=False)  # Monto en USD (después de conversión si era VES)
    payment_currency = Column(String, default="USD", nullable=False)  # Moneda en que pagó el usuario ('USD' o 'VES')
    exchange_rate_used = Column(Numeric(10, 4), nullable=True)  # Tasa usada si pagó en VES
    
    # Referencias del pago
    payment_reference = Column(String, nullable=False)  # Referencia del pago
    payment_capture_url = Column(String, nullable=True)  # URL de la captura
    
    # Estado del pago
    status = Column(String, default="pending", nullable=False, index=True)  # pending, approved, rejected
    admin_notes = Column(Text, nullable=True)  # Notas del admin
    
    # Timestamps
    created_at = Column(DateTime, default=get_ve_now)
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(String, nullable=True)  # Admin que aprobó
    
    # Relationships
    # order relationship eliminado - Order no se usa con Profit Plus
    # order = relationship("Order", back_populates="credit_payments")
    user = relationship("User", back_populates="credit_payments")
    
    def __repr__(self):
        return f"<CreditPayment(id={self.id}, amount={self.amount}, status={self.status})>"
