"""
Tests de integración para las nuevas funcionalidades implementadas
"""
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.category import Category, Brand
from app.models.product import Product
from app.models.promotion import FlashOffer, PromotionalCode, DiscountType
from app.models.inventory import InventoryMovement, StockAlert, BatchTracking, MovementType
from app.models.user import User


class TestCompleteWorkflow:
    """Tests de flujo completo del sistema farmacéutico."""
    
    def test_complete_pharmacy_setup(self, client: TestClient, admin_auth_headers, db: Session):
        """Test configuración completa de una farmacia."""
        
        # 1. Crear categorías
        category_data = {
            "name": "Analgésicos",
            "slug": "analgesicos",
            "description": "Medicamentos para el dolor",
            "icon": "pain-relief",
            "color": "#FF5722"
        }
        
        cat_response = client.post(
            "/api/v1/categories/",
            json=category_data,
            headers=admin_auth_headers
        )
        assert cat_response.status_code == 200
        category = cat_response.json()
        
        # 2. Crear subcategoría
        subcategory_data = {
            "name": "Analgésicos Orales",
            "slug": "analgesicos-orales",
            "parent_id": category["id"],
            "description": "Analgésicos de administración oral"
        }
        
        subcat_response = client.post(
            "/api/v1/categories/",
            json=subcategory_data,
            headers=admin_auth_headers
        )
        assert subcat_response.status_code == 200
        subcategory = subcat_response.json()
        
        # 3. Crear marca
        brand_data = {
            "name": "Bayer Farmacéutica",
            "slug": "bayer-farmaceutica",
            "description": "Farmacéutica alemana líder mundial",
            "logo_url": "https://example.com/bayer-logo.png",
            "is_featured": True
        }
        
        brand_response = client.post(
            "/api/v1/brands/",
            json=brand_data,
            headers=admin_auth_headers
        )
        assert brand_response.status_code == 200
        brand = brand_response.json()
        
        # 4. Crear producto con todas las relaciones
        product = Product(
            name="Aspirina 500mg",
            brand="Bayer Farmacéutica",
            category="Analgésicos Orales",
            brand_id=brand["id"],
            category_id=subcategory["id"],
            price_ves=25.50,
            price_ref=5.10,
            description="Aspirina 500mg para dolor y fiebre",
            image="aspirina-500mg.jpg",
            stock=0,  # Inicialmente sin stock
            sku="ASP-500-BAYER",
            slug="aspirina-500mg-bayer",
            prescription=False,
            is_active=True
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        
        # 5. Configurar alerta de stock
        stock_alert = StockAlert(
            product_id=product.id,
            min_stock_threshold=20,
            max_stock_threshold=500
        )
        db.add(stock_alert)
        db.commit()
        
        # 6. Crear lote de productos
        batch = BatchTracking(
            product_id=product.id,
            batch_number="ASP-2024-001",
            manufacture_date=datetime.utcnow() - timedelta(days=60),
            expiry_date=datetime.utcnow() + timedelta(days=1095),  # 3 años
            initial_quantity=200,
            current_quantity=200,
            unit_cost=12.75,
            selling_price=25.50,
            supplier_name="Distribuidora Farmacéutica ABC",
            supplier_invoice="INV-2024-001",
            quality_checked=True,
            quality_status="approved"
        )
        db.add(batch)
        db.commit()
        
        # 7. Registrar entrada de inventario
        inventory_in = InventoryMovement(
            product_id=product.id,
            movement_type=MovementType.IN,
            quantity=200,
            reason="Recepción de mercancía",
            reference_id=batch.batch_number,
            unit_cost=12.75,
            total_cost=2550.00,
            stock_before=0,
            stock_after=200,
            user_id=admin_auth_headers.get("user_id", "admin-id")
        )
        db.add(inventory_in)
        
        # Actualizar stock del producto
        product.stock = 200
        db.commit()
        
        # 8. Crear flash offer
        flash_offer = FlashOffer(
            product_id=product.id,
            discount_type=DiscountType.PERCENTAGE,
            discount_value=15.0,
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=48),
            max_quantity=50,
            is_active=True
        )
        db.add(flash_offer)
        db.commit()
        
        # 9. Crear código promocional
        promo_code = PromotionalCode(
            code="FARMA20",
            description="20% de descuento en compras mayores a $100",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=20.0,
            min_amount=100.0,
            max_discount=50.0,
            usage_limit=100,
            user_limit=1,
            valid_from=datetime.utcnow(),
            valid_until=datetime.utcnow() + timedelta(days=30),
            applicable_categories=[subcategory["id"]],
            is_active=True
        )
        db.add(promo_code)
        db.commit()
        
        # 10. Verificar configuración completa
        
        # Verificar categorías creadas
        cat_check = client.get(f"/api/v1/categories/{category['id']}")
        assert cat_check.status_code == 200
        
        subcat_check = client.get(f"/api/v1/categories/{subcategory['id']}")
        assert subcat_check.status_code == 200
        assert subcat_check.json()["parent_id"] == category["id"]
        
        # Verificar marca creada
        brand_check = client.get(f"/api/v1/brands/{brand['id']}")
        assert brand_check.status_code == 200
        assert brand_check.json()["product_count"] == 1
        
        # Verificar producto con todas las relaciones
        assert product.brand_obj.name == "Bayer Farmacéutica"
        assert product.category_obj.name == "Analgésicos Orales"
        assert product.category_obj.parent.name == "Analgésicos"
        
        # Verificar stock alert
        stock_alert.check_stock_levels(200)
        assert stock_alert.is_low_stock is False
        assert stock_alert.is_out_of_stock is False
        assert stock_alert.is_overstocked is False
        
        # Verificar batch tracking
        assert batch.available_quantity == 200
        assert batch.is_expired is False
        assert batch.days_to_expiry > 1000
        
        # Verificar promociones
        assert flash_offer.is_valid is True
        assert flash_offer.calculate_discount_amount(25.50) == 3.825  # 15% de 25.50
        
        assert promo_code.is_valid is True
        assert promo_code.calculate_discount(150.0) == 30.0  # 20% de 150
    
    def test_sales_workflow(self, client: TestClient, db: Session, test_user, test_admin_user):
        """Test flujo completo de ventas."""
        
        # Configurar producto con stock
        category = Category(name="Vitaminas", slug="vitaminas")
        brand = Brand(name="VitaMax", slug="vitamax")
        db.add_all([category, brand])
        db.commit()
        
        product = Product(
            name="Vitamina C 1000mg",
            brand="VitaMax",
            category="Vitaminas",
            brand_id=brand.id,
            category_id=category.id,
            price_ves=35.00,
            price_ref=7.00,
            description="Vitamina C 1000mg",
            image="vitamin-c.jpg",
            stock=100,
            sku="VIT-C-1000"
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        
        # Configurar promociones
        promo_code = PromotionalCode(
            code="VITAMINAS10",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=10.0,
            valid_from=datetime.utcnow(),
            valid_until=datetime.utcnow() + timedelta(days=7),
            applicable_categories=[category.id],
            is_active=True
        )
        db.add(promo_code)
        db.commit()
        
        # Simular venta de 25 unidades
        sale_quantity = 25
        
        # Movimiento de salida por venta
        inventory_out = InventoryMovement(
            product_id=product.id,
            movement_type=MovementType.OUT,
            quantity=sale_quantity,
            reason="Venta a cliente",
            reference_id="ORDER-2024-001",
            stock_before=100,
            stock_after=75,
            user_id=test_admin_user.id
        )
        db.add(inventory_out)
        
        # Actualizar stock
        product.stock = 75
        db.commit()
        
        # Verificar stock después de venta
        stock_alert = StockAlert(
            product_id=product.id,
            min_stock_threshold=20,
            max_stock_threshold=200
        )
        db.add(stock_alert)
        db.commit()
        
        stock_alert.check_stock_levels(75)
        assert stock_alert.is_low_stock is False
        assert stock_alert.is_out_of_stock is False
        
        # Verificar historial de movimientos
        movements = db.query(InventoryMovement).filter(
            InventoryMovement.product_id == product.id
        ).all()
        
        assert len(movements) == 1
        assert movements[0].movement_type == MovementType.OUT
        assert movements[0].quantity == 25
    
    def test_low_stock_alert_workflow(self, client: TestClient, db: Session, test_admin_user):
        """Test flujo de alertas de stock bajo."""
        
        # Crear producto con stock inicial
        product = Product(
            name="Paracetamol 500mg",
            brand="Genérico",
            category="Analgésicos",
            price_ves=15.00,
            price_ref=3.00,
            description="Paracetamol 500mg",
            image="paracetamol.jpg",
            stock=30,
            sku="PAR-500-GEN"
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        
        # Configurar alerta con umbral alto para testing
        stock_alert = StockAlert(
            product_id=product.id,
            min_stock_threshold=25,
            max_stock_threshold=200
        )
        db.add(stock_alert)
        db.commit()
        
        # Primera venta - stock normal
        inventory_out1 = InventoryMovement(
            product_id=product.id,
            movement_type=MovementType.OUT,
            quantity=5,
            reason="Venta",
            stock_before=30,
            stock_after=25,
            user_id=test_admin_user.id
        )
        db.add(inventory_out1)
        product.stock = 25
        db.commit()
        
        stock_alert.check_stock_levels(25)
        assert stock_alert.is_low_stock is False  # Exactamente en el límite
        
        # Segunda venta - stock bajo
        inventory_out2 = InventoryMovement(
            product_id=product.id,
            movement_type=MovementType.OUT,
            quantity=10,
            reason="Venta",
            stock_before=25,
            stock_after=15,
            user_id=test_admin_user.id
        )
        db.add(inventory_out2)
        product.stock = 15
        db.commit()
        
        stock_alert.check_stock_levels(15)
        assert stock_alert.is_low_stock is True
        assert stock_alert.is_out_of_stock is False
        
        # Tercera venta - stock agotado
        inventory_out3 = InventoryMovement(
            product_id=product.id,
            movement_type=MovementType.OUT,
            quantity=15,
            reason="Venta",
            stock_before=15,
            stock_after=0,
            user_id=test_admin_user.id
        )
        db.add(inventory_out3)
        product.stock = 0
        db.commit()
        
        stock_alert.check_stock_levels(0)
        assert stock_alert.is_out_of_stock is True
        assert stock_alert.is_low_stock is False  # Prioridad a out_of_stock
        
        # Reposición de stock
        inventory_in = InventoryMovement(
            product_id=product.id,
            movement_type=MovementType.IN,
            quantity=100,
            reason="Reposición de stock",
            stock_before=0,
            stock_after=100,
            user_id=test_admin_user.id
        )
        db.add(inventory_in)
        product.stock = 100
        db.commit()
        
        stock_alert.check_stock_levels(100)
        assert stock_alert.is_out_of_stock is False
        assert stock_alert.is_low_stock is False
        assert stock_alert.is_overstocked is False
    
    def test_batch_expiry_workflow(self, client: TestClient, db: Session):
        """Test flujo de manejo de lotes próximos a vencer."""
        
        product = Product(
            name="Antibiótico XYZ",
            brand="Pharma Lab",
            category="Antibióticos",
            price_ves=85.00,
            price_ref=17.00,
            description="Antibiótico de amplio espectro",
            image="antibiotico-xyz.jpg",
            stock=0
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        
        # Crear lotes con diferentes fechas de vencimiento
        current_time = datetime.utcnow()
        
        # Lote próximo a vencer (30 días)
        batch_expiring = BatchTracking(
            product_id=product.id,
            batch_number="ANT-2024-001",
            manufacture_date=current_time - timedelta(days=330),
            expiry_date=current_time + timedelta(days=30),
            initial_quantity=50,
            current_quantity=50,
            unit_cost=40.00
        )
        
        # Lote con fecha lejana (1 año)
        batch_fresh = BatchTracking(
            product_id=product.id,
            batch_number="ANT-2024-002",
            manufacture_date=current_time - timedelta(days=30),
            expiry_date=current_time + timedelta(days=365),
            initial_quantity=100,
            current_quantity=100,
            unit_cost=42.00
        )
        
        # Lote expirado
        batch_expired = BatchTracking(
            product_id=product.id,
            batch_number="ANT-2023-001",
            manufacture_date=current_time - timedelta(days=400),
            expiry_date=current_time - timedelta(days=5),
            initial_quantity=25,
            current_quantity=25,
            unit_cost=38.00
        )
        
        db.add_all([batch_expiring, batch_fresh, batch_expired])
        db.commit()
        
        # Verificar estado de lotes
        assert batch_expiring.days_to_expiry == 30
        assert batch_expiring.is_expired is False
        
        assert batch_fresh.days_to_expiry == 365
        assert batch_fresh.is_expired is False
        
        assert batch_expired.is_expired is True
        assert batch_expired.days_to_expiry == 0
        
        # Simular uso de lotes por orden FEFO (First Expired, First Out)
        batches_by_expiry = db.query(BatchTracking).filter(
            BatchTracking.product_id == product.id,
            BatchTracking.is_active == True,
            BatchTracking.current_quantity > 0
        ).order_by(BatchTracking.expiry_date).all()
        
        # El primer lote debería ser el próximo a vencer (no el expirado)
        first_batch = next(batch for batch in batches_by_expiry if not batch.is_expired)
        assert first_batch.batch_number == "ANT-2024-001"
        
        # Ajuste de inventario para lote expirado
        expired_adjustment = InventoryMovement(
            product_id=product.id,
            movement_type=MovementType.ADJUSTMENT,
            quantity=-25,  # Retiro por vencimiento
            reason="Producto vencido - retiro",
            reference_id=batch_expired.batch_number,
            stock_before=175,  # 50 + 100 + 25
            stock_after=150,   # 50 + 100
            user_id=None
        )
        db.add(expired_adjustment)
        
        # Marcar lote como inactivo
        batch_expired.is_active = False
        batch_expired.current_quantity = 0
        db.commit()
        
        # Verificar que solo quedan lotes activos
        active_batches = db.query(BatchTracking).filter(
            BatchTracking.product_id == product.id,
            BatchTracking.is_active == True,
            BatchTracking.current_quantity > 0
        ).all()
        
        assert len(active_batches) == 2
        assert all(not batch.is_expired for batch in active_batches)


class TestPublicEndpointsIntegration:
    """Tests de integración para endpoints públicos con nuevas funcionalidades."""
    
    def test_public_catalog_with_categories_and_brands(self, client: TestClient, db: Session):
        """Test catálogo público con categorías y marcas."""
        
        # Crear estructura completa
        category = Category(name="Suplementos", slug="suplementos", is_active=True)
        brand = Brand(name="NutriMax", slug="nutrimax", is_active=True, is_featured=True)
        db.add_all([category, brand])
        db.commit()
        
        # Crear productos
        products = [
            Product(
                name="Omega 3",
                brand="NutriMax",
                category="Suplementos",
                brand_id=brand.id,
                category_id=category.id,
                price_ves=45.00,
                price_ref=9.00,
                description="Omega 3 1000mg",
                image="omega3.jpg",
                is_active=True,
                featured=True,
                stock=50
            ),
            Product(
                name="Multivitamínico",
                brand="NutriMax",
                category="Suplementos",
                brand_id=brand.id,
                category_id=category.id,
                price_ves=35.00,
                price_ref=7.00,
                description="Complejo multivitamínico",
                image="multivit.jpg",
                is_active=True,
                stock=30
            )
        ]
        
        for product in products:
            db.add(product)
        db.commit()
        
        # Test endpoints públicos
        
        # Categorías públicas
        cat_response = client.get("/api/v1/categories/")
        assert cat_response.status_code == 200
        assert len(cat_response.json()["categories"]) == 1
        assert cat_response.json()["categories"][0]["product_count"] == 2
        
        # Marcas públicas
        brand_response = client.get("/api/v1/brands/")
        assert brand_response.status_code == 200
        assert len(brand_response.json()["brands"]) == 1
        assert brand_response.json()["brands"][0]["product_count"] == 2
        
        # Marcas destacadas
        featured_response = client.get("/api/v1/brands/featured")
        assert featured_response.status_code == 200
        assert len(featured_response.json()) == 1
        assert featured_response.json()[0]["is_featured"] is True
        
        # Productos públicos (endpoint existente debería seguir funcionando)
        products_response = client.get("/public/products")
        assert products_response.status_code == 200


class TestErrorHandling:
    """Tests de manejo de errores en las nuevas funcionalidades."""
    
    def test_category_brand_constraint_errors(self, client: TestClient, admin_auth_headers, db: Session):
        """Test errores de restricciones en categorías y marcas."""
        
        # Crear categoría
        category_data = {"name": "Test Category", "slug": "test-category"}
        response1 = client.post("/api/v1/categories/", json=category_data, headers=admin_auth_headers)
        assert response1.status_code == 200
        
        # Intentar crear otra con mismo slug
        response2 = client.post("/api/v1/categories/", json=category_data, headers=admin_auth_headers)
        assert response2.status_code == 400
        assert "Ya existe una categoría" in response2.json()["detail"]
        
        # Similar para marcas
        brand_data = {"name": "Test Brand", "slug": "test-brand"}
        response3 = client.post("/api/v1/brands/", json=brand_data, headers=admin_auth_headers)
        assert response3.status_code == 200
        
        response4 = client.post("/api/v1/brands/", json=brand_data, headers=admin_auth_headers)
        assert response4.status_code == 400
        assert "Ya existe una marca" in response4.json()["detail"]
    
    def test_delete_with_dependencies_errors(self, client: TestClient, admin_auth_headers, db: Session):
        """Test errores al eliminar con dependencias."""
        
        # Crear categoría y producto
        category = Category(name="Test Cat", slug="test-cat")
        db.add(category)
        db.commit()
        db.refresh(category)
        
        product = Product(
            name="Test Product",
            brand="Test",
            category="Test",
            category_id=category.id,
            price_ves=10.0,
            price_ref=2.0,
            description="Test",
            image="test.jpg"
        )
        db.add(product)
        db.commit()
        
        # Intentar eliminar categoría con productos
        response = client.delete(f"/api/v1/categories/{category.id}", headers=admin_auth_headers)
        assert response.status_code == 400
        assert "productos asociados" in response.json()["detail"] 