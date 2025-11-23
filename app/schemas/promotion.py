from pydantic import BaseModel, Field, validator, model_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum
from decimal import Decimal

class DiscountTypeEnum(str, Enum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"

# Flash Offer Schemas
class FlashOfferBase(BaseModel):
    product_id: Optional[str] = Field(
        None, description="ID del producto local (opcional, para referencia cruzada)"
    )
    article_code: str = Field(..., min_length=1, description="Código del artículo (co_art) en Profit Plus")
    discount_type: DiscountTypeEnum = DiscountTypeEnum.PERCENTAGE
    discount_value: float = Field(..., gt=0)
    start_time: datetime
    end_time: datetime
    max_quantity: Optional[int] = None
    is_active: bool = True

    @validator('end_time')
    def validate_end_time(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('La fecha de fin debe ser posterior a la fecha de inicio')
        return v

    @validator('discount_value')
    def validate_discount_value(cls, v, values):
        if values.get('discount_type') == DiscountTypeEnum.PERCENTAGE and v > 100:
            raise ValueError('El descuento porcentual no puede ser mayor a 100%')
        return v

class FlashOfferCreate(FlashOfferBase):
    discount_type: Optional[DiscountTypeEnum] = None
    discount_value: Optional[float] = Field(None, gt=0)
    fixed_price: Optional[float] = Field(None, gt=0)

    @model_validator(mode="after")
    def validate_discount_input(cls, values: "FlashOfferCreate"):
        if values.fixed_price is None and values.discount_value is None:
            raise ValueError(
                "Debes proporcionar un descuento porcentual (discount_value) "
                "o un precio objetivo (fixed_price)"
            )

        if values.fixed_price is not None and values.discount_value is not None:
            raise ValueError(
                "Solo se permite proporcionar fixed_price o discount_value, no ambos"
            )

        if values.discount_value is not None and values.discount_type is None:
            values.discount_type = DiscountTypeEnum.PERCENTAGE

        return values

class FlashOfferUpdate(BaseModel):
    discount_type: Optional[DiscountTypeEnum] = None
    discount_value: Optional[float] = Field(None, gt=0)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    max_quantity: Optional[int] = None
    is_active: Optional[bool] = None
    article_code: Optional[str] = Field(None, min_length=1)


class FlashOfferArticleData(BaseModel):
    article_code: str
    description: str
    original_price: Decimal
    offer_price: Decimal
    currency: str
    discount_percentage: float
    stock: Optional[Decimal] = None
    image_url: Optional[str] = None
    gallery: List[str] = Field(default_factory=list)


class FlashOfferResponse(FlashOfferBase):
    id: str
    used_quantity: int
    created_at: datetime
    updated_at: datetime
    is_valid: bool
    article_details: Optional[FlashOfferArticleData] = None
    
    class Config:
        from_attributes = True

# Promotional Code Schemas
class PromotionalCodeBase(BaseModel):
    code: str = Field(..., min_length=3, max_length=50)
    description: Optional[str] = None
    discount_type: DiscountTypeEnum = DiscountTypeEnum.PERCENTAGE
    discount_value: float = Field(..., gt=0)
    min_amount: Optional[float] = Field(None, ge=0)
    max_discount: Optional[float] = Field(None, gt=0)
    usage_limit: Optional[int] = Field(None, gt=0)
    user_limit: int = Field(1, gt=0)
    valid_from: datetime
    valid_until: datetime
    applicable_categories: Optional[List[str]] = None
    applicable_products: Optional[List[str]] = None
    is_active: bool = True

    @validator('code')
    def validate_code(cls, v):
        return v.upper().strip()

    @validator('valid_until')
    def validate_valid_until(cls, v, values):
        if 'valid_from' in values and v <= values['valid_from']:
            raise ValueError('La fecha de fin debe ser posterior a la fecha de inicio')
        return v

    @validator('discount_value')
    def validate_discount_value(cls, v, values):
        if values.get('discount_type') == DiscountTypeEnum.PERCENTAGE and v > 100:
            raise ValueError('El descuento porcentual no puede ser mayor a 100%')
        return v

class PromotionalCodeCreate(PromotionalCodeBase):
    pass

class PromotionalCodeUpdate(BaseModel):
    description: Optional[str] = None
    discount_type: Optional[DiscountTypeEnum] = None
    discount_value: Optional[float] = Field(None, gt=0)
    min_amount: Optional[float] = Field(None, ge=0)
    max_discount: Optional[float] = Field(None, gt=0)
    usage_limit: Optional[int] = Field(None, gt=0)
    user_limit: Optional[int] = Field(None, gt=0)
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    applicable_categories: Optional[List[str]] = None
    applicable_products: Optional[List[str]] = None
    is_active: Optional[bool] = None

class PromotionalCodeResponse(PromotionalCodeBase):
    id: str
    used_count: int
    created_at: datetime
    updated_at: datetime
    is_valid: bool
    
    class Config:
        from_attributes = True

# Promotion Usage Schemas
class PromotionUsageBase(BaseModel):
    promotional_code_id: str
    user_id: str
    order_id: Optional[str] = None
    discount_amount: float = Field(..., ge=0)
    order_amount: float = Field(..., gt=0)

class PromotionUsageCreate(PromotionUsageBase):
    pass

class PromotionUsageResponse(PromotionUsageBase):
    id: str
    used_at: datetime
    
    class Config:
        from_attributes = True

# Validation Schemas
class ValidatePromotionalCodeRequest(BaseModel):
    code: str
    order_amount: float = Field(..., gt=0)
    applicable_products: Optional[List[str]] = None
    applicable_categories: Optional[List[str]] = None

class ValidatePromotionalCodeResponse(BaseModel):
    valid: bool
    code: Optional[str] = None
    discount_amount: Optional[float] = None
    message: str
    promotional_code: Optional[PromotionalCodeResponse] = None

# List responses
class FlashOfferListResponse(BaseModel):
    offers: List[FlashOfferResponse]
    total: int
    page: int
    pages: int

class PromotionalCodeListResponse(BaseModel):
    codes: List[PromotionalCodeResponse]
    total: int
    page: int
    pages: int

# Quantity Discount Schemas
class QuantityDiscountBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    min_quantity: int = Field(..., gt=0)
    max_quantity: Optional[int] = Field(None, gt=0)
    discount_type: DiscountTypeEnum = DiscountTypeEnum.PERCENTAGE
    discount_value: float = Field(..., gt=0)
    priority: int = Field(0, ge=0)
    is_active: bool = True

    @validator('max_quantity')
    def validate_max_quantity(cls, v, values):
        if v is not None and 'min_quantity' in values and v < values['min_quantity']:
            raise ValueError('La cantidad máxima debe ser mayor o igual a la cantidad mínima')
        return v

    @validator('discount_value')
    def validate_discount_value(cls, v, values):
        if values.get('discount_type') == DiscountTypeEnum.PERCENTAGE and v > 100:
            raise ValueError('El descuento porcentual no puede ser mayor a 100%')
        return v

class QuantityDiscountCreate(QuantityDiscountBase):
    pass

class QuantityDiscountUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    min_quantity: Optional[int] = Field(None, gt=0)
    max_quantity: Optional[int] = Field(None, gt=0)
    discount_type: Optional[DiscountTypeEnum] = None
    discount_value: Optional[float] = Field(None, gt=0)
    priority: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None

class QuantityDiscountResponse(QuantityDiscountBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class QuantityDiscountListResponse(BaseModel):
    discounts: List[QuantityDiscountResponse]
    total: int
    page: int
    pages: int