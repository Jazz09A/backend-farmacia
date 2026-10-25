import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import desc, func, or_, text
from sqlalchemy.orm import Session, joinedload

from app.config.logging_config import get_logger
from app.config.settings import Settings
from app.models.blog import BlogCategory, BlogPost
from app.models.user import User
from app.schemas.blog import (
    BlogCategoryCreate,
    BlogCategoryUpdate,
    BlogPostCreate,
    BlogPostUpdate,
)
from app.services.cache_service import cache_service
from app.utils.timezone import get_ve_now

logger = get_logger("blog")
settings = Settings()

# Prefijos de caché para el blog
CACHE_PREFIX_BLOG_POSTS = "blog:posts"
CACHE_PREFIX_BLOG_CATEGORIES = "blog:categories"
CACHE_PREFIX_BLOG_POST_DETAIL = "blog:post"
CACHE_TTL_BLOG_POSTS = 300  # 5 minutos para listados
CACHE_TTL_BLOG_CATEGORIES = 600  # 10 minutos para categorías
CACHE_TTL_BLOG_POST_DETAIL = 600  # 10 minutos para detalle


class BlogService:
    """Servicio para gestionar blogs y categorías de blog."""

    def __init__(self, db: Session):
        self.db = db

    # =============================================================================
    # CACHE INVALIDATION METHODS
    # =============================================================================

    @staticmethod
    def invalidate_posts_cache():
        """Invalida todo el caché de posts del blog."""
        count = cache_service.invalidate_pattern_sync(f"{CACHE_PREFIX_BLOG_POSTS}:")
        logger.info(f"Cache de posts invalidado: {count} entradas eliminadas")
        return count

    @staticmethod
    def invalidate_categories_cache():
        """Invalida todo el caché de categorías del blog."""
        count = cache_service.invalidate_pattern_sync(f"{CACHE_PREFIX_BLOG_CATEGORIES}:")
        logger.info(f"Cache de categorías invalidado: {count} entradas eliminadas")
        return count

    @staticmethod
    def invalidate_all_blog_cache():
        """Invalida todo el caché del blog (posts y categorías)."""
        posts_count = BlogService.invalidate_posts_cache()
        categories_count = BlogService.invalidate_categories_cache()
        return posts_count + categories_count

    # =============================================================================
    # HELPER METHODS
    # =============================================================================

    @staticmethod
    def generate_slug_from_name(name: str) -> str:
        """Genera un slug válido a partir de un nombre."""
        # Convertir a minúsculas
        slug = name.lower()

        # Reemplazar caracteres especiales y espacios con guiones
        slug = re.sub(r"[àáâãäå]", "a", slug)
        slug = re.sub(r"[èéêë]", "e", slug)
        slug = re.sub(r"[ìíîï]", "i", slug)
        slug = re.sub(r"[òóôõö]", "o", slug)
        slug = re.sub(r"[ùúûü]", "u", slug)
        slug = re.sub(r"[ñ]", "n", slug)
        slug = re.sub(r"[ç]", "c", slug)

        # Remover caracteres no alfanuméricos excepto guiones y guiones bajos
        slug = re.sub(r"[^a-z0-9\-_]", "-", slug)

        # Reemplazar múltiples guiones con uno solo
        slug = re.sub(r"-+", "-", slug)

        # Remover guiones al inicio y final
        slug = slug.strip("-")

        # Si está vacío, usar un slug por defecto
        if not slug:
            slug = "categoria"

        return slug

    @staticmethod
    def _normalize_featured_image(value: str | None) -> str | None:
        """
        Guarda solo la ruta relativa para imágenes internas.
        - Si viene vacía, retorna None.
        - Si es una URL externa (http y no empieza con nuestro API_URL), se conserva.
        - Si empieza con API_URL, se recorta y se guarda solo desde la primera '/'.
        - Si ya es relativa, se deja igual (asegurando que arranque con '/').
        """
        if not value:
            return None

        trimmed = value.strip()
        if not trimmed:
            return None

        base_api = settings.app.API_URL.rstrip("/")

        # URL externa
        if trimmed.startswith("http") and not trimmed.startswith(base_api):
            return trimmed

        # Si arranca con el API_URL, recortar
        if trimmed.startswith(base_api):
            trimmed = trimmed[len(base_api) :]
            if not trimmed.startswith("/"):
                trimmed = "/" + trimmed

        # Si es relativa pero no empieza con '/', agregarlo
        if not trimmed.startswith("/"):
            trimmed = "/" + trimmed

        return trimmed

    def generate_unique_slug(self, base_slug: str, exclude_id: str | None = None) -> str:
        """Genera un slug único. Si ya existe, agrega un número incremental."""
        slug = base_slug
        counter = 1

        while True:
            query = self.db.query(BlogCategory).filter(
                BlogCategory.slug == slug,
                BlogCategory.deleted == False,  # Solo considerar categorías no eliminadas
            )

            # Si estamos actualizando, excluir el ID actual
            if exclude_id:
                query = query.filter(BlogCategory.id != exclude_id)

            existing = query.first()

            if not existing:
                return slug

            # Si existe, agregar un número
            slug = f"{base_slug}-{counter}"
            counter += 1

    # =============================================================================
    # BLOG CATEGORY METHODS
    # =============================================================================

    def create_category(self, category_data: BlogCategoryCreate) -> BlogCategory:
        """Crear una nueva categoría de blog. El slug se genera automáticamente desde el nombre."""
        # Generar slug desde el nombre
        base_slug = self.generate_slug_from_name(category_data.name)

        # Generar slug único
        unique_slug = self.generate_unique_slug(base_slug)

        # Crear la categoría con el slug generado
        category = BlogCategory(name=category_data.name, slug=unique_slug, description=category_data.description)

        self.db.add(category)
        self.db.commit()
        self.db.refresh(category)

        # Invalidar caché de categorías
        self.invalidate_categories_cache()

        logger.info(f"Categoría de blog creada: {category.name} (slug: {category.slug})")
        return category

    def get_category_by_id(self, category_id: str, include_deleted: bool = False) -> BlogCategory | None:
        """Obtener categoría por ID."""
        query = self.db.query(BlogCategory).filter(BlogCategory.id == category_id)
        if not include_deleted:
            query = query.filter(BlogCategory.deleted == False)
        return query.first()

    def get_category_by_slug(
        self, slug: str, include_deleted: bool = False, use_cache: bool = True
    ) -> BlogCategory | None:
        """Obtener categoría por slug (con caché opcional)."""
        # Intentar obtener del caché
        cache_key = None
        if use_cache and not include_deleted:
            cache_key = f"{CACHE_PREFIX_BLOG_CATEGORIES}:slug:{slug}"
            cached = cache_service.get_sync(cache_key)
            if cached is not None:
                return cached

        query = self.db.query(BlogCategory).filter(BlogCategory.slug == slug)
        if not include_deleted:
            query = query.filter(BlogCategory.deleted == False)
        category = query.first()

        # Guardar en caché
        if cache_key and category:
            cache_service.set_sync(cache_key, category, ttl=CACHE_TTL_BLOG_CATEGORIES)

        return category

    def get_all_categories(self, include_deleted: bool = False, use_cache: bool = True) -> list[BlogCategory]:
        """Obtener todas las categorías (optimizado con caché)."""
        # Intentar obtener del caché si está habilitado y no incluye eliminadas
        if use_cache and not include_deleted:
            cache_key = f"{CACHE_PREFIX_BLOG_CATEGORIES}:all"
            cached = cache_service.get_sync(cache_key)
            if cached is not None:
                logger.debug("Cache HIT para categorías del blog")
                return cached

        query = self.db.query(BlogCategory)
        if not include_deleted:
            query = query.filter(BlogCategory.deleted == False)
        # Ordenar usando índice para mejor rendimiento
        categories = query.order_by(BlogCategory.name).all()

        # Guardar en caché si aplica
        if use_cache and not include_deleted:
            cache_service.set_sync(cache_key, categories, ttl=CACHE_TTL_BLOG_CATEGORIES)
            logger.debug(f"Cache SET para categorías del blog ({len(categories)} items)")

        return categories

    def update_category(self, category_id: str, category_data: BlogCategoryUpdate) -> BlogCategory:
        """Actualizar una categoría. Si se actualiza el nombre, el slug se genera automáticamente."""
        category = self.get_category_by_id(category_id)
        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")

        # Actualizar campos
        update_data = category_data.model_dump(exclude_unset=True)

        # Si se actualiza el nombre, generar nuevo slug automáticamente
        if update_data.get("name"):
            new_name = update_data["name"]
            # Generar slug desde el nuevo nombre
            base_slug = self.generate_slug_from_name(new_name)
            # Generar slug único
            unique_slug = self.generate_unique_slug(base_slug, exclude_id=category_id)
            # Actualizar el slug
            category.slug = unique_slug
            category.name = new_name
            logger.info(f"Slug regenerado para categoría: {new_name} -> {unique_slug}")

        # Actualizar otros campos
        for field, value in update_data.items():
            if field != "name":  # El nombre ya se actualizó arriba
                setattr(category, field, value)

        self.db.commit()
        self.db.refresh(category)

        # Invalidar caché de categorías y posts (los posts muestran info de categoría)
        self.invalidate_all_blog_cache()

        logger.info(f"Categoría actualizada: {category.name} (slug: {category.slug})")
        return category

    def delete_category(self, category_id: str) -> bool:
        """Eliminar una categoría (soft delete)."""
        # Incluir eliminadas para poder verificar si existe
        category = self.get_category_by_id(category_id, include_deleted=True)
        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")

        # Verificar si ya está eliminada
        if category.deleted:
            logger.warning(f"Intento de eliminar categoría ya eliminada: {category.name}")
            return False

        # Verificar si hay posts asociados
        posts_count = self.db.query(BlogPost).filter(BlogPost.category_id == category_id).count()

        if posts_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se puede eliminar la categoría porque tiene {posts_count} post(s) asociado(s)",
            )

        # Soft delete: marcar como eliminada
        category.deleted = True
        self.db.commit()
        self.db.refresh(category)

        # Invalidar caché de categorías
        self.invalidate_categories_cache()

        logger.info(f"Categoría eliminada (soft delete): {category.name}")
        return True

    # =============================================================================
    # BLOG POST METHODS
    # =============================================================================

    def generate_unique_post_slug(self, base_slug: str, exclude_id: str | None = None) -> str:
        """Genera un slug único para posts. Si ya existe, agrega un número incremental."""
        slug = base_slug
        counter = 1

        while True:
            query = self.db.query(BlogPost).filter(BlogPost.slug == slug)

            if exclude_id:
                query = query.filter(BlogPost.id != exclude_id)

            existing = query.first()

            if not existing:
                return slug

            slug = f"{base_slug}-{counter}"
            counter += 1

    def create_post(self, post_data: BlogPostCreate, default_author_id: str) -> BlogPost:
        """Crear un nuevo post de blog. El slug se genera automáticamente desde el título."""
        # Generar slug desde el título
        base_slug = self.generate_slug_from_name(post_data.title)

        # Generar slug único
        unique_slug = self.generate_unique_post_slug(base_slug)

        # Verificar que la categoría existe y no está eliminada
        category = self.get_category_by_id(post_data.category_id, include_deleted=False)
        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")

        # Determinar el autor y el nombre del autor
        author_id = default_author_id  # Siempre guardar el ID del usuario autenticado como referencia
        author_name = None

        # Si se proporciona author_name, usarlo. Si no, usar el nombre del usuario autenticado
        if post_data.author_name:
            author_name = post_data.author_name
        else:
            # Obtener el nombre del usuario autenticado
            author = self.db.query(User).filter(User.id == default_author_id).first()
            if author:
                author_name = author.full_name

        # Si el estado es 'published', establecer published_at automáticamente
        published_at = None
        if post_data.status == "published":
            published_at = get_ve_now()

        normalized_featured = self._normalize_featured_image(post_data.featured_image_url)

        post = BlogPost(
            title=post_data.title,
            slug=unique_slug,
            content=post_data.content,
            category_id=post_data.category_id,
            featured_image_url=normalized_featured,
            status=post_data.status or "draft",
            published_at=published_at,
            author_id=author_id,
            author_name=author_name,
        )

        self.db.add(post)
        self.db.commit()
        self.db.refresh(post)

        # Invalidar caché de posts
        self.invalidate_posts_cache()

        logger.info(f"Post de blog creado: {post.title} (slug: {post.slug})")
        return post

    def get_post_by_id(
        self, post_id: str, include_relations: bool = True, include_deleted: bool = False
    ) -> BlogPost | None:
        """Obtener post por ID."""
        query = self.db.query(BlogPost)

        if include_relations:
            query = query.options(joinedload(BlogPost.author), joinedload(BlogPost.category))

        query = query.filter(BlogPost.id == post_id)

        # Filtrar eliminados si no se incluyen
        if not include_deleted:
            query = query.filter(BlogPost.deleted == False)

        return query.first()

    def get_post_by_slug(self, slug: str, include_relations: bool = True) -> BlogPost | None:
        """Obtener post por slug (solo no eliminados)."""
        query = self.db.query(BlogPost)

        if include_relations:
            query = query.options(joinedload(BlogPost.author), joinedload(BlogPost.category))

        return query.filter(BlogPost.slug == slug, BlogPost.deleted == False).first()

    def get_published_posts(
        self,
        page: int = 1,
        limit: int = 10,
        category_slug: str | None = None,
        search: str | None = None,
        use_cache: bool = True,
    ) -> tuple[list[BlogPost], int]:
        """Obtener posts publicados (para usuarios públicos) - Optimizado con caché y proyección."""
        # Intentar obtener del caché si no hay búsqueda (búsquedas no se cachean)
        cache_key = None
        if use_cache and not search:
            cache_key = cache_service._generate_key(
                CACHE_PREFIX_BLOG_POSTS, page=page, limit=limit, category=category_slug or ""
            )
            cached = cache_service.get_sync(cache_key)
            if cached is not None:
                logger.debug(f"Cache HIT para posts públicos: page={page}, limit={limit}")
                return cached

        # Crear query base para filtros (sin joinedload para count más rápido)
        base_query = self.db.query(BlogPost).filter(
            BlogPost.status == "published", BlogPost.published_at.isnot(None), BlogPost.deleted == False
        )

        # Filtrar por categoría si se especifica
        if category_slug:
            category = self.get_category_by_slug(category_slug, use_cache=False)
            if category:
                base_query = base_query.filter(BlogPost.category_id == category.id)

        # Buscar en título y contenido (optimizado)
        if search:
            search_pattern = f"%{search}%"
            # Para búsquedas, limitar la búsqueda en contenido a los primeros caracteres para mejor rendimiento
            base_query = base_query.filter(
                or_(
                    BlogPost.title.ilike(search_pattern),
                    func.substring(BlogPost.content, 1, 5000).ilike(search_pattern),  # Limitar búsqueda en contenido
                )
            )

        # OPTIMIZACIÓN: Contar usando subquery sin joinedloads (mucho más rápido)
        total = base_query.count()

        # Paginar primero para limitar la cantidad de datos
        offset = (page - 1) * limit

        # OPTIMIZACIÓN: Usar SQL directo para cargar solo preview del contenido
        # Esto evita cargar contenido de 50KB+ cuando solo necesitamos 500 chars
        post_ids_query = base_query.order_by(desc(BlogPost.published_at)).offset(offset).limit(limit)
        post_ids = [p.id for p in post_ids_query.with_entities(BlogPost.id).all()]

        if not post_ids:
            return [], total

        # Query optimizada con SQL para cargar solo preview del contenido
        posts_data = self.db.execute(
            text("""
                SELECT 
                    bp.id, bp.title, bp.slug,
                    SUBSTRING(bp.content, 1, 500) as content_preview,
                    bp.featured_image_url, bp.status, bp.published_at,
                    bp.created_at, bp.updated_at, bp.author_id, bp.author_name,
                    bp.category_id, bp.deleted,
                    u.id as author_user_id, u.email as author_email,
                    u.user_type as author_user_type, u.first_name as author_first_name,
                    u.last_name as author_last_name, u.company_name as author_company_name,
                    bc.id as category_id_full, bc.name as category_name,
                    bc.slug as category_slug, bc.description as category_description
                FROM blog_posts bp
                LEFT JOIN users u ON bp.author_id = u.id
                LEFT JOIN blog_categories bc ON bp.category_id = bc.id
                WHERE bp.id = ANY(:post_ids)
                ORDER BY bp.published_at DESC
            """),
            {"post_ids": post_ids},
        ).fetchall()

        # Mapear a objetos BlogPost
        posts = []
        for row in posts_data:
            post = BlogPost()
            post.id = row.id
            post.title = row.title
            post.slug = row.slug
            post.content = row.content_preview  # Solo preview
            post.featured_image_url = row.featured_image_url
            post.status = row.status
            post.published_at = row.published_at
            post.created_at = row.created_at
            post.updated_at = row.updated_at
            post.author_id = row.author_id
            post.author_name = row.author_name
            post.category_id = row.category_id
            post.deleted = row.deleted

            if row.author_user_id:
                author = User()
                author.id = row.author_user_id
                author.email = row.author_email
                author.user_type = row.author_user_type or "natural"
                author.first_name = row.author_first_name
                author.last_name = row.author_last_name
                author.company_name = row.author_company_name
                post.author = author

            if row.category_id_full:
                category = BlogCategory()
                category.id = row.category_id_full
                category.name = row.category_name
                category.slug = row.category_slug
                category.description = row.category_description
                post.category = category

            posts.append(post)

        # Guardar en caché si aplica (no cachear búsquedas)
        result = (posts, total)
        if cache_key:
            cache_service.set_sync(cache_key, result, ttl=CACHE_TTL_BLOG_POSTS)
            logger.debug(f"Cache SET para posts públicos: {len(posts)} items")

        return result

    def get_all_posts(
        self,
        page: int = 1,
        limit: int = 10,
        status_filter: str | None = None,
        category_id: str | None = None,
        search: str | None = None,
        include_deleted: bool = False,
        use_cache: bool = True,
    ) -> tuple[list[BlogPost], int]:
        """Obtener todos los posts (para admin) - Optimizado con SQL directo y caché."""
        # Intentar obtener del caché si no hay búsqueda y no incluye eliminados
        cache_key = None
        if use_cache and not search and not include_deleted:
            cache_key = cache_service._generate_key(
                f"{CACHE_PREFIX_BLOG_POSTS}:admin",
                page=page,
                limit=limit,
                status=status_filter or "",
                category=category_id or "",
            )
            cached = cache_service.get_sync(cache_key)
            if cached is not None:
                logger.debug(f"Cache HIT para posts admin: page={page}")
                return cached

        # Construir condiciones WHERE
        where_conditions = []
        params: dict[str, Any] = {}

        # Filtrar eliminados si no se incluyen
        if not include_deleted:
            where_conditions.append("bp.deleted = :deleted")
            params["deleted"] = False

        # Filtrar por estado (validado contra whitelist)
        if status_filter:
            _ALLOWED_STATUSES = {"draft", "published", "archived"}
            if status_filter not in _ALLOWED_STATUSES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Estado inválido: {status_filter}",
                )
            where_conditions.append("bp.status = :status_filter")
            params["status_filter"] = status_filter

        # Filtrar por categoría (UUID-like, validado por regex)
        if category_id:
            import re as _re

            if not _re.fullmatch(r"[0-9a-fA-F-]{8,64}", category_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="ID de categoría inválido",
                )
            where_conditions.append("bp.category_id = :category_id")
            params["category_id"] = category_id

        # Buscar en título y contenido (optimizado)
        if search:
            where_conditions.append("(bp.title ILIKE :search OR SUBSTRING(bp.content, 1, 5000) ILIKE :search)")
            params["search"] = f"%{search}%"

        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        # Sanitización defensiva: la where_clause se construye solo con literales
        # controlados arriba, pero validamos que no contenga caracteres peligrosos
        # por si en el futuro se agrega un parámetro controlado por el usuario.
        forbidden = [";", "--", "/*", "*/", "'", '"', "\\"]
        if any(token in where_clause for token in forbidden):
            raise ValueError("Invalid WHERE clause constructed (security check)")

        # Query para contar total (optimizado - solo cuenta IDs)
        count_query = text(f"""
            SELECT COUNT(*) as total
            FROM blog_posts bp
            WHERE {where_clause}
        """)

        result = self.db.execute(count_query, params)
        total = result.scalar() or 0

        # Query principal optimizada con JOINs - SIN cargar content completo
        # Solo cargamos los primeros 500 caracteres para el excerpt
        offset = (page - 1) * limit
        params["offset"] = offset
        params["limit"] = limit

        main_query = text(f"""
            SELECT
                bp.id,
                bp.title,
                bp.slug,
                SUBSTRING(bp.content, 1, 500) as content_preview,
                bp.featured_image_url,
                bp.status,
                bp.published_at,
                bp.created_at,
                bp.updated_at,
                bp.author_id,
                bp.author_name,
                bp.category_id,
                bp.deleted,
                -- Author info (solo campos necesarios para mejor rendimiento)
                u.id as author_user_id,
                u.email as author_email,
                u.user_type as author_user_type,
                u.first_name as author_first_name,
                u.last_name as author_last_name,
                u.company_name as author_company_name,
                -- Category info
                bc.id as category_id_full,
                bc.name as category_name,
                bc.slug as category_slug,
                bc.description as category_description
            FROM blog_posts bp
            LEFT JOIN users u ON bp.author_id = u.id
            LEFT JOIN blog_categories bc ON bp.category_id = bc.id
            WHERE {where_clause}
            ORDER BY bp.created_at DESC
            LIMIT :limit OFFSET :offset
        """)

        result = self.db.execute(main_query, params)
        rows = result.fetchall()

        # Mapear resultados a objetos BlogPost
        posts = []
        for row in rows:
            # Crear instancia de BlogPost
            post = BlogPost()
            post.id = row.id
            post.title = row.title
            post.slug = row.slug
            post.content = row.content_preview  # Solo preview, no contenido completo
            post.featured_image_url = row.featured_image_url
            post.status = row.status
            post.published_at = row.published_at
            post.created_at = row.created_at
            post.updated_at = row.updated_at
            post.author_id = row.author_id
            post.author_name = row.author_name
            post.category_id = row.category_id
            post.deleted = row.deleted

            # Crear objeto User simplificado si existe (solo campos necesarios)
            if row.author_user_id:
                author = User()
                author.id = row.author_user_id
                author.email = row.author_email
                author.user_type = row.author_user_type or "natural"
                author.first_name = row.author_first_name
                author.last_name = row.author_last_name
                author.company_name = row.author_company_name
                post.author = author

            # Crear objeto BlogCategory si existe
            if row.category_id_full:
                category = BlogCategory()
                category.id = row.category_id_full
                category.name = row.category_name
                category.slug = row.category_slug
                category.description = row.category_description
                post.category = category

            posts.append(post)

        # Guardar en caché si aplica
        result_tuple = (posts, total)
        if cache_key:
            cache_service.set_sync(cache_key, result_tuple, ttl=CACHE_TTL_BLOG_POSTS)
            logger.debug(f"Cache SET para posts admin: {len(posts)} items")

        return result_tuple

    def update_post(self, post_id: str, post_data: BlogPostUpdate) -> BlogPost:
        """Actualizar un post."""
        post = self.get_post_by_id(post_id, include_relations=False)
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post no encontrado")

        # Verificar si el nuevo slug ya existe (si se está cambiando)
        if post_data.slug and post_data.slug != post.slug:
            existing = self.db.query(BlogPost).filter(BlogPost.slug == post_data.slug, BlogPost.id != post_id).first()

            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=f"Ya existe un post con el slug '{post_data.slug}'"
                )

        # Verificar que la categoría existe y no está eliminada (si se está cambiando)
        if post_data.category_id and post_data.category_id != post.category_id:
            category = self.get_category_by_id(post_data.category_id, include_deleted=False)
            if not category:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")

        # Actualizar el nombre del autor si se proporciona
        if post_data.author_name is not None:
            # Si se proporciona un nuevo nombre, actualizarlo
            # El author_id se mantiene como referencia al usuario que hizo la modificación
            pass  # Se actualizará en el loop de update_data

        # Si el estado cambia a 'published' y no hay published_at, establecerlo
        if post_data.status == "published" and not post.published_at:
            post_data.published_at = get_ve_now()

        # Actualizar campos
        update_data = post_data.model_dump(exclude_unset=True)
        if "featured_image_url" in update_data:
            update_data["featured_image_url"] = self._normalize_featured_image(update_data["featured_image_url"])
        for field, value in update_data.items():
            setattr(post, field, value)

        self.db.commit()
        self.db.refresh(post)

        # Invalidar caché de posts
        self.invalidate_posts_cache()

        logger.info(f"Post actualizado: {post.title} ({post.slug})")
        return post

    def delete_post(self, post_id: str) -> bool:
        """Eliminar un post (soft delete)."""
        post = self.get_post_by_id(post_id, include_relations=False, include_deleted=True)
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post no encontrado")

        if post.deleted:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El post ya está eliminado")

        # Soft delete: marcar como eliminado
        post.deleted = True
        self.db.commit()
        self.db.refresh(post)

        # Invalidar caché de posts
        self.invalidate_posts_cache()

        logger.info(f"Post eliminado (soft delete): {post.title}")
        return True

    @staticmethod
    def generate_excerpt(content: str, max_length: int = 200) -> str:
        """Generar un extracto del contenido (optimizado para rendimiento)."""
        if not content:
            return ""

        # OPTIMIZACIÓN: Limitar el contenido a procesar (evitar procesar contenido muy largo)
        # Solo procesar los primeros caracteres necesarios + margen (reducido de 3x a 2x para mejor rendimiento)
        process_limit = max_length * 2 + 100  # Margen más pequeño
        content_to_process = content[:process_limit] if len(content) > process_limit else content

        # OPTIMIZACIÓN: Remover HTML tags básicos de manera más eficiente
        # Usar una expresión regular compilada sería mejor, pero para simplicidad usamos la básica
        text = re.sub(r"<[^>]+>", "", content_to_process, flags=re.IGNORECASE)

        # Remover espacios múltiples y caracteres de control
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) <= max_length:
            return text

        # Truncar en el último espacio antes del límite (más eficiente)
        truncated = text[:max_length].rsplit(" ", 1)[0]
        return truncated + "..."
