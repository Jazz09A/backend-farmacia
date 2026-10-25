from decimal import Decimal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import (
    PaginationParams,
    get_admin_user,
    get_current_active_user,
    get_optional_current_user,
    get_pagination_params,
)
from app.models.user import User
from app.schemas.article import (
    ArticleDetail,
    ArticleListResponse,
    ArticleRecommendations,
    ArticleSummary,
    ImageUploadResponse,
)
from app.schemas.product_image import (
    ProductImageBulkDeleteResponse,
    ProductImageDeleteResponse,
    ProductImageFromURL,
    ProductImageListResponse,
    ProductImageResponse,
    ProductImageUploadResponse,
    SetMainImageResponse,
)
from app.services.article_service import article_service
from app.services.product_image_service import product_image_service
from app.services.recommendation_service import RecommendationService
from app.services.source_system_service import source_system_service

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}

router = APIRouter()


@router.get("", response_model=ArticleListResponse)
async def list_articles(
    pagination: PaginationParams = Depends(get_pagination_params),
    search: str | None = Query(None, description="Buscar por código o descripción"),
    line_code: str | None = Query(None, description="Filtrar por línea (co_lin)"),
    category_code: str | None = Query(
        None, description="Filtrar por categoría (co_cat)"
    ),
    min_price: float | None = Query(None, ge=0, description="Precio mínimo"),
    max_price: float | None = Query(None, ge=0, description="Precio máximo"),
    sort_by: str = Query(
        "art_des",
        description="Campo de ordenamiento: art_des, art_des_desc, price_asc, price_desc, stock_asc, stock_desc",
    ),
    price_code: str = Query("01", description="Lista de precio de referencia"),
    warehouse_code: str = Query("001", description="Almacén principal para stock"),
    in_stock_only: bool = Query(
        False,
        description="Si es true, filtra para traer solo artículos con stock > 0 en el almacén seleccionado",
    ),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Catálogo paginado de artículos directamente desde Profit Plus.
    Requiere autenticación (token JWT).
    """
    min_price_decimal = Decimal(str(min_price)) if min_price is not None else None
    max_price_decimal = Decimal(str(max_price)) if max_price is not None else None

    return article_service.get_catalog(
        page=pagination.page,
        limit=pagination.limit,
        search=search,
        line_code=line_code,
        category_code=category_code,
        min_price=min_price_decimal,
        max_price=max_price_decimal,
        sort_by=sort_by,
        price_code=price_code,
        warehouse_code=warehouse_code,
        in_stock_only=in_stock_only,
        db=db,
    )


@router.get("/{co_art}", response_model=ArticleDetail)
async def get_article_detail(
    co_art: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Obtiene el detalle completo de un artículo específico.
    Requiere autenticación (token JWT).
    """
    return article_service.get_article_detail(co_art, db=db)


@router.get("/{co_art}/recommendations", response_model=ArticleRecommendations)
async def get_article_recommendations(
    co_art: str,
    price_code: str = Query("01", description="Lista de precio de referencia"),
    warehouse_code: str = Query("001", description="Almacén principal para stock"),
    current_user: User = Depends(get_current_active_user),
):
    """
    🎯 **Recomendaciones de artículo**
    
    Obtiene artículos relacionados y recomendados para un artículo específico.
    Incluye:
    - Artículos relacionados (misma categoría, línea, etc.)
    - Artículos frecuentemente comprados juntos
    - También te pueden interesar (basado en historial del cliente si está autenticado)
    """
    # Verificar que el artículo existe
    article_detail = article_service.get_article_detail(co_art)
    if not article_detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artículo no encontrado"
        )
    
    recommendation_service = RecommendationService()
    
    # Obtener código de cliente si el usuario está autenticado
    customer_code = None
    try:
        customer = source_system_service.get_customer_by_email(current_user.email)
        if customer:
            customer_code = customer.get('customer_code')
    except Exception as e:
        logger = article_service.logger
        logger.debug(f"No se pudo obtener código de cliente para recomendaciones: {e}")
    
    # Obtener artículos relacionados
    related = recommendation_service.get_related_articles(
        co_art, 
        limit=3, 
        price_code=price_code, 
        warehouse_code=warehouse_code
    )
    
    # Obtener artículos frecuentemente comprados juntos
    frequently_bought = recommendation_service.get_frequently_bought_together(co_art, limit=4)
    
    # Obtener recomendaciones personalizadas
    you_may_like = recommendation_service.get_recommended_articles(
        customer_code=customer_code,
        limit=3,
        price_code=price_code,
        warehouse_code=warehouse_code
    )
    
    # Convertir a ArticleSummary
    def row_to_summary(row: dict) -> ArticleSummary:
        image_guid = row.get('image_guid')
        image_guid_normalized = None
        if image_guid:
            image_guid_normalized = str(image_guid).strip().upper().replace('{', '').replace('}', '')
        
        image_url = article_service._build_image_url(image_guid_normalized)
        
        return ArticleSummary(
            co_art=(row.get('co_art') or '').strip(),
            art_des=row.get('art_des') or '',
            category_code=(row.get('category_code') or '').strip() if row.get('category_code') else None,
            category_name=row.get('category_name'),
            price=article_service._to_decimal(row.get('price')),
            currency=(row.get('currency') or 'VES').strip(),
            stock=article_service._to_decimal(row.get('stock')),
            warehouse_code=(row.get('warehouse_code') or '').strip() if row.get('warehouse_code') else None,
            image_url=image_url,
            has_image=bool(image_guid_normalized)
        )
    
    return ArticleRecommendations(
        related_articles=[row_to_summary(row) for row in related],
        frequently_bought_together=[row_to_summary(row) for row in frequently_bought],
        you_may_also_like=[row_to_summary(row) for row in you_may_like]
    )


@router.post(
    "/{co_art}/images",
    response_model=ImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_article_image(
    co_art: str,
    file: UploadFile = File(...),
    tip: str | None = Form(
        None,
        description="Código único de la imagen (máx. 6 caracteres). Si no se proporciona, se genera automáticamente (IMG001, IMG002, etc.). Debe ser único para el artículo.",
    ),
    admin_user=Depends(get_admin_user),
):
    """
    Sube una imagen para un artículo en Profit Plus (requiere perfil administrador).
    
    - Si `tip` no se proporciona, se genera automáticamente un código único (IMG001, IMG002, etc.).
    - Si `tip` se proporciona, se verifica que no exista ya para ese artículo.
    - El código `tip` debe ser único por artículo (máximo 6 caracteres).
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de archivo no soportado. Usa JPG o PNG.",
        )

    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo de imagen está vacío.",
        )
    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_PAYLOAD_TOO_LARGE,
            detail="El archivo excede el tamaño máximo permitido (5 MB).",
        )

    return article_service.upload_image(
        co_art=co_art,
        image_bytes=contents,
        filename=file.filename,
        tip=tip,
        created_by=getattr(admin_user, "email", "API_USER"),
    )


@router.get("/images/{image_guid}")
async def get_article_image(
    image_guid: str,
    current_user: User | None = Depends(get_optional_current_user),  # Cambiar a opcional
):
    """
    Devuelve los bytes de una imagen almacenada en saArtImagen.
    Permite acceso público (sin autenticación requerida) para facilitar
    la carga de imágenes en el frontend.
    
    Args:
        image_guid: GUID único de la imagen (formato UUID)
    """
    # Normalizar el GUID: quitar espacios, convertir a mayúsculas, remover llaves
    image_guid_clean = image_guid.strip().upper().replace('{', '').replace('}', '')
    
    if not image_guid_clean:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GUID de imagen inválido",
        )
    
    try:
        row = article_service.get_image_binary(image_guid_clean)
        description = (row.get("imagen_des") or "").lower()
        
        # Determinar el tipo de contenido basado en la descripción o usar JPEG por defecto
        if description.endswith(".png"):
            media_type = "image/png"
        elif description.endswith(".gif"):
            media_type = "image/gif"
        elif description.endswith(".webp"):
            media_type = "image/webp"
        else:
            media_type = "image/jpeg"
        
        return Response(content=row["picture"], media_type=media_type)
    except HTTPException:
        # Re-lanzar HTTPException tal cual
        raise
    except Exception as e:
        # Capturar otros errores y devolver 500
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener la imagen: {e!s}",
        )


# =============================================================================
# ENDPOINTS DE IMÁGENES EN CLOUDINARY (Base de datos local)
# =============================================================================

@router.post(
    "/{co_art}/cloudinary-images",
    response_model=ProductImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Product Images - Cloudinary"],
)
async def upload_product_image_cloudinary(
    co_art: str,
    file: UploadFile = File(..., description="Archivo de imagen (JPG, PNG, WEBP)"),
    is_main: bool = Form(False, description="Marcar como imagen principal"),
    description: str | None = Form(None, description="Descripción o alt text de la imagen"),
    admin_user=Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """
    📷 **Subir imagen de producto a Cloudinary**
    
    Sube una imagen a Cloudinary y guarda la referencia en la base de datos local.
    La imagen queda asociada al código de artículo de Profit Plus (co_art).
    
    **Requiere perfil administrador.**
    
    Args:
        co_art: Código del artículo en Profit Plus
        file: Archivo de imagen
        is_main: Si debe ser la imagen principal (desmarca las anteriores)
        description: Descripción o texto alternativo de la imagen
        
    Returns:
        Información de la imagen subida incluyendo URL de Cloudinary
    """
    result = await product_image_service.upload_product_image(
        co_art=co_art,
        file=file,
        is_main=is_main,
        description=description,
        created_by=getattr(admin_user, "email", "API_USER"),
    )
    return ProductImageUploadResponse(**result)


@router.post(
    "/{co_art}/cloudinary-images/from-url",
    response_model=ProductImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Product Images - Cloudinary"],
)
async def upload_product_image_from_url(
    co_art: str,
    image_data: ProductImageFromURL,
    admin_user=Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """
    📷 **Subir imagen de producto desde URL a Cloudinary**
    
    Descarga una imagen desde una URL externa y la sube a Cloudinary.
    
    **Requiere perfil administrador.**
    
    Args:
        co_art: Código del artículo en Profit Plus
        image_data: Datos de la imagen incluyendo URL origen
        
    Returns:
        Información de la imagen subida
    """
    result = await product_image_service.upload_product_image_from_url(
        co_art=co_art,
        image_url=image_data.image_url,
        is_main=image_data.is_main,
        description=image_data.description,
        created_by=getattr(admin_user, "email", "API_USER"),
    )
    return ProductImageUploadResponse(**result)


@router.get(
    "/{co_art}/cloudinary-images",
    response_model=ProductImageListResponse,
    tags=["Product Images - Cloudinary"],
)
async def get_product_cloudinary_images(
    co_art: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    📷 **Obtener imágenes de Cloudinary de un producto**
    
    Retorna todas las imágenes almacenadas en Cloudinary para un artículo.
    Las imágenes vienen ordenadas con la principal primero.
    
    Args:
        co_art: Código del artículo en Profit Plus
        
    Returns:
        Lista de imágenes del producto
    """
    images = product_image_service.get_images_by_article(co_art, db=db)
    
    return ProductImageListResponse(
        co_art_profit=co_art.strip().upper(),
        images=[ProductImageResponse(**img) for img in images],
        total=len(images)
    )


@router.delete(
    "/cloudinary-images/{image_id}",
    response_model=ProductImageDeleteResponse,
    tags=["Product Images - Cloudinary"],
)
async def delete_product_cloudinary_image(
    image_id: int,
    admin_user=Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """
    🗑️ **Eliminar imagen de Cloudinary**
    
    Elimina una imagen específica de Cloudinary y de la base de datos.
    
    **Requiere perfil administrador.**
    
    Args:
        image_id: ID de la imagen en la base de datos
        
    Returns:
        Resultado de la eliminación
    """
    result = await product_image_service.delete_image(image_id, db=db)
    return ProductImageDeleteResponse(**result)


@router.delete(
    "/{co_art}/cloudinary-images",
    response_model=ProductImageBulkDeleteResponse,
    tags=["Product Images - Cloudinary"],
)
async def delete_all_product_cloudinary_images(
    co_art: str,
    admin_user=Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """
    🗑️ **Eliminar todas las imágenes de un producto**
    
    Elimina todas las imágenes de Cloudinary asociadas a un artículo.
    
    **Requiere perfil administrador.**
    
    Args:
        co_art: Código del artículo en Profit Plus
        
    Returns:
        Resultado de la eliminación masiva
    """
    result = await product_image_service.delete_all_images_by_article(co_art, db=db)
    return ProductImageBulkDeleteResponse(**result)


@router.patch(
    "/cloudinary-images/{image_id}/set-main",
    response_model=SetMainImageResponse,
    tags=["Product Images - Cloudinary"],
)
async def set_main_product_image(
    image_id: int,
    admin_user=Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """
    ⭐ **Establecer imagen principal**
    
    Marca una imagen como la imagen principal del producto.
    Las demás imágenes del mismo producto se desmarcan como principales.
    
    **Requiere perfil administrador.**
    
    Args:
        image_id: ID de la imagen a establecer como principal
        
    Returns:
        Información de la imagen actualizada
    """
    result = await product_image_service.set_main_image(image_id, db=db)
    return SetMainImageResponse(**result)

