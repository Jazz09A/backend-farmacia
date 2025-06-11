"""
Tests básicos para validar la configuración de testing
"""

import pytest
from fastapi.testclient import TestClient


class TestBasicSetup:
    """Tests básicos para validar que el setup funciona"""
    
    def test_client_setup(self, client: TestClient):
        """Test que el cliente de testing funciona"""
        assert client is not None
        assert hasattr(client, 'get')
        assert hasattr(client, 'post')
    
    def test_database_setup(self, db):
        """Test que la base de datos de testing funciona"""
        assert db is not None
        assert hasattr(db, 'query')
        assert hasattr(db, 'add')
        assert hasattr(db, 'commit')
    
    def test_root_endpoint_works(self, client: TestClient):
        """Test que el endpoint raíz funciona"""
        response = client.get("/")
        assert response.status_code == 200
        
        data = response.json()
        assert "message" in data
        assert data["success"] is True
    
    def test_health_endpoint_works(self, client: TestClient):
        """Test que el endpoint de salud funciona"""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert data["success"] is True


class TestFixtures:
    """Tests para validar que las fixtures funcionan"""
    
    def test_user_data_fixture(self, test_user_data):
        """Test que la fixture de datos de usuario funciona"""
        assert "email" in test_user_data
        assert "name" in test_user_data
        assert "password" in test_user_data
        assert "user_type" in test_user_data
        assert test_user_data["user_type"] in ["natural", "juridico"]
    
    def test_user_fixture(self, test_user):
        """Test que la fixture de usuario funciona"""
        assert test_user.id is not None
        assert test_user.email is not None
        assert test_user.name is not None
        assert test_user.is_active is True
    
    def test_auth_headers_fixture(self, auth_headers):
        """Test que la fixture de headers de auth funciona"""
        assert "Authorization" in auth_headers
        assert auth_headers["Authorization"].startswith("Bearer ")
    
    def test_sample_product_data_fixture(self, sample_product_data):
        """Test que la fixture de datos de producto funciona"""
        assert "name" in sample_product_data
        assert "brand" in sample_product_data
        assert "category" in sample_product_data
        assert "price_ves" in sample_product_data 