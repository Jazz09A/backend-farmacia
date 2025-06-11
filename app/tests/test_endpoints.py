"""
Tests básicos para los endpoints de la API
"""

import pytest
from fastapi.testclient import TestClient


class TestBasicEndpoints:
    """Tests para endpoints básicos"""
    
    def test_root_endpoint(self, client: TestClient):
        """Test endpoint raíz"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "FarmaPlus API" in data["message"]
        assert data["success"] is True
    
    def test_health_endpoint(self, client: TestClient):
        """Test endpoint de salud"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["success"] is True
    
    def test_api_info_endpoint(self, client: TestClient):
        """Test endpoint de información de la API"""
        response = client.get("/api/v1/info")
        assert response.status_code == 200
        data = response.json()
        assert "FarmaPlus API" in data["name"]
        assert "endpoints" in data
        assert data["success"] is True


class TestAuthEndpoints:
    """Tests para endpoints de autenticación"""
    
    def test_register_success(self, client: TestClient, test_user_data):
        """Test registro exitoso"""
        response = client.post("/api/v1/auth/register", json=test_user_data)
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == test_user_data["email"]
        assert data["name"] == test_user_data["name"]
        assert data["is_active"] is True
    
    def test_register_duplicate_email(self, client: TestClient, test_user_data):
        """Test registro con email duplicado"""
        # Register first user
        client.post("/api/v1/auth/register", json=test_user_data)
        
        # Try again with same email
        response = client.post("/api/v1/auth/register", json=test_user_data)
        assert response.status_code == 400
    
    def test_login_success(self, client: TestClient, test_user, test_login_data):
        """Test login exitoso"""
        response = client.post("/api/v1/auth/login", json=test_login_data)
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
    
    def test_login_invalid_credentials(self, client: TestClient):
        """Test login con credenciales inválidas"""
        login_data = {
            "email": "wrong@example.com",
            "password": "wrongpassword"
        }
        response = client.post("/api/v1/auth/login", json=login_data)
        assert response.status_code == 401
    
    def test_get_current_user_success(self, client: TestClient, auth_headers):
        """Test obtener usuario actual"""
        response = client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        assert "name" in data
    
    def test_get_current_user_no_token(self, client: TestClient):
        """Test obtener usuario sin token"""
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 403
    
    def test_logout_success(self, client: TestClient, auth_headers):
        """Test logout exitoso"""
        response = client.post("/api/v1/auth/logout", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True 