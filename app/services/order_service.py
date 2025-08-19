import uuid
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.cart import CartItem
from app.models.order import Order, OrderItem, OrderAddress
from app.models.address import Address
from app.models.shipping import ShippingZone
from app.schemas.order import OrderCreate
from app.services.cart_service import CartService

class OrderService:
    def __init__(self, db: Session):
        self.db = db

    def create_order_from_cart(self, user_id: str, order_data: OrderCreate) -> Order:
        """
        Creates a new order from the user's current cart.
        This process is a single transaction: if any part fails, all changes are rolled back.
        """
        print(f"🔍 Creating order from cart for user: {user_id}")
        print(f"🔍 Shipping zone ID: {order_data.shipping_address_id}")
        # 1. Retrieve all items from the user's cart
        cart_items = self.db.query(CartItem).filter(CartItem.user_id == user_id).all()
        if not cart_items:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your cart is empty.")

        # 2. Get the chosen shipping address from the user's address book
        shipping_address = self.db.query(Address).filter(
            Address.id == order_data.shipping_address_id,
            Address.user_id == user_id
        ).first()
        if not shipping_address:
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
                status="processing",
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

            # 10. Clear the user's cart
            cart_service = CartService(self.db)
            cart_service.clear_cart(user_id)

            self.db.refresh(new_order)
            
            return new_order

        except Exception as e:
            self.db.rollback()
            # Log the error e
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

    
