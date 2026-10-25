from datetime import date
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.user import UserCreate


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(UserCreate):
    user_type: Literal["juridico"] = "juridico"
    company_name: str
    rif: str
    registro_mercantil: str

    # Representantes legales
    representante_legal_cedula: str
    representante_legal_nombre: str
    representantes_adicionales: list[str] | None

    # Referencias comerciales y bancarias
    referencia_comercial_proveedor: str
    referencia_bancaria: str

    # Dirección del establecimiento (requerida para jurídicos)
    direccion_establecimiento: str

    # Contactos especializados
    dueno_telefono: str | None = None
    dueno_email: str | None = None
    dueno_cumpleanos: date | None = None

    encargado_compra_telefono: str | None = None
    encargado_compra_email: str | None = None
    encargado_compra_cumpleanos: date | None = None

    encargado_cobranza_telefono: str | None = None
    encargado_cobranza_email: str | None = None
    encargado_cobranza_cumpleanos: date | None = None

    # Información adicional
    redes_sociales: str | None = None
    pagina_web: str | None = None
    codigo_sicm: str | None = None

    # Fotos del establecimiento
    fotos_establecimiento: list[str] | None = None


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str


class TokenData(BaseModel):
    email: str | None = None
    user_id: str | None = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str

    @field_validator("confirm_password")
    def passwords_match(cls, v, info):
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Las contraseñas no coinciden")
        return v

    @field_validator("new_password")
    def validate_new_password(cls, v):
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres")
        if not any(c.isupper() for c in v):
            raise ValueError("La contraseña debe tener al menos una mayúscula")
        if not any(c.islower() for c in v):
            raise ValueError("La contraseña debe tener al menos una minúscula")
        if not any(c.isdigit() for c in v):
            raise ValueError("La contraseña debe tener al menos un número")
        return v


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class AuthResponse(BaseModel):
    message: str
    success: bool = True


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=100)

    @field_validator("new_password")
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres")
        if not any(c.isupper() for c in v):
            raise ValueError("La contraseña debe tener al menos una mayúscula")
        if not any(c.islower() for c in v):
            raise ValueError("La contraseña debe tener al menos una minúscula")
        if not any(c.isdigit() for c in v):
            raise ValueError("La contraseña debe tener al menos un número")
        return v
