from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Union

from app.config.database import get_db
from app.schemas.auth import (
    LoginRequest, 
    RegisterNaturalRequest,
    RegisterJuridicoRequest,
    Token, 
    RefreshTokenRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
    ResendVerificationRequest,
    AuthResponse
)
from app.schemas.user import UserNaturalResponse, UserJuridicoResponse
from app.services.auth_service import AuthService
from app.core.dependencies import get_current_active_user, get_current_user
from app.models.user import User

router = APIRouter()

@router.post("/register/natural", response_model=UserNaturalResponse, status_code=status.HTTP_201_CREATED)
async def register_natural_user(
    user_data: RegisterNaturalRequest,
    db: Session = Depends(get_db)
):
    """
    Registrar un nuevo usuario natural (persona).
    
    - **email**: Email del usuario (debe ser único)
    - **first_name**: Nombre del usuario
    - **last_name**: Apellido del usuario
    - **cedula**: Cédula de identidad
    - **password**: Contraseña (mínimo 8 caracteres)
    - **phone**: Teléfono
    - **preferred_currency**: Moneda preferida (VES o USD)
    - **birth_date**: Fecha de nacimiento (opcional)
    - **address**: Dirección (opcional)
    """
    return await AuthService.register_natural_user(db, user_data)

@router.post("/register/juridico", response_model=UserJuridicoResponse, status_code=status.HTTP_201_CREATED)
async def register_juridico_user(
    user_data: RegisterJuridicoRequest,
    db: Session = Depends(get_db)
):
    """
    Registrar un nuevo usuario jurídico (empresa/farmacia).
    
    - **email**: Email de la empresa (debe ser único)
    - **company_name**: Nombre de la empresa
    - **rif**: RIF de la empresa
    - **registro_mercantil**: Número de registro mercantil
    - **representante_legal_cedula**: Cédula del representante legal
    - **representante_legal_nombre**: Nombre del representante legal
    - **referencia_comercial_proveedor**: Referencia comercial
    - **referencia_bancaria**: Referencia bancaria
    - **direccion_establecimiento**: Dirección del establecimiento
    - **password**: Contraseña (mínimo 8 caracteres)
    - **phone**: Teléfono principal
    - **preferred_currency**: Moneda preferida (VES o USD)
    - Y campos opcionales adicionales...
    """
    return await AuthService.register_juridico_user(db, user_data)

@router.post("/login", response_model=Token)
async def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    Iniciar sesión con email y contraseña.
    
    Funciona para ambos tipos de usuario (natural y jurídico).
    Retorna tokens de acceso y actualización.
    """
    return await AuthService.authenticate_user(db, login_data)

@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    Actualizar token de acceso usando token de actualización.
    """
    return await AuthService.refresh_access_token(db, refresh_data.refresh_token)

@router.get("/me", response_model=Union[UserNaturalResponse, UserJuridicoResponse])
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """
    Obtener información del usuario actual autenticado.
    
    Retorna el schema apropiado según el tipo de usuario.
    """
    if current_user.user_type == "natural":
        return UserNaturalResponse.from_orm(current_user)
    else:
        return UserJuridicoResponse.from_orm(current_user)

@router.post("/verify-email", response_model=AuthResponse)
async def verify_email(
    verify_data: VerifyEmailRequest,
    db: Session = Depends(get_db)
):
    """
    Verificar email del usuario con token.
    """
    return await AuthService.verify_email(db, verify_data.token)

@router.post("/resend-verification", response_model=AuthResponse)
async def resend_verification_email(
    resend_data: ResendVerificationRequest,
    db: Session = Depends(get_db)
):
    """
    Reenviar email de verificación.
    """
    return await AuthService.resend_verification_email(db, resend_data.email)

@router.post("/forgot-password", response_model=AuthResponse)
async def forgot_password(
    forgot_data: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Solicitar recuperación de contraseña.
    
    Se enviará un email con instrucciones si el email existe.
    """
    return await AuthService.send_reset_password_email(db, forgot_data.email)

@router.post("/reset-password", response_model=AuthResponse)
async def reset_password(
    reset_data: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Restablecer contraseña con token de recuperación.
    """
    return await AuthService.reset_password(db, reset_data.token, reset_data.new_password)

@router.post("/change-password", response_model=AuthResponse)
async def change_password(
    current_password: str,
    new_password: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Cambiar contraseña del usuario autenticado.
    """
    return await AuthService.change_password(
        db, 
        current_user.id, 
        current_password, 
        new_password
    )

@router.post("/logout", response_model=AuthResponse)
async def logout(
    current_user: User = Depends(get_current_user)
):
    """
    Cerrar sesión (invalidar token).
    
    Nota: En esta implementación simple, solo confirmamos el logout.
    En un sistema más avanzado, se podría mantener una lista de tokens revocados.
    """
    return AuthResponse(
        message="Sesión cerrada exitosamente",
        success=True
    ) 