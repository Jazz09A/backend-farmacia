"""
Endpoints de administración para gestión de blogs.
Solo accesibles para usuarios con rol de administrador.
"""

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.auth import get_admin_user
from app.models.user import User
from app.schemas.blog import (
    BlogCategoryCreate,
    BlogCategoryResponse,
    BlogCategoryUpdate,
    BlogImageListResponse,
    BlogImageResponse,
    BlogImageUploadResponse,
    BlogPostCreate,
    BlogPostListResponse,
    BlogPostResponse,
    BlogPostSummary,
    BlogPostUpdate,
)
from app.services.blog_image_service import BlogImageService
from app.services.blog_service import BlogService

router = APIRouter(prefix="/admin/blog", tags=["👑 Admin - Blog"])


# =============================================================================
# BLOG CATEGORIES - ADMIN
# =============================================================================


@router.post("/categories", response_model=BlogCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_blog_category(
    category_data: BlogCategoryCreate, current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)
):
    """
    📝 **Crear categoría de blog**

    Crea una nueva categoría para los artículos del blog.
    Requiere permisos de administrador.
    """
    service = BlogService(db)
    category = service.create_category(category_data)
    return category


@router.get("/categories", response_model=list[BlogCategoryResponse])
async def get_all_blog_categories(
    include_deleted: bool = Query(False, description="Incluir categorías eliminadas"),
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """
    📂 **Listar todas las categorías de blog**

    Obtiene todas las categorías del blog.
    Por defecto solo muestra categorías no eliminadas.
    Requiere permisos de administrador.
    """
    service = BlogService(db)
    categories = service.get_all_categories(include_deleted=include_deleted)
    return categories


@router.get("/categories/{category_id}", response_model=BlogCategoryResponse)
async def get_blog_category(
    category_id: str, current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)
):
    """
    📂 **Obtener categoría de blog por ID**

    Obtiene una categoría específica del blog.
    Requiere permisos de administrador.
    """
    service = BlogService(db)
    category = service.get_category_by_id(category_id)

    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")

    return category


@router.put("/categories/{category_id}", response_model=BlogCategoryResponse)
async def update_blog_category(
    category_id: str,
    category_data: BlogCategoryUpdate,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """
    ✏️ **Actualizar categoría de blog**

    Actualiza una categoría existente del blog.
    Requiere permisos de administrador.
    """
    service = BlogService(db)
    category = service.update_category(category_id, category_data)
    return category


@router.delete("/categories/{category_id}")
async def delete_blog_category(
    category_id: str, current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)
):
    """
    🗑️ **Eliminar categoría de blog (soft delete)**

    Elimina una categoría del blog usando soft delete (marca como eliminada).
    No se puede eliminar si tiene posts asociados.
    Requiere permisos de administrador.

    Retorna un objeto con el campo `success` indicando si la eliminación fue exitosa.
    """

    class DeleteResponse(BaseModel):
        success: bool
        message: str

    service = BlogService(db)
    try:
        success = service.delete_category(category_id)
        if success:
            return DeleteResponse(success=True, message="Categoría eliminada correctamente")
        else:
            return DeleteResponse(success=False, message="La categoría ya estaba eliminada")
    except HTTPException as e:
        # Si hay posts asociados u otro error, retornar success=False
        return DeleteResponse(success=False, message=e.detail)


# =============================================================================
# BLOG POSTS - ADMIN
# =============================================================================


@router.post("/posts", response_model=BlogPostResponse, status_code=status.HTTP_201_CREATED)
async def create_blog_post(
    post_data: BlogPostCreate, current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)
):
    """
    📝 **Crear artículo de blog**

    Crea un nuevo artículo en el blog.
    Si se proporciona `author_id` en el body, se usa ese autor. Si no, se asigna automáticamente al usuario autenticado.
    Requiere permisos de administrador.
    """
    service = BlogService(db)
    post = service.create_post(post_data, default_author_id=current_user.id)

    # Cargar relaciones para la respuesta
    post_with_relations = service.get_post_by_id(post.id, include_relations=True)
    return post_with_relations if post_with_relations is not None else post


@router.get("/posts", response_model=BlogPostListResponse)
async def get_all_blog_posts(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(10, ge=1, le=50, description="Elementos por página"),
    status_filter: str | None = Query(None, description="Filtrar por estado: draft, published, archived"),
    category_id: str | None = Query(None, description="Filtrar por ID de categoría"),
    search: str | None = Query(None, description="Buscar en título y contenido"),
    include_deleted: bool = Query(False, description="Incluir artículos eliminados"),
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """
    📰 **Listar todos los artículos del blog (admin)**

    Obtiene una lista paginada de todos los artículos del blog, incluyendo borradores.
    Requiere permisos de administrador.
    """
    service = BlogService(db)
    posts, total = service.get_all_posts(
        page=page,
        limit=limit,
        status_filter=status_filter,
        category_id=category_id,
        search=search,
        include_deleted=include_deleted,
    )

    # OPTIMIZACIÓN: Obtener todas las imágenes de todos los posts en una sola query
    if posts:
        post_ids = [post.id for post in posts]
        image_service = BlogImageService(db)

        # Obtener todas las imágenes de todos los posts en una sola query
        from app.models.blog import BlogImage

        all_images = (
            db.query(BlogImage)
            .filter(BlogImage.blog_post_id.in_(post_ids))
            .order_by(BlogImage.blog_post_id, BlogImage.image_code)
            .all()
        )

        # Crear un diccionario para acceso rápido: post_id -> [imágenes]
        images_by_post: dict[str, list[BlogImage]] = {}
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
                id=post.author_id, email=post.author.email if post.author else None, full_name=post.author_name
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
            excerpt=excerpt,
        )
        items.append(summary)

    pages = (total + limit - 1) // limit if total > 0 else 1

    return BlogPostListResponse(items=items, total=total, page=page, limit=limit, pages=pages)


@router.get("/posts/{post_id}", response_model=BlogPostResponse)
async def get_blog_post(
    post_id: str,
    include_deleted: bool = Query(False, description="Incluir artículos eliminados"),
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """
    📖 **Obtener artículo de blog por ID (admin)**

    Obtiene un artículo específico del blog, incluyendo borradores.
    Requiere permisos de administrador.
    """
    service = BlogService(db)
    post = service.get_post_by_id(post_id, include_relations=True, include_deleted=include_deleted)

    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artículo no encontrado")

    return post


@router.put("/posts/{post_id}", response_model=BlogPostResponse)
async def update_blog_post(
    post_id: str, post_data: BlogPostUpdate, current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)
):
    """
    ✏️ **Actualizar artículo de blog**

    Actualiza un artículo existente del blog.
    Requiere permisos de administrador.
    """
    service = BlogService(db)
    post = service.update_post(post_id, post_data)

    # Cargar relaciones para la respuesta
    post_with_relations = service.get_post_by_id(post.id, include_relations=True)
    return post_with_relations if post_with_relations is not None else post


@router.delete("/posts/{post_id}")
async def delete_blog_post(post_id: str, current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    """
    🗑️ **Eliminar artículo de blog (Soft Delete)**

    Elimina un artículo del blog usando soft delete (marca como eliminado).
    Requiere permisos de administrador.
    """
    service = BlogService(db)
    try:
        service.delete_post(post_id)
        return {"success": True, "message": "Artículo eliminado correctamente"}
    except HTTPException as e:
        if e.status_code == status.HTTP_400_BAD_REQUEST:
            return {"success": False, "message": e.detail}
        raise


# =============================================================================
# BLOG IMAGES - ADMIN
# =============================================================================

ALLOWED_CONTENT_TYPES = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
MAX_IMAGE_SIZE = 6 * 1024 * 1024  # 6 MB


@router.post("/posts/{post_id}/images", response_model=BlogImageUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_blog_image(
    post_id: str,
    file: UploadFile = File(...),
    description: str | None = Form(None),
    image_code: str | None = Form(
        None, description="Código único opcional (máx. 10 caracteres). Si no se proporciona, se genera automáticamente"
    ),
    optimize: bool = Form(True, description="Optimizar imagen automáticamente (recomendado)"),
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """
    📸 **Subir imagen para artículo de blog (Asíncrono Optimizado)**

    Sube una imagen para un artículo de blog de forma asíncrona y optimizada.
    - Si `image_code` no se proporciona, se genera automáticamente (IMG001, IMG002, etc.)
    - Si `image_code` se proporciona, debe ser único para el post
    - Formatos permitidos: JPEG, JPG, PNG, WEBP
    - Tamaño máximo: 6 MB
    - La imagen se optimiza automáticamente para reducir tamaño
    - La subida se procesa de forma asíncrona para no bloquear el servidor
    Requiere permisos de administrador.
    """
    # Validar tipo de archivo (validación rápida)
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de archivo no soportado. Usa JPEG, PNG o WEBP."
        )

    # Leer contenido del archivo de forma asíncrona en chunks para mejor rendimiento
    contents = b""
    chunk_size = 1024 * 1024  # 1 MB chunks

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        contents += chunk

        # Validar tamaño mientras se lee (validación temprana)
        if len(contents) > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo excede el tamaño máximo permitido (6 MB)"
            )

    if len(contents) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo de imagen está vacío")

    # Subir imagen de forma asíncrona
    image_service = BlogImageService(db)
    blog_image = await image_service.upload_image(
        blog_post_id=post_id,
        image_bytes=contents,
        description=description,
        image_code=image_code,
        created_by=current_user.email or current_user.id,
        optimize=optimize,
    )

    # Construir URL
    image_url = image_service._build_image_url(blog_image.id)

    return BlogImageUploadResponse(
        success=True,
        message="Imagen subida correctamente",
        image_id=blog_image.id,
        image_code=blog_image.image_code,
        image_url=image_url,
    )


@router.get("/posts/{post_id}/images", response_model=BlogImageListResponse)
async def get_blog_images(post_id: str, current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    """
    📷 **Listar imágenes de un artículo de blog**

    Obtiene todas las imágenes asociadas a un artículo de blog.
    Requiere permisos de administrador.
    """
    image_service = BlogImageService(db)
    images = image_service.get_images_by_post(post_id)

    image_responses = []
    for img in images:
        image_url = image_service._build_image_url(img.id)
        image_responses.append(
            BlogImageResponse(
                id=img.id,
                blog_post_id=img.blog_post_id,
                image_code=img.image_code,
                description=img.description,
                created_by=img.created_by,
                created_at=img.created_at,
                updated_at=img.updated_at,
                image_url=image_url,
            )
        )

    return BlogImageListResponse(images=image_responses, total=len(image_responses))


@router.delete("/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blog_image(image_id: str, current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    """
    🗑️ **Eliminar imagen de blog**

    Elimina una imagen de un artículo de blog.
    Requiere permisos de administrador.
    """
    image_service = BlogImageService(db)
    image_service.delete_image(image_id)
