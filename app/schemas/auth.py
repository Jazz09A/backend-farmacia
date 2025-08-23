from pydantic import BaseModel, EmailStr, field_validator, Field
from typing import Optional, Literal, List
from app.schemas.user import UserCreate

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RegisterRequest(UserCreate):
    user_type: Literal['juridico'] = 'juridico'
    company_name: str
    rif: str
    registro_mercantil: str
    
    # Representantes legales
    representante_legal_cedula: str
    representante_legal_nombre: str
    representantes_adicionales: Optional[List[str]]
    
    # Referencias comerciales y bancarias
    referencia_comercial_proveedor: str
    referencia_bancaria: str
    
    # Dirección del establecimiento (requerida para jurídicos)
    direccion_establecimiento: str
    
    # Contactos especializados
    dueno_telefono: Optional[str] = None
    dueno_email: Optional[str] = None
    dueno_cumpleanos: Optional[str] = None
    
    encargado_compra_telefono: Optional[str] = None
    encargado_compra_email: Optional[str] = None
    encargado_compra_cumpleanos: Optional[str] = None
    
    encargado_cobranza_telefono: Optional[str] = None
    encargado_cobranza_email: Optional[str] = None
    encargado_cobranza_cumpleanos: Optional[str] = None
    
    # Información adicional
    redes_sociales: Optional[str] = None
    pagina_web: Optional[str] = None
    codigo_sicm: Optional[str] = None
    
    # Fotos del establecimiento
    fotos_establecimiento: Optional[List[str]] = None   

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str

class TokenData(BaseModel):
    email: Optional[str] = None
    user_id: Optional[str] = None

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str
    
    @field_validator('confirm_password')
    def passwords_match(cls, v, info):
        if 'new_password' in info.data and v != info.data['new_password']:
            raise ValueError('Las contraseñas no coinciden')
        return v
    
    @field_validator('new_password')
    def validate_new_password(cls, v):
        if len(v) < 8:
            raise ValueError('La contraseña debe tener al menos 8 caracteres')
        if not any(c.isupper() for c in v):
            raise ValueError('La contraseña debe tener al menos una mayúscula')
        if not any(c.islower() for c in v):
            raise ValueError('La contraseña debe tener al menos una minúscula')
        if not any(c.isdigit() for c in v):
            raise ValueError('La contraseña debe tener al menos un número')
        return v

class VerifyEmailRequest(BaseModel):
    token: str

class ResendVerificationRequest(BaseModel):
    email: EmailStr

class AuthResponse(BaseModel):
    message: str
    success: bool = True 