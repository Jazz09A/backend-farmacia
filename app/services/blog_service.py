from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, asc, or_, func
from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from app.models.blog import BlogPost, BlogCategory
from app.models.user import User
from app.schemas.blog import (
    BlogPostCreate, BlogPostUpdate, BlogCategoryCreate, BlogCategoryUpdate
)
from app.config.logging_config import get_logger
from app.utils.timezone import get_ve_now
import re

logger = get_logger("blog")


class BlogService:
    """Servicio para gestionar blogs y categorías de blog."""
    
    def __init__(self, db: Session):
        self.db = db
    
    # =============================================================================
    # HELPER METHODS
    # =============================================================================
    
    @staticmethod
    def generate_slug_from_name(name: str) -> str:
        """Genera un slug válido a partir de un nombre."""
        # Convertir a minúsculas
        slug = name.lower()
        
        # Reemplazar caracteres especiales y espacios con guiones
        slug = re.sub(r'[àáâãäå]', 'a', slug)
        slug = re.sub(r'[èéêë]', 'e', slug)
        slug = re.sub(r'[ìíîï]', 'i', slug)
        slug = re.sub(r'[òóôõö]', 'o', slug)
        slug = re.sub(r'[ùúûü]', 'u', slug)
        slug = re.sub(r'[ñ]', 'n', slug)
        slug = re.sub(r'[ç]', 'c', slug)
        
        # Remover caracteres no alfanuméricos excepto guiones y guiones bajos
        slug = re.sub(r'[^a-z0-9\-_]', '-', slug)
        
        # Reemplazar múltiples guiones con uno solo
        slug = re.sub(r'-+', '-', slug)
        
        # Remover guiones al inicio y final
        slug = slug.strip('-')
        
        # Si está vacío, usar un slug por defecto
        if not slug:
            slug = 'categoria'
        
        return slug
    
    def generate_unique_slug(self, base_slug: str, exclude_id: Optional[str] = None) -> str:
        """Genera un slug único. Si ya existe, agrega un número incremental."""
        slug = base_slug
        counter = 1
        
        while True:
            query = self.db.query(BlogCategory).filter(
                BlogCategory.slug == slug,
                BlogCategory.deleted == False  # Solo considerar categorías no eliminadas
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
        category = BlogCategory(
            name=category_data.name,
            slug=unique_slug,
            description=category_data.description
        )
        
        self.db.add(category)
        self.db.commit()
        self.db.refresh(category)
        
        logger.info(f"Categoría de blog creada: {category.name} (slug: {category.slug})")
        return category
    
    def get_category_by_id(self, category_id: str, include_deleted: bool = False) -> Optional[BlogCategory]:
        """Obtener categoría por ID."""
        query = self.db.query(BlogCategory).filter(BlogCategory.id == category_id)
        if not include_deleted:
            query = query.filter(BlogCategory.deleted == False)
        return query.first()
    
    def get_category_by_slug(self, slug: str, include_deleted: bool = False) -> Optional[BlogCategory]:
        """Obtener categoría por slug."""
        query = self.db.query(BlogCategory).filter(BlogCategory.slug == slug)
        if not include_deleted:
            query = query.filter(BlogCategory.deleted == False)
        return query.first()
    
    def get_all_categories(self, include_deleted: bool = False) -> List[BlogCategory]:
        """Obtener todas las categorías."""
        query = self.db.query(BlogCategory)
        if not include_deleted:
            query = query.filter(BlogCategory.deleted == False)
        return query.order_by(BlogCategory.name).all()
    
    def update_category(self, category_id: str, category_data: BlogCategoryUpdate) -> BlogCategory:
        """Actualizar una categoría. Si se actualiza el nombre, el slug se genera automáticamente."""
        category = self.get_category_by_id(category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoría no encontrada"
            )
        
        # Actualizar campos
        update_data = category_data.model_dump(exclude_unset=True)
        
        # Si se actualiza el nombre, generar nuevo slug automáticamente
        if 'name' in update_data and update_data['name']:
            new_name = update_data['name']
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
            if field != 'name':  # El nombre ya se actualizó arriba
                setattr(category, field, value)
        
        self.db.commit()
        self.db.refresh(category)
        
        logger.info(f"Categoría actualizada: {category.name} (slug: {category.slug})")
        return category
    
    def delete_category(self, category_id: str) -> bool:
        """Eliminar una categoría (soft delete)."""
        # Incluir eliminadas para poder verificar si existe
        category = self.get_category_by_id(category_id, include_deleted=True)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoría no encontrada"
            )
        
        # Verificar si ya está eliminada
        if category.deleted:
            logger.warning(f"Intento de eliminar categoría ya eliminada: {category.name}")
            return False
        
        # Verificar si hay posts asociados
        posts_count = self.db.query(BlogPost).filter(
            BlogPost.category_id == category_id
        ).count()
        
        if posts_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se puede eliminar la categoría porque tiene {posts_count} post(s) asociado(s)"
            )
        
        # Soft delete: marcar como eliminada
        category.deleted = True
        self.db.commit()
        self.db.refresh(category)
        
        logger.info(f"Categoría eliminada (soft delete): {category.name}")
        return True
    
    # =============================================================================
    # BLOG POST METHODS
    # =============================================================================
    
    def generate_unique_post_slug(self, base_slug: str, exclude_id: Optional[str] = None) -> str:
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoría no encontrada"
            )
        
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
        if post_data.status == 'published':
            published_at = get_ve_now()
        
        post = BlogPost(
            title=post_data.title,
            slug=unique_slug,
            content=post_data.content,
            category_id=post_data.category_id,
            featured_image_url=post_data.featured_image_url,
            status=post_data.status or 'draft',
            published_at=published_at,
            author_id=author_id,
            author_name=author_name
        )
        
        self.db.add(post)
        self.db.commit()
        self.db.refresh(post)
        
        logger.info(f"Post de blog creado: {post.title} (slug: {post.slug})")
        return post
    
    def get_post_by_id(self, post_id: str, include_relations: bool = True, include_deleted: bool = False) -> Optional[BlogPost]:
        """Obtener post por ID."""
        query = self.db.query(BlogPost)
        
        if include_relations:
            query = query.options(
                joinedload(BlogPost.author),
                joinedload(BlogPost.category)
            )
        
        query = query.filter(BlogPost.id == post_id)
        
        # Filtrar eliminados si no se incluyen
        if not include_deleted:
            query = query.filter(BlogPost.deleted == False)
        
        return query.first()
    
    def get_post_by_slug(self, slug: str, include_relations: bool = True) -> Optional[BlogPost]:
        """Obtener post por slug (solo no eliminados)."""
        query = self.db.query(BlogPost)
        
        if include_relations:
            query = query.options(
                joinedload(BlogPost.author),
                joinedload(BlogPost.category)
            )
        
        return query.filter(
            BlogPost.slug == slug,
            BlogPost.deleted == False
        ).first()
    
    def get_published_posts(
        self,
        page: int = 1,
        limit: int = 10,
        category_slug: Optional[str] = None,
        search: Optional[str] = None
    ) -> Tuple[List[BlogPost], int]:
        """Obtener posts publicados (para usuarios públicos)."""
        query = self.db.query(BlogPost).options(
            joinedload(BlogPost.author),
            joinedload(BlogPost.category)
        ).filter(
            BlogPost.status == 'published',
            BlogPost.published_at.isnot(None),
            BlogPost.deleted == False
        )
        
        # Filtrar por categoría si se especifica
        if category_slug:
            category = self.get_category_by_slug(category_slug)
            if category:
                query = query.filter(BlogPost.category_id == category.id)
        
        # Buscar en título y contenido
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    BlogPost.title.ilike(search_pattern),
                    BlogPost.content.ilike(search_pattern)
                )
            )
        
        # Ordenar por fecha de publicación (más recientes primero)
        query = query.order_by(desc(BlogPost.published_at))
        
        # Contar total
        total = query.count()
        
        # Paginar
        offset = (page - 1) * limit
        posts = query.offset(offset).limit(limit).all()
        
        return posts, total
    
    def get_all_posts(
        self,
        page: int = 1,
        limit: int = 10,
        status_filter: Optional[str] = None,
        category_id: Optional[str] = None,
        search: Optional[str] = None,
        include_deleted: bool = False
    ) -> Tuple[List[BlogPost], int]:
        """Obtener todos los posts (para admin)."""
        query = self.db.query(BlogPost).options(
            joinedload(BlogPost.author),
            joinedload(BlogPost.category)
        )
        
        # Filtrar eliminados si no se incluyen
        if not include_deleted:
            query = query.filter(BlogPost.deleted == False)
        
        # Filtrar por estado
        if status_filter:
            query = query.filter(BlogPost.status == status_filter)
        
        # Filtrar por categoría
        if category_id:
            query = query.filter(BlogPost.category_id == category_id)
        
        # Buscar en título y contenido
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    BlogPost.title.ilike(search_pattern),
                    BlogPost.content.ilike(search_pattern)
                )
            )
        
        # Ordenar por fecha de creación (más recientes primero)
        query = query.order_by(desc(BlogPost.created_at))
        
        # Contar total
        total = query.count()
        
        # Paginar
        offset = (page - 1) * limit
        posts = query.offset(offset).limit(limit).all()
        
        return posts, total
    
    def update_post(self, post_id: str, post_data: BlogPostUpdate) -> BlogPost:
        """Actualizar un post."""
        post = self.get_post_by_id(post_id, include_relations=False)
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Post no encontrado"
            )
        
        # Verificar si el nuevo slug ya existe (si se está cambiando)
        if post_data.slug and post_data.slug != post.slug:
            existing = self.db.query(BlogPost).filter(
                BlogPost.slug == post_data.slug,
                BlogPost.id != post_id
            ).first()
            
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Ya existe un post con el slug '{post_data.slug}'"
                )
        
        # Verificar que la categoría existe y no está eliminada (si se está cambiando)
        if post_data.category_id and post_data.category_id != post.category_id:
            category = self.get_category_by_id(post_data.category_id, include_deleted=False)
            if not category:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Categoría no encontrada"
                )
        
        # Actualizar el nombre del autor si se proporciona
        if post_data.author_name is not None:
            # Si se proporciona un nuevo nombre, actualizarlo
            # El author_id se mantiene como referencia al usuario que hizo la modificación
            pass  # Se actualizará en el loop de update_data
        
        # Si el estado cambia a 'published' y no hay published_at, establecerlo
        if post_data.status == 'published' and not post.published_at:
            post_data.published_at = get_ve_now()
        
        # Actualizar campos
        update_data = post_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(post, field, value)
        
        self.db.commit()
        self.db.refresh(post)
        
        logger.info(f"Post actualizado: {post.title} ({post.slug})")
        return post
    
    def delete_post(self, post_id: str) -> bool:
        """Eliminar un post (soft delete)."""
        post = self.get_post_by_id(post_id, include_relations=False, include_deleted=True)
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Post no encontrado"
            )
        
        if post.deleted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El post ya está eliminado"
            )
        
        # Soft delete: marcar como eliminado
        post.deleted = True
        self.db.commit()
        self.db.refresh(post)
        
        logger.info(f"Post eliminado (soft delete): {post.title}")
        return True
    
    @staticmethod
    def generate_excerpt(content: str, max_length: int = 200) -> str:
        """Generar un extracto del contenido."""
        # Remover HTML tags básicos
        text = re.sub(r'<[^>]+>', '', content)
        # Remover espacios múltiples
        text = re.sub(r'\s+', ' ', text).strip()
        
        if len(text) <= max_length:
            return text
        
        # Truncar en el último espacio antes del límite
        truncated = text[:max_length].rsplit(' ', 1)[0]
        return truncated + '...'

