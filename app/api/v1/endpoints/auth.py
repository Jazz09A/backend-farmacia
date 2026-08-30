from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.config.logging_config import get_logger
from app.core.dependencies import get_current_active_user, get_current_user
from app.core.rate_limit import limiter
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    Token,
)
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService
from app.utils.logging_helpers import log_security_event

router = APIRouter()
logger = get_logger("auth")


def _redact_email(email: str) -> str:
    """Devuelve un hash del email para logs (no reversible)."""
    if not email:
        return ""
    import hashlib
    return hashlib.sha256(email.lower().strip().encode()).hexdigest()[:16]


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")
async def register_user(
    request: Request,
    user_data: RegisterRequest,
    db: Session = Depends(get_db)
):
    try:
        new_user = await AuthService(db).register_user(user_data)
        logger.info(
            f"User registered: {new_user.email}",
            extra={
                "user_id": new_user.id,
                "user_email": new_user.email,
                "user_type": new_user.user_type,
                "event": "user_registered",
            },
        )
        return new_user
    except HTTPException:
        # Re-raise sin alterar: el handler global la loggea como warning.
        raise
    except Exception as e:
        # Error interno: loggear TODO con stack y devolver genérico.
        from app.utils.logging_helpers import log_internal_error
        tracking_id = log_internal_error(
            request, e,
            context={"operation": "register_user", "email_hash": _redact_email(user_data.email)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo completar el registro. Intente nuevamente.",
            headers={"X-Tracking-ID": tracking_id},
        )

@router.get("/verify-email/{token}", response_model=AuthResponse)
async def verify_email_with_token(token: str, db: Session = Depends(get_db)):
    """
    **Verificar correo electrónico**: Confirma la dirección de correo del usuario a través de un token.
    """
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token requerido")
    log_security_event(
        "verify_email_attempt",
        extra={"token_present": True, "token_length": len(token)},
    )
    try:
        success = await AuthService(db).verify_email(db, token)
        if success:
            log_security_event("verify_email_success")
            return AuthResponse(message="Email verified successfully. You can now log in.")
    except HTTPException:
        log_security_event("verify_email_failed")
        raise

    log_security_event("verify_email_invalid_token")
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification token.")


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
async def login(
    request: Request,
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    Iniciar sesión con email y contraseña.

    Funciona para ambos tipos de usuario (natural y jurídico).
    Retorna tokens de acceso y actualización.
    """
    log_security_event(
        "login_attempt",
        request=request,
        user_email=login_data.email,
    )
    try:
        result = await AuthService.authenticate_user(db, login_data)
        log_security_event(
            "login_success",
            request=request,
            user_email=login_data.email,
        )
        return result
    except HTTPException:
        log_security_event(
            "login_failed",
            request=request,
            user_email=login_data.email,
        )
        raise

@router.post("/refresh", response_model=Token)
async def refresh_token(
    request: Request,
    refresh_data: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    Actualizar token de acceso usando token de actualización.
    """
    if not refresh_data.refresh_token:
        log_security_event("refresh_token_missing", request=request)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token es requerido"
        )

    log_security_event(
        "refresh_attempt",
        request=request,
        extra={"token_present": True},
    )
    try:
        result = await AuthService.refresh_access_token(db, refresh_data.refresh_token)
        log_security_event("refresh_success", request=request)
        return result
    except HTTPException:
        log_security_event("refresh_failed", request=request)
        raise

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """
    Obtener información del usuario actual autenticado.

    Retorna el schema apropiado según el tipo de usuario.
    """
    from app.utils.logging_helpers import set_request_context
    set_request_context(user_id=str(current_user.id), user_email=str(current_user.email))
    return AuthService.get_user_info(current_user)


@router.post("/resend-verification", response_model=AuthResponse)
async def resend_verification_email(
    resend_data: ResendVerificationRequest,
    db: Session = Depends(get_db)
):
    """
    Reenviar email de verificación.
    """
    log_security_event(
        "resend_verification_request",
        user_email=resend_data.email,
    )
    return await AuthService.resend_verification_email(db, resend_data.email)


@router.get("/get-email-verification/{email}", response_model=AuthResponse)
async def get_email_verification(
    email: str,
    db: Session = Depends(get_db)
):
    """
    Endpoint intencionalmente opaco: la respuesta es idéntica exista o no el
    usuario, para no permitir enumeración. El contenido útil debe obtenerse
    únicamente por canales autenticados.
    """
    log_security_event(
        "get_email_verification_request",
        user_email=email,
    )
    return AuthResponse(
        message=(
            "Si las credenciales son correctas pero no tienes cuenta, "
            "recibirás un email de activación"
        ),
        success=True,
    )

@router.post("/forgot-password", response_model=AuthResponse)
@limiter.limit("3/hour")
async def forgot_password(
    request: Request,
    forgot_data: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Solicitar recuperación de contraseña.

    Respuesta genérica (no revela si el email existe).
    """
    log_security_event(
        "forgot_password_request",
        request=request,
        user_email=forgot_data.email,
    )
    return await AuthService.send_reset_password_email(db, forgot_data.email)

@router.post("/reset-password", response_model=AuthResponse)
async def reset_password(
    request: Request,
    reset_data: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Restablecer contraseña con token de recuperación.
    """
    log_security_event(
        "reset_password_attempt",
        request=request,
        extra={"token_present": bool(reset_data.token)},
    )
    try:
        result = await AuthService.reset_password(db, reset_data.token, reset_data.new_password)
        log_security_event("reset_password_success", request=request)
        return result
    except HTTPException:
        log_security_event("reset_password_failed", request=request)
        raise


@router.post("/change-password", response_model=AuthResponse)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Cambiar contraseña del usuario autenticado.
    """
    log_security_event(
        "change_password_attempt",
        user_email=str(current_user.email),
    )
    try:
        result = await AuthService.change_password(
            db,
            str(current_user.id),
            payload.current_password,
            payload.new_password,
        )
        log_security_event("change_password_success", user_email=str(current_user.email))
        return result
    except HTTPException:
        log_security_event("change_password_failed", user_email=str(current_user.email))
        raise


@router.post("/logout", response_model=AuthResponse)
async def logout(
    current_user: User = Depends(get_current_user)
):
    """
    Cerrar sesión (invalidar token).
    """
    log_security_event("logout", user_email=str(current_user.email))
    return AuthResponse(
        message="Sesión cerrada exitosamente",
        success=True
    )