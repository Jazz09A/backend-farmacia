from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
from typing import Optional
import uuid

from app.models.user import User
from app.models.address import UserPreferences
from app.schemas.auth import LoginRequest, RegisterRequest, Token
from app.schemas.user import UserResponse
from app.core.security import (
    verify_password, 
    get_password_hash, 
    create_access_token, 
    create_refresh_token,
    verify_token,
    create_url_safe_token,
    verify_url_safe_token,
    generate_verification_token,
    generate_reset_token
)
from app.core.exceptions import (
    InvalidCredentialsException,
    UserAlreadyExistsException,
    UserNotFoundException,
    EmailNotVerifiedException
)
from app.config.settings import settings

class AuthService:
    @staticmethod
    async def register_user(db: Session, user_data: RegisterRequest) -> UserResponse:
        """Register a new user."""
        try:
            # Check if user already exists
            existing_user = db.query(User).filter(User.email == user_data.email).first()
            if existing_user:
                raise UserAlreadyExistsException("El email ya está registrado")
            
            # Create new user
            hashed_password = get_password_hash(user_data.password)
            db_user = User(
                email=user_data.email,
                name=user_data.name,
                hashed_password=hashed_password,
                user_type=user_data.user_type,
                phone=user_data.phone,
                preferred_currency=user_data.preferred_currency,
                verification_token=generate_verification_token(),
                is_verified=False  # User needs to verify email
            )
            
            db.add(db_user)
            db.commit()
            db.refresh(db_user)
            
            # Create user preferences
            user_preferences = UserPreferences(
                user_id=db_user.id,
                preferred_currency=user_data.preferred_currency
            )
            db.add(user_preferences)
            db.commit()
            
            # TODO: Send verification email
            # await EmailService.send_verification_email(db_user.email, db_user.verification_token)
            
            return UserResponse.from_orm(db_user)
            
        except IntegrityError:
            db.rollback()
            raise UserAlreadyExistsException("Error al crear el usuario")
    
    @staticmethod
    async def authenticate_user(db: Session, login_data: LoginRequest) -> Token:
        """Authenticate user and return tokens."""
        user = db.query(User).filter(User.email == login_data.email).first()
        
        if not user or not verify_password(login_data.password, user.hashed_password):
            raise InvalidCredentialsException()
        
        if not user.is_active:
            raise InvalidCredentialsException("Cuenta desactivada")
        
        # Update last login
        user.last_login = datetime.utcnow()
        db.commit()
        
        # Create tokens
        access_token = create_access_token(data={"sub": user.email})
        refresh_token = create_refresh_token(data={"sub": user.email})
        
        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
    
    @staticmethod
    async def refresh_access_token(db: Session, refresh_token: str) -> Token:
        """Refresh access token using refresh token."""
        try:
            email = verify_token(refresh_token, "refresh")
            user = db.query(User).filter(User.email == email).first()
            
            if not user or not user.is_active:
                raise InvalidCredentialsException("Usuario no válido")
            
            # Create new tokens
            access_token = create_access_token(data={"sub": user.email})
            new_refresh_token = create_refresh_token(data={"sub": user.email})
            
            return Token(
                access_token=access_token,
                refresh_token=new_refresh_token,
                token_type="bearer",
                expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            )
        except Exception:
            raise InvalidCredentialsException("Token de actualización inválido")
    
    @staticmethod
    async def verify_email(db: Session, token: str) -> dict:
        """Verify user email with token."""
        user = db.query(User).filter(User.verification_token == token).first()
        
        if not user:
            raise UserNotFoundException("Token de verificación inválido")
        
        if user.is_verified:
            return {"message": "Email ya verificado", "success": True}
        
        user.is_verified = True
        user.verification_token = None
        db.commit()
        
        return {"message": "Email verificado exitosamente", "success": True}
    
    @staticmethod
    async def send_reset_password_email(db: Session, email: str) -> dict:
        """Send password reset email."""
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            # Don't reveal if email exists or not for security
            return {"message": "Si el email existe, se enviará un enlace de recuperación", "success": True}
        
        # Generate reset token
        reset_token = generate_reset_token()
        user.reset_token = reset_token
        user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        db.commit()
        
        # TODO: Send reset email
        # await EmailService.send_password_reset_email(user.email, reset_token)
        
        return {"message": "Si el email existe, se enviará un enlace de recuperación", "success": True}
    
    @staticmethod
    async def reset_password(db: Session, token: str, new_password: str) -> dict:
        """Reset user password with token."""
        user = db.query(User).filter(
            User.reset_token == token,
            User.reset_token_expires > datetime.utcnow()
        ).first()
        
        if not user:
            raise UserNotFoundException("Token de recuperación inválido o expirado")
        
        # Update password
        user.hashed_password = get_password_hash(new_password)
        user.reset_token = None
        user.reset_token_expires = None
        db.commit()
        
        return {"message": "Contraseña actualizada exitosamente", "success": True}
    
    @staticmethod
    async def resend_verification_email(db: Session, email: str) -> dict:
        """Resend verification email."""
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            raise UserNotFoundException("Usuario no encontrado")
        
        if user.is_verified:
            return {"message": "Email ya verificado", "success": True}
        
        # Generate new verification token
        user.verification_token = generate_verification_token()
        db.commit()
        
        # TODO: Send verification email
        # await EmailService.send_verification_email(user.email, user.verification_token)
        
        return {"message": "Email de verificación enviado", "success": True}
    
    @staticmethod
    async def change_password(db: Session, user_id: str, current_password: str, new_password: str) -> dict:
        """Change user password."""
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise UserNotFoundException()
        
        if not verify_password(current_password, user.hashed_password):
            raise InvalidCredentialsException("Contraseña actual incorrecta")
        
        user.hashed_password = get_password_hash(new_password)
        db.commit()
        
        return {"message": "Contraseña cambiada exitosamente", "success": True} 