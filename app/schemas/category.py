from datetime import datetime

from pydantic import BaseModel, Field, validator


# Category Schemas
class CategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    parent_id: str | None = None
    is_active: bool = True
    sort_order: int = 0


class CategoryCreate(CategoryBase):
    @validator("slug")
    def validate_slug(cls, v):
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Slug debe contener solo letras, números, guiones y guiones bajos")
        return v.lower()


class CategoryUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    slug: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    parent_id: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None

    @validator("slug")
    def validate_slug(cls, v):
        if v is not None and not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Slug debe contener solo letras, números, guiones y guiones bajos")
        return v.lower() if v else v


class CategoryResponse(CategoryBase):
    id: str
    created_at: datetime
    updated_at: datetime
    full_path: str
    product_count: int | None = 0

    class Config:
        from_attributes = True


class CategoryWithSubcategories(CategoryResponse):
    subcategories: list[CategoryResponse] = []


# Brand Schemas
class BrandBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    is_featured: bool = False
    is_active: bool = True


class BrandCreate(BrandBase):
    @validator("slug")
    def validate_slug(cls, v):
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Slug debe contener solo letras, números, guiones y guiones bajos")
        return v.lower()


class BrandUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    slug: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    is_featured: bool | None = None
    is_active: bool | None = None

    @validator("slug")
    def validate_slug(cls, v):
        if v is not None and not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Slug debe contener solo letras, números, guiones y guiones bajos")
        return v.lower() if v else v


class BrandResponse(BrandBase):
    id: str
    created_at: datetime
    updated_at: datetime
    product_count: int | None = 0

    class Config:
        from_attributes = True


# List responses
class CategoryListResponse(BaseModel):
    categories: list[CategoryResponse]
    total: int
    page: int
    pages: int


class BrandListResponse(BaseModel):
    brands: list[BrandResponse]
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
