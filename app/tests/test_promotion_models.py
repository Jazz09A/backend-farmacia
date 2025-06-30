"""
Tests para los modelos del sistema de promociones
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.promotion import (
    FlashOffer, PromotionalCode, PromotionUsage, 
    DiscountType
)
from app.models.product import Product
from app.models.user import User
from app.models.order import Order


class TestFlashOfferModel:
    """Tests para el modelo FlashOffer."""
    
    @pytest.fixture
    def sample_product(self, db: Session):
        """Crear un producto de prueba."""
        product = Product(
            name="Vitamina D",
            brand="Test Brand",
            category="Vitaminas",
            price_ves=30.00,
            price_ref=6.00,
            description="Vitamina D 1000IU",
            image="vitamin-d.jpg"
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        return product
    
    def test_create_flash_offer_percentage(self, db: Session, sample_product):
        """Test crear flash offer con descuento porcentual."""
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(hours=24)
        
        offer = FlashOffer(
            product_id=sample_product.id,
            discount_type=DiscountType.PERCENTAGE,
            discount_value=20.0,
            start_time=start_time,
            end_time=end_time,
            max_quantity=100
        )
        
        db.add(offer)
        db.commit()
        db.refresh(offer)
        
        assert offer.id is not None
        assert offer.product_id == sample_product.id
        assert offer.discount_type == DiscountType.PERCENTAGE
        assert offer.discount_value == 20.0
        assert offer.max_quantity == 100
        assert offer.used_quantity == 0
        assert offer.is_active is True
    
    def test_create_flash_offer_fixed(self, db: Session, sample_product):
        """Test crear flash offer con descuento fijo."""
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(days=3)
        
        offer = FlashOffer(
            product_id=sample_product.id,
            discount_type=DiscountType.FIXED,
            discount_value=5.0,
            start_time=start_time,
            end_time=end_time
        )
        
        db.add(offer)
        db.commit()
        db.refresh(offer)
        
        assert offer.discount_type == DiscountType.FIXED
        assert offer.discount_value == 5.0
        assert offer.max_quantity is None
    
    def test_flash_offer_is_valid_property(self, db: Session, sample_product):
        """Test propiedad is_valid de flash offer."""
        now = datetime.utcnow()
        
        # Offer válida (activa y en tiempo)
        valid_offer = FlashOffer(
            product_id=sample_product.id,
            discount_type=DiscountType.PERCENTAGE,
            discount_value=15.0,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
            max_quantity=10,
            used_quantity=5
        )
        
        # Offer expirada
        expired_offer = FlashOffer(
            product_id=sample_product.id,
            discount_type=DiscountType.PERCENTAGE,
            discount_value=15.0,
            start_time=now - timedelta(hours=2),
            end_time=now - timedelta(hours=1)
        )
        
        # Offer agotada
        exhausted_offer = FlashOffer(
            product_id=sample_product.id,
            discount_type=DiscountType.PERCENTAGE,
            discount_value=15.0,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
            max_quantity=10,
            used_quantity=10
        )
        
        # Offer inactiva
        inactive_offer = FlashOffer(
            product_id=sample_product.id,
            discount_type=DiscountType.PERCENTAGE,
            discount_value=15.0,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
            is_active=False
        )
        
        assert valid_offer.is_valid is True
        assert expired_offer.is_valid is False
        assert exhausted_offer.is_valid is False
        assert inactive_offer.is_valid is False
    
    def test_flash_offer_calculate_discount(self, db: Session, sample_product):
        """Test cálculo de descuento."""
        # Descuento porcentual
        percentage_offer = FlashOffer(
            product_id=sample_product.id,
            discount_type=DiscountType.PERCENTAGE,
            discount_value=25.0,
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=1)
        )
        
        # Descuento fijo
        fixed_offer = FlashOffer(
            product_id=sample_product.id,
            discount_type=DiscountType.FIXED,
            discount_value=8.0,
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=1)
        )
        
        original_price = 40.0
        
        assert percentage_offer.calculate_discount_amount(original_price) == 10.0  # 25% de 40
        assert fixed_offer.calculate_discount_amount(original_price) == 8.0
        
        # Descuento fijo mayor al precio original
        assert fixed_offer.calculate_discount_amount(5.0) == 5.0  # No puede ser mayor al precio


class TestPromotionalCodeModel:
    """Tests para el modelo PromotionalCode."""
    
    def test_create_promotional_code(self, db: Session):
        """Test crear código promocional."""
        valid_from = datetime.utcnow()
        valid_until = valid_from + timedelta(days=30)
        
        code = PromotionalCode(
            code="SAVE20",
            description="Descuento 20% en toda la tienda",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=20.0,
            min_amount=50.0,
            max_discount=100.0,
            usage_limit=1000,
            user_limit=1,
            valid_from=valid_from,
            valid_until=valid_until,
            applicable_categories=["vitaminas", "analgesicos"],
            applicable_products=["product-1", "product-2"]
        )
        
        db.add(code)
        db.commit()
        db.refresh(code)
        
        assert code.id is not None
        assert code.code == "SAVE20"
        assert code.discount_value == 20.0
        assert code.min_amount == 50.0
        assert code.max_discount == 100.0
        assert code.usage_limit == 1000
        assert code.used_count == 0
        assert code.user_limit == 1
        assert code.applicable_categories == ["vitaminas", "analgesicos"]
        assert code.applicable_products == ["product-1", "product-2"]
    
    def test_promotional_code_is_valid_property(self, db: Session):
        """Test propiedad is_valid de código promocional."""
        now = datetime.utcnow()
        
        # Código válido
        valid_code = PromotionalCode(
            code="VALID",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=10.0,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=1),
            usage_limit=100,
            used_count=50
        )
        
        # Código expirado
        expired_code = PromotionalCode(
            code="EXPIRED",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=10.0,
            valid_from=now - timedelta(days=2),
            valid_until=now - timedelta(days=1)
        )
        
        # Código agotado
        exhausted_code = PromotionalCode(
            code="EXHAUSTED",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=10.0,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=1),
            usage_limit=10,
            used_count=10
        )
        
        assert valid_code.is_valid is True
        assert expired_code.is_valid is False
        assert exhausted_code.is_valid is False
    
    def test_promotional_code_can_be_used_by_user(self, db: Session, test_user):
        """Test si código puede ser usado por usuario específico."""
        code = PromotionalCode(
            code="USERTEST",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=15.0,
            valid_from=datetime.utcnow() - timedelta(days=1),
            valid_until=datetime.utcnow() + timedelta(days=1),
            user_limit=2
        )
        
        db.add(code)
        db.commit()
        db.refresh(code)
        
        # Usuario sin usos previos
        assert code.can_be_used_by_user(test_user.id) is True
        
        # Agregar un uso
        usage1 = PromotionUsage(
            promotional_code_id=code.id,
            user_id=test_user.id,
            discount_amount=10.0,
            order_amount=100.0
        )
        db.add(usage1)
        db.commit()
        
        # Refrescar relaciones
        db.refresh(code)
        
        # Aún puede usar (limit = 2)
        assert code.can_be_used_by_user(test_user.id) is True
        
        # Agregar segundo uso
        usage2 = PromotionUsage(
            promotional_code_id=code.id,
            user_id=test_user.id,
            discount_amount=15.0,
            order_amount=150.0
        )
        db.add(usage2)
        db.commit()
        db.refresh(code)
        
        # Ya no puede usar más
        assert code.can_be_used_by_user(test_user.id) is False
    
    def test_promotional_code_calculate_discount(self, db: Session):
        """Test cálculo de descuento del código promocional."""
        # Código con descuento porcentual
        percentage_code = PromotionalCode(
            code="PERCENT20",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=20.0,
            min_amount=100.0,
            max_discount=50.0,
            valid_from=datetime.utcnow(),
            valid_until=datetime.utcnow() + timedelta(days=1)
        )
        
        # Código con descuento fijo
        fixed_code = PromotionalCode(
            code="FIXED10",
            discount_type=DiscountType.FIXED,
            discount_value=10.0,
            min_amount=50.0,
            valid_from=datetime.utcnow(),
            valid_until=datetime.utcnow() + timedelta(days=1)
        )
        
        # Test descuento porcentual
        assert percentage_code.calculate_discount(200.0) == 40.0  # 20% de 200
        assert percentage_code.calculate_discount(300.0) == 50.0  # Limitado por max_discount
        assert percentage_code.calculate_discount(50.0) == 0.0   # Menos que min_amount
        
        # Test descuento fijo
        assert fixed_code.calculate_discount(100.0) == 10.0
        assert fixed_code.calculate_discount(30.0) == 0.0  # Menos que min_amount


class TestPromotionUsageModel:
    """Tests para el modelo PromotionUsage."""
    
    def test_create_promotion_usage(self, db: Session, test_user):
        """Test crear uso de promoción."""
        # Crear código promocional
        code = PromotionalCode(
            code="TESTUSAGE",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=10.0,
            valid_from=datetime.utcnow(),
            valid_until=datetime.utcnow() + timedelta(days=1)
        )
        db.add(code)
        db.commit()
        db.refresh(code)
        
        # Crear uso
        usage = PromotionUsage(
            promotional_code_id=code.id,
            user_id=test_user.id,
            discount_amount=12.50,
            order_amount=125.0
        )
        
        db.add(usage)
        db.commit()
        db.refresh(usage)
        
        assert usage.id is not None
        assert usage.promotional_code_id == code.id
        assert usage.user_id == test_user.id
        assert usage.discount_amount == 12.50
        assert usage.order_amount == 125.0
        assert usage.used_at is not None
    
    def test_promotion_usage_relationships(self, db: Session, test_user):
        """Test relaciones del modelo PromotionUsage."""
        code = PromotionalCode(
            code="RELATIONTEST",
            discount_type=DiscountType.FIXED,
            discount_value=5.0,
            valid_from=datetime.utcnow(),
            valid_until=datetime.utcnow() + timedelta(days=1)
        )
        db.add(code)
        db.commit()
        db.refresh(code)
        
        usage = PromotionUsage(
            promotional_code_id=code.id,
            user_id=test_user.id,
            discount_amount=5.0,
            order_amount=50.0
        )
        db.add(usage)
        db.commit()
        db.refresh(usage)
        
        # Verificar relaciones
        assert usage.promotional_code.code == "RELATIONTEST"
        assert usage.user.email == test_user.email
        assert len(code.usages) == 1
        assert code.usages[0].id == usage.id 