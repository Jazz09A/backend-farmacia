from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import timedelta

from app.models.user import User
from app.config.logging_config import get_logger, log_error
from app.schemas.auth import LoginRequest, RegisterRequest, Token
from app.schemas.user import UserResponse
from app.core.security import (
    verify_password, 
    get_password_hash, 
    create_access_token, 
    create_refresh_token,
    verify_token,
    generate_verification_token,
    generate_reset_token,
    create_url_safe_token,
    verify_url_safe_token
)
from app.core.exceptions import (
    InvalidCredentialsException,
    UserAlreadyExistsException,
    UserNotFoundException,
)
from app.schemas.role import UserRole
from app.config.settings import Settings
from app.services.email_service import email_service # Import the service instance
from app.services.source_system_service import source_system_service
from app.services.source_system_user_creation_service import SourceSystemUserCreationService
from app.utils.timezone import get_ve_now
settings = Settings()
class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.auth_logger = get_logger("auth")
        self.error_logger = get_logger("errors")

    async def register_user(self, user_data: RegisterRequest) -> UserResponse:
        """Register a new user and send a verification email."""
        self.auth_logger.info(
            f"Attempting user registration for email: {user_data.email}",
            extra={
                'email': user_data.email, 
                'user_email': user_data.email,
                'user_type': user_data.user_type,
                'event': 'registration_attempt'
            }
        )
        
        try:
            existing_user = self.db.query(User).filter(User.email == user_data.email).first()
            if existing_user:
                self.auth_logger.warning(
                    f"Registration failed - email already exists: {user_data.email}",
                    extra={
                        'email': user_data.email, 
                        'user_email': user_data.email,
                        'reason': 'email_exists',
                        'event': 'registration_failed'
                    }
                )
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
            
            self.auth_logger.info(
                f"User successfully registered: {db_user.email}",
                extra={
                    'user_id': db_user.id,
                    'email': db_user.email,
                    'user_email': db_user.email,
                    'user_type': db_user.user_type,
                    'event': 'user_registered'
                }
            )

            # Send verification email
            verification_link = f"{settings.FRONTEND_URL}/verify-email/{verification_token}" # Adjust the base URL as needed
            await email_service.send_email(
                to_email=db_user.email,
                subject="Verifica tu cuenta en Grupo Drozainka",
                template_name="verify_email.html",
                context={
                    "verification_link": verification_link,
                    "year": get_ve_now().year
                }
            )

            self.db.refresh(db_user)
            return UserResponse.model_validate(db_user)

        except IntegrityError as e:
            self.db.rollback()
            log_error(
                self.error_logger,
                e,
                context={'email': user_data.email, 'operation': 'user_registration'},
                user_email=user_data.email
            )
            raise UserAlreadyExistsException("Error al crear el usuario")
        except Exception as e:
            self.db.rollback()
            log_error(
                self.error_logger,
                e,
                context={'email': user_data.email, 'operation': 'user_registration'},
                user_email=user_data.email
            )
            raise

    @staticmethod
    async def authenticate_user(db: Session, login_data: LoginRequest) -> Token:
        """Authenticate user and return tokens."""
        auth_logger = get_logger("auth")
        error_logger = get_logger("errors")
        auth_logger.info(
            f"Authentication attempt for email: {login_data.email}",
            extra={
                'email': login_data.email, 
                'user_email': login_data.email, 
                'event': 'login_attempt'
            }
        )
        
        try:
            user = db.query(User).filter(User.email == login_data.email).first()
            auth_logger.debug(
                "Resultado de búsqueda de usuario para login",
                extra={
                    "email": login_data.email,
                    "user_found": user is not None,
                },
            )
            if not user:
                # Fallback: buscar en DEMOA por email y auto-provisionar
                try:
                    demoa_customer = source_system_service.get_customer_by_email(login_data.email)
                except Exception as _e:
                    demoa_customer = None
                if demoa_customer and demoa_customer.get('customer_code'):
                    try:
                        provisioner = SourceSystemUserCreationService(db)
                        provision_result = await provisioner.create_user_from_source_system(
                            demoa_customer['customer_code'],
                            use_alternate_email=False
                        )
                        auth_logger.info(
                            f"Auto-provisioned user from DEMOA: {login_data.email}",
                            extra={
                                'email': login_data.email,
                                'user_email': login_data.email,
                                'event': 'auto_provision_demoa',
                                'provision_success': provision_result.get('success', False),
                                'email_sent': provision_result.get('email_sent', False)
                            }
                        )
                    except Exception as _e:
                        auth_logger.warning(
                            f"Auto-provision from DEMOA failed for {login_data.email}: {_e}",
                            extra={'email': login_data.email, 'event': 'auto_provision_demoa_failed'}
                        )
                    # En cualquier caso, indicar al usuario que revise su email
                    raise InvalidCredentialsException(
                        "No tenías cuenta en el sistema. La hemos creado y enviamos una contraseña temporal a tu correo. Intenta nuevamente tras revisar tu email."
                    )
                auth_logger.warning(
                    f"Login failed - user not found: {login_data.email}",
                    extra={
                        'email': login_data.email, 
                        'user_email': login_data.email, 
                        'reason': 'user_not_found', 
                        'event': 'login_failed'
                    }
                )
                raise InvalidCredentialsException()
            
            if not verify_password(login_data.password, user.hashed_password):
                auth_logger.warning(
                    f"Login failed - invalid password: {login_data.email}",
                    extra={
                        'email': login_data.email, 
                        'user_email': login_data.email, 
                        'user_id': user.id, 
                        'reason': 'invalid_password', 
                        'event': 'login_failed'
                    }
                )
                raise InvalidCredentialsException()
            
            if not user.is_active:
                auth_logger.warning(
                    f"Login failed - account disabled: {login_data.email}",
                    extra={
                        'email': login_data.email, 
                        'user_email': login_data.email, 
                        'user_id': user.id, 
                        'reason': 'account_disabled', 
                        'event': 'login_failed'
                    }
                )
                raise InvalidCredentialsException("Cuenta desactivada")
            
            # TODO: Verify email if not verified
            user.last_login = get_ve_now()
            db.commit()
            
            auth_logger.info(
                f"User successfully authenticated: {user.email}",
                extra={
                    'user_id': user.id,
                    'email': user.email,
                    'user_email': user.email,
                    'role': user.role,
                    'event': 'login_success',
                    'last_login': user.last_login.isoformat()
                }
            )
            
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
            log_error(
                error_logger,
                e,
                context={'email': login_data.email, 'operation': 'user_authentication'},
                user_email=login_data.email
            )
            raise InvalidCredentialsException()
    
    @staticmethod
    async def refresh_access_token(db: Session, refresh_token: str) -> Token:
        """Refresh access token using refresh token."""
        logger = get_logger("auth")
        try:
            logger.debug(
                "Iniciando refresh de token",
                extra={
                    "refresh_token_length": len(refresh_token) if refresh_token else 0,
                    "refresh_token_preview": refresh_token[:30] + "..." if refresh_token and len(refresh_token) > 30 else (refresh_token or "None"),
                },
            )
            
            email = verify_token(refresh_token, "refresh")
            logger.debug("Token de refresh verificado", extra={"email": email})
            
            user = db.query(User).filter(User.email == email).first()
            
            if not user or not user.is_active:
                logger.warning(
                    "Usuario no válido o inactivo en refresh",
                    extra={"email": email, "user_exists": user is not None, "is_active": user.is_active if user else False},
                )
                raise InvalidCredentialsException("Usuario no válido")
            
            # Create new tokens
            access_token = create_access_token(data={"sub": user.email})
            new_refresh_token = create_refresh_token(data={"sub": user.email})
            
            logger.info("Tokens de acceso y refresh generados exitosamente", extra={"email": email})
            
            return Token(
                access_token=access_token,
                refresh_token=new_refresh_token,
                token_type="bearer",
                expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                role=user.role
            )
        except HTTPException as e:
            # Re-lanzar HTTPException para mantener el código de estado correcto
            logger.warning(
                "HTTPException en refresh_access_token",
                extra={"status_code": e.status_code, "detail": e.detail},
            )
            raise
        except InvalidCredentialsException:
            raise
        except Exception as e:
            log_error(logger, e, context={"operation": "refresh_access_token"})
            raise InvalidCredentialsException("Token de actualización inválido")
    
    @staticmethod
    async def verify_email(db: Session, token: str) -> dict:
        """Verify user email with token."""
        auth_logger = get_logger("auth")
        auth_logger.debug(
            "Verificando email con token",
            extra={
                "token_preview": token[:5] + "***" if token else None,
                "token_length": len(token) if token else 0,
            },
        )
        user = db.query(User).filter(User.verification_token == token).first()
        auth_logger.debug(
            "Resultado de búsqueda de usuario para verificación de email",
            extra={
                "token_present": bool(token),
                "user_found": user is not None,
            },
        )
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
        """Send password reset email with JWT token."""
        auth_logger = get_logger("auth")
        auth_logger.info(
            f"Password reset requested for email: {email}",
            extra={
                'email': email,
                'user_email': email,
                'event': 'password_reset_requested'
            }
        )
        
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            # Don't reveal if email exists or not for security
            auth_logger.warning(
                f"Password reset requested for non-existent email: {email}",
                extra={
                    'email': email,
                    'user_email': email,
                    'event': 'password_reset_email_not_found'
                }
            )
            return {"message": "Si el email existe, se enviará un enlace de recuperación", "success": True}
        
        # Generate JWT reset token (more secure than UUID)
        reset_token = create_url_safe_token(
            {"email": user.email, "type": "password_reset"},
            expires_hours=1
        )
        
        # Store token in database for additional validation
        user.reset_token = reset_token
        user.reset_token_expires = get_ve_now() + timedelta(hours=1)
        db.commit()
        
        # Send reset email
        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
        try:
            await email_service.send_password_reset_email(
                to_email=user.email,
                reset_link=reset_link,
                user_name=user.full_name
            )
            auth_logger.info(
                f"Password reset email sent successfully to: {email}",
                extra={
                    'email': email,
                    'user_email': email,
                    'user_id': user.id,
                    'event': 'password_reset_email_sent'
                }
            )
        except Exception as e:
            auth_logger.error(
                f"Failed to send password reset email to: {email}",
                extra={
                    'email': email,
                    'user_email': email,
                    'user_id': user.id,
                    'error': str(e),
                    'event': 'password_reset_email_failed'
                }
            )
            # Don't fail the request, just log the error
            # The user will still see the success message for security
        
        return {"message": "Si el email existe, se enviará un enlace de recuperación", "success": True}
    
    @staticmethod
    async def reset_password(db: Session, token: str, new_password: str) -> dict:
        """Reset user password with JWT token validation."""
        auth_logger = get_logger("auth")
        auth_logger.info(
            "Password reset attempt with token",
            extra={
                'token_preview': token[:10] + "***" if token else None,
                'event': 'password_reset_attempt'
            }
        )
        
        # First verify the JWT token
        payload = verify_url_safe_token(token)
        if not payload or payload.get("type") != "password_reset":
            auth_logger.warning(
                "Invalid password reset token (JWT validation failed)",
                extra={
                    'event': 'password_reset_token_invalid'
                }
            )
            raise UserNotFoundException("Token de recuperación inválido o expirado")
        
        email = payload.get("email")
        if not email:
            auth_logger.warning(
                "Password reset token missing email",
                extra={
                    'event': 'password_reset_token_missing_email'
                }
            )
            raise UserNotFoundException("Token de recuperación inválido o expirado")
        
        # Find user by email and verify token matches database (double validation)
        user = db.query(User).filter(
            User.email == email,
            User.reset_token == token,  # Additional check against database
            User.reset_token_expires > get_ve_now()
        ).first()
        
        if not user:
            auth_logger.warning(
                f"Password reset failed - token not found or expired for email: {email}",
                extra={
                    'email': email,
                    'user_email': email,
                    'event': 'password_reset_token_not_found'
                }
            )
            raise UserNotFoundException("Token de recuperación inválido o expirado")
        
        # Update password
        user.hashed_password = get_password_hash(new_password)
        user.reset_token = None
        user.reset_token_expires = None
        db.commit()
        
        auth_logger.info(
            f"Password reset successful for email: {email}",
            extra={
                'email': email,
                'user_email': email,
                'user_id': user.id,
                'event': 'password_reset_success'
            }
        )
        
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
                "verification_link": f"{settings.FRONTEND_URL}/verify-email/{user.verification_token}",
                "year": get_ve_now().year
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
    