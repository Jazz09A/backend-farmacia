from typing import List, Optional, Dict, Any
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, Field


class ArticleImageResponse(BaseModel):
    """Representa una imagen asociada a un artículo en Profit Plus."""

    guid: str = Field(..., description="RowGUID de la imagen en saArtImagen")
    url: str = Field(..., description="URL pública construida para servir la imagen")
    description: Optional[str] = Field(
        None, description="Descripción o nombre de la imagen (imagen_des)"
    )
    tip: Optional[str] = Field(
        None, description="Tipo de la imagen (campo tip en saArtImagen)"
    )


class ArticlePriceDetail(BaseModel):
    """Detalle de precio por lista (co_precio) para un artículo."""

    price_code: str = Field(..., description="Código de lista de precio (co_precio)")
    price_name: Optional[str] = Field(
        None, description="Descripción de la lista de precio (saTipoPrecio)"
    )
    amount: Decimal = Field(..., description="Monto de la lista de precio")
    currency: str = Field(
        "VES", description="Moneda en la que está expresado el precio (co_mone)"
    )
    desde: Optional[datetime] = Field(
        None, description="Fecha desde la cual es válido el precio (columna desde en saArtPrecio)"
    )


class ArticleStockDetail(BaseModel):
    """Detalle de inventario por almacén para un artículo."""

    warehouse_code: str = Field(..., description="Código del almacén (co_alma)")
    warehouse_name: Optional[str] = Field(
        None, description="Descripción del almacén (saAlmacen)"
    )
    quantity: Decimal = Field(..., description="Cantidad disponible (stock)")


class ArticleSummary(BaseModel):
    """Resumen para listados de catálogo público."""

    co_art: str = Field(..., description="Código del artículo (co_art)")
    art_des: str = Field(..., description="Descripción del artículo (art_des)")
    category_code: Optional[str] = Field(
        None, description="Código de categoría (co_cat)"
    )
    category_name: Optional[str] = Field(
        None, description="Descripción de la categoría (cat_des desde saCatArticulo)"
    )
    price: Optional[Decimal] = Field(
        None, description="Precio de referencia (lista 01) para catálogo"
    )
    currency: str = Field("VES", description="Moneda asociada al precio de referencia")
    stock: Optional[Decimal] = Field(
        None, description="Cantidad disponible en el almacén principal"
    )
    warehouse_code: Optional[str] = Field(
        None, description="Almacén base usado para el stock de catálogo"
    )
    image_url: Optional[str] = Field(
        None, description="URL de la imagen principal construida desde rowguid"
    )
    has_image: bool = Field(
        False, description="Indica si el artículo tiene al menos una imagen"
    )


class ArticleDetail(BaseModel):
    """Detalle completo de un artículo para la vista pública."""

    co_art: str = Field(..., description="Código del artículo (co_art)")
    art_des: str = Field(..., description="Descripción del artículo (art_des)")
    modelo: Optional[str] = Field(None, description="Modelo del artículo (modelo)")
    ref: Optional[str] = Field(None, description="Referencia del artículo (ref)")
    category_code: Optional[str] = Field(None, description="Código de categoría (co_cat)")
    category_name: Optional[str] = Field(
        None, description="Descripción de la categoría (cat_des desde saCatArticulo)"
    )
    line_code: Optional[str] = Field(None, description="Código de línea (co_lin)")
    sub_line_code: Optional[str] = Field(None, description="Código de sub-línea (co_subl)")
    presentation: Optional[str] = Field(
        None, description="Presentación o unidad de empaque (campo adicional)"
    )
    additional_data: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Datos adicionales relevantes del artículo"
    )
    prices: List[ArticlePriceDetail] = Field(
        default_factory=list, description="Listas de precio disponibles"
    )
    stock_by_warehouse: List[ArticleStockDetail] = Field(
        default_factory=list, description="Inventario agrupado por almacén"
    )
    images: List[ArticleImageResponse] = Field(
        default_factory=list, description="Galería de imágenes del artículo"
    )


class ArticleListResponse(BaseModel):
    """Respuesta paginada para listados de artículos desde Profit Plus."""

    articles: List[ArticleSummary]
    total: int
    page: int
    limit: int
    total_pages: int
    has_next: bool = Field(..., description="Indica si existe una página siguiente")
    has_prev: bool = Field(..., description="Indica si existe una página anterior")
    filters_applied: Dict[str, Any] = Field(
        default_factory=dict, description="Filtros que se aplicaron a la consulta"
    )


class ImageUploadResponse(BaseModel):
    """Respuesta al subir una imagen para un artículo."""

    success: bool = Field(True, description="Estado de la operación")
    message: str = Field(..., description="Mensaje descriptivo de la operación")
    image_guid: str = Field(..., description="RowGUID generado en saArtImagen")
    url: str = Field(..., description="URL pública de la imagen recién subida")

