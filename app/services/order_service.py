import os
import uuid
from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status
from decimal import Decimal

from app.models.user import User
from app.models.cart import CartItem
from app.models.order import Order, OrderItem, OrderAddress, OrderStatus
from app.models.address import Address
from app.models.shipping import ShippingZone
from app.models.order_discount import OrderDiscount, DiscountType
from app.schemas.order import OrderCreate
from app.services.discount_service import DiscountService
from app.config.logging_config import get_logger, log_error
from dotenv import load_dotenv

load_dotenv()

class OrderService:
    def __init__(self, db: Session):
        self.db = db
        self.orders_logger = get_logger("orders")
        self.error_logger = get_logger("errors")

    async def create_order_from_cart(self, user_id: str, order_data: OrderCreate) -> Order:
        """
        Creates a new order from the user's current cart.
        SISTEMA UNIFICADO USD: Todo se calcula y almacena en USD.
        
        Flujo:
        1. Validar carrito y dirección
        2. Si payment_currency es VES, obtener tasa del día
        3. Calcular todos los montos EN USD (products.price ya es USD)
        4. Guardar orden con payment_currency y exchange_rate (si aplicó)
        """
        # Obtener email del usuario para logging
        user_email = None
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if user:
                user_email = user.email
        except Exception:
            pass
        
        # Obtener payment_currency del request
        payment_currency = getattr(order_data, 'payment_currency', 'USD') or 'USD'
        payment_currency = payment_currency.upper()
        
        self.orders_logger.info(
            f"Starting order creation from cart",
            extra={
                'user_id': user_id,
                'user_email': user_email,
                'shipping_address_id': order_data.shipping_address_id,
                'payment_method': order_data.payment_method,
                'payment_currency': payment_currency,
                'event': 'order_creation_started'
            }
        )
        
        # Obtener tipo de cambio SOLO si el usuario va a pagar en VES
        exchange_rate = None
        if payment_currency == "VES":
            try:
                exchange_rate = await self._get_exchange_rate()
            except Exception as e:
                self.orders_logger.warning(f"Could not get exchange rate: {e}, using default")
                exchange_rate = Decimal('40.0')  # Valor por defecto si falla la API
            
            # Asegurar que exchange_rate sea Decimal
            if not isinstance(exchange_rate, Decimal):
                try:
                    exchange_rate = Decimal(str(exchange_rate))
                except Exception:
                    exchange_rate = Decimal('40.0')
            
            self.orders_logger.info(
                f"Order will be paid in VES, exchange rate: {exchange_rate}",
                extra={'exchange_rate': str(exchange_rate), 'payment_currency': 'VES'}
            )
        
        # 1. Retrieve all items from the user's cart
        cart_items = self.db.query(CartItem).filter(CartItem.user_id == user_id).all()
        if not cart_items:
            self.orders_logger.warning(
                f"Order creation failed - empty cart",
                extra={
                    'user_id': user_id, 
                    'user_email': user_email,
                    'reason': 'empty_cart', 
                    'event': 'order_creation_failed'
                }
            )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your cart is empty.")
        
        self.orders_logger.info(
            f"Found {len(cart_items)} items in cart",
            extra={
                'user_id': user_id, 
                'user_email': user_email,
                'cart_items_count': len(cart_items)
            }
        )

        # 2. Get the chosen shipping address from the user's address book
        shipping_address = self.db.query(Address).filter(
            Address.id == order_data.shipping_address_id,
            Address.user_id == user_id
        ).first()

        # DEBUG: Log cart items processing
        self.orders_logger.info("DEBUG: Processing cart items", extra={
            'user_id': user_id,
            'cart_items_count': len(cart_items),
            'first_item_product_id': cart_items[0].product_id if cart_items else None,
            'event': 'debug_cart_processing'
        })

        if not shipping_address:
            self.orders_logger.warning(
                f"Order creation failed - shipping address not found",
                extra={
                    'user_id': user_id,
                    'user_email': user_email,
                    'shipping_address_id': order_data.shipping_address_id,
                    'reason': 'shipping_address_not_found',
                    'event': 'order_creation_failed'
                }
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipping address not found for this user.")


        # Transaction starts here
        try:
            # 3. Initialize order totals (TODO EN USD)
            subtotal = Decimal('0.00')
            order_items = []

            # 4. Calcular descuentos aplicables antes de crear items
            discount_service = DiscountService(self.db)
            discounts_info = discount_service.calculate_cart_discounts(cart_items)

            # 5. Aplicar descuento por cantidad al subtotal base
            subtotal_after_quantity_discount = discounts_info["subtotal_after_discounts"]

            # 6. Create OrderItems and calculate subtotal EN USD
            for item in cart_items:
                product = item.product
                if not product or not product.is_available or product.stock < item.quantity:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Product '{product.name}' is out of stock or unavailable."
                    )

                # Calcular precios EN USD (product.price ya es USD)
                unit_price = product.price  # USD

                # Aplicar descuento flash si existe para este producto
                flash_discount = discounts_info["flash_discounts"].get(product.id, Decimal('0.00'))
                if flash_discount > 0:
                    # El descuento flash ya está calculado por item, convertir a descuento por unidad
                    discount_per_unit = flash_discount / item.quantity
                    unit_price -= discount_per_unit

                total_price = unit_price * item.quantity

                subtotal += total_price

                order_item = OrderItem(
                    id=str(uuid.uuid4()),
                    product_id=product.id,
                    quantity=item.quantity,
                    unit_price=unit_price,  # USD (ya con descuento flash aplicado)
                    total_price=total_price,  # USD
                    selected_presentation=item.selected_presentation,
                    # Snapshot product details at time of purchase
                    product_name=product.name,
                    product_brand=product.brand,
                    product_image=product.image,
                )
                order_items.append(order_item)

                # Decrease product stock
                product.stock -= item.quantity
                if product.stock == 0:
                    product.in_stock = False

            # 5. Define shipping, taxes, and total EN USD
            shipping_zone_id = shipping_address.city.lower().replace(" ", "-")
            shipping_zone = self.db.query(ShippingZone).filter(ShippingZone.id == shipping_zone_id).first()
            
            # NOTA: ShippingZone.price debería estar en USD después de la migración
            # Por ahora asumimos que ya está en USD o lo será después de la migración
            shipping_cost = shipping_zone.price if shipping_zone else Decimal('0.00')  # USD
            
            taxes = (subtotal * Decimal('0.16')).quantize(Decimal('0.01'))  # 16% VAT en USD
            
            total = (subtotal + shipping_cost + taxes).quantize(Decimal('0.01'))  # USD

            # DEBUG: Log order totals calculation (after calculation)
            self.orders_logger.info("DEBUG: Order totals calculated", extra={
                'user_id': user_id,
                'subtotal': str(subtotal),
                'shipping_cost': str(shipping_cost),
                'taxes': str(taxes),
                'total': str(total),
                'payment_currency': payment_currency,
                'exchange_rate': str(exchange_rate),
                'event': 'debug_totals_calculated'
            })

            # 6. Aplicar descuento por cantidad al subtotal antes de calcular impuestos
            final_subtotal = subtotal_after_quantity_discount

            # Recalcular impuestos y total con el descuento aplicado
            taxes = (final_subtotal * Decimal('0.16')).quantize(Decimal('0.01'))  # 16% VAT en USD
            total = (final_subtotal + shipping_cost + taxes).quantize(Decimal('0.01'))  # USD

            order_number = await self._generate_order_number()
            # 7. Create the main Order record (TODO EN USD)
            new_order = Order(
                id=str(uuid.uuid4()),
                order_number=order_number,
                user_id=user_id,
                status=OrderStatus.PENDING.value,
                subtotal=final_subtotal,  # USD (con descuento por cantidad aplicado)
                shipping_cost=shipping_cost,  # USD
                taxes=taxes,  # USD
                total=total,  # USD
                payment_currency=payment_currency,  # "USD" o "VES"
                exchange_rate=exchange_rate,  # Tasa si pagó en VES, None si USD
                payment_method=order_data.payment_method,
                payment_capture_url=order_data.payment_capture_url,
                payment_status="pending",
                customer_notes=order_data.customer_notes,
                quantity_discount_id=discounts_info["quantity_discount"].id if discounts_info["quantity_discount"] else None,
                quantity_discount_amount=discounts_info["quantity_discount_amount"]
            )
            
            # 7. Create the OrderAddress by copying from the user's address book
            order_address = OrderAddress(
                id=str(uuid.uuid4()),
                order_id=new_order.id,
                street=shipping_address.street,
                city=shipping_address.city,
                state=shipping_address.state,
                postal_code=shipping_address.postal_code,
                country=shipping_address.country,
                recipient_name=shipping_address.recipient_name,
                recipient_phone=shipping_address.recipient_phone,
                delivery_instructions=shipping_address.delivery_instructions
            )
            
            # 8. Associate items and address with the order
            # DEBUG: Log order commit
            self.orders_logger.info("DEBUG: Order committed to database", extra={
                'user_id': user_id,
                'order_id': new_order.id,
                'order_number': new_order.order_number,
                'total_items': len(new_order.items),
                'event': 'debug_order_committed'
            })
            new_order.items.extend(order_items)
            new_order.shipping_address = order_address

            # 9. Add to session and commit
            print("🔵 [OrderService] Agregando orden a la sesión...")
            self.db.add(new_order)
            print("🔵 [OrderService] Haciendo commit de la orden...")
            self.db.commit()
            print(f"🟢 [OrderService] Orden commiteada exitosamente: {new_order.id}")
            
            # 10. Guardar descuentos aplicados a la orden
            try:
                print(f"🔵 [OrderService] Guardando descuentos para orden: {new_order.id}")
                self._save_order_discounts(new_order.id, discounts_info)
                print("🟢 [OrderService] Descuentos guardados exitosamente")
            except Exception as e:
                print(f"🔴 [OrderService ERROR] Error guardando descuentos: {e}")
                self.error_logger.error(f"Error guardando descuentos para orden {new_order.id}: {e}")
                # No fallar la creación de la orden por error en descuentos
            
            self.orders_logger.info(
                "Order successfully created",
                extra={
                    'user_id': user_id,
                    'user_email': user_email,
                    'order_id': new_order.id,
                    'order_number': new_order.order_number,
                    'total_amount': new_order.total,
                    'currency': new_order.payment_currency,
                    'items_count': len(new_order.items),
                    'payment_method': new_order.payment_method,
                    'event': 'order_created_successfully'
                }
            )

            print("🔵 [OrderService] Refrescando objeto de orden...")
            self.db.refresh(new_order)
            print("🟢 [OrderService] Orden refrescada, retornando...")
            
            # 11. Send order tracking email to customer
            try:
                from app.services.email_service import email_service
                from app.models.user import User
                
                # Get user information for the email
                user = self.db.query(User).filter(User.id == user_id).first()
                if user and user.email:
                    # Prepare order data for the email
                    order_data = {
                        "order_number": new_order.order_number,
                        "order_date": new_order.created_at.strftime("%d/%m/%Y %H:%M"),
                        "order_total": f"{new_order.total:.2f} {new_order.payment_currency}",
                        "order_status": new_order.status.title(),
                        "payment_method": new_order.payment_method.title() if new_order.payment_method else "N/A",
                        "tracking_link": os.getenv("FRONTEND_URL", "http://localhost:5173") + f"/tracking/{new_order.id}"
                    }
                    
                    # Send tracking email asynchronously
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # If we're already in an async context, create a task
                            asyncio.create_task(
                                email_service.send_order_tracking_email(user.email, order_data)
                            )
                        else:
                            # If we're in a sync context, run the async function
                            loop.run_until_complete(
                                email_service.send_order_tracking_email(user.email, order_data)
                            )
                    except RuntimeError:
                        # If no event loop is available, we'll skip the email
                        print("No event loop available, skipping email sending")
                        pass
                        
            except Exception as email_error:
                # Don't fail the order creation if email fails
                print(f"Failed to send tracking email: {email_error}")
            
            return new_order

        except Exception as e:
            self.db.rollback()
            log_error(
                self.error_logger,
                e,
                context={
                    'user_id': user_id,
                    'operation': 'order_creation',
                    'shipping_address_id': order_data.shipping_address_id,
                    'payment_method': order_data.payment_method
                },
                user_email=user_email
            )
            self.orders_logger.error(
                f"Order creation failed for user {user_id}",
                extra={
                    'user_id': user_id,
                    'user_email': user_email,
                    'error': str(e),
                    'event': 'order_creation_failed'
                }
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An unexpected error occurred while creating the order: {e}"
            )

    def get_order_by_id(self, order_id: str, user_id: str) -> Optional[Order]:
        """Retrieves a single order by its ID, ensuring it belongs to the user."""
        return self.db.query(Order).options(
            joinedload(Order.discounts),
            joinedload(Order.items),
            joinedload(Order.shipping_address)
        ).filter(Order.id == order_id, Order.user_id == user_id).first()

    async def get_user_orders(self, user_id: str) -> List[Order]:
        """Retrieves all orders for a specific user."""
        return self.db.query(Order).options(
            joinedload(Order.discounts)
        ).filter(Order.user_id == user_id).order_by(Order.created_at.desc()).all()

    def _calculate_order_discount_info(self, order: Order) -> dict:
        """
        Calcula información de descuentos para una orden.
        
        Args:
            order: Orden con descuentos cargados
            
        Returns:
            dict con información de descuentos
        """
        if not order.discounts:
            return {
                "total_discounts": 0,
                "total_discount_amount": Decimal('0.00'),
                "discount_breakdown": [],
                "savings_percentage": 0.0,
                "original_subtotal": order.subtotal,
                "total_savings": Decimal('0.00')
            }
        
        total_discount_amount = sum(discount.discount_amount for discount in order.discounts)
        original_subtotal = order.subtotal + total_discount_amount
        savings_percentage = (total_discount_amount / original_subtotal * 100) if original_subtotal > 0 else 0.0
        
        # Convertir descuentos a formato de respuesta usando model_validate
        from app.schemas.order_discount import OrderDiscountResponse
        discount_breakdown = [
            OrderDiscountResponse.model_validate(discount) for discount in order.discounts
        ]
        
        return {
            "total_discounts": len(order.discounts),
            "total_discount_amount": total_discount_amount,
            "discount_breakdown": discount_breakdown,
            "savings_percentage": round(savings_percentage, 2),
            "original_subtotal": original_subtotal,
            "total_savings": total_discount_amount
        }

    async def _generate_order_number(self):
        """Generates a unique, human-readable order number."""
        from datetime import datetime
        import random
        timestamp = datetime.now().strftime("%Y%m%d")
        random_suffix = ''.join(random.choices('0123456789', k=4))
        return f"FP-{timestamp}-{random_suffix}"

    async def _get_exchange_rate(self) -> float:
        """Get current exchange rate from the exchange service."""
        try:
            from app.services.exchange_service import exchange_service
            rate_data = await exchange_service.get_exchange_rate(force_refresh=False)
            if rate_data and "price" in rate_data:
                return rate_data["price"]
            else:
                return Decimal('35.0')  # Default fallback
        except Exception as e:
            self.orders_logger.warning(f"Failed to get exchange rate: {e}")
            return Decimal('35.0')  # Default fallback

    async def calculate_checkout_totals(self, user_id: str, shipping_address_id: str, payment_currency: str = "USD") -> dict:
        """
        Calcula el desglose completo de costos para el checkout sin crear la orden.
        SISTEMA UNIFICADO USD: Todo se calcula en USD.
        
        Args:
            user_id: ID del usuario
            shipping_address_id: ID de la dirección de envío
            payment_currency: Moneda de pago ("USD" o "VES")
            
        Returns:
            dict con el desglose completo de costos
        """
        try:
            # 1. Validar carrito
            cart_items = self.db.query(CartItem).options(
                joinedload(CartItem.product)
            ).filter(CartItem.user_id == user_id).all()
            
            if not cart_items:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El carrito está vacío."
                )

            # 2. Validar dirección de envío
            shipping_address = self.db.query(Address).filter(
                Address.id == shipping_address_id, 
                Address.user_id == user_id
            ).first()
            
            if not shipping_address:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Dirección de envío no encontrada para este usuario."
                )

            # 3. Calcular descuentos aplicables
            discount_service = DiscountService(self.db)
            discounts_info = discount_service.calculate_cart_discounts(cart_items)

            # 4. Calcular subtotal con descuentos aplicados
            subtotal = discounts_info["subtotal_after_discounts"]

            # 4. Obtener costo de envío EN USD
            shipping_zone_id = shipping_address.city.lower().replace(" ", "-")
            shipping_zone = self.db.query(ShippingZone).filter(ShippingZone.id == shipping_zone_id).first()
            shipping_cost = shipping_zone.price if shipping_zone else Decimal('0.00')  # USD
            
            # 5. Calcular impuestos (16% IVA) EN USD
            taxes = (subtotal * Decimal('0.16')).quantize(Decimal('0.01'))  # USD
            
            # 6. Calcular total EN USD
            total = (subtotal + shipping_cost + taxes).quantize(Decimal('0.01'))  # USD

            # 7. Manejar tasa de cambio si es necesario
            exchange_rate = None
            if payment_currency == "VES":
                exchange_rate = await self._get_exchange_rate()

            # 8. Crear OrderAddressSchema para la respuesta
            from app.schemas.order import OrderAddressSchema
            shipping_address_schema = OrderAddressSchema(
                street=shipping_address.street,
                city=shipping_address.city,
                state=shipping_address.state,
                postal_code=shipping_address.postal_code,
                country=shipping_address.country,
                recipient_name=shipping_address.recipient_name,
                recipient_phone=shipping_address.recipient_phone,
                delivery_instructions=shipping_address.delivery_instructions
            )

            # 9. Log para debugging
            self.orders_logger.info("DEBUG: Checkout totals calculated", extra={
                'user_id': user_id,
                'subtotal': str(subtotal),
                'shipping_cost': str(shipping_cost),
                'taxes': str(taxes),
                'total': str(total),
                'payment_currency': payment_currency,
                'exchange_rate': str(exchange_rate),
                'shipping_zone': shipping_zone_id,
                'event': 'debug_checkout_totals_calculated'
            })

            return {
                "subtotal": subtotal,
                "shipping_cost": shipping_cost,
                "taxes": taxes,
                "total": total,
                "payment_currency": payment_currency,
                "exchange_rate": exchange_rate,
                "shipping_zone": shipping_zone_id,
                "shipping_address": shipping_address_schema,
                # Información de descuentos
                "quantity_discount": discounts_info.get("quantity_discount"),
                "quantity_discount_amount": discounts_info.get("quantity_discount_amount", Decimal('0.00')),
                "flash_discounts": discounts_info.get("flash_discounts", []),
                "total_discount": discounts_info.get("total_discount", Decimal('0.00'))
            }

        except HTTPException:
            raise
        except Exception as e:
            self.error_logger.error(f"Error calculating checkout totals: {e}", extra={
                'user_id': user_id,
                'shipping_address_id': shipping_address_id,
                'payment_currency': payment_currency,
                'event': 'error_checkout_totals_calculation'
            })
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error calculando totales del checkout: {str(e)}"
            )

    def _save_order_discounts(self, order_id: str, discounts_info: dict) -> List[OrderDiscount]:
        """
        Guarda los descuentos aplicados a una orden.
        
        Args:
            order_id: ID de la orden
            discounts_info: Información de descuentos del DiscountService
            
        Returns:
            Lista de OrderDiscount creados
        """
        order_discounts = []
        
        try:
            # Guardar descuento por cantidad
            if discounts_info.get('quantity_discount') and discounts_info.get('quantity_discount_amount', 0) > 0:
                quantity_discount = discounts_info['quantity_discount']
                discount_amount = Decimal(str(discounts_info['quantity_discount_amount']))
                
                order_discount = OrderDiscount(
                    order_id=order_id,
                    discount_type=DiscountType.QUANTITY,
                    discount_id=quantity_discount.id,
                    discount_name=quantity_discount.name,
                    discount_description=quantity_discount.description,
                    discount_value=Decimal(str(quantity_discount.discount_value)),
                    discount_amount=discount_amount,
                    applied_to="subtotal",
                    quantity_threshold=f"{quantity_discount.min_quantity}+"
                )
                self.db.add(order_discount)
                order_discounts.append(order_discount)
            
            # Guardar descuentos flash
            if discounts_info.get('flash_discounts'):
                for product_id, discount_amount in discounts_info['flash_discounts'].items():
                    if discount_amount > 0:
                        # Obtener información del producto para el nombre del descuento
                        product = self.db.query(CartItem).filter(
                            CartItem.product_id == product_id
                        ).first()
                        
                        order_discount = OrderDiscount(
                            order_id=order_id,
                            discount_type=DiscountType.FLASH,
                            discount_id=product_id,  # Usar product_id como referencia
                            discount_name=f"Oferta Flash - {product.product.name if product else 'Producto'}",
                            discount_description="Descuento por oferta flash",
                            discount_value=Decimal(str(discount_amount)),
                            discount_amount=Decimal(str(discount_amount)),
                            applied_to="subtotal",
                            product_id=product_id
                        )
                        self.db.add(order_discount)
                        order_discounts.append(order_discount)
            
            # Commit de todos los descuentos
            self.db.commit()
            
            self.orders_logger.info(f"Descuentos guardados para orden {order_id}", extra={
                'order_id': order_id,
                'discounts_count': len(order_discounts),
                'total_discount_amount': float(sum(d.discount_amount for d in order_discounts)),
                'event': 'order_discounts_saved'
            })
            
            return order_discounts
            
        except Exception as e:
            self.error_logger.error(f"Error guardando descuentos para orden {order_id}: {e}", extra={
                'order_id': order_id,
                'event': 'error_saving_order_discounts'
            })
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error guardando descuentos de la orden: {str(e)}"
            )

    
