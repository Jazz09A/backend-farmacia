from datetime import date, datetime

# OrderResponse eliminado - Order no se usa con Profit Plus
# from app.schemas.order import OrderResponse
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


# Base común para ambos tipos de usuarios
class UserCommonBase(BaseModel):
    email: EmailStr
    phone: str = Field(..., max_length=20)
    preferred_currency: str = Field(default="VES", description="Moneda preferida")

    @field_validator("preferred_currency")
    def validate_currency(cls, v):
        if v not in ["VES", "USD"]:
            raise ValueError("La moneda debe ser VES o USD")
        return v


# Usuario Jurídico (Empresa/Farmacia)
class UserJuridicoBase(UserCommonBase):
    user_type: Literal["juridico"] = "juridico"
    company_name: str = Field(..., min_length=2, max_length=100)
    rif: str = Field(..., max_length=20, description="RIF de la empresa")
    registro_mercantil: str = Field(..., description="Número de registro mercantil")

    # Representantes legales
    representante_legal_cedula: str = Field(..., description="Cédula del representante legal principal")
    representante_legal_nombre: str = Field(..., description="Nombre del representante legal")
    representantes_adicionales: list[str] | None = Field(None, description="Cédulas de representantes adicionales")

    # Referencias comerciales y bancarias
    referencia_comercial_proveedor: str = Field(..., description="Referencia comercial de proveedor reconocido")
    referencia_bancaria: str = Field(..., description="Referencia bancaria actual")

    # Dirección del establecimiento (requerida para jurídicos)
    direccion_establecimiento: str = Field(..., description="Dirección completa del establecimiento")

    # Contactos especializados
    dueno_telefono: str | None = Field(None, description="Teléfono del dueño")
    dueno_email: str | None = Field(None, description="Email del dueño")
    dueno_cumpleanos: date | None = Field(None, description="Fecha de cumpleaños del dueño")

    encargado_compra_telefono: str | None = Field(None, description="Teléfono del encargado de compras")
    encargado_compra_email: str | None = Field(None, description="Email del encargado de compras")
    encargado_compra_cumpleanos: date | None = Field(None, description="Fecha de cumpleaños del encargado de compras")

    encargado_cobranza_telefono: str | None = Field(None, description="Teléfono del encargado de cobranzas")
    encargado_cobranza_email: str | None = Field(None, description="Email del encargado de cobranzas")
    encargado_cobranza_cumpleanos: date | None = Field(
        None, description="Fecha de cumpleaños del encargado de cobranzas"
    )

    # Información adicional
    redes_sociales: str | None = Field(None, description="Enlaces a redes sociales")
    pagina_web: str | None = Field(None, description="URL de la página web")
    codigo_sicm: str | None = Field(None, description="Código SICM")

    # Fotos del establecimiento
    fotos_establecimiento: list[str] | None = Field(None, description="URLs de las fotos del establecimiento")


class UserCreate(UserJuridicoBase):
    password: str = Field(..., min_length=8, max_length=100)


class UserUpdate(BaseModel):
    company_name: str | None = Field(None, min_length=2, max_length=100)
    phone: str | None = Field(None, max_length=20)
    representante_legal_nombre: str | None = None
    referencia_comercial_proveedor: str | None = None
    referencia_bancaria: str | None = None
    dueno_telefono: str | None = None
    dueno_email: EmailStr | None = None
    dueno_cumpleanos: date | None = None
    encargado_compra_telefono: str | None = None
    encargado_compra_email: EmailStr | None = None
    encargado_compra_cumpleanos: date | None = None
    encargado_cobranza_telefono: str | None = None
    encargado_cobranza_email: EmailStr | None = None
    encargado_cobranza_cumpleanos: date | None = None
    redes_sociales: str | None = None
    pagina_web: str | None = None
    codigo_sicm: str | None = None
    fotos_establecimiento: list[str] | None = None
    direccion_establecimiento: str | None = None
    preferred_currency: str | None = None

    @field_validator("preferred_currency")
    def validate_currency(cls, v):
        if v is not None and v not in ["VES", "USD"]:
            raise ValueError("La moneda debe ser VES o USD")
        return v


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    phone: str
    is_active: bool
    is_verified: bool
    role: str
    created_at: datetime
    last_login: datetime | None = None
    preferred_currency: str
    user_type: str | None = None

    # Juridico fields (optional for admin/other roles)
    company_name: str | None = None
    rif: str | None = None
    registro_mercantil: str | None = None

    representante_legal_cedula: str | None = None
    representante_legal_nombre: str | None = None
    representantes_adicionales: list[str] | None = None

    referencia_comercial_proveedor: str | None = None
    referencia_bancaria: str | None = None

    direccion_establecimiento: str | None = None

    dueno_telefono: str | None = None
    dueno_email: str | None = None
    dueno_cumpleanos: date | None = None

    encargado_compra_telefono: str | None = None
    encargado_compra_email: str | None = None
    encargado_compra_cumpleanos: date | None = None

    encargado_cobranza_telefono: str | None = None
    encargado_cobranza_email: str | None = None
    encargado_cobranza_cumpleanos: date | None = None

    redes_sociales: str | None = None
    pagina_web: str | None = None
    codigo_sicm: str | None = None

    fotos_establecimiento: list[str] | None = None

    class Config:
        from_attributes = True


class UserProfile(UserResponse):
    """Extended juridico user profile with additional information."""

    total_orders: int | None = 0
    total_reviews: int | None = 0


class PasswordChange(BaseModel):
    current_password: str
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


class UserPreferencesBase(BaseModel):
    email_notifications: bool = True
    sms_notifications: bool = False
    push_notifications: bool = True
    promotional_emails: bool = True
    product_recommendations: bool = True
    preferred_currency: str = "VES"
    preferred_language: str = "es"
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


# UserDashboard eliminado - Order no se usa con Profit Plus
# class UserDashboard(UserResponse):
#     orders: List[OrderResponse]


# Alias para compatibilidad hacia atrás
UserResponse = UserResponse
UserUpdate = UserUpdate

# =============================================================================
# ESQUEMAS PARA ESTADÍSTICAS DE CLIENTES
# =============================================================================


class ProductPurchaseStats(BaseModel):
    """Estadísticas de compra de un producto específico"""

    product_id: str
    product_name: str
    product_brand: str
    total_quantity: int
    times_purchased: int
    total_spent: float
    last_purchase_date: datetime | None = None
    average_quantity_per_order: float


class CustomerStats(BaseModel):
    """Estadísticas generales del cliente"""

    total_orders: int
    total_spent: float
    average_order_value: float
    first_order_date: datetime | None = None
    last_order_date: datetime | None = None
    days_as_customer: int
    order_frequency_days: float | None = None  # Promedio de días entre pedidos
    preferred_payment_method: str | None = None
    most_used_shipping_zone: str | None = None


class OrderStatusDistribution(BaseModel):
    """Distribución de estados de pedidos"""

    status: str
    count: int
    percentage: float


class MonthlyPurchaseStats(BaseModel):
    """Estadísticas de compras mensuales"""

    month: str  # YYYY-MM
    order_count: int
    total_spent: float
    total_items: int


class CustomerDetailedStats(BaseModel):
    """Respuesta completa con estadísticas detalladas del cliente"""

    user_info: UserResponse
    general_stats: CustomerStats
    top_purchased_products: list[ProductPurchaseStats]
    order_status_distribution: list[OrderStatusDistribution]
    monthly_stats: list[MonthlyPurchaseStats]
    favorite_categories: list[dict[str, Any]]
    purchase_trends: dict[str, Any]

    class Config:
        from_attributes = True


class UserStats(BaseModel):
    total_orders: int
    total_spent: float
    total_products_purchased: int
