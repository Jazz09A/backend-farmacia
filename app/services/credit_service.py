from sqlalchemy.orm import Session, joinedload
from app.models.user import User
# Order model eliminado - Order no se usa con Profit Plus
# from app.models.order import Order
from app.models.cart import CartItem
from app.models.address import Address
# ShippingZone eliminado - no se usa con Profit Plus
# from app.models.shipping import ShippingZone
from fastapi import HTTPException
from datetime import timedelta
from app.config.logging_config import get_logger
# OrderCreate schema eliminado - Order no se usa con Profit Plus
# from app.schemas.order import OrderCreate
from decimal import Decimal

from app.services.currency_service import CurrencyService
from app.services.exchange_service import ExchangeRateService
from app.utils.timezone import get_ve_now

class CreditService:
    def __init__(self, db: Session):
        self.db = db
        self.logger = get_logger("credit")
        self.currency_service = CurrencyService(db)
        self.exchange_service = ExchangeRateService()
    
    def get_user_credit(self, user_id: str) -> dict:
        """Obtener información de crédito del usuario"""
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        return {
            "available_credit": user.available_credit,
            "credit_limit": user.credit_limit,
            "credit_status": user.credit_status
        }
    
    def assign_credit(self, user_id: str, amount: Decimal) -> bool:
        """Asignar crédito a un usuario (solo admin)"""
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        user.available_credit += amount
        self.db.commit()
        
        self.logger.info(f"Crédito asignado: {amount} a usuario {user_id}")
        return True
    
    def use_credit(self, user: User, amount: Decimal):
        """Usar crédito para una orden. No hace commit."""
        if user.available_credit < amount:
            raise HTTPException(
                status_code=400,
                detail="Crédito insuficiente. Verificación final falló."
            )
        
        user.available_credit -= amount
        self.logger.info(f"Crédito usado: {amount} por usuario {user.id}")

    # create_credit_order eliminado - Order no se usa con Profit Plus
    async def create_credit_order(self, user_id: str, order_data: dict):
        """
        ELIMINADO - Order no se usa con Profit Plus
        Las cotizaciones se manejan a través de /quotes que se conecta directamente a Profit Plus.
        """
        raise HTTPException(status_code=501, detail="create_credit_order eliminado - Order no se usa con Profit Plus")