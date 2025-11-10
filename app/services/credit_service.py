from sqlalchemy.orm import Session, joinedload
from app.models.user import User
from app.models.order import Order
from app.models.cart import CartItem
from app.models.address import Address
from app.models.shipping import ShippingZone
from fastapi import HTTPException
from datetime import timedelta
from app.config.logging_config import get_logger
from app.schemas.order import OrderCreate
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

    async def create_credit_order(self, user_id: str, order_data: dict) -> Order:
        """
        Crear orden con crédito - SISTEMA UNIFICADO USD
        
        IMPORTANTE: 
        - Todo se calcula en USD (product.price ya es USD)
        - El crédito del usuario (available_credit) debe estar en USD
        - payment_currency será "USD" (orden de crédito)
        """
        from app.services.order_service import OrderService
        
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        cart_items = self.db.query(CartItem).options(joinedload(CartItem.product)).filter(CartItem.user_id == user_id).all()
        if not cart_items:
            raise HTTPException(status_code=400, detail="El carrito está vacío.")

        shipping_address = self.db.query(Address).filter(Address.id == order_data["shipping_address_id"], Address.user_id == user_id).first()
        if not shipping_address:
            raise HTTPException(status_code=404, detail="Dirección de envío no encontrada.")
        
        # 1. Calcular subtotal en USD (products.price ya es USD)
        subtotal = sum(item.product.price * item.quantity for item in cart_items)
        
        # 2. Obtener costo de envío (debería estar en USD después de migración)
        shipping_zone_id = shipping_address.city.lower().replace(" ", "-")
        shipping_zone = self.db.query(ShippingZone).filter(ShippingZone.id == shipping_zone_id).first()
        shipping_cost = shipping_zone.price if shipping_zone else Decimal('0.00')  # USD
        
        # 3. Calcular impuestos y total en USD
        taxes = subtotal * Decimal('0.16')
        estimated_total = subtotal + shipping_cost + taxes
        
        self.logger.info(
            f"Cálculo orden crédito - "
            f"Subtotal USD: {subtotal}, "
            f"Envío USD: {shipping_cost}, "
            f"Impuestos USD: {taxes}, "
            f"Total USD: {estimated_total}"
        )

        # 4. Validar crédito disponible (todo en USD)
        if user.available_credit < estimated_total:
            raise HTTPException(
                status_code=400,
                detail=f"Crédito insuficiente. "
                       f"Disponible: ${user.available_credit} USD, "
                       f"Requerido: ${estimated_total} USD"
            )
        
        # 5. Crear orden usando OrderService existente
        order_service = OrderService(self.db)
        
        # Crear datos de orden (payment_currency siempre USD para crédito)
        order_create_data = OrderCreate(
            shipping_address_id=order_data["shipping_address_id"],
            payment_method="credit",
            payment_currency="USD",  # Orden de crédito siempre en USD
            payment_capture_url="",
            customer_notes=order_data.get("customer_notes", "")
        )
        
        # Crear orden usando el servicio existente
        order = order_service.create_order_from_cart(user_id, order_create_data)
        
        # 6. Configurar como orden de crédito (TODO EN USD)
        order.is_credit_order = True
        order.credit_amount = order.total           # Total en USD
        order.credit_remaining = order.total        # Saldo pendiente en USD
        order.credit_paid_total = Decimal('0.00')   # Pagado hasta ahora en USD
        order.payment_due_date = get_ve_now() + timedelta(days=30)
        # exchange_rate será None porque payment_currency es USD
        
        # 7. Usar crédito del usuario (en USD)
        self.use_credit(user, order.total)
        
        # 8. Operación atómica
        self.db.add(order)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(order)
        self.db.refresh(user)
        
        self.logger.info(
            f"Orden de crédito creada: {order.id} por usuario {user_id}. "
            f"Total USD: ${order.total}, "
            f"Crédito restante usuario: ${user.available_credit} USD"
        )
        return order