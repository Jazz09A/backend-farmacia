"""
Tests para los endpoints de categorías y marcas
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.category import Category, Brand
from app.models.product import Product


class TestCategoryEndpoints:
    """Tests para endpoints de categorías."""
    
    @pytest.fixture
    def sample_categories(self, db: Session):
        """Crear categorías de prueba."""
        categories = [
            Category(
                name="Medicamentos",
                slug="medicamentos",
                description="Categoría principal de medicamentos",
                is_active=True,
                sort_order=1
            ),
            Category(
                name="Vitaminas",
                slug="vitaminas",
                description="Suplementos vitamínicos",
                is_active=True,
                sort_order=2
            ),
            Category(
                name="Cuidado Personal",
                slug="cuidado-personal",
                description="Productos de higiene",
                is_active=False,  # Inactiva
                sort_order=3
            )
        ]
        
        for category in categories:
            db.add(category)
        db.commit()
        
        # Crear subcategoría
        subcategory = Category(
            name="Analgésicos",
            slug="analgesicos",
            description="Medicamentos para el dolor",
            parent_id=categories[0].id,
            is_active=True
        )
        db.add(subcategory)
        db.commit()
        
        return categories
    
    def test_get_categories_public(self, client: TestClient, sample_categories):
        """Test obtener categorías públicas."""
        response = client.get("/api/v1/categories/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "categories" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data
        
        # Solo deben aparecer categorías activas principales (sin parent_id)
        categories = data["categories"]
        assert len(categories) == 2  # Medicamentos y Vitaminas (no Cuidado Personal porque está inactiva)
        
        category_names = [cat["name"] for cat in categories]
        assert "Medicamentos" in category_names
        assert "Vitaminas" in category_names
        assert "Cuidado Personal" not in category_names
    
    def test_get_categories_with_filters(self, client: TestClient, sample_categories):
        """Test obtener categorías con filtros."""
        # Test filtro active_only=false (incluir inactivas)
        response = client.get("/api/v1/categories/?active_only=false")
        assert response.status_code == 200
        
        data = response.json()
        categories = data["categories"]
        
        # Ahora debería incluir la categoría inactiva
        category_names = [cat["name"] for cat in categories]
        assert "Cuidado Personal" in category_names
    
    def test_get_category_by_id(self, client: TestClient, sample_categories, db: Session):
        """Test obtener categoría específica."""
        category_id = sample_categories[0].id
        
        # Agregar un producto para verificar el conteo
        product = Product(
            name="Aspirina",
            brand="Test",
            category="Medicamentos",
            category_id=category_id,
            price_ves=20.0,
            price_ref=4.0,
            description="Test product",
            image="test.jpg",
            is_active=True
        )
        db.add(product)
        db.commit()
        
        response = client.get(f"/api/v1/categories/{category_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["name"] == "Medicamentos"
        assert data["slug"] == "medicamentos"
        assert data["product_count"] == 1
    
    def test_get_category_not_found(self, client: TestClient):
        """Test obtener categoría inexistente."""
        response = client.get("/api/v1/categories/nonexistent-id")
        
        assert response.status_code == 404
        assert "Categoría no encontrada" in response.json()["detail"]
    
    def test_get_subcategories(self, client: TestClient, sample_categories, db: Session):
        """Test obtener subcategorías."""
        parent_id = sample_categories[0].id  # Medicamentos
        
        response = client.get(f"/api/v1/categories/{parent_id}/subcategories")
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data) == 1
        assert data[0]["name"] == "Analgésicos"
        assert data[0]["parent_id"] == parent_id
    
    def test_get_categories_simple(self, client: TestClient, sample_categories):
        """Test obtener lista simple de categorías."""
        response = client.get("/api/v1/categories/simple/list")
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) >= 2
        
        # Verificar estructura simple
        category = data[0]
        assert "id" in category
        assert "name" in category
        assert "slug" in category
        assert len(category) == 3  # Solo 3 campos
    
    def test_create_category_admin(self, client: TestClient, admin_auth_headers):
        """Test crear categoría como administrador."""
        category_data = {
            "name": "Nueva Categoría",
            "slug": "nueva-categoria",
            "description": "Descripción de prueba",
            "icon": "test-icon",
            "color": "#FF0000",
            "is_active": True,
            "sort_order": 10
        }
        
        response = client.post(
            "/api/v1/categories/",
            json=category_data,
            headers=admin_auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["name"] == "Nueva Categoría"
        assert data["slug"] == "nueva-categoria"
        assert data["description"] == "Descripción de prueba"
        assert data["icon"] == "test-icon"
        assert data["color"] == "#FF0000"
    
    def test_create_category_duplicate_slug(self, client: TestClient, admin_auth_headers, sample_categories):
        """Test crear categoría con slug duplicado."""
        category_data = {
            "name": "Otra Medicamentos",
            "slug": "medicamentos",  # Slug duplicado
            "description": "Descripción"
        }
        
        response = client.post(
            "/api/v1/categories/",
            json=category_data,
            headers=admin_auth_headers
        )
        
        assert response.status_code == 400
        assert "Ya existe una categoría con ese slug" in response.json()["detail"]
    
    def test_create_category_unauthorized(self, client: TestClient, auth_headers):
        """Test crear categoría sin permisos de admin."""
        category_data = {
            "name": "Test Category",
            "slug": "test-category"
        }
        
        response = client.post(
            "/api/v1/categories/",
            json=category_data,
            headers=auth_headers
        )
        
        assert response.status_code == 403
    
    def test_update_category_admin(self, client: TestClient, admin_auth_headers, sample_categories):
        """Test actualizar categoría como administrador."""
        category_id = sample_categories[0].id
        update_data = {
            "name": "Medicamentos Actualizados",
            "description": "Descripción actualizada",
            "color": "#00FF00"
        }
        
        response = client.put(
            f"/api/v1/categories/{category_id}",
            json=update_data,
            headers=admin_auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["name"] == "Medicamentos Actualizados"
        assert data["description"] == "Descripción actualizada"
        assert data["color"] == "#00FF00"
        assert data["slug"] == "medicamentos"  # No cambiado
    
    def test_delete_category_admin(self, client: TestClient, admin_auth_headers, db: Session):
        """Test eliminar categoría como administrador."""
        # Crear categoría sin productos
        category = Category(
            name="Categoría a Eliminar",
            slug="categoria-eliminar"
        )
        db.add(category)
        db.commit()
        db.refresh(category)
        
        response = client.delete(
            f"/api/v1/categories/{category.id}",
            headers=admin_auth_headers
        )
        
        assert response.status_code == 200
        assert "eliminada exitosamente" in response.json()["message"]
    
    def test_delete_category_with_products(self, client: TestClient, admin_auth_headers, sample_categories, db: Session):
        """Test no se puede eliminar categoría con productos."""
        category_id = sample_categories[0].id
        
        # Agregar producto a la categoría
        product = Product(
            name="Producto Test",
            brand="Test",
            category="Test",
            category_id=category_id,
            price_ves=10.0,
            price_ref=2.0,
            description="Test",
            image="test.jpg"
        )
        db.add(product)
        db.commit()
        
        response = client.delete(
            f"/api/v1/categories/{category_id}",
            headers=admin_auth_headers
        )
        
        assert response.status_code == 400
        assert "productos asociados" in response.json()["detail"]


class TestBrandEndpoints:
    """Tests para endpoints de marcas."""
    
    @pytest.fixture
    def sample_brands(self, db: Session):
        """Crear marcas de prueba."""
        brands = [
            Brand(
                name="Bayer",
                slug="bayer",
                description="Farmacéutica alemana",
                logo_url="https://example.com/bayer.png",
                is_featured=True,
                is_active=True
            ),
            Brand(
                name="Pfizer",
                slug="pfizer",
                description="Farmacéutica estadounidense",
                is_featured=False,
                is_active=True
            ),
            Brand(
                name="Marca Inactiva",
                slug="marca-inactiva",
                is_active=False
            )
        ]
        
        for brand in brands:
            db.add(brand)
        db.commit()
        
        return brands
    
    def test_get_brands_public(self, client: TestClient, sample_brands):
        """Test obtener marcas públicas."""
        response = client.get("/api/v1/brands/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "brands" in data
        assert "total" in data
        
        # Solo marcas activas
        brands = data["brands"]
        assert len(brands) == 2
        
        brand_names = [brand["name"] for brand in brands]
        assert "Bayer" in brand_names
        assert "Pfizer" in brand_names
        assert "Marca Inactiva" not in brand_names
    
    def test_get_brands_featured(self, client: TestClient, sample_brands):
        """Test obtener marcas destacadas."""
        response = client.get("/api/v1/brands/featured")
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data) == 1
        assert data[0]["name"] == "Bayer"
        assert data[0]["is_featured"] is True
    
    def test_get_brands_with_search(self, client: TestClient, sample_brands):
        """Test buscar marcas."""
        response = client.get("/api/v1/brands/?search=bayer")
        
        assert response.status_code == 200
        data = response.json()
        
        brands = data["brands"]
        assert len(brands) == 1
        assert brands[0]["name"] == "Bayer"
    
    def test_get_brand_by_id(self, client: TestClient, sample_brands, db: Session):
        """Test obtener marca específica."""
        brand_id = sample_brands[0].id
        
        # Agregar producto para verificar conteo
        product = Product(
            name="Aspirina Bayer",
            brand="Bayer",
            brand_id=brand_id,
            category="Analgésicos",
            price_ves=25.0,
            price_ref=5.0,
            description="Test product",
            image="test.jpg",
            is_active=True
        )
        db.add(product)
        db.commit()
        
        response = client.get(f"/api/v1/brands/{brand_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["name"] == "Bayer"
        assert data["slug"] == "bayer"
        assert data["product_count"] == 1
    
    def test_get_brands_simple(self, client: TestClient, sample_brands):
        """Test obtener lista simple de marcas."""
        response = client.get("/api/v1/brands/simple/list")
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) == 2  # Solo activas
        
        # Verificar estructura simple
        brand = data[0]
        assert "id" in brand
        assert "name" in brand
        assert "slug" in brand
        assert len(brand) == 3
    
    def test_create_brand_admin(self, client: TestClient, admin_auth_headers):
        """Test crear marca como administrador."""
        brand_data = {
            "name": "Nueva Marca",
            "slug": "nueva-marca",
            "description": "Descripción de prueba",
            "logo_url": "https://example.com/logo.png",
            "is_featured": True
        }
        
        response = client.post(
            "/api/v1/brands/",
            json=brand_data,
            headers=admin_auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["name"] == "Nueva Marca"
        assert data["slug"] == "nueva-marca"
        assert data["description"] == "Descripción de prueba"
        assert data["logo_url"] == "https://example.com/logo.png"
        assert data["is_featured"] is True
    
    def test_create_brand_duplicate_slug(self, client: TestClient, admin_auth_headers, sample_brands):
        """Test crear marca con slug duplicado."""
        brand_data = {
            "name": "Otra Bayer",
            "slug": "bayer",  # Slug duplicado
            "description": "Descripción"
        }
        
        response = client.post(
            "/api/v1/brands/",
            json=brand_data,
            headers=admin_auth_headers
        )
        
        assert response.status_code == 400
        assert "Ya existe una marca con ese slug" in response.json()["detail"]
    
    def test_update_brand_admin(self, client: TestClient, admin_auth_headers, sample_brands):
        """Test actualizar marca como administrador."""
        brand_id = sample_brands[1].id  # Pfizer
        update_data = {
            "description": "Descripción actualizada",
            "is_featured": True,
            "logo_url": "https://example.com/pfizer-new.png"
        }
        
        response = client.put(
            f"/api/v1/brands/{brand_id}",
            json=update_data,
            headers=admin_auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["description"] == "Descripción actualizada"
        assert data["is_featured"] is True
        assert data["logo_url"] == "https://example.com/pfizer-new.png"
        assert data["name"] == "Pfizer"  # No cambiado
    
    def test_delete_brand_admin(self, client: TestClient, admin_auth_headers, db: Session):
        """Test eliminar marca como administrador."""
        # Crear marca sin productos
        brand = Brand(
            name="Marca a Eliminar",
            slug="marca-eliminar"
        )
        db.add(brand)
        db.commit()
        db.refresh(brand)
        
        response = client.delete(
            f"/api/v1/brands/{brand.id}",
            headers=admin_auth_headers
        )
        
        assert response.status_code == 200
        assert "eliminada exitosamente" in response.json()["message"]
    
    def test_delete_brand_with_products(self, client: TestClient, admin_auth_headers, sample_brands, db: Session):
        """Test no se puede eliminar marca con productos."""
        brand_id = sample_brands[0].id  # Bayer
        
        # Agregar producto a la marca
        product = Product(
            name="Producto Test",
            brand="Bayer",
            brand_id=brand_id,
            category="Test",
            price_ves=10.0,
            price_ref=2.0,
            description="Test",
            image="test.jpg"
        )
        db.add(product)
        db.commit()
        
        response = client.delete(
            f"/api/v1/brands/{brand_id}",
            headers=admin_auth_headers
        )
        
        assert response.status_code == 400
        assert "productos asociados" in response.json()["detail"]


class TestCategoryBrandIntegration:
    """Tests de integración entre endpoints de categorías y marcas."""
    
    def test_product_with_category_and_brand_endpoints(self, client: TestClient, admin_auth_headers, db: Session):
        """Test integración completa con producto, categoría y marca."""
        # Crear categoría
        category_data = {
            "name": "Analgésicos",
            "slug": "analgesicos",
            "description": "Medicamentos para el dolor"
        }
        
        cat_response = client.post(
            "/api/v1/categories/",
            json=category_data,
            headers=admin_auth_headers
        )
        assert cat_response.status_code == 200
        category = cat_response.json()
        
        # Crear marca
        brand_data = {
            "name": "Bayer Test",
            "slug": "bayer-test",
            "description": "Farmacéutica de prueba"
        }
        
        brand_response = client.post(
            "/api/v1/brands/",
            json=brand_data,
            headers=admin_auth_headers
        )
        assert brand_response.status_code == 200
        brand = brand_response.json()
        
        # Crear producto con ambas relaciones
        product = Product(
            name="Aspirina Test",
            brand="Bayer Test",
            category="Analgésicos",
            brand_id=brand["id"],
            category_id=category["id"],
            price_ves=20.0,
            price_ref=4.0,
            description="Aspirina de prueba",
            image="aspirina-test.jpg",
            is_active=True
        )
        db.add(product)
        db.commit()
        
        # Verificar conteos en endpoints
        cat_check = client.get(f"/api/v1/categories/{category['id']}")
        brand_check = client.get(f"/api/v1/brands/{brand['id']}")
        
        assert cat_check.status_code == 200
        assert brand_check.status_code == 200
        assert cat_check.json()["product_count"] == 1
        assert brand_check.json()["product_count"] == 1 