from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.models.cart import CartItem
from app.models.product import Product
from app.schemas.cart import CartDiscountsInfo, CartItemResponse, CartResponse
from app.schemas.product import ProductSummary
from app.services.discount_service import DiscountService


class CartService:
    def __init__(self, db: Session):
        self.db = db

    def add_item(self, user_id: str, product_id: str, quantity: int, selected_presentation: str | None = None):
        """
        Adds a product to the user's cart. If the item already exists, its quantity is updated.
        """
        # OPTIMIZACIÓN: cargar producto + item existente en una sola query con JOIN
        existing_item = (
            self.db.query(CartItem)
            .filter(
                CartItem.user_id == user_id,
                CartItem.product_id == product_id,
                CartItem.selected_presentation == selected_presentation
            )
            .first()
        )
        # Si existe, validar stock contra el producto ya en la relación
        if existing_item and existing_item.product is None:
            existing_item.product = (
                self.db.query(Product).filter(Product.id == product_id).first()
            )

        if existing_item:
            product = existing_item.product
            new_quantity = existing_item.quantity + quantity
            if new_quantity > product.stock:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not enough stock available.")
            existing_item.quantity = new_quantity
        else:
            # Si no existe, cargar producto y crear nuevo item
            product = self.db.query(Product).filter(Product.id == product_id).first()
            if not product:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
            if not product.is_available:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product is out of stock.")
            if quantity > product.stock:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not enough stock available.")
            new_item = CartItem(
                user_id=user_id,
                product_id=product_id,
                quantity=quantity,
                selected_presentation=selected_presentation
            )
            self.db.add(new_item)

        self.db.commit()

    def update_item_quantity(self, user_id: str, item_id: str, new_quantity: int) -> CartItem:
        """
        Updates the quantity of a specific item in the cart.
        """
        cart_item = self._get_cart_item(user_id, item_id)
        
        if new_quantity <= 0:
            # If quantity is zero or less, remove the item
            self.db.delete(cart_item)
            self.db.commit()
            return None # Indicates item was removed
        
        # Check for available stock
        if new_quantity > cart_item.product.stock:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not enough stock available.")
            
        cart_item.quantity = new_quantity
        self.db.commit()
        self.db.refresh(cart_item)
        return cart_item

    def remove_item(self, user_id: str, item_id: str):
        """
        Removes an item from the cart.
        """
        cart_item = self._get_cart_item(user_id, item_id)
        self.db.delete(cart_item)
        self.db.commit()

    def clear_cart(self, user_id: str):
        """
        Removes all items from a user's cart.
        """
        self.db.query(CartItem).filter(CartItem.user_id == user_id).delete()
        self.db.commit()

    def get_user_cart(self, user_id: str) -> CartResponse | None:
        """
        Retrieves the user's cart with detailed product information and calculated totals.
        SISTEMA UNIFICADO USD: Todo calculado en USD únicamente.
        """
        cart_items = self.db.query(CartItem).options(
            joinedload(CartItem.product)
        ).filter(CartItem.user_id == user_id).all()

        if not cart_items:
            return CartResponse(
                items=[],
                total_items=0,
                total_unique_items=0,
                total=Decimal('0.00'),
                discounts=CartDiscountsInfo()
            )

        response_items = []
        total = Decimal('0.00')

        for item in cart_items:
            product = item.product
            # Calcular subtotal EN USD (product.price ya es USD)
            subtotal = (product.price * item.quantity).quantize(Decimal('0.01'))
            total += subtotal

            product_summary = ProductSummary.model_validate(product)

            response_items.append(CartItemResponse(
                id=item.id,
                quantity=item.quantity,
                selected_presentation=item.selected_presentation,
                product=product_summary,
                subtotal=subtotal,  # USD únicamente
                created_at=item.created_at,
                updated_at=item.updated_at
            ))

        # Calcular descuentos aplicables
        discount_service = DiscountService(self.db)
        discounts_info = discount_service.calculate_cart_discounts(cart_items)

        # Crear objeto de descuentos para respuesta
        discounts = CartDiscountsInfo(
            quantity_discount=discounts_info["quantity_discount"],
            quantity_discount_amount=discounts_info["quantity_discount_amount"],
            flash_discounts=discounts_info["flash_discounts"],
            flash_discount_total=discounts_info["flash_discount_total"],
            total_discount=discounts_info["total_discount"],
            subtotal_after_discounts=discounts_info["subtotal_after_discounts"]
        )

        return CartResponse(
            items=response_items,
            total_items=sum(item.quantity for item in cart_items),
            total_unique_items=len(cart_items),
            total=total.quantize(Decimal('0.01')),  # USD únicamente
            discounts=discounts
        )

    def _get_cart_item(self, user_id: str, item_id: str) -> CartItem:
        """
        A helper method to retrieve a specific cart item and ensure it belongs to the user.
        """
        cart_item = self.db.query(CartItem).options(
            joinedload(CartItem.product)
        ).filter(
            CartItem.id == item_id,
            CartItem.user_id == user_id
        ).first()

        if not cart_item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found.")
        
        return cart_item
