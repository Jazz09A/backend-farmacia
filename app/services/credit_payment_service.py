import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config.logging_config import get_logger
from app.models.credit_payment import CreditPayment

# Order model eliminado - Order no se usa con Profit Plus
# from app.models.order import Order
from app.services.currency_service import CurrencyService
from app.utils.timezone import get_ve_now


class CreditPaymentService:
    def __init__(self, db: Session):
        self.db = db
        self.logger = get_logger("credit_payments")
        self.currency_service = CurrencyService(db)

    async def create_payment(self, user_id: str, order_id: str, payment_data: dict) -> CreditPayment:
        """
        Crear un pago parcial para una orden - SISTEMA UNIFICADO USD

        IMPORTANTE: Usa la tasa del DÍA DEL PAGO, NO la de la orden original.
        Esto es más justo para el usuario.
        """

        # Validar que la orden existe y pertenece al usuario
        order = (
            self.db.query(Order)  # type: ignore[name-defined]  # noqa: F821
            .filter(  # type: ignore[name-defined]
                Order.id == order_id,  # type: ignore[name-defined]  # noqa: F821
                Order.user_id == user_id,  # type: ignore[name-defined]  # noqa: F821
                Order.is_credit_order == True,  # type: ignore[name-defined]  # noqa: F821
            )
            .first()
        )

        if not order:
            raise HTTPException(status_code=404, detail="Orden no encontrada")

        # Validar que no esté completamente pagada
        if order.credit_remaining <= 0:
            raise HTTPException(status_code=400, detail="Esta orden ya está completamente pagada")

        # 1. Extraer datos del pago
        payment_amount = Decimal(str(payment_data["amount"]))
        payment_currency = payment_data.get("payment_currency", "USD").upper()

        # Validar que el monto sea mayor a 0
        if payment_amount <= 0:
            raise HTTPException(status_code=400, detail="El monto del pago debe ser mayor a 0")

        self.logger.info(f"Procesando pago: {payment_amount} {payment_currency} para orden {order_id}")

        # 2. Obtener tasa del DÍA DEL PAGO (no la de la orden)
        exchange_rate = None
        if payment_currency == "VES":
            exchange_rate = await self.currency_service.get_current_rate()
            self.logger.info(f"Pago en VES, tasa del día: {exchange_rate}")

        # 3. Convertir pago a USD
        conversion_result = self.currency_service.convert_payment_to_usd(
            amount=payment_amount, payment_currency=payment_currency, exchange_rate=exchange_rate or Decimal("1.0")
        )

        amount_usd = conversion_result["amount_usd"]

        # 4. Validar que el monto en USD no exceda el saldo pendiente (también en USD)
        if amount_usd > order.credit_remaining:
            raise HTTPException(
                status_code=400,
                detail=f"El monto excede el saldo pendiente. "
                f"Saldo: ${order.credit_remaining} USD, "
                f"Intento de pago: ${amount_usd} USD",
            )

        self.logger.info(
            f"Conversión pago - Original: {payment_amount} {payment_currency}, USD: {amount_usd}, Tasa: {exchange_rate}"
        )

        # 5. Crear el pago EN USD
        payment = CreditPayment(
            id=str(uuid.uuid4()),
            order_id=order_id,
            user_id=user_id,
            amount=amount_usd,  # Monto en USD (después de conversión si era VES)
            payment_currency=payment_currency,  # "USD" o "VES"
            exchange_rate_used=conversion_result["exchange_rate_used"],
            payment_reference=payment_data["payment_reference"],
            payment_capture_url=payment_data.get("payment_capture_url"),
            status="pending",
        )

        self.db.add(payment)
        self.db.commit()

        self.logger.info(f"Pago creado: {payment.id} para orden {order_id}")

        # Enviar email de confirmación de pago registrado
        self._send_payment_registered_email(user_id, payment)

        return payment

    def approve_payment(self, payment_id: str, admin_id: str, admin_notes: str | None = None) -> bool:
        """Aprobar un pago desde el dashboard de admin"""

        payment = self.db.query(CreditPayment).filter(CreditPayment.id == payment_id).first()
        if not payment:
            return False

        # Aprobar el pago
        payment.status = "approved"
        payment.approved_at = get_ve_now()
        payment.approved_by = admin_id
        payment.admin_notes = admin_notes

        # Código eliminado - Order no existe
        # order = payment.order
        # order.credit_paid_total += payment.amount
        # order.credit_remaining -= payment.amount

        self.db.commit()

        self.logger.info(f"Pago aprobado: {payment_id} por admin {admin_id}")

        # Enviar email de aprobación
        self._send_payment_approved_email(payment.user_id, payment)

        return True

    def reject_payment(self, payment_id: str, admin_id: str, admin_notes: str) -> bool:
        """Rechazar un pago desde el dashboard de admin"""

        payment = self.db.query(CreditPayment).filter(CreditPayment.id == payment_id).first()
        if not payment:
            return False

        payment.status = "rejected"
        payment.approved_at = get_ve_now()
        payment.approved_by = admin_id
        payment.admin_notes = admin_notes

        self.db.commit()

        self.logger.info(f"Pago rechazado: {payment_id} por admin {admin_id}")

        # Enviar email de rechazo
        self._send_payment_rejected_email(payment.user_id, payment)

        return True

    def get_order_payments(self, order_id: str) -> list[CreditPayment]:
        """Obtener todos los pagos de una orden"""
        return (
            self.db.query(CreditPayment)
            .filter(CreditPayment.order_id == order_id)
            .order_by(CreditPayment.created_at.desc())
            .all()
        )

    def get_pending_payments(self) -> list[CreditPayment]:
        """Obtener todos los pagos pendientes de aprobación"""
        return (
            self.db.query(CreditPayment)
            .filter(CreditPayment.status == "pending")
            .order_by(CreditPayment.created_at.desc())
            .all()
        )

    def get_payments_filtered(
        self,
        status: str | None = None,
        user_id: str | None = None,
        order_id: str | None = None,
        min_amount: Decimal | None = None,
        max_amount: Decimal | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[CreditPayment]:
        """
        Obtener pagos con filtros opcionales. Ordena por fecha de creación desc.
        """
        query = self.db.query(CreditPayment)

        if status:
            query = query.filter(CreditPayment.status == status)
        if user_id:
            query = query.filter(CreditPayment.user_id == user_id)
        if order_id:
            query = query.filter(CreditPayment.order_id == order_id)
        if min_amount is not None:
            query = query.filter(CreditPayment.amount >= min_amount)
        if max_amount is not None:
            query = query.filter(CreditPayment.amount <= max_amount)
        if start_date is not None:
            query = query.filter(CreditPayment.created_at >= start_date)
        if end_date is not None:
            query = query.filter(CreditPayment.created_at <= end_date)

        return query.order_by(CreditPayment.created_at.desc()).all()

    def get_user_payments(self, user_id: str) -> list[CreditPayment]:
        """Obtener todos los pagos de un usuario"""
        return (
            self.db.query(CreditPayment)
            .filter(CreditPayment.user_id == user_id)
            .order_by(CreditPayment.created_at.desc())
            .all()
        )

    def get_payment_by_id(self, payment_id: str) -> CreditPayment | None:
        """Obtener un pago por ID"""
        return self.db.query(CreditPayment).filter(CreditPayment.id == payment_id).first()

    def _send_payment_registered_email(self, user_id: str, payment: CreditPayment):
        """Enviar email de pago registrado"""
        try:
            import asyncio

            from app.models.user import User
            from app.services.email_service import email_service

            user = self.db.query(User).filter(User.id == user_id).first()
            if user and user.email:
                payment_data = {
                    "user_name": user.company_name or user.email,
                    "amount": payment.amount,
                    "currency": "VES",
                    "order_number": payment.order_id,  # Usar order_id directamente
                    "payment_reference": payment.payment_reference,
                    "payment_date": payment.created_at.strftime("%d/%m/%Y %H:%M"),
                }

                # Enviar email de forma asíncrona
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(email_service.send_payment_registered_email(user.email, payment_data))
                    else:
                        loop.run_until_complete(email_service.send_payment_registered_email(user.email, payment_data))
                except RuntimeError:
                    # Si no hay event loop, enviar de forma síncrona
                    pass
        except Exception as e:
            self.logger.error(f"Error enviando email de pago registrado: {e}")

    def _send_payment_approved_email(self, user_id: str, payment: CreditPayment):
        """Enviar email de pago aprobado"""
        try:
            import asyncio

            from app.models.user import User
            from app.services.email_service import email_service

            user = self.db.query(User).filter(User.id == user_id).first()
            if user and user.email:
                payment_data = {
                    "user_name": user.company_name or user.email,
                    "amount": payment.amount,
                    "currency": "VES",
                    "order_number": payment.order_id,  # Usar order_id directamente
                    "order_total": None,  # Order no existe
                    "paid_total": None,  # Order no existe
                    "remaining_balance": None,  # Order no existe
                }

                # Enviar email de forma asíncrona
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(email_service.send_payment_approved_email(user.email, payment_data))
                    else:
                        loop.run_until_complete(email_service.send_payment_approved_email(user.email, payment_data))
                except RuntimeError:
                    # Si no hay event loop, enviar de forma síncrona
                    pass
        except Exception as e:
            self.logger.error(f"Error enviando email de pago aprobado: {e}")

    def _send_payment_rejected_email(self, user_id: str, payment: CreditPayment):
        """Enviar email de pago rechazado"""
        try:
            import asyncio

            from app.models.user import User
            from app.services.email_service import email_service

            user = self.db.query(User).filter(User.id == user_id).first()
            if user and user.email:
                payment_data = {
                    "user_name": user.company_name or user.email,
                    "amount": payment.amount,
                    "currency": "VES",
                    "order_number": payment.order_id,  # Usar order_id directamente
                    "admin_notes": payment.admin_notes or "No se proporcionó motivo específico",
                }

                # Enviar email de forma asíncrona
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(email_service.send_payment_rejected_email(user.email, payment_data))
                    else:
                        loop.run_until_complete(email_service.send_payment_rejected_email(user.email, payment_data))
                except RuntimeError:
                    # Si no hay event loop, enviar de forma síncrona
                    pass
        except Exception as e:
            self.logger.error(f"Error enviando email de pago rechazado: {e}")
