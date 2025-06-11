"""
Tests para los servicios de negocio
"""

import pytest
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.services.auth_service import AuthService
from app.schemas.auth import RegisterRequest, LoginRequest
from app.models.user import User
from app.core.security import verify_password, get_password_hash
from app.core.exceptions import (
    UserAlreadyExistsException,
    InvalidCredentialsException,
    UserNotFoundException
)


class TestAuthService:
    """Tests para el servicio de autenticación"""
    
    @pytest.mark.asyncio
    async def test_register_user_success(self, db: Session):
        """Test registro exitoso de usuario"""
        user_data = RegisterRequest(
            email="newuser@example.com",
            name="New User",
            password="NewPassword123",
            confirm_password="NewPassword123",
            user_type="natural",
            phone="+58414123456",
            preferred_currency="VES"
        )
        
        result = await AuthService.register_user(db, user_data)
        
        assert result.email == "newuser@example.com"
        assert result.name == "New User"
        assert result.user_type == "natural"
        assert result.is_active is True
        assert result.is_verified is False
        
        # Verify user was created in database
        db_user = db.query(User).filter(User.email == "newuser@example.com").first()
        assert db_user is not None
        assert verify_password("NewPassword123", db_user.hashed_password)
    
    @pytest.mark.asyncio
    async def test_register_user_duplicate_email(self, db: Session, test_user):
        """Test registro con email duplicado"""
        user_data = RegisterRequest(
            email=test_user.email,  # Same email as existing user
            name="Duplicate User",
            password="Password123",
            confirm_password="Password123",
            user_type="natural",
            preferred_currency="VES"
        )
        
        with pytest.raises(UserAlreadyExistsException):
            await AuthService.register_user(db, user_data)
    
    @pytest.mark.asyncio
    async def test_authenticate_user_success(self, db: Session, test_user):
        """Test autenticación exitosa"""
        login_data = LoginRequest(
            email=test_user.email,
            password="testpass123"
        )
        
        result = await AuthService.authenticate_user(db, login_data)
        
        assert "access_token" in result.dict()
        assert "refresh_token" in result.dict()
        assert result.token_type == "bearer"
        assert result.expires_in > 0
    
    @pytest.mark.asyncio
    async def test_authenticate_user_wrong_password(self, db: Session, test_user):
        """Test autenticación con contraseña incorrecta"""
        login_data = LoginRequest(
            email=test_user.email,
            password="wrongpassword"
        )
        
        with pytest.raises(InvalidCredentialsException):
            await AuthService.authenticate_user(db, login_data)
    
    @pytest.mark.asyncio
    async def test_authenticate_user_nonexistent(self, db: Session):
        """Test autenticación con usuario inexistente"""
        login_data = LoginRequest(
            email="nonexistent@example.com",
            password="anypassword"
        )
        
        with pytest.raises(InvalidCredentialsException):
            await AuthService.authenticate_user(db, login_data)
    
    @pytest.mark.asyncio
    async def test_authenticate_inactive_user(self, db: Session, test_user):
        """Test autenticación con usuario inactivo"""
        # Deactivate user
        test_user.is_active = False
        db.commit()
        
        login_data = LoginRequest(
            email=test_user.email,
            password="testpass123"
        )
        
        with pytest.raises(InvalidCredentialsException):
            await AuthService.authenticate_user(db, login_data)
    
    @pytest.mark.asyncio
    async def test_refresh_access_token_success(self, db: Session, test_user):
        """Test actualización exitosa de token"""
        # First authenticate to get refresh token
        login_data = LoginRequest(
            email=test_user.email,
            password="testpass123"
        )
        
        tokens = await AuthService.authenticate_user(db, login_data)
        
        # Now refresh the token
        result = await AuthService.refresh_access_token(db, tokens.refresh_token)
        
        assert "access_token" in result.dict()
        assert "refresh_token" in result.dict()
        assert result.token_type == "bearer"
        assert result.expires_in > 0
    
    @pytest.mark.asyncio
    async def test_refresh_token_invalid(self, db: Session):
        """Test actualización con token inválido"""
        with pytest.raises(InvalidCredentialsException):
            await AuthService.refresh_access_token(db, "invalid_refresh_token")
    
    @pytest.mark.asyncio
    async def test_verify_email_success(self, db: Session):
        """Test verificación exitosa de email"""
        # Create user with verification token
        user = User(
            email="verify@example.com",
            name="Verify User",
            hashed_password=get_password_hash("password123"),
            user_type="natural",
            is_verified=False,
            verification_token="test-verification-token"
        )
        db.add(user)
        db.commit()
        
        result = await AuthService.verify_email(db, "test-verification-token")
        
        assert result["success"] is True
        assert "verificado" in result["message"]
        
        # Check that user is now verified
        db.refresh(user)
        assert user.is_verified is True
        assert user.verification_token is None
    
    @pytest.mark.asyncio
    async def test_verify_email_invalid_token(self, db: Session):
        """Test verificación con token inválido"""
        with pytest.raises(UserNotFoundException):
            await AuthService.verify_email(db, "invalid-token")
    
    @pytest.mark.asyncio
    async def test_send_reset_password_email_success(self, db: Session, test_user):
        """Test solicitud de reset de contraseña"""
        result = await AuthService.send_reset_password_email(db, test_user.email)
        
        assert result["success"] is True
        assert "recuperación" in result["message"]
        
        # Check that reset token was set
        db.refresh(test_user)
        assert test_user.reset_token is not None
        assert test_user.reset_token_expires is not None
        assert test_user.reset_token_expires > datetime.utcnow()
    
    @pytest.mark.asyncio
    async def test_send_reset_password_email_nonexistent(self, db: Session):
        """Test solicitud de reset con email inexistente"""
        result = await AuthService.send_reset_password_email(db, "nonexistent@example.com")
        
        # Should still return success for security
        assert result["success"] is True
    
    @pytest.mark.asyncio
    async def test_reset_password_success(self, db: Session, test_user):
        """Test reset exitoso de contraseña"""
        # Set reset token
        test_user.reset_token = "valid-reset-token"
        test_user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        db.commit()
        
        result = await AuthService.reset_password(db, "valid-reset-token", "NewPassword123")
        
        assert result["success"] is True
        assert "actualizada" in result["message"]
        
        # Check that password was changed
        db.refresh(test_user)
        assert verify_password("NewPassword123", test_user.hashed_password)
        assert test_user.reset_token is None
        assert test_user.reset_token_expires is None
    
    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(self, db: Session):
        """Test reset con token inválido"""
        with pytest.raises(UserNotFoundException):
            await AuthService.reset_password(db, "invalid-token", "NewPassword123")
    
    @pytest.mark.asyncio
    async def test_reset_password_expired_token(self, db: Session, test_user):
        """Test reset con token expirado"""
        # Set expired reset token
        test_user.reset_token = "expired-token"
        test_user.reset_token_expires = datetime.utcnow() - timedelta(hours=1)
        db.commit()
        
        with pytest.raises(UserNotFoundException):
            await AuthService.reset_password(db, "expired-token", "NewPassword123")
    
    @pytest.mark.asyncio
    async def test_change_password_success(self, db: Session, test_user):
        """Test cambio exitoso de contraseña"""
        result = await AuthService.change_password(
            db, 
            test_user.id, 
            "testpass123", 
            "NewPassword456"
        )
        
        assert result["success"] is True
        assert "exitosamente" in result["message"]
        
        # Check that password was changed
        db.refresh(test_user)
        assert verify_password("NewPassword456", test_user.hashed_password)
    
    @pytest.mark.asyncio
    async def test_change_password_wrong_current(self, db: Session, test_user):
        """Test cambio con contraseña actual incorrecta"""
        with pytest.raises(InvalidCredentialsException):
            await AuthService.change_password(
                db, 
                test_user.id, 
                "wrongpassword", 
                "NewPassword456"
            )
    
    @pytest.mark.asyncio
    async def test_change_password_nonexistent_user(self, db: Session):
        """Test cambio de contraseña con usuario inexistente"""
        with pytest.raises(UserNotFoundException):
            await AuthService.change_password(
                db, 
                "nonexistent-user-id", 
                "anypassword", 
                "newpassword"
            ) 