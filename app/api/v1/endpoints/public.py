"""
Endpoints públicos que no requieren autenticación.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

# from app.utils.timezone import get_ve_now
from fastapi.responses import Response
from sqlalchemy.orm import Session

# from sqlalchemy import func, and_, or_, desc, asc
# from decimal import Decimal
from app.config.database import get_db
from app.schemas.blog import (
    BlogCategoryResponse,
    BlogPostDetailResponse,
    BlogPostListResponse,
    BlogPostSummary,
)
from app.services.blog_image_service import BlogImageService

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

router = APIRouter(prefix="/public")


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


# =============================================================================
# BLOG PÚBLICO - LECTURA DE ARTÍCULOS
# =============================================================================

@router.get("/blog/posts", response_model=BlogPostListResponse)
async def get_blog_posts(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(10, ge=1, le=50, description="Elementos por página"),
    category_slug: str | None = Query(None, description="Filtrar por slug de categoría"),
    search: str | None = Query(None, description="Buscar en título y contenido"),
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


@router.get("/blog/categories", response_model=list[BlogCategoryResponse])
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
async def get_blog_image(image_id: str):
    """
    🖼️ **Obtener imagen de blog (público) - Optimizado para carga paralela**
    
    Obtiene una imagen de un artículo de blog por su ID.
    - Usa caché en memoria para respuestas ultra-rápidas
    - Procesamiento asíncrono para no bloquear otras requests
    - Headers de caché para que el navegador guarde la imagen
    """
    # Usar método asíncrono con caché (no necesita sesión de BD como dependencia)
    result = await BlogImageService.get_image_data_async(image_id)
    
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Imagen no encontrada"
        )
    
    image_data, content_type = result
    
    # Determinar extensión para el filename
    ext_map = {
        "image/jpeg": "jpg",
        "image/png": "png", 
        "image/webp": "webp",
        "image/gif": "gif"
    }
    ext = ext_map.get(content_type, "jpg")
    
    return Response(
        content=image_data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'inline; filename="image_{image_id[:8]}.{ext}"',
            # Headers de caché agresivo - las imágenes no cambian
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": f'"{image_id}"',
            # Headers para permitir carga paralela desde cualquier origen
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Expose-Headers": "Content-Length, Content-Type",
        }
    )  