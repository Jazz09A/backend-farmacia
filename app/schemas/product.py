from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ProductBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    brand: str = Field(..., min_length=1, max_length=100)
    category: str = Field(..., min_length=1, max_length=100)
    subcategory: str | None = Field(None, max_length=100)
    price: Decimal = Field(..., gt=0, description="Precio en USD (única moneda interna)")
    description: str = Field(..., min_length=10)
    ingredients: list[str] | None = []
    image: str | None = Field(None, description="URL de imagen principal (deprecated, use images)")
    images: list[str] | None = Field(default_factory=list, description="Lista de URLs de imágenes del producto")
    in_stock: bool = True
    stock: int | None = Field(default=0, ge=0)
    prescription: bool = False

    @field_validator('images', mode='before')
    def validate_images(cls, v):
        """Convert None to empty list for images field."""
        if v is None:
            return []
        return v

    @field_validator('price')
    def validate_price(cls, v):
        if v <= 0:
            raise ValueError('El precio debe ser mayor que 0')
        return v

class ProductCreateInput(BaseModel):
    """Schema for creating products with USD price (sistema unificado)."""
    name: str = Field(..., min_length=1, max_length=200)
    brand: str = Field(..., min_length=1, max_length=100)
    category: str = Field(..., min_length=1, max_length=100)
    subcategory: str | None = Field(None, max_length=100)
    price: Decimal = Field(..., gt=0, description="Precio en USD")
    description: str = Field(..., min_length=10)
    ingredients: list[str] | None = []
    image: str = Field(..., min_length=1, description="URL de imagen principal")
    images: list[str] | None = []
    in_stock: bool = True
    stock: int | None = Field(default=0, ge=0)
    prescription: bool = False
    slug: str | None = Field(None, max_length=200)
    featured: bool = False
    is_offer: bool = False
    original_price: Decimal | None = Field(None, gt=0, description="Precio original en USD para ofertas")

    @field_validator('price', 'original_price')
    def validate_prices(cls, v):
        if v is not None and v <= 0:
            raise ValueError('El precio debe ser mayor que 0')
        return v

    @field_validator('slug') 
    def validate_slug(cls, v):
        if v and not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError('El slug solo puede contener letras, números, guiones y guiones bajos')
        return v

class ProductCreate(ProductBase):
    slug: str | None = Field(None, max_length=200)
    featured: bool = False
    is_offer: bool = False
    original_price: Decimal | None = Field(None, gt=0)

    @field_validator('slug')
    def validate_slug(cls, v):
        if v and not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError('El slug solo puede contener letras, números, guiones y guiones bajos')
        return v

class ProductUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    brand: str | None = Field(None, min_length=1, max_length=100)
    category: str | None = Field(None, min_length=1, max_length=100)
    subcategory: str | None = Field(None, max_length=100)
    price: Decimal | None = Field(None, gt=0, description="Precio en USD")
    description: str | None = Field(None, min_length=10)
    ingredients: list[str] | None = None
    image: str | None = Field(None, description="URL de imagen principal (deprecated, use images)")
    images: list[str] | None = Field(None, description="Lista de URLs de imágenes del producto")
    in_stock: bool | None = None
    stock: int | None = Field(None, ge=0)
    prescription: bool | None = None
    featured: bool | None = None
    is_offer: bool | None = None
    original_price: Decimal | None = Field(None, gt=0, description="Precio original en USD para ofertas")

class FlashOfferInfo(BaseModel):
    """Información de flash offer aplicable a un producto"""
    id: str
    discount_type: str
    discount_value: float
    original_price: float
    offer_price: float
    discount_percentage: float
    end_time: str | None = None
    max_quantity: int | None = None
    remaining_quantity: int | None = None
    
    class Config:
        from_attributes = True


class ProfitDiscountInfo(BaseModel):
    """Información de descuento por volumen desde Profit Plus (saDescArticulo)"""
    co_desc: str = Field(..., description="Código del descuento")
    des_des: str | None = Field(None, description="Descripción del descuento")
    tip_cli: str = Field(..., description="Tipo de cliente")
    des_tipo: str | None = Field(None, description="Descripción del tipo de cliente")
    
    # Rangos de descuento disponibles
    ranges: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Rangos de cantidad y porcentaje de descuento"
    )
    
    # Información de vigencia
    fecha_ini: datetime | None = Field(None, description="Fecha de inicio")
    fecha_fin: datetime | None = Field(None, description="Fecha de fin")
    is_active: bool = Field(True, description="Si el descuento está vigente")
    
    # Mejor descuento aplicable (para cantidad 1)
    best_discount_percentage: Decimal | None = Field(
        None,
        description="Mejor porcentaje de descuento disponible"
    )
    min_quantity_for_discount: Decimal | None = Field(
        None,
        description="Cantidad mínima para obtener descuento"
    )
    
    class Config:
        from_attributes = True

class ProductResponse(ProductBase):
    id: str
    rating: Decimal
    is_offer: bool
    original_price: Decimal | None = None
    featured: bool
    slug: str | None = None
    discount_percentage: Decimal | None = Decimal('0.00')
    current_price: Decimal
    is_available: bool
    created_at: datetime
    updated_at: datetime
    flash_offer: FlashOfferInfo | None = None
    
    class Config:
        from_attributes = True

class ProductSummary(BaseModel):
    """Simplified product model for lists and search results (sistema unificado USD)."""
    id: str
    name: str
    brand: str
    category: str
    price: Decimal  # USD únicamente
    image: str | None = None  # Deprecated, use images
    images: list[str] | None = Field(default_factory=list)
    rating: Decimal
    in_stock: bool
    prescription: bool
    is_offer: bool
    discount_percentage: Decimal | None = Decimal('0.00')
    featured: bool
    slug: str | None = None
    
    @field_validator('images', mode='before')
    def validate_images(cls, v):
        """Convert None to empty list for images field."""
        if v is None:
            return []
        return v
    
    class Config:
        from_attributes = True

class ProductSearchFilters(BaseModel):
    category: str | None = None
    subcategory: str | None = None
    brand: str | None = None
    min_price: Decimal | None = Field(None, ge=0)
    max_price: Decimal | None = Field(None, ge=0)
    in_stock: bool | None = None
    prescription: bool | None = None
    min_rating: Decimal | None = Field(None, ge=0, le=5)
    featured: bool | None = None
    is_offer: bool | None = None
    sort_by: str = Field(default='name', description="Campo por el cual ordenar")
    sort_order: str = Field(default='asc', description="Orden: asc o desc")
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator('sort_by')
    def validate_sort_by(cls, v):
        allowed_fields = ['name', 'price', 'rating', 'created_at', 'popularity']
        if v not in allowed_fields:
            raise ValueError(f'sort_by debe ser uno de: {", ".join(allowed_fields)}')
        return v

    @field_validator('sort_order')
    def validate_sort_order(cls, v):
        if v not in ['asc', 'desc']:
            raise ValueError('sort_order debe ser "asc" o "desc"')
        return v

    @field_validator('max_price')
    def validate_price_range(cls, v, values):
        if v is not None and 'min_price' in values and values['min_price'] is not None:
            if v < values['min_price']:
                raise ValueError('max_price debe ser mayor que min_price')
        return v

class ProductSearchResponse(BaseModel):
    products: list[ProductSummary]
    total: int
    page: int
    limit: int
    total_pages: int
    has_next: bool
    has_prev: bool

class ProductListResponse(BaseModel):
    """Enhanced paginated response for product listings"""
    products: list[ProductResponse]
    pagination: dict
    filters_applied: dict
    total: int
    
    @classmethod
    def create(cls, products: list[ProductResponse], total: int, page: int, limit: int, filters: dict | None = None):
        total_pages = (total + limit - 1) // limit if total > 0 else 0
        return cls(
            products=products,
            pagination={
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
                "next_page": page + 1 if page < total_pages else None,
                "prev_page": page - 1 if page > 1 else None
            },
            filters_applied=filters or {},
            total=total
        )

class CategoryResponse(BaseModel):
    name: str
    count: int
    subcategories: list[dict] | None = []

class ProductStats(BaseModel):
    total_products: int
    in_stock_products: int
    featured_products: int
    offer_products: int
    categories_count: int
    avg_rating: Decimal

# Schemas for bulk product upload
class ProductBulkUploadItem(BaseModel):
    """Schema for individual product in bulk upload (sistema unificado USD)"""
    # Required fields
    name: str = Field(..., min_length=1, max_length=200)
    price: Decimal = Field(..., gt=0, description="Precio en USD")
    description: str = Field(..., min_length=10)
    
    # Optional fields with defaults
    brand: str | None = Field(None, max_length=100)
    category: str | None = Field(None, max_length=100)
    subcategory: str | None = Field(None, max_length=100)
    image: str | None = Field(None, min_length=1, description="URL de imagen principal")
    images: list[str] | None = []
    ingredients: list[str] | None = []
    in_stock: bool | None = True
    stock: int | None = Field(default=0, ge=0)
    prescription: bool | None = False
    sku: str | None = Field(None, max_length=50)
    featured: bool | None = False
    is_offer: bool | None = False
    original_price: Decimal | None = Field(None, gt=0, description="Precio original en USD")
    
    # Row reference for error reporting
    row_number: int | None = None
    
    @field_validator('price')
    def validate_price(cls, v):
        if v and v <= 0:
            raise ValueError('El precio debe ser mayor que 0')
        return v
    
    @field_validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('El nombre del producto es obligatorio')
        return v.strip()
    
    @field_validator('description')
    def validate_description(cls, v):
        if not v or len(v.strip()) < 10:
            raise ValueError('La descripción debe tener al menos 10 caracteres')
        return v.strip()

class ProductValidationError(BaseModel):
    """Schema for validation errors in bulk upload"""
    row_number: int
    field: str
    value: str
    error_message: str

class ProductBulkUploadResult(BaseModel):
    """Schema for bulk upload results"""
    total_rows: int
    valid_products: list[ProductBulkUploadItem]
    validation_errors: list[ProductValidationError]
    processed_count: int
    error_count: int
    warnings: list[str] = []
    
    @property
    def success_rate(self) -> Decimal:
        if self.total_rows == 0:
            return Decimal('0.00')
        return Decimal(str(round((self.processed_count / self.total_rows) * 100, 2)))

class ProductRecommendations(BaseModel):
    """Respuesta con productos relacionados y recomendados"""
    related_products: list[ProductResponse] = Field(default_factory=list, description="Productos relacionados")
    frequently_bought_together: list[ProductResponse] = Field(default_factory=list, description="Productos frecuentemente comprados juntos")
    you_may_also_like: list[ProductResponse] = Field(default_factory=list, description="También te pueden interesar") 