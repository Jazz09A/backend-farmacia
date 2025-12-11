"""
Endpoints públicos que no requieren autenticación.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
# from sqlalchemy import func, and_, or_, desc, asc
# from decimal import Decimal
from app.config.database import get_db
# Product model eliminado - Los artículos vienen de Profit Plus a través de /articles
# from app.models.product import Product
# from app.models.user import User
# from app.models.promotion import FlashOffer, DiscountType
# from app.core.dependencies import PaginationParams, get_pagination_params
# Product schemas eliminados - Los artículos vienen de Profit Plus
# from app.schemas.product import ProductResponse, ProductListResponse, ProductSummary, FlashOfferInfo
# from app.schemas.promotion import QuantityDiscountResponse
# from app.core.dependencies import get_optional_current_user
# from app.services.discount_service import DiscountService
from app.services.blog_service import BlogService
from app.services.blog_image_service import BlogImageService
from app.schemas.blog import BlogPostListResponse, BlogPostDetailResponse, BlogPostSummary, BlogCategoryResponse
# from app.utils.timezone import get_ve_now
from fastapi.responses import Response

router = APIRouter(prefix="/public")


# Funciones helper eliminadas - ya no se usan porque los endpoints de productos fueron eliminados
# Los artículos vienen de Profit Plus a través de /articles

# Endpoints de productos eliminados - Los artículos vienen de Profit Plus a través de /articles
# @router.get("/products") - ELIMINADO
# @router.get("/products/{product_id}") - ELIMINADO  
# @router.get("/products/search") - ELIMINADO
# Los artículos se obtienen desde /api/v1/articles que se conecta directamente a Profit Plus

# =============================================================================
# INFORMACIÓN GENERAL - PÚBLICO
# =============================================================================


# @router.get("/payment-methods")
# async def get_payment_methods():
#     """
#     💳 **Métodos de pago disponibles**
    
#     Obtiene los métodos de pago activos en el sistema.
#     """
#     methods = [
#         {
#             "id": "cash",
#             "name": "Efectivo",
#             "description": "Pago en efectivo contra entrega",
#             "fee": 0.00,
#             "active": True
#         },
#         {
#             "id": "transfer",
#             "name": "Transferencia Bancaria", 
#             "description": "Transferencia a cuenta bancaria",
#             "fee": 0.00,
#             "active": True
#         },
#         {
#             "id": "mobile_payment",
#             "name": "Pago Móvil",
#             "description": "Pago móvil interbancario",
#             "fee": 0.00,
#             "active": True
#         }
#     ]
#     return {"payment_methods": methods}

# Endpoints de categories y brands eliminados - no se usan con Profit Plus
# Las categorías y marcas vienen de Profit Plus a través de articles.py

# =============================================================================
# INFORMACIÓN DEL SISTEMA
# =============================================================================

@router.get("/health")
async def health_check():
    """
    ❤️ **Health Check**
    
    Endpoint para verificar que la API está funcionando.
    """
    return {
        "status": "healthy",
        "service": "Farmacia API",
        "version": "1.0.0"
    }

# @router.get("/features")
# async def get_public_features():
#     """
#     ⭐ **Características del sistema**
    
#     Obtiene las características públicas del sistema.
#     """
#     return {
#         "features": {
#             "user_registration": True,
#             "guest_checkout": False,
#             "multiple_payment_methods": True,
#             "prescription_upload": True,
#             "delivery_tracking": True,
#             "customer_reviews": True,
#             "loyalty_program": False
#         },
#         "supported_currencies": ["VES", "USD"],
#         "supported_languages": ["es"],
#         "api_version": "v1"
#     } 

# # =============================================================================
# # DESCUENTOS PÚBLICOS
# # =============================================================================

# @router.get("/quantity-discounts/applicable", response_model=Optional[QuantityDiscountResponse])
# async def get_applicable_quantity_discount(
#     total_quantity: int = Query(..., gt=0, description="Cantidad total de productos"),
#     db: Session = Depends(get_db)
# ):
#     """
#     Obtener el descuento por cantidad aplicable para una cantidad dada.

#     **Endpoint público** - No requiere autenticación.
#     """
#     service = DiscountService(db)
#     discount = service.get_applicable_quantity_discount(total_quantity)
#     return discount

# =============================================================================
# BLOG PÚBLICO - LECTURA DE ARTÍCULOS
# =============================================================================

@router.get("/blog/posts", response_model=BlogPostListResponse)
async def get_blog_posts(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(10, ge=1, le=50, description="Elementos por página"),
    category_slug: Optional[str] = Query(None, description="Filtrar por slug de categoría"),
    search: Optional[str] = Query(None, description="Buscar en título y contenido"),
    db: Session = Depends(get_db)
):
    """
    📰 **Listar artículos del blog (público)**
    
    Obtiene una lista paginada de artículos publicados del blog.
    Solo muestra artículos con estado 'published'.
    """
    service = BlogService(db)
    posts, total = service.get_published_posts(
        page=page,
        limit=limit,
        category_slug=category_slug,
        search=search
    )
    
    # OPTIMIZACIÓN: Obtener todas las imágenes de todos los posts en una sola query
    if posts:
        post_ids = [post.id for post in posts]
        image_service = BlogImageService(db)
        
        # Obtener todas las imágenes de todos los posts en una sola query
        from app.models.blog import BlogImage
        all_images = db.query(BlogImage).filter(
            BlogImage.blog_post_id.in_(post_ids)
        ).order_by(BlogImage.blog_post_id, BlogImage.image_code).all()
        
        # Crear un diccionario para acceso rápido: post_id -> [imágenes]
        images_by_post = {}
        for img in all_images:
            if img.blog_post_id not in images_by_post:
                images_by_post[img.blog_post_id] = []
            images_by_post[img.blog_post_id].append(img)
    else:
        images_by_post = {}
        image_service = BlogImageService(db)
    
    # Convertir a summaries con extracto
    items = []
    
    for post in posts:
        excerpt = BlogService.generate_excerpt(post.content, max_length=200)
        
        # Obtener imágenes del diccionario (sin query adicional)
        blog_images = images_by_post.get(post.id, [])
        image_urls = [image_service._build_image_url(img.id) for img in blog_images]
        
        # Si no hay featured_image_url pero hay imágenes subidas, usar la primera como destacada
        featured_url = post.featured_image_url
        if not featured_url and image_urls:
            featured_url = image_urls[0]
        
        # Construir objeto author: usar author_name si existe, sino usar el usuario relacionado
        from app.schemas.blog import BlogPostAuthor
        if post.author_name:
            author_obj = BlogPostAuthor(
                id=post.author_id,
                email=post.author.email if post.author else None,
                full_name=post.author_name
            )
        else:
            author_obj = post.author
        
        summary = BlogPostSummary(
            id=post.id,
            title=post.title,
            slug=post.slug,
            featured_image_url=featured_url,
            images=image_urls if image_urls else None,
            status=post.status,
            published_at=post.published_at,
            created_at=post.created_at,
            updated_at=post.updated_at,
            author=author_obj,
            category=post.category,
            excerpt=excerpt
        )
        items.append(summary)
    
    pages = (total + limit - 1) // limit if total > 0 else 1
    
    return BlogPostListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        pages=pages
    )


@router.get("/blog/posts/{slug}", response_model=BlogPostDetailResponse)
async def get_blog_post_by_slug(
    slug: str,
    db: Session = Depends(get_db)
):
    """
    📖 **Obtener artículo del blog por slug (público)**
    
    Obtiene un artículo publicado del blog por su slug.
    Solo muestra artículos con estado 'published'.
    """
    service = BlogService(db)
    post = service.get_post_by_slug(slug, include_relations=True)
    
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artículo no encontrado"
        )
    
    # Verificar que el post esté publicado
    if post.status != 'published' or not post.published_at:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artículo no encontrado"
        )
    
    # Construir objeto author: usar author_name si existe, sino usar el usuario relacionado
    from app.schemas.blog import BlogPostAuthor
    if post.author_name:
        author_obj = BlogPostAuthor(
            id=post.author_id,
            email=post.author.email if post.author else None,
            full_name=post.author_name
        )
    else:
        author_obj = post.author
    
    return BlogPostDetailResponse(
        id=post.id,
        title=post.title,
        slug=post.slug,
        content=post.content,
        category_id=post.category_id,
        featured_image_url=post.featured_image_url,
        status=post.status,
        published_at=post.published_at,
        author_id=post.author_id or "",
        author=author_obj,
        category=post.category,
        created_at=post.created_at,
        updated_at=post.updated_at,
        is_published=post.is_published
    )


@router.get("/blog/categories", response_model=List[BlogCategoryResponse])
async def get_blog_categories(
    db: Session = Depends(get_db)
):
    """
    📂 **Listar categorías del blog (público)**
    
    Obtiene todas las categorías del blog.
    """
    service = BlogService(db)
    categories = service.get_all_categories()
    return categories


@router.get("/blog/images/{image_id}")
async def get_blog_image(
    image_id: str,
    db: Session = Depends(get_db)
):
    """
    🖼️ **Obtener imagen de blog (público)**
    
    Obtiene una imagen de un artículo de blog por su ID.
    Retorna la imagen como archivo binario.
    """
    image_service = BlogImageService(db)
    image = image_service.get_image_by_id(image_id)
    
    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Imagen no encontrada"
        )
    
    # Determinar content type basado en los datos
    # Por simplicidad, asumimos JPEG si no podemos determinarlo
    content_type = "image/jpeg"
    if image.image_data[:4] == b'\x89PNG':
        content_type = "image/png"
    elif image.image_data[:2] == b'\xff\xd8':
        content_type = "image/jpeg"
    elif image.image_data[:4] == b'RIFF' and image.image_data[8:12] == b'WEBP':
        content_type = "image/webp"
    
    return Response(
        content=image.image_data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'inline; filename="{image.image_code}.jpg"'
        }
    )