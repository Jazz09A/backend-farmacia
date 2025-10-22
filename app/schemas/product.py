from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

class ProductBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    brand: str = Field(..., min_length=1, max_length=100)
    category: str = Field(..., min_length=1, max_length=100)
    subcategory: Optional[str] = Field(None, max_length=100)
    patology: Optional[str] = Field(None, max_length=100)
    price: Decimal = Field(..., gt=0, description="Precio en USD (única moneda interna)")
    description: str = Field(..., min_length=10)
    ingredients: Optional[List[str]] = []
    image: Optional[str] = Field(None, description="URL de imagen principal (deprecated, use images)")
    images: List[str] = Field(default_factory=list, description="Lista de URLs de imágenes del producto")
    in_stock: bool = True
    stock: Optional[int] = Field(default=0, ge=0)
    prescription: bool = False
    dosage: Optional[str] = Field(None, max_length=100)
    presentation: Optional[str] = Field(None, max_length=100)
    laboratorio: Optional[str] = Field(None, max_length=100)
    registro_sanitario: Optional[str] = Field(None, max_length=100)
    contraindicaciones: Optional[str] = None
    efectos_secundarios: Optional[str] = None

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
    subcategory: Optional[str] = Field(None, max_length=100)
    patology: Optional[str] = Field(None, max_length=100)
    price: Decimal = Field(..., gt=0, description="Precio en USD")
    description: str = Field(..., min_length=10)
    ingredients: Optional[List[str]] = []
    image: str = Field(..., min_length=1, description="URL de imagen principal")
    images: Optional[List[str]] = []
    in_stock: bool = True
    stock: Optional[int] = Field(default=0, ge=0)
    prescription: bool = False
    dosage: Optional[str] = Field(None, max_length=100)
    presentation: Optional[str] = Field(None, max_length=100)
    laboratorio: Optional[str] = Field(None, max_length=100)
    registro_sanitario: Optional[str] = Field(None, max_length=100)
    contraindicaciones: Optional[str] = None
    efectos_secundarios: Optional[str] = None
    slug: Optional[str] = Field(None, max_length=200)
    featured: bool = False
    is_offer: bool = False
    original_price: Optional[Decimal] = Field(None, gt=0, description="Precio original en USD para ofertas")
    offer_end_time: Optional[datetime] = None

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
    slug: Optional[str] = Field(None, max_length=200)
    featured: bool = False
    is_offer: bool = False
    original_price: Optional[Decimal] = Field(None, gt=0)
    offer_end_time: Optional[datetime] = None

    @field_validator('slug')
    def validate_slug(cls, v):
        if v and not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError('El slug solo puede contener letras, números, guiones y guiones bajos')
        return v

class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    brand: Optional[str] = Field(None, min_length=1, max_length=100)
    category: Optional[str] = Field(None, min_length=1, max_length=100)
    subcategory: Optional[str] = Field(None, max_length=100)
    patology: Optional[str] = Field(None, max_length=100)
    price: Optional[Decimal] = Field(None, gt=0, description="Precio en USD")
    description: Optional[str] = Field(None, min_length=10)
    ingredients: Optional[List[str]] = None
    image: Optional[str] = Field(None, description="URL de imagen principal (deprecated, use images)")
    images: Optional[List[str]] = Field(None, description="Lista de URLs de imágenes del producto")
    in_stock: Optional[bool] = None
    stock: Optional[int] = Field(None, ge=0)
    prescription: Optional[bool] = None
    featured: Optional[bool] = None
    is_offer: Optional[bool] = None
    original_price: Optional[Decimal] = Field(None, gt=0, description="Precio original en USD para ofertas")
    offer_end_time: Optional[datetime] = None

class ProductResponse(ProductBase):
    id: str
    rating: Decimal
    review_count: int
    is_offer: bool
    original_price: Optional[Decimal] = None
    offer_end_time: Optional[datetime] = None
    featured: bool
    slug: Optional[str] = None
    discount_percentage: Optional[Decimal] = Decimal('0.00')
    current_price: Decimal
    is_available: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class ProductSummary(BaseModel):
    """Simplified product model for lists and search results (sistema unificado USD)."""
    id: str
    name: str
    brand: str
    category: str
    price: Decimal  # USD únicamente
    image: Optional[str] = None  # Deprecated, use images
    images: List[str] = Field(default_factory=list)
    rating: Decimal
    review_count: int
    in_stock: bool
    prescription: bool
    is_offer: bool
    discount_percentage: Optional[Decimal] = Decimal('0.00')
    featured: bool
    slug: Optional[str] = None
    
    class Config:
        from_attributes = True

class ProductSearchFilters(BaseModel):
    category: Optional[str] = None
    subcategory: Optional[str] = None
    patology: Optional[str] = None
    brand: Optional[str] = None
    min_price: Optional[Decimal] = Field(None, ge=0)
    max_price: Optional[Decimal] = Field(None, ge=0)
    in_stock: Optional[bool] = None
    prescription: Optional[bool] = None
    min_rating: Optional[Decimal] = Field(None, ge=0, le=5)
    featured: Optional[bool] = None
    is_offer: Optional[bool] = None
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
    products: List[ProductSummary]
    total: int
    page: int
    limit: int
    total_pages: int
    has_next: bool
    has_prev: bool

class ProductListResponse(BaseModel):
    """Enhanced paginated response for product listings"""
    products: List[ProductResponse]
    pagination: dict
    filters_applied: dict
    total: int
    
    @classmethod
    def create(cls, products: List[ProductResponse], total: int, page: int, limit: int, filters: dict = None):
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
    subcategories: Optional[List[dict]] = []

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
    brand: Optional[str] = Field(None, max_length=100)
    category: Optional[str] = Field(None, max_length=100)
    subcategory: Optional[str] = Field(None, max_length=100)
    patology: Optional[str] = Field(None, max_length=100)
    image: Optional[str] = Field(None, min_length=1, description="URL de imagen principal")
    images: Optional[List[str]] = []
    ingredients: Optional[List[str]] = []
    in_stock: Optional[bool] = True
    stock: Optional[int] = Field(default=0, ge=0)
    prescription: Optional[bool] = False
    dosage: Optional[str] = Field(None, max_length=100)
    presentation: Optional[str] = Field(None, max_length=100)
    laboratorio: Optional[str] = Field(None, max_length=100)
    registro_sanitario: Optional[str] = Field(None, max_length=100)
    contraindicaciones: Optional[str] = None
    efectos_secundarios: Optional[str] = None
    sku: Optional[str] = Field(None, max_length=50)
    featured: Optional[bool] = False
    is_offer: Optional[bool] = False
    original_price: Optional[Decimal] = Field(None, gt=0, description="Precio original en USD")
    
    # Row reference for error reporting
    row_number: Optional[int] = None
    
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
    valid_products: List[ProductBulkUploadItem]
    validation_errors: List[ProductValidationError]
    processed_count: int
    error_count: int
    warnings: List[str] = []
    
    @property
    def success_rate(self) -> Decimal:
        if self.total_rows == 0:
            return Decimal('0.00')
        return Decimal(str(round((self.processed_count / self.total_rows) * 100, 2))) 