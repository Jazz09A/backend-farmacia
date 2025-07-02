"""
Tests para la funcionalidad de favoritos
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.favorites import UserFavorite
from app.models.product import Product
from app.models.category import Category, Brand
from app.services.favorites_service import FavoritesService


@pytest.fixture
def sample_brand(db: Session):
    """Crear una marca de prueba"""
    brand = Brand(
        name="Marca Test",
        slug="marca-test",
        description="Marca para testing",
        is_active=True
    )
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


@pytest.fixture
def sample_category(db: Session):
    """Crear una categoría de prueba"""
    category = Category(
        name="Categoría Test",
        slug="categoria-test",
        description="Categoría para testing",
        is_active=True
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@pytest.fixture
def sample_product(db: Session, sample_brand: Brand, sample_category: Category):
    """Crear un producto de prueba"""
    product = Product(
        name="Producto Test",
        slug="producto-test",
        sku="TEST-001",
        brand_id=sample_brand.id,
        category_id=sample_category.id,
        brand="Marca Test",
        category="Categoría Test",
        price_ves=25.50,
        price_ref=5.00,
        description="Producto de prueba para testing",
        image="test-image.jpg",
        in_stock=True,
        stock=100,
        prescription=False,
        rating=4.5,
        review_count=10
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@pytest.fixture
def sample_product_2(db: Session, sample_brand: Brand, sample_category: Category):
    """Crear un segundo producto de prueba"""
    product = Product(
        name="Producto Test 2",
        slug="producto-test-2",
        sku="TEST-002",
        brand_id=sample_brand.id,
        category_id=sample_category.id,
        brand="Marca Test",
        category="Categoría Test",
        price_ves=45.00,
        price_ref=8.50,
        description="Segundo producto de prueba para testing",
        image="test-image-2.jpg",
        in_stock=True,
        stock=50,
        prescription=True,
        rating=4.8,
        review_count=25
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


class TestFavoritesService:
    """Tests para el servicio de favoritos"""
    
    def test_add_to_favorites_success(self, db: Session, test_user, sample_product):
        """Test agregar producto a favoritos exitosamente"""
        favorite = FavoritesService.add_to_favorites(
            db=db,
            user_id=test_user.id,
            product_id=sample_product.id
        )
        
        assert favorite is not None
        assert favorite.user_id == test_user.id
        assert favorite.product_id == sample_product.id
        
        # Verificar que se guardó en la base de datos
        db_favorite = db.query(UserFavorite).filter(
            UserFavorite.user_id == test_user.id,
            UserFavorite.product_id == sample_product.id
        ).first()
        assert db_favorite is not None
    
    def test_add_to_favorites_nonexistent_product(self, db: Session, test_user):
        """Test agregar producto inexistente a favoritos"""
        with pytest.raises(Exception):  # Should raise HTTPException
            FavoritesService.add_to_favorites(
                db=db,
                user_id=test_user.id,
                product_id="nonexistent-product-id"
            )
    
    def test_add_duplicate_favorite(self, db: Session, test_user, sample_product):
        """Test agregar producto que ya está en favoritos"""
        # Agregar por primera vez
        FavoritesService.add_to_favorites(
            db=db,
            user_id=test_user.id,
            product_id=sample_product.id
        )
        
        # Intentar agregar nuevamente
        with pytest.raises(Exception):  # Should raise HTTPException
            FavoritesService.add_to_favorites(
                db=db,
                user_id=test_user.id,
                product_id=sample_product.id
            )
    
    def test_remove_from_favorites_success(self, db: Session, test_user, sample_product):
        """Test remover producto de favoritos exitosamente"""
        # Primero agregar a favoritos
        FavoritesService.add_to_favorites(
            db=db,
            user_id=test_user.id,
            product_id=sample_product.id
        )
        
        # Luego remover
        result = FavoritesService.remove_from_favorites(
            db=db,
            user_id=test_user.id,
            product_id=sample_product.id
        )
        
        assert result is True
        
        # Verificar que ya no existe en la base de datos
        db_favorite = db.query(UserFavorite).filter(
            UserFavorite.user_id == test_user.id,
            UserFavorite.product_id == sample_product.id
        ).first()
        assert db_favorite is None
    
    def test_remove_nonexistent_favorite(self, db: Session, test_user, sample_product):
        """Test remover producto que no está en favoritos"""
        with pytest.raises(Exception):  # Should raise HTTPException
            FavoritesService.remove_from_favorites(
                db=db,
                user_id=test_user.id,
                product_id=sample_product.id
            )
    
    def test_is_favorite(self, db: Session, test_user, sample_product):
        """Test verificar si producto está en favoritos"""
        # Inicialmente no debe estar en favoritos
        assert FavoritesService.is_favorite(db, test_user.id, sample_product.id) is False
        
        # Agregar a favoritos
        FavoritesService.add_to_favorites(db, test_user.id, sample_product.id)
        
        # Ahora debe estar en favoritos
        assert FavoritesService.is_favorite(db, test_user.id, sample_product.id) is True
    
    def test_get_user_favorites(self, db: Session, test_user, sample_product, sample_product_2):
        """Test obtener lista de favoritos del usuario"""
        # Agregar productos a favoritos
        FavoritesService.add_to_favorites(db, test_user.id, sample_product.id)
        FavoritesService.add_to_favorites(db, test_user.id, sample_product_2.id)
        
        # Obtener favoritos
        favorites, total_count = FavoritesService.get_user_favorites(
            db=db,
            user_id=test_user.id,
            skip=0,
            limit=10
        )
        
        assert total_count == 2
        assert len(favorites) == 2
        
        product_ids = [fav.product_id for fav in favorites]
        assert sample_product.id in product_ids
        assert sample_product_2.id in product_ids
    
    def test_get_user_favorites_pagination(self, db: Session, test_user, sample_product, sample_product_2):
        """Test paginación en lista de favoritos"""
        # Agregar productos a favoritos
        FavoritesService.add_to_favorites(db, test_user.id, sample_product.id)
        FavoritesService.add_to_favorites(db, test_user.id, sample_product_2.id)
        
        # Obtener solo el primer favorito
        favorites, total_count = FavoritesService.get_user_favorites(
            db=db,
            user_id=test_user.id,
            skip=0,
            limit=1
        )
        
        assert total_count == 2
        assert len(favorites) == 1
    
    def test_get_favorite_count(self, db: Session, test_user, sample_product, sample_product_2):
        """Test obtener contador de favoritos"""
        # Inicialmente debe ser 0
        assert FavoritesService.get_favorite_count(db, test_user.id) == 0
        
        # Agregar un favorito
        FavoritesService.add_to_favorites(db, test_user.id, sample_product.id)
        assert FavoritesService.get_favorite_count(db, test_user.id) == 1
        
        # Agregar otro favorito
        FavoritesService.add_to_favorites(db, test_user.id, sample_product_2.id)
        assert FavoritesService.get_favorite_count(db, test_user.id) == 2
    
    def test_clear_user_favorites(self, db: Session, test_user, sample_product, sample_product_2):
        """Test limpiar todos los favoritos del usuario"""
        # Agregar productos a favoritos
        FavoritesService.add_to_favorites(db, test_user.id, sample_product.id)
        FavoritesService.add_to_favorites(db, test_user.id, sample_product_2.id)
        
        # Verificar que hay favoritos
        assert FavoritesService.get_favorite_count(db, test_user.id) == 2
        
        # Limpiar favoritos
        deleted_count = FavoritesService.clear_user_favorites(db, test_user.id)
        
        assert deleted_count == 2
        assert FavoritesService.get_favorite_count(db, test_user.id) == 0


class TestFavoritesEndpoints:
    """Tests para los endpoints de favoritos"""
    
    def test_add_to_favorites_endpoint(self, client: TestClient, auth_headers, sample_product):
        """Test endpoint para agregar a favoritos"""
        response = client.post(
            "/api/v1/favorites/add",
            json={"product_id": sample_product.id},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["is_favorite"] is True
        assert "agregado a favoritos" in data["message"]
    
    def test_add_to_favorites_unauthenticated(self, client: TestClient, sample_product):
        """Test endpoint agregar a favoritos sin autenticación"""
        response = client.post(
            "/api/v1/favorites/add",
            json={"product_id": sample_product.id}
        )
        
        assert response.status_code == 401
    
    def test_add_nonexistent_product_to_favorites(self, client: TestClient, auth_headers):
        """Test agregar producto inexistente a favoritos"""
        response = client.post(
            "/api/v1/favorites/add",
            json={"product_id": "nonexistent-id"},
            headers=auth_headers
        )
        
        assert response.status_code == 404
    
    def test_remove_from_favorites_endpoint(self, client: TestClient, auth_headers, sample_product):
        """Test endpoint para remover de favoritos"""
        # Primero agregar a favoritos
        client.post(
            "/api/v1/favorites/add",
            json={"product_id": sample_product.id},
            headers=auth_headers
        )
        
        # Luego remover
        response = client.delete(
            f"/api/v1/favorites/remove/{sample_product.id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["is_favorite"] is False
        assert "removido de favoritos" in data["message"]
    
    def test_get_favorites_list_endpoint(self, client: TestClient, auth_headers, sample_product, sample_product_2):
        """Test endpoint para obtener lista de favoritos"""
        # Agregar productos a favoritos
        client.post(
            "/api/v1/favorites/add",
            json={"product_id": sample_product.id},
            headers=auth_headers
        )
        client.post(
            "/api/v1/favorites/add",
            json={"product_id": sample_product_2.id},
            headers=auth_headers
        )
        
        # Obtener lista de favoritos
        response = client.get(
            "/api/v1/favorites/",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 2
        assert len(data["favorites"]) == 2
        
        # Verificar que incluye información del producto
        for favorite in data["favorites"]:
            assert "product" in favorite
            assert favorite["product"] is not None
    
    def test_check_favorite_status_endpoint(self, client: TestClient, auth_headers, sample_product):
        """Test endpoint para verificar estado de favorito"""
        # Verificar que inicialmente no está en favoritos
        response = client.get(
            f"/api/v1/favorites/check/{sample_product.id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["is_favorite"] is False
        
        # Agregar a favoritos
        client.post(
            "/api/v1/favorites/add",
            json={"product_id": sample_product.id},
            headers=auth_headers
        )
        
        # Verificar que ahora está en favoritos
        response = client.get(
            f"/api/v1/favorites/check/{sample_product.id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["is_favorite"] is True
    
    def test_get_favorites_count_endpoint(self, client: TestClient, auth_headers, sample_product):
        """Test endpoint para obtener contador de favoritos"""
        # Inicialmente debe ser 0
        response = client.get(
            "/api/v1/favorites/count",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_favorites"] == 0
        
        # Agregar un favorito
        client.post(
            "/api/v1/favorites/add",
            json={"product_id": sample_product.id},
            headers=auth_headers
        )
        
        # Verificar que el contador aumentó
        response = client.get(
            "/api/v1/favorites/count",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_favorites"] == 1
    
    def test_clear_favorites_endpoint(self, client: TestClient, auth_headers, sample_product, sample_product_2):
        """Test endpoint para limpiar todos los favoritos"""
        # Agregar productos a favoritos
        client.post(
            "/api/v1/favorites/add",
            json={"product_id": sample_product.id},
            headers=auth_headers
        )
        client.post(
            "/api/v1/favorites/add",
            json={"product_id": sample_product_2.id},
            headers=auth_headers
        )
        
        # Limpiar favoritos
        response = client.delete(
            "/api/v1/favorites/clear",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["deleted_count"] == 2
        
        # Verificar que la lista está vacía
        response = client.get(
            "/api/v1/favorites/",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 0
    
    def test_favorites_pagination(self, client: TestClient, auth_headers, sample_product, sample_product_2):
        """Test paginación en endpoint de favoritos"""
        # Agregar productos a favoritos
        client.post(
            "/api/v1/favorites/add",
            json={"product_id": sample_product.id},
            headers=auth_headers
        )
        client.post(
            "/api/v1/favorites/add",
            json={"product_id": sample_product_2.id},
            headers=auth_headers
        )
        
        # Obtener solo el primer favorito
        response = client.get(
            "/api/v1/favorites/?skip=0&limit=1",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 2
        assert len(data["favorites"]) == 1 