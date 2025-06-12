"""
Tests para los endpoints de autenticación
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from app.core.security import verify_password, create_access_token


class TestAuthRegistration:
    """Tests para registro de usuarios"""
    
    def test_register_user_success(self, client: TestClient, test_user_data):
        """Test registro exitoso de usuario natural"""
        response = client.post("/api/v1/auth/register/natural", json=test_user_data)
        
        assert response.status_code == 201
        data = response.json()
        
        assert data["email"] == test_user_data["email"]
        assert data["first_name"] == test_user_data["first_name"]
        assert data["last_name"] == test_user_data["last_name"]
        assert data["cedula"] == test_user_data["cedula"]
        assert data["user_type"] == "natural"
        assert data["phone"] == test_user_data["phone"]
        assert data["preferred_currency"] == test_user_data["preferred_currency"]
        assert data["is_active"] is True
        assert data["is_verified"] is False  # User needs to verify email
        assert "id" in data
        assert "created_at" in data
    
    def test_register_juridico_user_success(self, client: TestClient, test_user_data_juridico):
        """Test registro exitoso de usuario jurídico"""
        response = client.post("/api/v1/auth/register/juridico", json=test_user_data_juridico)
        
        assert response.status_code == 201
        data = response.json()
        
        assert data["email"] == test_user_data_juridico["email"]
        assert data["company_name"] == test_user_data_juridico["company_name"]
        assert data["rif"] == test_user_data_juridico["rif"]
        assert data["registro_mercantil"] == test_user_data_juridico["registro_mercantil"]
        assert data["representante_legal_cedula"] == test_user_data_juridico["representante_legal_cedula"]
        assert data["representante_legal_nombre"] == test_user_data_juridico["representante_legal_nombre"]
        assert data["user_type"] == "juridico"
        assert data["preferred_currency"] == "USD"
        assert data["is_active"] is True
        assert data["is_verified"] is False
    
    def test_register_duplicate_email(self, client: TestClient, test_user_data):
        """Test registro con email duplicado"""
        # Register first user
        client.post("/api/v1/auth/register/natural", json=test_user_data)
        
        # Try to register with same email
        response = client.post("/api/v1/auth/register/natural", json=test_user_data)
        
        assert response.status_code == 400
        assert "ya está registrado" in response.json()["detail"]
    
    def test_register_weak_password_natural(self, client: TestClient, test_user_data):
        """Test registro natural con contraseña débil"""
        test_user_data["password"] = "123"
        
        response = client.post("/api/v1/auth/register/natural", json=test_user_data)
        
        assert response.status_code == 422
    
    def test_register_invalid_email_natural(self, client: TestClient, test_user_data):
        """Test registro natural con email inválido"""
        test_user_data["email"] = "invalid-email"
        
        response = client.post("/api/v1/auth/register/natural", json=test_user_data)
        
        assert response.status_code == 422
    
    def test_register_invalid_currency_natural(self, client: TestClient, test_user_data):
        """Test registro natural con moneda inválida"""
        test_user_data["preferred_currency"] = "EUR"
        
        response = client.post("/api/v1/auth/register/natural", json=test_user_data)
        
        assert response.status_code == 422
    
    def test_register_missing_required_fields_natural(self, client: TestClient):
        """Test registro natural con campos requeridos faltantes"""
        incomplete_data = {
            "email": "test@example.com",
            "password": "TestPassword123"
            # Missing required fields: first_name, last_name, cedula, phone
        }
        
        response = client.post("/api/v1/auth/register/natural", json=incomplete_data)
        
        assert response.status_code == 422
    
    def test_register_missing_required_fields_juridico(self, client: TestClient):
        """Test registro jurídico con campos requeridos faltantes"""
        incomplete_data = {
            "email": "empresa@test.com",
            "password": "EmpresaPass456",
            "company_name": "Test Company"
            # Missing many required fields
        }
        
        response = client.post("/api/v1/auth/register/juridico", json=incomplete_data)
        
        assert response.status_code == 422


class TestAuthLogin:
    """Tests para login de usuarios"""
    
    def test_login_success(self, client: TestClient, test_user: User, test_login_data):
        """Test login exitoso"""
        response = client.post("/api/v1/auth/login", json=test_login_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data
        assert data["expires_in"] > 0
    
    def test_login_wrong_email(self, client: TestClient, invalid_login_data):
        """Test login con email incorrecto"""
        response = client.post("/api/v1/auth/login", json=invalid_login_data)
        
        assert response.status_code == 401
        assert "incorrectos" in response.json()["detail"]
    
    def test_login_wrong_password(self, client: TestClient, test_user: User):
        """Test login con contraseña incorrecta"""
        login_data = {
            "email": test_user.email,
            "password": "wrongpassword"
        }
        
        response = client.post("/api/v1/auth/login", json=login_data)
        
        assert response.status_code == 401
    
    def test_login_inactive_user(self, client: TestClient, db: Session, test_user: User):
        """Test login con usuario inactivo"""
        # Deactivate user
        test_user.is_active = False
        db.commit()
        
        login_data = {
            "email": test_user.email,
            "password": "testpass123"
        }
        
        response = client.post("/api/v1/auth/login", json=login_data)
        
        assert response.status_code == 401
        assert "desactivada" in response.json()["detail"]


class TestAuthTokens:
    """Tests para manejo de tokens"""
    
    def test_get_current_user_success(self, client: TestClient, test_user: User, auth_headers):
        """Test obtener información del usuario actual"""
        response = client.get("/api/v1/auth/me", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["email"] == test_user.email
        assert data["first_name"] == test_user.first_name
        assert data["last_name"] == test_user.last_name
        assert data["user_type"] == "natural"
        assert data["id"] == test_user.id
    
    def test_get_current_user_no_token(self, client: TestClient):
        """Test obtener usuario sin token"""
        response = client.get("/api/v1/auth/me")
        
        assert response.status_code == 403
    
    def test_get_current_user_invalid_token(self, client: TestClient):
        """Test obtener usuario con token inválido"""
        headers = {"Authorization": "Bearer invalid_token"}
        response = client.get("/api/v1/auth/me", headers=headers)
        
        assert response.status_code == 401
    
    def test_refresh_token_success(self, client: TestClient, test_user: User, test_login_data):
        """Test actualizar token exitosamente"""
        # Login to get tokens
        login_response = client.post("/api/v1/auth/login", json=test_login_data)
        tokens = login_response.json()
        
        # Refresh token
        refresh_data = {"refresh_token": tokens["refresh_token"]}
        response = client.post("/api/v1/auth/refresh", json=refresh_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
    
    def test_refresh_token_invalid(self, client: TestClient):
        """Test actualizar con token inválido"""
        refresh_data = {"refresh_token": "invalid_refresh_token"}
        response = client.post("/api/v1/auth/refresh", json=refresh_data)
        
        assert response.status_code == 401


class TestAuthPasswordManagement:
    """Tests para gestión de contraseñas"""
    
    def test_forgot_password_success(self, client: TestClient, test_user: User):
        """Test solicitud de recuperación de contraseña"""
        forgot_data = {"email": test_user.email}
        response = client.post("/api/v1/auth/forgot-password", json=forgot_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "recuperación" in data["message"]
    
    def test_forgot_password_nonexistent_email(self, client: TestClient):
        """Test solicitud de recuperación con email inexistente"""
        forgot_data = {"email": "nonexistent@example.com"}
        response = client.post("/api/v1/auth/forgot-password", json=forgot_data)
        
        # Should return success for security (don't reveal if email exists)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
    
    def test_change_password_success(self, client: TestClient, test_user: User, auth_headers):
        """Test cambio de contraseña exitoso"""
        response = client.post(
            "/api/v1/auth/change-password",
            headers=auth_headers,
            params={
                "current_password": "testpass123",
                "new_password": "NewPassword456"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "exitosamente" in data["message"]
    
    def test_change_password_wrong_current(self, client: TestClient, auth_headers):
        """Test cambio de contraseña con contraseña actual incorrecta"""
        response = client.post(
            "/api/v1/auth/change-password",
            headers=auth_headers,
            params={
                "current_password": "wrongpassword",
                "new_password": "NewPassword456"
            }
        )
        
        assert response.status_code == 401
        assert "incorrecta" in response.json()["detail"]


class TestAuthEmailVerification:
    """Tests para verificación de email"""
    
    def test_verify_email_success(self, client: TestClient, db: Session):
        """Test verificación de email exitosa"""
        # Create user with verification token
        from app.core.security import get_password_hash
        user = User(
            email="verify@example.com",
            first_name="Verify",
            last_name="User",
            cedula="V12345678",
            phone="+58414123456",
            hashed_password=get_password_hash("password123"),
            user_type="natural",
            is_verified=False,
            verification_token="test-verification-token"
        )
        db.add(user)
        db.commit()
        
        verify_data = {"token": "test-verification-token"}
        response = client.post("/api/v1/auth/verify-email", json=verify_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "verificado" in data["message"]
    
    def test_verify_email_invalid_token(self, client: TestClient):
        """Test verificación con token inválido"""
        verify_data = {"token": "invalid-token"}
        response = client.post("/api/v1/auth/verify-email", json=verify_data)
        
        assert response.status_code == 404
    
    def test_resend_verification_success(self, client: TestClient, db: Session):
        """Test reenvío de verificación exitoso"""
        # Create unverified user
        from app.core.security import get_password_hash
        user = User(
            email="resend@example.com",
            first_name="Resend",
            last_name="User",
            cedula="V87654321",
            phone="+58414987654",
            hashed_password=get_password_hash("password123"),
            user_type="natural",
            is_verified=False,
            verification_token="old-token"
        )
        db.add(user)
        db.commit()
        
        resend_data = {"email": "resend@example.com"}
        response = client.post("/api/v1/auth/resend-verification", json=resend_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestAuthLogout:
    """Tests para logout"""
    
    def test_logout_success(self, client: TestClient, auth_headers):
        """Test logout exitoso"""
        response = client.post("/api/v1/auth/logout", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "cerrada" in data["message"]
    
    def test_logout_no_token(self, client: TestClient):
        """Test logout sin token"""
        response = client.post("/api/v1/auth/logout")
        
        assert response.status_code == 403 