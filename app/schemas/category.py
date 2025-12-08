from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime

# Category Schemas
class CategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    parent_id: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0

class CategoryCreate(CategoryBase):
    @validator('slug')
    def validate_slug(cls, v):
        if not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError('Slug debe contener solo letras, números, guiones y guiones bajos')
        return v.lower()

class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    slug: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    parent_id: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None

    @validator('slug')
    def validate_slug(cls, v):
        if v is not None and not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError('Slug debe contener solo letras, números, guiones y guiones bajos')
        return v.lower() if v else v

class CategoryResponse(CategoryBase):
    id: str
    created_at: datetime
    updated_at: datetime
    full_path: str
    product_count: Optional[int] = 0
    
    class Config:
        from_attributes = True

class CategoryWithSubcategories(CategoryResponse):
    subcategories: List[CategoryResponse] = []

# Brand Schemas
class BrandBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    is_featured: bool = False
    is_active: bool = True

class BrandCreate(BrandBase):
    @validator('slug')
    def validate_slug(cls, v):
        if not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError('Slug debe contener solo letras, números, guiones y guiones bajos')
        return v.lower()

class BrandUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    slug: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_featured: Optional[bool] = None
    is_active: Optional[bool] = None

    @validator('slug')
    def validate_slug(cls, v):
        if v is not None and not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError('Slug debe contener solo letras, números, guiones y guiones bajos')
        return v.lower() if v else v

class BrandResponse(BrandBase):
    id: str
    created_at: datetime
    updated_at: datetime
    product_count: Optional[int] = 0
    
    class Config:
        from_attributes = True

# List responses
class CategoryListResponse(BaseModel):
    categories: List[CategoryResponse]
    total: int
    page: int
    pages: int

class BrandListResponse(BaseModel):
    brands: List[BrandResponse]
    total: int
    page: int
    pages: int

# Simple responses for dropdowns
class CategorySimple(BaseModel):
    id: str
    name: str
    slug: str

class BrandSimple(BaseModel):
    id: str
    name: str
    slug: str 