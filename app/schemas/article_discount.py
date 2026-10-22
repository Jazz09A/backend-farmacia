from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, validator


class ArticleDiscountCreate(BaseModel):
    co_art: str = Field(..., min_length=1, max_length=30, description="Código del artículo en Profit Plus")
    tip_cli: str | None = Field(
        None, max_length=6, description="Tipo de cliente (si no se proporciona, se usa el del usuario autenticado)"
    )
    des_des: str | None = Field(None, max_length=60, description="Descripción del descuento")
    fecha_ini: datetime | None = Field(None, description="Fecha de inicio de vigencia")
    fecha_fin: datetime | None = Field(None, description="Fecha de fin de vigencia")

    # Rango 1 (Obligatorio)
    hasta1: Decimal = Field(..., gt=0, description="Cantidad límite para el rango 1")
    porc1: Decimal = Field(..., ge=0, le=100, description="Porcentaje de descuento para el rango 1")

    # Rangos opcionales
    hasta2: Decimal | None = Field(None, gt=0)
    porc2: Decimal | None = Field(None, ge=0, le=100)
    hasta3: Decimal | None = Field(None, gt=0)
    porc3: Decimal | None = Field(None, ge=0, le=100)
    hasta4: Decimal | None = Field(None, gt=0)
    porc4: Decimal | None = Field(None, ge=0, le=100)
    hasta5: Decimal | None = Field(None, gt=0)
    porc5: Decimal | None = Field(None, ge=0, le=100)
    porc6: Decimal | None = Field(None, ge=0, le=100, description="Porcentaje adicional (porc6)")

    # Campos de contadores de uso (campo1...campo5 corresponden a hasta1...hasta5)
    campo1: int = Field(0, ge=0, description="Contador de uso para rango 1")
    campo2: int = Field(0, ge=0, description="Contador de uso para rango 2")
    campo3: int = Field(0, ge=0, description="Contador de uso para rango 3")
    campo4: int = Field(0, ge=0, description="Contador de uso para rango 4")
    campo5: int = Field(0, ge=0, description="Contador de uso para rango 5")

    # Campos adicionales
    campo6: str | None = Field(None, max_length=60)
    campo7: str | None = Field(None, max_length=60)
    campo8: str | None = Field(None, max_length=60)

    @validator("co_art", "tip_cli", pre=True)
    def normalize_codes(cls, value):
        if isinstance(value, str):
            return value.strip().upper()
        return value


class ArticleDiscountUpdate(BaseModel):
    """Schema para actualizar un descuento existente"""

    des_des: str | None = Field(None, max_length=60)
    fecha_ini: datetime | None = None
    fecha_fin: datetime | None = None
    tip_cli: str | None = Field(None, max_length=6)

    # Rangos
    hasta1: Decimal | None = None
    porc1: Decimal | None = None
    hasta2: Decimal | None = None
    porc2: Decimal | None = None
    hasta3: Decimal | None = None
    porc3: Decimal | None = None
    hasta4: Decimal | None = None
    porc4: Decimal | None = None
    hasta5: Decimal | None = None
    porc5: Decimal | None = None

    # Contadores
    campo1: int | None = None
    campo2: int | None = None
    campo3: int | None = None
    campo4: int | None = None
    campo5: int | None = None


class ArticleDiscountResponse(ArticleDiscountCreate):
    co_desc: str
    tip_cli: str
    co_us_in: str
    co_us_mo: str
    success: bool = True
    message: str = "Descuento creado o actualizado exitosamente"


class ArticleDiscountDetail(BaseModel):
    """Detalle completo de un descuento de artículo"""

    success: bool = Field(default=True, description="Indica si la consulta fue exitosa")
    co_desc: str = Field(..., description="Código del descuento")
    co_art: str = Field(..., description="Código del artículo")
    art_des: str | None = Field(None, description="Descripción del artículo")
    tip_cli: str = Field(..., description="Tipo de cliente")
    des_tipo: str | None = Field(None, description="Descripción del tipo de cliente")
    des_des: str | None = Field(None, description="Descripción del descuento")
    fecha_ini: datetime | None = Field(None, description="Fecha de inicio")
    fecha_fin: datetime | None = Field(None, description="Fecha de fin")

    # Rangos de descuento
    hasta1: Decimal | None = Field(None, description="Cantidad límite rango 1")
    porc1: Decimal | None = Field(None, description="Porcentaje rango 1")
    hasta2: Decimal | None = Field(None, description="Cantidad límite rango 2")
    porc2: Decimal | None = Field(None, description="Porcentaje rango 2")
    hasta3: Decimal | None = Field(None, description="Cantidad límite rango 3")
    porc3: Decimal | None = Field(None, description="Porcentaje rango 3")
    hasta4: Decimal | None = Field(None, description="Cantidad límite rango 4")
    porc4: Decimal | None = Field(None, description="Porcentaje rango 4")
    hasta5: Decimal | None = Field(None, description="Cantidad límite rango 5")
    porc5: Decimal | None = Field(None, description="Porcentaje rango 5")
    porc6: Decimal | None = Field(None, description="Porcentaje adicional")

    # Campos de control de disponibilidad
    campo1: int | None = Field(None, description="Uso rango 1")
    campo2: int | None = Field(None, description="Uso rango 2")
    campo3: int | None = Field(None, description="Uso rango 3")
    campo4: int | None = Field(None, description="Uso rango 4")
    campo5: int | None = Field(None, description="Uso rango 5")

    # Metadatos
    is_active: bool = Field(..., description="Si el descuento está activo (basado en fechas)")
    fe_us_in: datetime | None = Field(None, description="Fecha de creación")
    fe_us_mo: datetime | None = Field(None, description="Fecha de última modificación")


class ArticleDiscountListResponse(BaseModel):
    """Respuesta paginada de descuentos"""

    success: bool = Field(default=True, description="Indica si la consulta fue exitosa")
    items: list[ArticleDiscountDetail] = Field(default_factory=list)
    total: int = Field(..., description="Total de registros")
    page: int = Field(..., description="Página actual")
    limit: int = Field(..., description="Registros por página")
    has_active: int = Field(0, description="Cantidad de descuentos activos")
    has_expired: int = Field(0, description="Cantidad de descuentos expirados")
