import os
import uuid
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.cart import CartItem
from app.models.order import Order, OrderItem, OrderAddress, OrderStatus
from app.models.address import Address
from app.models.shipping import ShippingZone
from app.schemas.order import OrderCreate
from app.services.cart_service import CartService
from app.config.logging_config import get_logger, log_error
from dotenv import load_dotenv

load_dotenv()

class OrderService:
    def __init__(self, db: Session):
        self.db = db
        self.orders_logger = get_logger("orders")
        self.error_logger = get_logger("errors")

    def create_order_from_cart(self, user_id: str, order_data: OrderCreate) -> Order:
        """
        Creates a new order from the user's current cart.
        This process is a single transaction: if any part fails, all changes are rolled back.
        """
        # Obtener email del usuario para logging
        user_email = None
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if user:
                user_email = user.email
        except Exception:
            pass
        
        self.orders_logger.info(
            f"Starting order creation from cart",
            extra={
                'user_id': user_id,
                'user_email': user_email,
                'shipping_address_id': order_data.shipping_address_id,
                'payment_method': order_data.payment_method,
                'event': 'order_creation_started'
            }
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
            # 3. Initialize order totals
            subtotal = 0.0
            order_items = []

            # 4. Create OrderItems and calculate subtotal
            for item in cart_items:
                product = item.product
                if not product or not product.is_available or product.stock < item.quantity:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Product '{product.name}' is out of stock or unavailable."
                    )
                
                total_price = product.price_ves * item.quantity
                subtotal += total_price

                order_item = OrderItem(
                    id=str(uuid.uuid4()),
                    product_id=product.id,
                    quantity=item.quantity,
                    unit_price=product.price_ves,
                    total_price=total_price,
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

            # 5. Define shipping, taxes, and total based on the address's city
            shipping_zone_id = shipping_address.city.lower().replace(" ", "-")
            shipping_zone = self.db.query(ShippingZone).filter(ShippingZone.id == shipping_zone_id).first()
            
            shipping_cost = shipping_zone.price if shipping_zone else 0.0 # Default to 0 if no zone found
            taxes = subtotal * 0.16  # Example 16% VAT
            total = subtotal + shipping_cost + taxes

            # 6. Create the main Order record
            new_order = Order(
                id=str(uuid.uuid4()),
                order_number=self._generate_order_number(),
                user_id=user_id,
                status=OrderStatus.PENDING.value,
                subtotal=subtotal,
                shipping_cost=shipping_cost,
                taxes=taxes,
                total=total,
                currency="VES",
                payment_method=order_data.payment_method,
                payment_capture_url=order_data.payment_capture_url,
                payment_status="pending",
                customer_notes=order_data.customer_notes
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
            new_order.items.extend(order_items)
            new_order.shipping_address = order_address

            # 9. Add to session and commit
            self.db.add(new_order)
            self.db.commit()
            
            self.orders_logger.info(
                f"Order successfully created",
                extra={
                    'user_id': user_id,
                    'user_email': user_email,
                    'order_id': new_order.id,
                    'order_number': new_order.order_number,
                    'total_amount': new_order.total,
                    'currency': new_order.currency,
                    'items_count': len(new_order.items),
                    'payment_method': new_order.payment_method,
                    'event': 'order_created_successfully'
                }
            )

            # 10. Clear the user's cart
            cart_service = CartService(self.db)
            cart_service.clear_cart(user_id)

            self.db.refresh(new_order)
            
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
                        "order_total": f"{new_order.total:.2f} {new_order.currency}",
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
        return self.db.query(Order).filter(Order.id == order_id, Order.user_id == user_id).first()

    def get_user_orders(self, user_id: str) -> List[Order]:
        """Retrieves all orders for a specific user."""
        return self.db.query(Order).filter(Order.user_id == user_id).order_by(Order.created_at.desc()).all()

    def _generate_order_number(self):
        """Generates a unique, human-readable order number."""
        from datetime import datetime
        import random
        timestamp = datetime.now().strftime("%Y%m%d")
        random_suffix = ''.join(random.choices('0123456789', k=4))
        return f"FP-{timestamp}-{random_suffix}"

    
