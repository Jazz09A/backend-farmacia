from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime


# =============================================================================
# BLOG CATEGORY SCHEMAS
# =============================================================================

class BlogCategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None

    @field_validator('slug')
    def validate_slug(cls, v):
        if v and not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError('El slug solo puede contener letras, números, guiones y guiones bajos')
        return v.lower()


class BlogCategoryCreate(BaseModel):
    """Schema para crear categoría - el slug se genera automáticamente desde el nombre"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class BlogCategoryUpdate(BaseModel):
    """Schema para actualizar categoría - el slug se genera automáticamente desde el nombre si se actualiza"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None


class BlogCategoryResponse(BlogCategoryBase):
    id: str
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# =============================================================================
# BLOG POST SCHEMAS
# =============================================================================

class BlogPostBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    category_id: str = Field(..., description="ID de la categoría del blog")
    featured_image_url: Optional[str] = None
    status: Optional[str] = Field(default="draft", description="Estado: draft, published, archived")
    published_at: Optional[datetime] = None

    @field_validator('slug')
    def validate_slug(cls, v):
        if v and not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError('El slug solo puede contener letras, números, guiones y guiones bajos')
        return v.lower()

    @field_validator('status')
    def validate_status(cls, v):
        if v and v not in ['draft', 'published', 'archived']:
            raise ValueError('El estado debe ser: draft, published o archived')
        return v


class BlogPostCreate(BaseModel):
    """Schema para crear post - el slug y published_at se generan automáticamente"""
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    category_id: str = Field(..., description="ID de la categoría del blog")
    author_name: Optional[str] = Field(None, description="Nombre del autor del artículo. Si no se proporciona, se usa el nombre del usuario autenticado")
    featured_image_url: Optional[str] = None
    status: Optional[str] = Field(default="draft", description="Estado: draft, published, archived")


class BlogPostUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    slug: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, min_length=1)
    category_id: Optional[str] = None
    author_name: Optional[str] = Field(None, description="Nombre del autor del artículo")
    featured_image_url: Optional[str] = None
    status: Optional[str] = Field(None, description="Estado: draft, published, archived")
    published_at: Optional[datetime] = None

    @field_validator('slug')
    def validate_slug(cls, v):
        if v and not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError('El slug solo puede contener letras, números, guiones y guiones bajos')
        return v.lower() if v else v

    @field_validator('status')
    def validate_status(cls, v):
        if v and v not in ['draft', 'published', 'archived']:
            raise ValueError('El estado debe ser: draft, published o archived')
        return v


class BlogPostAuthor(BaseModel):
    id: Optional[str] = None  # Opcional si solo se usa author_name
    email: Optional[str] = None  # Opcional si solo se usa author_name
    full_name: str
    
    class Config:
        from_attributes = True


class BlogPostCategory(BaseModel):
    id: str
    name: str
    slug: str
    
    class Config:
        from_attributes = True


class BlogPostResponse(BlogPostBase):
    id: str
    author_id: Optional[str] = None  # Opcional si solo se usa author_name
    author: Optional[BlogPostAuthor] = None
    category: Optional[BlogPostCategory] = None
    created_at: datetime
    updated_at: datetime
    is_published: bool = False
    
    class Config:
        from_attributes = True


class BlogPostSummary(BaseModel):
    """Resumen de un post para listados"""
    id: str
    title: str
    slug: str
    featured_image_url: Optional[str] = None  # URL externa o primera imagen subida
    images: Optional[List[str]] = None  # URLs de todas las imágenes subidas
    status: Optional[str] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    author: Optional[BlogPostAuthor] = None
    category: Optional[BlogPostCategory] = None
    excerpt: Optional[str] = None  # Primeros caracteres del contenido
    
    class Config:
        from_attributes = True


class BlogPostListResponse(BaseModel):
    """Respuesta paginada de lista de posts"""
    items: List[BlogPostSummary]
    total: int
    page: int
    limit: int
    pages: int


class BlogPostDetailResponse(BlogPostResponse):
    """Respuesta detallada de un post individual"""
    pass


# =============================================================================
# BLOG IMAGE SCHEMAS
# =============================================================================

class BlogImageBase(BaseModel):
    image_code: str = Field(..., max_length=10, description="Código único de la imagen (ej: IMG001)")
    description: Optional[str] = None


class BlogImageCreate(BaseModel):
    """Schema para crear imagen - el image_code se genera automáticamente si no se proporciona"""
    description: Optional[str] = None
    image_code: Optional[str] = Field(None, max_length=10, description="Código opcional. Si no se proporciona, se genera automáticamente")


class BlogImageResponse(BlogImageBase):
    id: str
    blog_post_id: str
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    image_url: str = Field(..., description="URL para obtener la imagen")
    
    class Config:
        from_attributes = True


class BlogImageListResponse(BaseModel):
    """Lista de imágenes de un post"""
    images: List[BlogImageResponse]
    total: int


class BlogImageUploadResponse(BaseModel):
    """Respuesta al subir una imagen"""
    success: bool
    message: str
    image_id: str
    image_code: str
    image_url: str

