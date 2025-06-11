"""
Tests de integración - Flujos completos de usuario
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestUserRegistrationFlow:
    """Test del flujo completo de registro de usuario"""
    
    def test_complete_registration_flow(self, client: TestClient):
        """Test flujo completo: registro -> login -> obtener perfil"""
        
        # 1. Registrar usuario
        register_data = {
            "email": "flowtest@example.com",
            "name": "Flow Test User",
            "password": "FlowTest123",
            "confirm_password": "FlowTest123",
            "user_type": "natural",
            "phone": "+58414111222",
            "preferred_currency": "VES"
        }
        
        register_response = client.post("/api/v1/auth/register", json=register_data)
        assert register_response.status_code == 201
        
        user_data = register_response.json()
        assert user_data["email"] == register_data["email"]
        assert user_data["is_active"] is True
        assert user_data["is_verified"] is False
        
        # 2. Hacer login
        login_data = {
            "email": "flowtest@example.com",
            "password": "FlowTest123"
        }
        
        login_response = client.post("/api/v1/auth/login", json=login_data)
        assert login_response.status_code == 200
        
        tokens = login_response.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        
        # 3. Obtener perfil de usuario
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        profile_response = client.get("/api/v1/auth/me", headers=headers)
        assert profile_response.status_code == 200
        
        profile_data = profile_response.json()
        assert profile_data["email"] == register_data["email"]
        assert profile_data["name"] == register_data["name"]
        
        # 4. Actualizar token
        refresh_data = {"refresh_token": tokens["refresh_token"]}
        refresh_response = client.post("/api/v1/auth/refresh", json=refresh_data)
        assert refresh_response.status_code == 200
        
        new_tokens = refresh_response.json()
        assert "access_token" in new_tokens
        assert "refresh_token" in new_tokens
        # Verify tokens are valid strings but don't compare them directly (they're always different)
        assert len(new_tokens["access_token"]) > 50
        assert len(new_tokens["refresh_token"]) > 50
        
        # 5. Logout
        logout_response = client.post("/api/v1/auth/logout", headers=headers)
        assert logout_response.status_code == 200
        
        logout_data = logout_response.json()
        assert logout_data["success"] is True


@pytest.mark.integration
class TestPasswordResetFlow:
    """Test del flujo completo de recuperación de contraseña"""
    
    def test_complete_password_reset_flow(self, client: TestClient, db):
        """Test flujo completo de reset de contraseña"""
        
        # 1. Registrar usuario
        register_data = {
            "email": "resettest@example.com",
            "name": "Reset Test User",
            "password": "OriginalPass123",
            "confirm_password": "OriginalPass123",
            "user_type": "natural",
            "preferred_currency": "VES"
        }
        
        register_response = client.post("/api/v1/auth/register", json=register_data)
        assert register_response.status_code == 201
        
        # 2. Solicitar reset de contraseña
        forgot_data = {"email": "resettest@example.com"}
        forgot_response = client.post("/api/v1/auth/forgot-password", json=forgot_data)
        assert forgot_response.status_code == 200
        
        # 3. Obtener token de reset de la base de datos (simulando email)
        from app.models.user import User
        user = db.query(User).filter(User.email == "resettest@example.com").first()
        assert user.reset_token is not None
        
        # 4. Resetear contraseña
        reset_data = {
            "token": user.reset_token,
            "new_password": "NewPassword456",
            "confirm_password": "NewPassword456"
        }
        
        reset_response = client.post("/api/v1/auth/reset-password", json=reset_data)
        assert reset_response.status_code == 200
        
        # 5. Probar login con nueva contraseña
        login_data = {
            "email": "resettest@example.com",
            "password": "NewPassword456"
        }
        
        login_response = client.post("/api/v1/auth/login", json=login_data)
        assert login_response.status_code == 200
        
        # 6. Verificar que la contraseña antigua ya no funciona
        old_login_data = {
            "email": "resettest@example.com",
            "password": "OriginalPass123"
        }
        
        old_login_response = client.post("/api/v1/auth/login", json=old_login_data)
        assert old_login_response.status_code == 401


@pytest.mark.integration
class TestEmailVerificationFlow:
    """Test del flujo completo de verificación de email"""
    
    def test_email_verification_flow(self, client: TestClient, db):
        """Test flujo completo de verificación de email"""
        
        # 1. Registrar usuario
        register_data = {
            "email": "verifytest@example.com",
            "name": "Verify Test User",
            "password": "VerifyPass123",
            "confirm_password": "VerifyPass123",
            "user_type": "natural",
            "preferred_currency": "VES"
        }
        
        register_response = client.post("/api/v1/auth/register", json=register_data)
        assert register_response.status_code == 201
        
        user_data = register_response.json()
        assert user_data["is_verified"] is False
        
        # 2. Obtener token de verificación de la base de datos
        from app.models.user import User
        user = db.query(User).filter(User.email == "verifytest@example.com").first()
        assert user.verification_token is not None
        
        # 3. Verificar email
        verify_data = {"token": user.verification_token}
        verify_response = client.post("/api/v1/auth/verify-email", json=verify_data)
        assert verify_response.status_code == 200
        
        verify_result = verify_response.json()
        assert verify_result["success"] is True
        
        # 4. Verificar que el usuario ahora está verificado
        db.refresh(user)
        assert user.is_verified is True
        assert user.verification_token is None
        
        # 5. Login y verificar estado
        login_data = {
            "email": "verifytest@example.com",
            "password": "VerifyPass123"
        }
        
        login_response = client.post("/api/v1/auth/login", json=login_data)
        assert login_response.status_code == 200
        
        tokens = login_response.json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        
        profile_response = client.get("/api/v1/auth/me", headers=headers)
        profile_data = profile_response.json()
        assert profile_data["is_verified"] is True


@pytest.mark.integration
class TestMultipleUserInteractions:
    """Test interacciones entre múltiples usuarios"""
    
    def test_multiple_users_registration_and_login(self, client: TestClient):
        """Test registro y login de múltiples usuarios"""
        
        users_data = [
            {
                "email": "user1@test.com",
                "name": "User One",
                "password": "User1Pass123",
                "confirm_password": "User1Pass123",
                "user_type": "natural",
                "preferred_currency": "VES"
            },
            {
                "email": "user2@test.com",
                "name": "User Two",
                "password": "User2Pass456",
                "confirm_password": "User2Pass456",
                "user_type": "juridico",
                "preferred_currency": "USD"
            },
            {
                "email": "user3@test.com",
                "name": "User Three",
                "password": "User3Pass789",
                "confirm_password": "User3Pass789",
                "user_type": "natural",
                "preferred_currency": "VES"
            }
        ]
        
        tokens_list = []
        
        # Registrar todos los usuarios
        for user_data in users_data:
            register_response = client.post("/api/v1/auth/register", json=user_data)
            assert register_response.status_code == 201
            
            # Login cada usuario
            login_data = {
                "email": user_data["email"],
                "password": user_data["password"]
            }
            
            login_response = client.post("/api/v1/auth/login", json=login_data)
            assert login_response.status_code == 200
            
            tokens = login_response.json()
            tokens_list.append(tokens)
        
        # Verificar que todos los usuarios pueden acceder a su perfil
        for i, tokens in enumerate(tokens_list):
            headers = {"Authorization": f"Bearer {tokens['access_token']}"}
            profile_response = client.get("/api/v1/auth/me", headers=headers)
            assert profile_response.status_code == 200
            
            profile_data = profile_response.json()
            assert profile_data["email"] == users_data[i]["email"]
            assert profile_data["name"] == users_data[i]["name"]


@pytest.mark.integration
class TestErrorHandlingFlow:
    """Test manejo de errores en flujos completos"""
    
    def test_invalid_registration_attempts(self, client: TestClient):
        """Test múltiples intentos de registro inválidos"""
        
        # 1. Contraseñas que no coinciden
        invalid_data1 = {
            "email": "error1@test.com",
            "name": "Error User 1",
            "password": "Password123",
            "confirm_password": "DifferentPassword123",
            "user_type": "natural",
            "preferred_currency": "VES"
        }
        
        response1 = client.post("/api/v1/auth/register", json=invalid_data1)
        assert response1.status_code == 422
        
        # 2. Email inválido
        invalid_data2 = {
            "email": "invalid-email",
            "name": "Error User 2",
            "password": "Password123",
            "confirm_password": "Password123",
            "user_type": "natural",
            "preferred_currency": "VES"
        }
        
        response2 = client.post("/api/v1/auth/register", json=invalid_data2)
        assert response2.status_code == 422
        
        # 3. Contraseña débil
        invalid_data3 = {
            "email": "error3@test.com",
            "name": "Error User 3",
            "password": "123",
            "confirm_password": "123",
            "user_type": "natural",
            "preferred_currency": "VES"
        }
        
        response3 = client.post("/api/v1/auth/register", json=invalid_data3)
        assert response3.status_code == 422
        
        # 4. Registrar usuario válido para probar email duplicado
        valid_data = {
            "email": "valid@test.com",
            "name": "Valid User",
            "password": "ValidPass123",
            "confirm_password": "ValidPass123",
            "user_type": "natural",
            "preferred_currency": "VES"
        }
        
        response4 = client.post("/api/v1/auth/register", json=valid_data)
        assert response4.status_code == 201
        
        # 5. Intentar registrar con email duplicado
        response5 = client.post("/api/v1/auth/register", json=valid_data)
        assert response5.status_code == 400 