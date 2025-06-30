"""
Fixtures adicionales para testing de nuevas funcionalidades
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.category import Category, Brand
from app.models.promotion import FlashOffer, PromotionalCode, DiscountType
from app.models.inventory import InventoryMovement, StockAlert, BatchTracking, MovementType
from app.models.product import Product


@pytest.fixture
def sample_category(db: Session):
    """Crear una categoría de prueba."""
    category = Category(
        name="Medicamentos de Prueba",
        slug="medicamentos-prueba",
        description="Categoría para testing",
        icon="test-icon",
        color="#FF0000",
        is_active=True,
        sort_order=1
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@pytest.fixture
def sample_brand(db: Session):
    """Crear una marca de prueba."""
    brand = Brand(
        name="Test Pharma",
        slug="test-pharma",
        description="Farmacéutica de prueba",
        logo_url="https://example.com/test-pharma.png",
        is_featured=True,
        is_active=True
    )
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


@pytest.fixture
def sample_product_with_relations(db: Session, sample_category, sample_brand):
    """Crear un producto con todas las relaciones nuevas."""
    product = Product(
        name="Producto de Prueba",
        brand="Test Pharma",  # Legacy
        category="Medicamentos de Prueba",  # Legacy
        brand_id=sample_brand.id,
        category_id=sample_category.id,
        price_ves=50.00,
        price_ref=10.00,
        description="Producto para testing",
        image="test-product.jpg",
        sku="TEST-PROD-001",
        slug="producto-de-prueba",
        stock=100,
        prescription=False,
        is_active=True
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@pytest.fixture
def sample_flash_offer(db: Session, sample_product_with_relations):
    """Crear una flash offer de prueba."""
    offer = FlashOffer(
        product_id=sample_product_with_relations.id,
        discount_type=DiscountType.PERCENTAGE,
        discount_value=25.0,
        start_time=datetime.utcnow() - timedelta(hours=1),
        end_time=datetime.utcnow() + timedelta(hours=23),
        max_quantity=50,
        used_quantity=0,
        is_active=True
    )
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return offer


@pytest.fixture
def sample_promotional_code(db: Session, sample_category):
    """Crear un código promocional de prueba."""
    code = PromotionalCode(
        code="TESTCODE20",
        description="Código de prueba 20% descuento",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=20.0,
        min_amount=100.0,
        max_discount=50.0,
        usage_limit=100,
        used_count=0,
        user_limit=1,
        valid_from=datetime.utcnow() - timedelta(days=1),
        valid_until=datetime.utcnow() + timedelta(days=30),
        applicable_categories=[sample_category.id],
        is_active=True
    )
    db.add(code)
    db.commit()
    db.refresh(code)
    return code


@pytest.fixture
def sample_stock_alert(db: Session, sample_product_with_relations):
    """Crear una alerta de stock de prueba."""
    alert = StockAlert(
        product_id=sample_product_with_relations.id,
        min_stock_threshold=20,
        max_stock_threshold=500,
        is_low_stock=False,
        is_out_of_stock=False,
        is_overstocked=False
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


@pytest.fixture
def sample_batch_tracking(db: Session, sample_product_with_relations):
    """Crear un seguimiento de lote de prueba."""
    batch = BatchTracking(
        product_id=sample_product_with_relations.id,
        batch_number="TEST-BATCH-001",
        manufacture_date=datetime.utcnow() - timedelta(days=30),
        expiry_date=datetime.utcnow() + timedelta(days=730),
        initial_quantity=100,
        current_quantity=90,
        reserved_quantity=10,
        unit_cost=25.00,
        selling_price=50.00,
        supplier_name="Proveedor Test",
        supplier_invoice="INV-TEST-001",
        quality_checked=True,
        quality_status="approved",
        quality_notes="Lote aprobado para testing",
        is_active=True
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


@pytest.fixture
def sample_inventory_movement(db: Session, sample_product_with_relations, test_admin_user):
    """Crear un movimiento de inventario de prueba."""
    movement = InventoryMovement(
        product_id=sample_product_with_relations.id,
        movement_type=MovementType.IN,
        quantity=50,
        reason="Entrada de prueba",
        reference_id="TEST-REF-001",
        unit_cost=25.00,
        total_cost=1250.00,
        stock_before=100,
        stock_after=150,
        user_id=test_admin_user.id
    )
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return movement


@pytest.fixture
def complete_product_setup(db: Session, test_admin_user):
    """Fixture completo con producto y todo su ecosistema."""
    # Crear categoría
    category = Category(
        name="Vitaminas Completas",
        slug="vitaminas-completas",
        description="Categoría completa para testing",
        is_active=True
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    
    # Crear marca
    brand = Brand(
        name="VitaComplete",
        slug="vita-complete",
        description="Marca completa para testing",
        is_featured=True,
        is_active=True
    )
    db.add(brand)
    db.commit()
    db.refresh(brand)
    
    # Crear producto
    product = Product(
        name="Multivitamínico Completo",
        brand="VitaComplete",
        category="Vitaminas Completas",
        brand_id=brand.id,
        category_id=category.id,
        price_ves=75.00,
        price_ref=15.00,
        description="Multivitamínico para testing completo",
        image="multivit-complete.jpg",
        sku="MULTI-COMPLETE-001",
        slug="multivitaminico-completo",
        stock=200,
        is_active=True
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    
    # Crear alerta de stock
    stock_alert = StockAlert(
        product_id=product.id,
        min_stock_threshold=30,
        max_stock_threshold=800
    )
    db.add(stock_alert)
    db.commit()
    
    # Crear lote
    batch = BatchTracking(
        product_id=product.id,
        batch_number="COMPLETE-2024-001",
        manufacture_date=datetime.utcnow() - timedelta(days=45),
        expiry_date=datetime.utcnow() + timedelta(days=900),
        initial_quantity=200,
        current_quantity=200,
        unit_cost=37.50,
        selling_price=75.00,
        supplier_name="Distribuidor Completo S.A.",
        quality_checked=True,
        quality_status="approved"
    )
    db.add(batch)
    db.commit()
    
    # Crear flash offer
    flash_offer = FlashOffer(
        product_id=product.id,
        discount_type=DiscountType.PERCENTAGE,
        discount_value=30.0,
        start_time=datetime.utcnow(),
        end_time=datetime.utcnow() + timedelta(days=7),
        max_quantity=100,
        is_active=True
    )
    db.add(flash_offer)
    db.commit()
    
    # Crear código promocional
    promo_code = PromotionalCode(
        code="COMPLETE30",
        description="30% descuento en productos completos",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=30.0,
        min_amount=200.0,
        usage_limit=50,
        user_limit=1,
        valid_from=datetime.utcnow(),
        valid_until=datetime.utcnow() + timedelta(days=15),
        applicable_products=[product.id],
        is_active=True
    )
    db.add(promo_code)
    db.commit()
    
    # Crear movimiento inicial de inventario
    inventory_movement = InventoryMovement(
        product_id=product.id,
        movement_type=MovementType.IN,
        quantity=200,
        reason="Stock inicial para testing completo",
        reference_id="COMPLETE-INIT-001",
        unit_cost=37.50,
        total_cost=7500.00,
        stock_before=0,
        stock_after=200,
        user_id=test_admin_user.id
    )
    db.add(inventory_movement)
    db.commit()
    
    return {
        "category": category,
        "brand": brand,
        "product": product,
        "stock_alert": stock_alert,
        "batch": batch,
        "flash_offer": flash_offer,
        "promo_code": promo_code,
        "inventory_movement": inventory_movement
    }


@pytest.fixture
def expired_products_setup(db: Session):
    """Setup para testing de productos próximos a vencer."""
    # Producto con lotes variados
    product = Product(
        name="Antibiótico Test",
        brand="Pharma Test",
        category="Antibióticos",
        price_ves=120.00,
        price_ref=24.00,
        description="Antibiótico para testing de vencimientos",
        image="antibiotico-test.jpg",
        stock=0
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    
    current_time = datetime.utcnow()
    
    # Lote próximo a vencer (15 días)
    expiring_batch = BatchTracking(
        product_id=product.id,
        batch_number="EXP-SOON-001",
        expiry_date=current_time + timedelta(days=15),
        initial_quantity=30,
        current_quantity=30,
        unit_cost=60.00
    )
    
    # Lote con fecha normal (6 meses)
    normal_batch = BatchTracking(
        product_id=product.id,
        batch_number="NORMAL-001",
        expiry_date=current_time + timedelta(days=180),
        initial_quantity=50,
        current_quantity=50,
        unit_cost=58.00
    )
    
    # Lote expirado
    expired_batch = BatchTracking(
        product_id=product.id,
        batch_number="EXPIRED-001",
        expiry_date=current_time - timedelta(days=10),
        initial_quantity=20,
        current_quantity=20,
        unit_cost=65.00
    )
    
    db.add_all([expiring_batch, normal_batch, expired_batch])
    db.commit()
    
    return {
        "product": product,
        "expiring_batch": expiring_batch,
        "normal_batch": normal_batch,
        "expired_batch": expired_batch
    }


@pytest.fixture
def promotion_scenarios(db: Session, sample_category, sample_brand):
    """Setup para diferentes escenarios de promociones."""
    # Crear productos para diferentes tipos de promociones
    products = []
    
    # Producto con flash offer
    product_flash = Product(
        name="Producto Flash",
        brand="Test Brand",
        category="Test Category",
        brand_id=sample_brand.id,
        category_id=sample_category.id,
        price_ves=100.00,
        price_ref=20.00,
        description="Producto con flash offer",
        image="flash.jpg",
        stock=50
    )
    products.append(product_flash)
    
    # Producto con código promocional
    product_promo = Product(
        name="Producto Promocional",
        brand="Test Brand",
        category="Test Category",  
        brand_id=sample_brand.id,
        category_id=sample_category.id,
        price_ves=80.00,
        price_ref=16.00,
        description="Producto con código promocional",
        image="promo.jpg",
        stock=30
    )
    products.append(product_promo)
    
    for product in products:
        db.add(product)
    db.commit()
    
    for product in products:
        db.refresh(product)
    
    # Crear flash offer activa
    flash_offer = FlashOffer(
        product_id=product_flash.id,
        discount_type=DiscountType.FIXED,
        discount_value=15.0,
        start_time=datetime.utcnow() - timedelta(hours=2),
        end_time=datetime.utcnow() + timedelta(hours=22),
        max_quantity=25,
        is_active=True
    )
    db.add(flash_offer)
    
    # Crear código promocional por categoría
    promo_code_category = PromotionalCode(
        code="CATEGORY15",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=15.0,
        valid_from=datetime.utcnow(),
        valid_until=datetime.utcnow() + timedelta(days=7),
        applicable_categories=[sample_category.id],
        is_active=True
    )
    db.add(promo_code_category)
    
    # Crear código promocional por producto específico
    promo_code_product = PromotionalCode(
        code="PRODUCT20",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=20.0,
        valid_from=datetime.utcnow(),
        valid_until=datetime.utcnow() + timedelta(days=10),
        applicable_products=[product_promo.id],
        user_limit=2,
        is_active=True
    )
    db.add(promo_code_product)
    
    db.commit()
    
    return {
        "product_flash": product_flash,
        "product_promo": product_promo,
        "flash_offer": flash_offer,
        "promo_code_category": promo_code_category,
        "promo_code_product": promo_code_product
    } 