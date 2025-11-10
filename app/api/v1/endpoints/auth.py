from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    Token,
    RefreshTokenRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    ResendVerificationRequest,
    AuthResponse,
)
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService
from app.core.dependencies import get_current_active_user, get_current_user
from app.models.user import User

router = APIRouter( tags=["Authentication"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: RegisterRequest,
    db: Session = Depends(get_db)
):
    try:
        new_user = await AuthService(db).register_user(user_data)
        return new_user
    except HTTPException as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/verify-email/{token}", response_model=AuthResponse)
async def verify_email_with_token(token: str, db: Session = Depends(get_db)):
    """
    **Verificar correo electrónico**: Confirma la dirección de correo del usuario a través de un token.
    """
    try:
        success = await AuthService(db).verify_email(db, token)
        if success:
            return AuthResponse(message="Email verified successfully. You can now log in.")
    except HTTPException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification token.")


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
    print("LOGIN DATA: " + str(login_data))
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

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """
    Obtener información del usuario actual autenticado.
    
    Retorna el schema apropiado según el tipo de usuario.
    """
    return AuthService.get_user_info(current_user)


@router.post("/resend-verification", response_model=AuthResponse)
async def resend_verification_email(
    resend_data: ResendVerificationRequest,
    db: Session = Depends(get_db)
):
    """
    Reenviar email de verificación.
    """
    return await AuthService.resend_verification_email(db, resend_data.email)

@router.get("/get-email-verification/{email}", response_model=AuthResponse)
async def get_email_verification(
    email: str,
    db: Session = Depends(get_db)
):
    """
    Obtener email de verificación.
    """
    print(f"EMAIL RECIBIDO: {email}")
    return await AuthService.get_email_verification(db, email) 

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