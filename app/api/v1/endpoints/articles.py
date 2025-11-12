from decimal import Decimal
from typing import Optional

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

from app.core.dependencies import (
    PaginationParams,
    get_admin_user,
    get_current_active_user,
    get_optional_current_user,  # Agregar esto
    get_pagination_params,
)
from app.models.user import User
from app.schemas.article import ArticleDetail, ArticleListResponse, ImageUploadResponse
from app.services.article_service import article_service


MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}

router = APIRouter()


@router.get("", response_model=ArticleListResponse)
async def list_articles(
    pagination: PaginationParams = Depends(get_pagination_params),
    search: Optional[str] = Query(None, description="Buscar por código o descripción"),
    line_code: Optional[str] = Query(None, description="Filtrar por línea (co_lin)"),
    category_code: Optional[str] = Query(
        None, description="Filtrar por categoría (co_cat)"
    ),
    min_price: Optional[float] = Query(None, ge=0, description="Precio mínimo"),
    max_price: Optional[float] = Query(None, ge=0, description="Precio máximo"),
    sort_by: str = Query(
        "art_des",
        description="Campo de ordenamiento: art_des, art_des_desc, price_asc, price_desc, stock_asc, stock_desc",
    ),
    price_code: str = Query("01", description="Lista de precio de referencia"),
    warehouse_code: str = Query("001", description="Almacén principal para stock"),
    current_user: User = Depends(get_current_active_user),
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
    )


@router.get("/{co_art}", response_model=ArticleDetail)
async def get_article_detail(
    co_art: str,
    current_user: User = Depends(get_current_active_user),
):
    """
    Obtiene el detalle completo de un artículo específico.
    Requiere autenticación (token JWT).
    """
    return article_service.get_article_detail(co_art)


@router.post(
    "/{co_art}/images",
    response_model=ImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_article_image(
    co_art: str,
    file: UploadFile = File(...),
    tip: Optional[str] = Form(
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
    current_user: Optional[User] = Depends(get_optional_current_user),  # Cambiar a opcional
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
            detail=f"Error al obtener la imagen: {str(e)}",
        )

