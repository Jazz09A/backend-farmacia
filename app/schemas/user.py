from pydantic import BaseModel, EmailStr, validator, Field
from typing import Optional, List
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=2, max_length=100)
    user_type: str = Field(..., description="Tipo de usuario: natural o juridico")
    phone: Optional[str] = Field(None, max_length=20)
    preferred_currency: str = Field(default='VES', description="Moneda preferida")

    @validator('user_type')
    def validate_user_type(cls, v):
        if v not in ['natural', 'juridico']:
            raise ValueError('El tipo de usuario debe ser "natural" o "juridico"')
        return v

    @validator('preferred_currency')
    def validate_currency(cls, v):
        if v not in ['VES', 'USD']:
            raise ValueError('La moneda debe ser VES o USD')
        return v

class UserCreate(UserBase):
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

class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    preferred_currency: Optional[str] = None
    
    @validator('preferred_currency')
    def validate_currency(cls, v):
        if v is not None and v not in ['VES', 'USD']:
            raise ValueError('La moneda debe ser VES o USD')
        return v

class UserResponse(UserBase):
    id: str
    is_active: bool
    is_verified: bool
    is_admin: bool
    created_at: datetime
    last_login: Optional[datetime]
    
    class Config:
        from_attributes = True

class UserProfile(UserResponse):
    """Extended user profile with additional information."""
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