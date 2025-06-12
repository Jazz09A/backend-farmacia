from pydantic import BaseModel, EmailStr, validator, Field
from typing import Optional, List, Literal
from datetime import datetime, date

# Base común para ambos tipos de usuarios
class UserCommonBase(BaseModel):
    email: EmailStr
    phone: str = Field(..., max_length=20)
    preferred_currency: str = Field(default='VES', description="Moneda preferida")

    @validator('preferred_currency')
    def validate_currency(cls, v):
        if v not in ['VES', 'USD']:
            raise ValueError('La moneda debe ser VES o USD')
        return v

# Usuario Natural (Persona)
class UserNaturalBase(UserCommonBase):
    user_type: Literal['natural'] = 'natural'
    first_name: str = Field(..., min_length=2, max_length=50)
    last_name: str = Field(..., min_length=2, max_length=50)
    cedula: str = Field(..., max_length=20, description="Cédula de identidad")
    birth_date: Optional[date] = None
    address: Optional[str] = Field(None, max_length=200)

class UserNaturalCreate(UserNaturalBase):
    password: str = Field(..., min_length=8, max_length=100)
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('La contraseña debe tener al menos 8 caracteres')
        if not any(c.isupper() for c in v):
            raise ValueError('La contraseña debe tener al menos una mayúscula')
        if not any(c.islower() for c in v):
            raise ValueError('La contraseña debe tener al menos una minúscula')
        if not any(c.isdigit() for c in v):
            raise ValueError('La contraseña debe tener al menos un número')
        return v

# Usuario Jurídico (Empresa/Farmacia)
class UserJuridicoBase(UserCommonBase):
    user_type: Literal['juridico'] = 'juridico'
    company_name: str = Field(..., min_length=2, max_length=100)
    rif: str = Field(..., max_length=20, description="RIF de la empresa")
    registro_mercantil: str = Field(..., description="Número de registro mercantil")
    
    # Representantes legales
    representante_legal_cedula: str = Field(..., description="Cédula del representante legal principal")
    representante_legal_nombre: str = Field(..., description="Nombre del representante legal")
    representantes_adicionales: Optional[List[str]] = Field(None, description="Cédulas de representantes adicionales")
    
    # Referencias comerciales y bancarias
    referencia_comercial_proveedor: str = Field(..., description="Referencia comercial de proveedor reconocido")
    referencia_bancaria: str = Field(..., description="Referencia bancaria actual")
    
    # Contactos especializados
    dueno_telefono: Optional[str] = Field(None, description="Teléfono del dueño")
    dueno_email: Optional[EmailStr] = Field(None, description="Email del dueño")
    dueno_cumpleanos: Optional[date] = Field(None, description="Fecha de cumpleaños del dueño")
    
    encargado_compra_telefono: Optional[str] = Field(None, description="Teléfono del encargado de compras")
    encargado_compra_email: Optional[EmailStr] = Field(None, description="Email del encargado de compras")
    encargado_compra_cumpleanos: Optional[date] = Field(None, description="Fecha de cumpleaños del encargado de compras")
    
    encargado_cobranza_telefono: Optional[str] = Field(None, description="Teléfono del encargado de cobranzas")
    encargado_cobranza_email: Optional[EmailStr] = Field(None, description="Email del encargado de cobranzas")
    encargado_cobranza_cumpleanos: Optional[date] = Field(None, description="Fecha de cumpleaños del encargado de cobranzas")
    
    # Información adicional
    redes_sociales: Optional[str] = Field(None, description="Enlaces a redes sociales")
    pagina_web: Optional[str] = Field(None, description="URL de la página web")
    codigo_sicm: Optional[str] = Field(None, description="Código SICM")
    
    # Fotos del establecimiento
    fotos_establecimiento: Optional[List[str]] = Field(None, description="URLs de las fotos del establecimiento")
    
    # Dirección del establecimiento (requerida para jurídicos)
    direccion_establecimiento: str = Field(..., description="Dirección completa del establecimiento")

class UserJuridicoCreate(UserJuridicoBase):
    password: str = Field(..., min_length=8, max_length=100)
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('La contraseña debe tener al menos 8 caracteres')
        if not any(c.isupper() for c in v):
            raise ValueError('La contraseña debe tener al menos una mayúscula')
        if not any(c.islower() for c in v):
            raise ValueError('La contraseña debe tener al menos una minúscula')
        if not any(c.isdigit() for c in v):
            raise ValueError('La contraseña debe tener al menos un número')
        return v

# Schemas de actualización
class UserNaturalUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=2, max_length=50)
    last_name: Optional[str] = Field(None, min_length=2, max_length=50)
    phone: Optional[str] = Field(None, max_length=20)
    birth_date: Optional[date] = None
    address: Optional[str] = Field(None, max_length=200)
    preferred_currency: Optional[str] = None
    
    @validator('preferred_currency')
    def validate_currency(cls, v):
        if v is not None and v not in ['VES', 'USD']:
            raise ValueError('La moneda debe ser VES o USD')
        return v

class UserJuridicoUpdate(BaseModel):
    company_name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    representante_legal_nombre: Optional[str] = None
    referencia_comercial_proveedor: Optional[str] = None
    referencia_bancaria: Optional[str] = None
    dueno_telefono: Optional[str] = None
    dueno_email: Optional[EmailStr] = None
    dueno_cumpleanos: Optional[date] = None
    encargado_compra_telefono: Optional[str] = None
    encargado_compra_email: Optional[EmailStr] = None
    encargado_compra_cumpleanos: Optional[date] = None
    encargado_cobranza_telefono: Optional[str] = None
    encargado_cobranza_email: Optional[EmailStr] = None
    encargado_cobranza_cumpleanos: Optional[date] = None
    redes_sociales: Optional[str] = None
    pagina_web: Optional[str] = None
    codigo_sicm: Optional[str] = None
    fotos_establecimiento: Optional[List[str]] = None
    direccion_establecimiento: Optional[str] = None
    preferred_currency: Optional[str] = None
    
    @validator('preferred_currency')
    def validate_currency(cls, v):
        if v is not None and v not in ['VES', 'USD']:
            raise ValueError('La moneda debe ser VES o USD')
        return v

# Schemas de respuesta
class UserNaturalResponse(UserNaturalBase):
    id: str
    is_active: bool
    is_verified: bool
    role: str
    created_at: datetime
    last_login: Optional[datetime]
    
    class Config:
        from_attributes = True

class UserJuridicoResponse(UserJuridicoBase):
    id: str
    is_active: bool
    is_verified: bool
    role: str
    created_at: datetime
    last_login: Optional[datetime]
    
    class Config:
        from_attributes = True

# Schemas de perfiles extendidos
class UserNaturalProfile(UserNaturalResponse):
    """Extended natural user profile with additional information."""
    total_orders: Optional[int] = 0
    total_reviews: Optional[int] = 0

class UserJuridicoProfile(UserJuridicoResponse):
    """Extended juridico user profile with additional information."""
    total_orders: Optional[int] = 0
    total_reviews: Optional[int] = 0
    
class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str
    
    @validator('confirm_password')
    def passwords_match(cls, v, values):
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('Las contraseñas no coinciden')
        return v
    
    @validator('new_password')
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

class UserPreferencesBase(BaseModel):
    email_notifications: bool = True
    sms_notifications: bool = False
    push_notifications: bool = True
    promotional_emails: bool = True
    product_recommendations: bool = True
    preferred_currency: str = 'VES'
    preferred_language: str = 'es'
    show_reviews_publicly: bool = True
    share_data_for_recommendations: bool = True

class UserPreferencesUpdate(UserPreferencesBase):
    pass

class UserPreferencesResponse(UserPreferencesBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# Alias para compatibilidad hacia atrás
UserResponse = UserNaturalResponse
UserUpdate = UserNaturalUpdate 