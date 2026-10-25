"""
Servicio centralizado para manejo de conversiones de moneda.
Estandariza todas las operaciones entre VES y REF/USD.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.config.logging_config import get_logger
from app.services.exchange_service import ExchangeRateService


class CurrencyService:
    """
    Servicio centralizado para conversiones de moneda - SISTEMA UNIFICADO USD.

    PRINCIPIOS CLAVE:
    1. TODO se almacena y procesa en USD internamente
    2. Conversión VES->USD SOLO cuando el usuario paga en VES
    3. Frontend maneja conversión USD->VES para display (si es necesario)
    4. Backend NO convierte para display, solo para pagos
    5. Se guarda tasa de cambio y moneda original del pago para trazabilidad
    6. Redondeo consistente a 2 decimales
    """

    def __init__(self, db: Session):
        self.db = db
        self.exchange_service = ExchangeRateService()
        self.logger = get_logger("currency")

        # Configuración de redondeo
        self.decimal_places = Decimal("0.01")  # 2 decimales
        self.rounding = ROUND_HALF_UP

    async def get_current_rate(self, force_refresh: bool = False) -> Decimal:
        """
        Obtener tasa de cambio actual del servicio centralizado.

        Args:
            force_refresh: Forzar actualización de la tasa

        Returns:
            Decimal: Tasa de cambio VES/USD
        """
        try:
            rate_data = await self.exchange_service.get_exchange_rate(force_refresh=force_refresh)

            if not rate_data or "price" not in rate_data:
                self.logger.warning("No se pudo obtener tasa de cambio, usando fallback")
                return Decimal("35.0")  # Fallback controlado

            rate = Decimal(str(rate_data["price"]))
            self.logger.info(f"Tasa de cambio obtenida: {rate}")

            return rate

        except Exception as e:
            self.logger.error(f"Error obteniendo tasa de cambio: {e}")
            return Decimal("35.0")  # Fallback en caso de error

    def convert_payment_to_usd(self, amount: Decimal, payment_currency: str, exchange_rate: Decimal) -> dict[str, Any]:
        """
        Convertir un pago a USD (ÚNICA conversión que hace el backend).

        Casos de uso:
        - Usuario paga una orden en VES -> convierte a USD
        - Usuario paga deuda de crédito en VES -> convierte a USD

        Args:
            amount: Monto del pago
            payment_currency: Moneda del pago ('USD' o 'VES')
            exchange_rate: Tasa de cambio VES/USD del día del pago

        Returns:
            Dict con:
            - amount_usd: Monto en USD (para guardar en DB)
            - original_amount: Monto original del pago
            - original_currency: 'USD' o 'VES'
            - exchange_rate_used: Tasa usada (None si ya era USD)
        """
        payment_currency = payment_currency.upper()

        if payment_currency == "USD":
            # Ya está en USD, no hay conversión
            self.logger.info(f"Pago recibido en USD: {amount}")
            return {
                "amount_usd": amount,
                "original_amount": amount,
                "original_currency": "USD",
                "exchange_rate_used": None,
            }

        elif payment_currency == "VES":
            # Convertir VES a USD usando la tasa del día
            if exchange_rate is None or exchange_rate <= 0:
                raise ValueError("Tasa de cambio inválida para conversión VES->USD")

            amount_usd = (amount / exchange_rate).quantize(self.decimal_places, rounding=self.rounding)

            self.logger.info(f"Pago VES convertido: {amount} VES = {amount_usd} USD (tasa: {exchange_rate})")

            return {
                "amount_usd": amount_usd,
                "original_amount": amount,
                "original_currency": "VES",
                "exchange_rate_used": exchange_rate,
            }

        else:
            raise ValueError(f"Moneda no soportada: {payment_currency}. Use 'USD' o 'VES'")

    def convert_usd_to_display(self, amount_usd: Decimal, target_currency: str, exchange_rate: Decimal) -> Decimal:
        """
        Convertir USD a otra moneda SOLO PARA DISPLAY (opcional, puede hacer el frontend).

        NOTA: Preferiblemente el frontend hace esta conversión.
        Este método está aquí por compatibilidad pero NO se usa en los flujos principales.

        Args:
            amount_usd: Monto en USD
            target_currency: Moneda objetivo ('VES')
            exchange_rate: Tasa de cambio

        Returns:
            Monto convertido
        """
        target_currency = target_currency.upper()

        if target_currency == "USD":
            return amount_usd
        elif target_currency == "VES":
            if exchange_rate is None or exchange_rate <= 0:
                raise ValueError("Se requiere tasa de cambio válida")

            amount_ves = (amount_usd * exchange_rate).quantize(self.decimal_places, rounding=self.rounding)

            return amount_ves
        else:
            raise ValueError(f"Moneda no soportada: {target_currency}")

    def standardize_to_usd(
        self, amount: Decimal, currency: str, exchange_rate: Decimal | None = None
    ) -> dict[str, Any]:
        """
        Estandarizar cualquier monto a USD (wrapper de convert_payment_to_usd).

        Args:
            amount: Monto a convertir
            currency: Moneda origen ('VES' o 'USD')
            exchange_rate: Tasa específica (requerida si currency es VES)

        Returns:
            Dict con monto estandarizado en USD
        """
        if exchange_rate is None and currency.upper() == "VES":
            raise ValueError("Se requiere exchange_rate para convertir VES a USD")

        return self.convert_payment_to_usd(amount, currency, exchange_rate or Decimal("1.0"))

    def validate_amount(self, amount: Decimal, min_amount: Decimal = Decimal("0.01")) -> bool:
        """
        Validar que un monto sea válido.

        Args:
            amount: Monto a validar
            min_amount: Monto mínimo permitido

        Returns:
            bool: True si es válido
        """
        try:
            if not isinstance(amount, Decimal):
                return False

            if amount < min_amount:
                return False

            # Verificar que no tenga más de 2 decimales
            return not amount.as_tuple().exponent < -2

        except Exception:
            return False

    def round_amount(self, amount: Decimal) -> Decimal:
        """
        Redondear monto a 2 decimales de forma consistente.

        Args:
            amount: Monto a redondear

        Returns:
            Decimal: Monto redondeado
        """
        return amount.quantize(self.decimal_places, rounding=self.rounding)

    def get_currency_info(self) -> dict[str, Any]:
        """
        Obtener información sobre las monedas soportadas (sistema unificado USD).

        Returns:
            Dict con información de monedas
        """
        return {
            "supported_payment_currencies": ["USD", "VES"],  # Monedas aceptadas para pago
            "base_currency": "USD",  # Moneda interna del sistema
            "display_currencies": ["USD", "VES"],  # Monedas para mostrar (frontend)
            "decimal_places": 2,
            "rounding_method": "ROUND_HALF_UP",
            "min_amount": "0.01",
            "note": "Sistema unificado: todo se almacena en USD, conversión VES solo en pagos",
        }


# Instancia global para uso en otros servicios
def get_currency_service(db: Session) -> CurrencyService:
    """Factory para obtener instancia de CurrencyService"""
    return CurrencyService(db)
