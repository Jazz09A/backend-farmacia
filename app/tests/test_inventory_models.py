"""
Tests para los modelos del sistema de inventario
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.inventory import (
    InventoryMovement, StockAlert, BatchTracking, MovementType
)
from app.models.product import Product
from app.models.user import User


class TestInventoryMovementModel:
    """Tests para el modelo InventoryMovement."""
    
    @pytest.fixture
    def sample_product(self, db: Session):
        """Crear un producto de prueba."""
        product = Product(
            name="Paracetamol",
            brand="Test Pharma",
            category="Analgésicos",
            price_ves=12.50,
            price_ref=2.50,
            description="Paracetamol 500mg",
            image="paracetamol.jpg",
            stock=100
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        return product
    
    def test_create_inventory_movement_in(self, db: Session, sample_product, test_admin_user):
        """Test crear movimiento de entrada de inventario."""
        movement = InventoryMovement(
            product_id=sample_product.id,
            movement_type=MovementType.IN,
            quantity=50,
            reason="Compra de mercancía",
            reference_id="PO-001",
            unit_cost=8.00,
            total_cost=400.00,
            stock_before=100,
            stock_after=150,
            user_id=test_admin_user.id
        )
        
        db.add(movement)
        db.commit()
        db.refresh(movement)
        
        assert movement.id is not None
        assert movement.product_id == sample_product.id
        assert movement.movement_type == MovementType.IN
        assert movement.quantity == 50
        assert movement.reason == "Compra de mercancía"
        assert movement.reference_id == "PO-001"
        assert movement.unit_cost == 8.00
        assert movement.total_cost == 400.00
        assert movement.stock_before == 100
        assert movement.stock_after == 150
        assert movement.user_id == test_admin_user.id
    
    def test_create_inventory_movement_out(self, db: Session, sample_product, test_admin_user):
        """Test crear movimiento de salida de inventario."""
        movement = InventoryMovement(
            product_id=sample_product.id,
            movement_type=MovementType.OUT,
            quantity=25,
            reason="Venta",
            reference_id="ORDER-123",
            stock_before=100,
            stock_after=75,
            user_id=test_admin_user.id
        )
        
        db.add(movement)
        db.commit()
        db.refresh(movement)
        
        assert movement.movement_type == MovementType.OUT
        assert movement.quantity == 25
        assert movement.reason == "Venta"
        assert movement.stock_before == 100
        assert movement.stock_after == 75
    
    def test_create_inventory_movement_adjustment(self, db: Session, sample_product, test_admin_user):
        """Test crear movimiento de ajuste de inventario."""
        movement = InventoryMovement(
            product_id=sample_product.id,
            movement_type=MovementType.ADJUSTMENT,
            quantity=-5,  # Ajuste negativo
            reason="Producto dañado",
            stock_before=100,
            stock_after=95,
            user_id=test_admin_user.id
        )
        
        db.add(movement)
        db.commit()
        db.refresh(movement)
        
        assert movement.movement_type == MovementType.ADJUSTMENT
        assert movement.quantity == -5
        assert movement.reason == "Producto dañado"
    
    def test_inventory_movement_relationships(self, db: Session, sample_product, test_admin_user):
        """Test relaciones del modelo InventoryMovement."""
        movement = InventoryMovement(
            product_id=sample_product.id,
            movement_type=MovementType.IN,
            quantity=20,
            stock_before=100,
            stock_after=120,
            user_id=test_admin_user.id
        )
        
        db.add(movement)
        db.commit()
        db.refresh(movement)
        
        # Verificar relaciones
        assert movement.product.name == "Paracetamol"
        assert movement.user.role == "admin"
        assert len(sample_product.inventory_movements) == 1
        assert len(test_admin_user.inventory_movements) == 1


class TestStockAlertModel:
    """Tests para el modelo StockAlert."""
    
    @pytest.fixture
    def sample_product(self, db: Session):
        """Crear un producto de prueba."""
        product = Product(
            name="Ibuprofeno",
            brand="Test Pharma",
            category="Analgésicos",
            price_ves=18.00,
            price_ref=3.60,
            description="Ibuprofeno 400mg",
            image="ibuprofeno.jpg",
            stock=50
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        return product
    
    def test_create_stock_alert(self, db: Session, sample_product):
        """Test crear alerta de stock."""
        alert = StockAlert(
            product_id=sample_product.id,
            min_stock_threshold=10,
            max_stock_threshold=500
        )
        
        db.add(alert)
        db.commit()
        db.refresh(alert)
        
        assert alert.id is not None
        assert alert.product_id == sample_product.id
        assert alert.min_stock_threshold == 10
        assert alert.max_stock_threshold == 500
        assert alert.is_low_stock is False
        assert alert.is_out_of_stock is False
        assert alert.is_overstocked is False
        assert alert.low_stock_notified is False
        assert alert.out_of_stock_notified is False
        assert alert.overstocked_notified is False
    
    def test_stock_alert_check_levels_normal(self, db: Session, sample_product):
        """Test verificación de niveles de stock normal."""
        alert = StockAlert(
            product_id=sample_product.id,
            min_stock_threshold=10,
            max_stock_threshold=200
        )
        
        db.add(alert)
        db.commit()
        db.refresh(alert)
        
        # Stock normal (50 unidades)
        alert.check_stock_levels(50)
        
        assert alert.is_low_stock is False
        assert alert.is_out_of_stock is False
        assert alert.is_overstocked is False
    
    def test_stock_alert_check_levels_low_stock(self, db: Session, sample_product):
        """Test verificación de stock bajo."""
        alert = StockAlert(
            product_id=sample_product.id,
            min_stock_threshold=10,
            max_stock_threshold=200
        )
        
        db.add(alert)
        db.commit()
        db.refresh(alert)
        
        # Stock bajo (5 unidades)
        alert.check_stock_levels(5)
        
        assert alert.is_low_stock is True
        assert alert.is_out_of_stock is False
        assert alert.is_overstocked is False
    
    def test_stock_alert_check_levels_out_of_stock(self, db: Session, sample_product):
        """Test verificación de stock agotado."""
        alert = StockAlert(
            product_id=sample_product.id,
            min_stock_threshold=10,
            max_stock_threshold=200
        )
        
        db.add(alert)
        db.commit()
        db.refresh(alert)
        
        # Stock agotado (0 unidades)
        alert.check_stock_levels(0)
        
        assert alert.is_low_stock is False
        assert alert.is_out_of_stock is True
        assert alert.is_overstocked is False
    
    def test_stock_alert_check_levels_overstocked(self, db: Session, sample_product):
        """Test verificación de sobrestock."""
        alert = StockAlert(
            product_id=sample_product.id,
            min_stock_threshold=10,
            max_stock_threshold=200
        )
        
        db.add(alert)
        db.commit()
        db.refresh(alert)
        
        # Sobrestock (300 unidades)
        alert.check_stock_levels(300)
        
        assert alert.is_low_stock is False
        assert alert.is_out_of_stock is False
        assert alert.is_overstocked is True
    
    def test_stock_alert_product_relationship(self, db: Session, sample_product):
        """Test relación única con producto."""
        alert = StockAlert(
            product_id=sample_product.id,
            min_stock_threshold=5,
            max_stock_threshold=100
        )
        
        db.add(alert)
        db.commit()
        db.refresh(alert)
        
        assert alert.product.name == "Ibuprofeno"
        assert sample_product.stock_alert.id == alert.id


class TestBatchTrackingModel:
    """Tests para el modelo BatchTracking."""
    
    @pytest.fixture
    def sample_product(self, db: Session):
        """Crear un producto de prueba."""
        product = Product(
            name="Vitamina B12",
            brand="VitaMax",
            category="Vitaminas",
            price_ves=35.00,
            price_ref=7.00,
            description="Vitamina B12 1000mcg",
            image="vitamin-b12.jpg",
            stock=200
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        return product
    
    def test_create_batch_tracking(self, db: Session, sample_product):
        """Test crear seguimiento de lote."""
        manufacture_date = datetime.utcnow() - timedelta(days=30)
        expiry_date = datetime.utcnow() + timedelta(days=730)  # 2 años
        
        batch = BatchTracking(
            product_id=sample_product.id,
            batch_number="VB12-2024-001",
            manufacture_date=manufacture_date,
            expiry_date=expiry_date,
            initial_quantity=200,
            current_quantity=180,
            reserved_quantity=20,
            unit_cost=15.00,
            selling_price=35.00,
            supplier_name="Laboratorios XYZ",
            supplier_invoice="INV-2024-001",
            quality_checked=True,
            quality_status="approved",
            quality_notes="Lote aprobado sin observaciones"
        )
        
        db.add(batch)
        db.commit()
        db.refresh(batch)
        
        assert batch.id is not None
        assert batch.product_id == sample_product.id
        assert batch.batch_number == "VB12-2024-001"
        assert batch.initial_quantity == 200
        assert batch.current_quantity == 180
        assert batch.reserved_quantity == 20
        assert batch.unit_cost == 15.00
        assert batch.selling_price == 35.00
        assert batch.supplier_name == "Laboratorios XYZ"
        assert batch.quality_checked is True
        assert batch.quality_status == "approved"
        assert batch.is_active is True
    
    def test_batch_available_quantity(self, db: Session, sample_product):
        """Test propiedad available_quantity."""
        batch = BatchTracking(
            product_id=sample_product.id,
            batch_number="TEST-001",
            initial_quantity=100,
            current_quantity=80,
            reserved_quantity=15
        )
        
        assert batch.available_quantity == 65  # 80 - 15
    
    def test_batch_is_expired(self, db: Session, sample_product):
        """Test propiedad is_expired."""
        # Lote expirado
        expired_batch = BatchTracking(
            product_id=sample_product.id,
            batch_number="EXPIRED-001",
            expiry_date=datetime.utcnow() - timedelta(days=1),
            initial_quantity=50,
            current_quantity=50
        )
        
        # Lote válido
        valid_batch = BatchTracking(
            product_id=sample_product.id,
            batch_number="VALID-001",
            expiry_date=datetime.utcnow() + timedelta(days=365),
            initial_quantity=50,
            current_quantity=50
        )
        
        # Lote sin fecha de expiración
        no_expiry_batch = BatchTracking(
            product_id=sample_product.id,
            batch_number="NOEXP-001",
            initial_quantity=50,
            current_quantity=50
        )
        
        assert expired_batch.is_expired is True
        assert valid_batch.is_expired is False
        assert no_expiry_batch.is_expired is False
    
    def test_batch_days_to_expiry(self, db: Session, sample_product):
        """Test propiedad days_to_expiry."""
        # Lote que expira en 30 días
        future_batch = BatchTracking(
            product_id=sample_product.id,
            batch_number="FUTURE-001",
            expiry_date=datetime.utcnow() + timedelta(days=30),
            initial_quantity=50,
            current_quantity=50
        )
        
        # Lote expirado
        expired_batch = BatchTracking(
            product_id=sample_product.id,
            batch_number="EXPIRED-001",
            expiry_date=datetime.utcnow() - timedelta(days=5),
            initial_quantity=50,
            current_quantity=50
        )
        
        # Lote sin fecha de expiración
        no_expiry_batch = BatchTracking(
            product_id=sample_product.id,
            batch_number="NOEXP-001",
            initial_quantity=50,
            current_quantity=50
        )
        
        assert future_batch.days_to_expiry == 30
        assert expired_batch.days_to_expiry == 0
        assert no_expiry_batch.days_to_expiry is None
    
    def test_batch_product_relationship(self, db: Session, sample_product):
        """Test relación con producto."""
        batch1 = BatchTracking(
            product_id=sample_product.id,
            batch_number="BATCH-001",
            initial_quantity=100,
            current_quantity=100
        )
        
        batch2 = BatchTracking(
            product_id=sample_product.id,
            batch_number="BATCH-002",
            initial_quantity=150,
            current_quantity=150
        )
        
        db.add_all([batch1, batch2])
        db.commit()
        
        assert len(sample_product.batches) == 2
        assert batch1.product.name == "Vitamina B12"
        assert batch2.product.name == "Vitamina B12"


class TestInventoryIntegration:
    """Tests de integración del sistema de inventario."""
    
    def test_complete_inventory_workflow(self, db: Session, test_admin_user):
        """Test flujo completo de inventario."""
        # Crear producto
        product = Product(
            name="Aspirina",
            brand="Pharma Test",
            category="Analgésicos",
            price_ves=20.00,
            price_ref=4.00,
            description="Aspirina 500mg",
            image="aspirina.jpg",
            stock=0
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        
        # Crear alerta de stock
        alert = StockAlert(
            product_id=product.id,
            min_stock_threshold=20,
            max_stock_threshold=500
        )
        db.add(alert)
        db.commit()
        
        # Crear lote
        batch = BatchTracking(
            product_id=product.id,
            batch_number="ASP-2024-001",
            initial_quantity=100,
            current_quantity=100,
            unit_cost=10.00,
            expiry_date=datetime.utcnow() + timedelta(days=365)
        )
        db.add(batch)
        db.commit()
        
        # Movimiento de entrada
        in_movement = InventoryMovement(
            product_id=product.id,
            movement_type=MovementType.IN,
            quantity=100,
            reason="Recepción de mercancía",
            reference_id=batch.batch_number,
            stock_before=0,
            stock_after=100,
            user_id=test_admin_user.id
        )
        db.add(in_movement)
        db.commit()
        
        # Verificar estado después de entrada
        alert.check_stock_levels(100)
        assert alert.is_out_of_stock is False
        assert alert.is_low_stock is False
        assert alert.is_overstocked is False
        
        # Movimiento de salida (venta)
        out_movement = InventoryMovement(
            product_id=product.id,
            movement_type=MovementType.OUT,
            quantity=85,
            reason="Venta",
            stock_before=100,
            stock_after=15,
            user_id=test_admin_user.id
        )
        db.add(out_movement)
        db.commit()
        
        # Actualizar lote
        batch.current_quantity = 15
        db.commit()
        
        # Verificar alerta de stock bajo
        alert.check_stock_levels(15)
        assert alert.is_low_stock is True
        assert alert.is_out_of_stock is False
        
        # Verificar historial de movimientos
        movements = db.query(InventoryMovement).filter(
            InventoryMovement.product_id == product.id
        ).order_by(InventoryMovement.created_at).all()
        
        assert len(movements) == 2
        assert movements[0].movement_type == MovementType.IN
        assert movements[1].movement_type == MovementType.OUT
        assert movements[0].quantity == 100
        assert movements[1].quantity == 85 