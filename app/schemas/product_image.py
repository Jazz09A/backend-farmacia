"""
Schemas para imágenes de productos.
"""

from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field
from datetime import datetime


class ProductImageBase(BaseModel):
    """Schema base para imágenes de producto."""
    co_art_profit: str = Field(..., description="Código del artículo en Profit Plus")
    is_main: bool = Field(default=False, description="Si es la imagen principal")
    description: Optional[str] = Field(None, description="Descripción o alt text de la imagen")


class ProductImageCreate(ProductImageBase):
    """Schema para crear una imagen de producto."""
    pass


class ProductImageFromURL(ProductImageBase):
    """Schema para crear imagen desde URL."""
    image_url: str = Field(..., description="URL de la imagen a subir")


class ProductImageResponse(BaseModel):
    """Schema de respuesta para una imagen de producto."""
    id: int
    co_art_profit: str
    cloudinary_url: str
    cloudinary_public_id: Optional[str] = None
    is_main: bool
    display_order: int
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ProductImageUploadResponse(BaseModel):
    """Schema de respuesta para subida de imagen."""
    id: int
    co_art_profit: str
    cloudinary_url: str
    cloudinary_public_id: Optional[str] = None
    is_main: bool
    display_order: int
    description: Optional[str] = None
    created_at: Optional[str] = None
    cloudinary_info: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


class ProductImageListResponse(BaseModel):
    """Schema de respuesta para lista de imágenes de un producto."""
    co_art_profit: str
    images: List[ProductImageResponse]
    total: int


class ProductImageDeleteResponse(BaseModel):
    """Schema de respuesta para eliminación de imagen."""
    success: bool
    message: str
    image_id: Optional[int] = None
    co_art_profit: Optional[str] = None
    cloudinary_deleted: bool = False


class ProductImageBulkDeleteResponse(BaseModel):
    """Schema de respuesta para eliminación masiva de imágenes."""
    success: bool
    message: str
    co_art_profit: str
    deleted_count: int
    cloudinary_result: Optional[Dict[str, Any]] = None


class SetMainImageResponse(BaseModel):
    """Schema de respuesta para establecer imagen principal."""
    success: bool
    message: str
    image_id: int
    co_art_profit: str
    cloudinary_url: str


class ProductImagesForCatalog(BaseModel):
    """
    Schema simplificado de imágenes para usar en el catálogo.
    Solo incluye la URL de la imagen principal.
    """
    co_art_profit: str
    main_image_url: Optional[str] = None
    has_cloudinary_images: bool = False
