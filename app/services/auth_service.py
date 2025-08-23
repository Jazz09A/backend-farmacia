from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta, timezone

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
    generate_verification_token,
    generate_reset_token
)
from app.core.exceptions import (
    InvalidCredentialsException,
    UserAlreadyExistsException,
    UserNotFoundException,
)
from app.schemas.role import UserRole
from app.config.settings import settings
from app.services.email_service import email_service # Import the service instance

class AuthService:
    def __init__(self, db: Session):
        self.db = db

    async def register_user(self, user_data: RegisterRequest) -> UserResponse:
        """Register a new user and send a verification email."""
        try:
            existing_user = self.db.query(User).filter(User.email == user_data.email).first()
            if existing_user:
                raise UserAlreadyExistsException("El email ya está registrado")

            hashed_password = get_password_hash(user_data.password)
            verification_token = generate_verification_token()

            user_dict = user_data.model_dump(exclude={'password'})

            db_user = User(
                **user_dict,
                hashed_password=hashed_password,
                is_verified=False,
                role=UserRole.USER,
                verification_token=verification_token
            )

            self.db.add(db_user)
            self.db.commit()

            # Send verification email
            verification_link = f"http://localhost:8000/api/v1/auth/verify-email/{verification_token}" # Adjust the base URL as needed
            await email_service.send_email(
                to_email=db_user.email,
                subject="Verifica tu cuenta en Grupo Drozainka",
                template_name="verify_email.html",
                context={
                    "verification_link": verification_link,
                    "year": datetime.now().year
                }
            )

            self.db.refresh(db_user)
            return UserResponse.model_validate(db_user)

        except IntegrityError:
            self.db.rollback()
            raise UserAlreadyExistsException("Error al crear el usuario")

    @staticmethod
    async def authenticate_user(db: Session, login_data: LoginRequest) -> Token:
        """Authenticate user and return tokens."""
        try:
            user = db.query(User).filter(User.email == login_data.email).first()
            
            if not user:
                print(f"Usuario no encontrado para email: {login_data.email}")
                raise InvalidCredentialsException()
            
            if not verify_password(login_data.password, user.hashed_password):
                print(f"Contraseña incorrecta para usuario: {login_data.email}")
                raise InvalidCredentialsException()
            
            if not user.is_active:
                print(f"Cuenta desactivada para usuario: {login_data.email}")
                raise InvalidCredentialsException("Cuenta desactivada")
            
            # TODO: Verify email if not verified
            # Update last login
            user.last_login = datetime.now(timezone.utc)
            db.commit()
            
            # Create tokens
            access_token = create_access_token(data={"sub": user.email})
            refresh_token = create_refresh_token(data={"sub": user.email})
            
            return Token(
                access_token=access_token,
                refresh_token=refresh_token,
                token_type="bearer",
                expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                role=user.role
            )
            
        except InvalidCredentialsException:
            # Re-raise InvalidCredentialsException as is
            raise
        except Exception as e:
            print(f"Error en authenticate_user: {str(e)}")
            import traceback
            traceback.print_exc()
            raise InvalidCredentialsException()
    
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
                expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                role=user.role
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
        await email_service.send_email(
            to_email=user.email,
            subject="Verifica tu cuenta en Grupo Drozainka",
            template_name="verify_email.html",
            context={
                "verification_link": f"http://localhost:8000/api/v1/auth/verify-email/{user.verification_token}",
                "year": datetime.now().year
            }
        )
        
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
    
    @staticmethod
    def get_user_info(db_user: User) -> UserResponse:
        """Get user information as UserResponse."""
        return UserResponse.model_validate(db_user)

    @staticmethod   
    async def get_email_verification(db: Session, email: str) -> dict:
        """Get email verification."""
        user = db.query(User).filter(User.email == email).first()
        if user:
            raise HTTPException(status_code=400, detail="Email encontrado")
        return {"message": "Email no encontrado", "success": True}
    