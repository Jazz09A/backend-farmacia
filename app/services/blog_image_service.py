from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional, Dict, Tuple
from fastapi import HTTPException, status
from app.models.blog import BlogPost, BlogImage
from app.config.logging_config import get_logger
from app.config.settings import Settings
from app.config.database import SessionLocal
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
import io
import time
from threading import RLock

logger = get_logger("blog_images")
settings = Settings()

# Thread pool para operaciones de base de datos bloqueantes
# Aumentado a 10 workers para mejor rendimiento
_db_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="blog_image_db")

# =============================================================================
# CACHÉ DE IMÁGENES EN MEMORIA
# =============================================================================

class ImageCache:
    """
    Caché en memoria para imágenes del blog.
    Optimizado para servir imágenes rápidamente sin acceder a la BD.
    """
    
    def __init__(self, max_size_mb: int = 100, ttl_seconds: int = 3600):
        self._cache: Dict[str, Tuple[bytes, str, float]] = {}  # id -> (data, content_type, timestamp)
        self._lock = RLock()
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._current_size = 0
        self._ttl = ttl_seconds
        self._hits = 0
        self._misses = 0
    
    def get(self, image_id: str) -> Optional[Tuple[bytes, str]]:
        """Obtiene imagen del caché. Retorna (data, content_type) o None."""
        with self._lock:
            if image_id in self._cache:
                data, content_type, timestamp = self._cache[image_id]
                # Verificar TTL
                if time.time() - timestamp < self._ttl:
                    self._hits += 1
                    return (data, content_type)
                else:
                    # Expirado, eliminar
                    self._remove(image_id)
            self._misses += 1
            return None
    
    def set(self, image_id: str, data: bytes, content_type: str) -> bool:
        """Guarda imagen en caché. Retorna True si se guardó."""
        # No cachear imágenes muy grandes (> 2MB)
        if len(data) > 2 * 1024 * 1024:
            return False
        
        with self._lock:
            # Hacer espacio si es necesario
            while self._current_size + len(data) > self._max_size_bytes and self._cache:
                # Eliminar la más antigua
                oldest_id = min(self._cache.keys(), key=lambda k: self._cache[k][2])
                self._remove(oldest_id)
            
            # Si después de limpiar aún no hay espacio, no cachear
            if self._current_size + len(data) > self._max_size_bytes:
                return False
            
            # Si ya existe, actualizar
            if image_id in self._cache:
                self._remove(image_id)
            
            self._cache[image_id] = (data, content_type, time.time())
            self._current_size += len(data)
            return True
    
    def _remove(self, image_id: str):
        """Elimina una imagen del caché (interno, sin lock)."""
        if image_id in self._cache:
            data, _, _ = self._cache.pop(image_id)
            self._current_size -= len(data)
    
    def invalidate(self, image_id: str):
        """Invalida una imagen específica del caché."""
        with self._lock:
            self._remove(image_id)
    
    def clear(self):
        """Limpia todo el caché."""
        with self._lock:
            self._cache.clear()
            self._current_size = 0
    
    def get_stats(self) -> Dict:
        """Obtiene estadísticas del caché."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._cache),
                "size_mb": round(self._current_size / (1024 * 1024), 2),
                "max_size_mb": self._max_size_bytes // (1024 * 1024),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total * 100, 2) if total > 0 else 0
            }

# Instancia global del caché de imágenes (100MB máx, 1 hora TTL)
_image_cache = ImageCache(max_size_mb=100, ttl_seconds=3600)

# Intentar importar Pillow para optimización de imágenes (opcional)
try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    logger.warning("Pillow no está disponible. La optimización de imágenes estará deshabilitada.")


class BlogImageService:
    """Servicio para gestionar imágenes de blog posts."""
    
    def __init__(self, db: Session):
        self.db = db
    
    @staticmethod
    def _validate_image_format(image_bytes: bytes) -> Tuple[str, str]:
        """
        Valida el formato de imagen sin leer todo el archivo.
        Retorna (formato, content_type)
        """
        # Leer solo los primeros bytes para validar formato
        if len(image_bytes) < 12:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archivo de imagen inválido o corrupto"
            )
        
        # Verificar magic numbers
        if image_bytes[:2] == b'\xff\xd8':
            return ('JPEG', 'image/jpeg')
        elif image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            return ('PNG', 'image/png')
        elif image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
            return ('WEBP', 'image/webp')
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Formato de imagen no soportado. Usa JPEG, PNG o WEBP."
            )
    
    @staticmethod
    def _optimize_image(image_bytes: bytes, max_size: int = 1920) -> bytes:
        """
        Optimiza una imagen reduciendo su tamaño si es necesario.
        Mantiene la calidad pero reduce dimensiones y comprime.
        """
        if not PILLOW_AVAILABLE:
            return image_bytes
        
        try:
            # Abrir imagen desde bytes
            img = Image.open(io.BytesIO(image_bytes))
            original_format = img.format
            
            # Si la imagen es muy grande, redimensionarla
            if img.width > max_size or img.height > max_size:
                # Calcular nuevas dimensiones manteniendo aspect ratio
                ratio = min(max_size / img.width, max_size / img.height)
                new_width = int(img.width * ratio)
                new_height = int(img.height * ratio)
                
                # Redimensionar con alta calidad
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logger.info(f"Imagen redimensionada de {img.width}x{img.height} a {new_width}x{new_height}")
            
            # Convertir a RGB si es necesario (para JPEG)
            if original_format == 'JPEG' and img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Guardar optimizada en bytes
            output = io.BytesIO()
            
            # Determinar formato y calidad
            if original_format == 'PNG':
                img.save(output, format='PNG', optimize=True)
            elif original_format == 'WEBP':
                img.save(output, format='WEBP', quality=85, method=6)
            else:  # JPEG
                img.save(output, format='JPEG', quality=85, optimize=True)
            
            optimized_bytes = output.getvalue()
            
            # Si la imagen optimizada es más grande que la original, usar la original
            if len(optimized_bytes) > len(image_bytes):
                logger.info("Imagen optimizada es más grande, usando original")
                return image_bytes
            
            logger.info(f"Imagen optimizada: {len(image_bytes)} -> {len(optimized_bytes)} bytes")
            return optimized_bytes
            
        except Exception as e:
            logger.warning(f"Error optimizando imagen, usando original: {e}")
            return image_bytes
    
    def _generate_image_code(self, blog_post_id: str) -> str:
        """Genera un código único de imagen para un post (IMG001, IMG002, etc.)."""
        # Obtener el último código de imagen para este post
        last_image = self.db.query(BlogImage).filter(
            BlogImage.blog_post_id == blog_post_id
        ).order_by(desc(BlogImage.image_code)).first()
        
        if not last_image:
            return "IMG001"
        
        # Extraer el número del último código
        match = re.match(r'IMG(\d+)', last_image.image_code)
        if match:
            next_num = int(match.group(1)) + 1
            return f"IMG{next_num:03d}"
        
        # Si el formato no es el esperado, empezar desde 001
        return "IMG001"
    
    def _validate_image_code(self, blog_post_id: str, image_code: str) -> bool:
        """Valida que el código de imagen sea único para el post."""
        existing = self.db.query(BlogImage).filter(
            BlogImage.blog_post_id == blog_post_id,
            BlogImage.image_code == image_code
        ).first()
        
        return existing is None
    
    @staticmethod
    def _upload_image_sync(
        blog_post_id: str,
        image_bytes: bytes,
        description: Optional[str] = None,
        image_code: Optional[str] = None,
        created_by: Optional[str] = None,
        optimize: bool = True
    ) -> BlogImage:
        """
        Método síncrono interno para subir imagen (ejecutado en thread pool).
        Crea su propia sesión de base de datos para ser thread-safe.
        """
        # Crear una nueva sesión de base de datos para este thread
        db = SessionLocal()
        try:
            # Validar formato de imagen (validación temprana)
            BlogImageService._validate_image_format(image_bytes)
            
            # Verificar que el post existe
            post = db.query(BlogPost).filter(BlogPost.id == blog_post_id).first()
            if not post:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Post de blog no encontrado"
                )
            
            # Validar que hay datos de imagen
            if not image_bytes or len(image_bytes) == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El archivo de imagen está vacío"
                )
            
            # Validar tamaño máximo (6 MB)
            MAX_SIZE = 6 * 1024 * 1024  # 6 MB
            if len(image_bytes) > MAX_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El archivo excede el tamaño máximo permitido (6 MB)"
                )
            
            # Optimizar imagen si está habilitado
            if optimize:
                image_bytes = BlogImageService._optimize_image(image_bytes)
            
            # Generar o validar código de imagen
            if image_code:
                # Validar formato
                if not re.match(r'^[A-Z0-9]{1,10}$', image_code):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="El código de imagen debe contener solo letras mayúsculas y números (máx. 10 caracteres)"
                    )
                
                # Validar que sea único
                existing = db.query(BlogImage).filter(
                    BlogImage.blog_post_id == blog_post_id,
                    BlogImage.image_code == image_code
                ).first()
                if existing:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Ya existe una imagen con el código '{image_code}' para este post"
                    )
            else:
                # Generar código automáticamente
                last_image = db.query(BlogImage).filter(
                    BlogImage.blog_post_id == blog_post_id
                ).order_by(desc(BlogImage.image_code)).first()
                
                if not last_image:
                    image_code = "IMG001"
                else:
                    match = re.match(r'IMG(\d+)', last_image.image_code)
                    if match:
                        next_num = int(match.group(1)) + 1
                        image_code = f"IMG{next_num:03d}"
                    else:
                        image_code = "IMG001"
            
            # Crear la imagen
            blog_image = BlogImage(
                blog_post_id=blog_post_id,
                image_data=image_bytes,
                image_code=image_code,
                description=description,
                created_by=created_by
            )
            
            db.add(blog_image)
            db.commit()
            db.refresh(blog_image)
            
            logger.info(f"Imagen subida para post {blog_post_id}: {image_code} ({len(image_bytes)} bytes)")
            return blog_image
        finally:
            db.close()
    
    async def upload_image(
        self,
        blog_post_id: str,
        image_bytes: bytes,
        description: Optional[str] = None,
        image_code: Optional[str] = None,
        created_by: Optional[str] = None,
        optimize: bool = True
    ) -> BlogImage:
        """
        Sube una imagen para un blog post de forma asíncrona.
        
        Las operaciones de base de datos se ejecutan en un thread pool
        para no bloquear el event loop de asyncio.
        """
        # Ejecutar la operación de base de datos en un thread pool
        loop = asyncio.get_event_loop()
        blog_image = await loop.run_in_executor(
            _db_executor,
            BlogImageService._upload_image_sync,
            blog_post_id,
            image_bytes,
            description,
            image_code,
            created_by,
            optimize
        )
        return blog_image
    
    def get_image_by_id(self, image_id: str) -> Optional[BlogImage]:
        """Obtiene una imagen por su ID."""
        return self.db.query(BlogImage).filter(BlogImage.id == image_id).first()
    
    @staticmethod
    def _detect_content_type(image_data: bytes) -> str:
        """Detecta el content-type de una imagen basándose en sus bytes."""
        if len(image_data) < 12:
            return "image/jpeg"
        
        if image_data[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"
        elif image_data[:2] == b'\xff\xd8':
            return "image/jpeg"
        elif image_data[:4] == b'RIFF' and image_data[8:12] == b'WEBP':
            return "image/webp"
        elif image_data[:4] == b'GIF8':
            return "image/gif"
        return "image/jpeg"
    
    @staticmethod
    def _get_image_from_db_sync(image_id: str) -> Optional[Tuple[bytes, str]]:
        """
        Obtiene imagen de la BD de forma síncrona (para ejecutar en thread pool).
        Retorna (image_data, content_type) o None.
        """
        db = SessionLocal()
        try:
            image = db.query(BlogImage).filter(BlogImage.id == image_id).first()
            if not image:
                return None
            
            content_type = BlogImageService._detect_content_type(image.image_data)
            return (image.image_data, content_type)
        finally:
            db.close()
    
    @staticmethod
    async def get_image_data_async(image_id: str) -> Optional[Tuple[bytes, str]]:
        """
        Obtiene los datos de una imagen de forma asíncrona.
        Usa caché en memoria para respuestas rápidas.
        Retorna (image_data, content_type) o None.
        """
        # 1. Intentar obtener del caché (muy rápido)
        cached = _image_cache.get(image_id)
        if cached is not None:
            logger.debug(f"Image cache HIT: {image_id}")
            return cached
        
        # 2. Obtener de BD en thread pool (no bloquea el event loop)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _db_executor,
            BlogImageService._get_image_from_db_sync,
            image_id
        )
        
        if result is None:
            return None
        
        image_data, content_type = result
        
        # 3. Guardar en caché para próximas requests
        _image_cache.set(image_id, image_data, content_type)
        logger.debug(f"Image cache SET: {image_id} ({len(image_data)} bytes)")
        
        return result
    
    @staticmethod
    def invalidate_image_cache(image_id: str):
        """Invalida una imagen del caché."""
        _image_cache.invalidate(image_id)
        logger.debug(f"Image cache invalidated: {image_id}")
    
    @staticmethod
    def get_image_cache_stats() -> Dict:
        """Obtiene estadísticas del caché de imágenes."""
        return _image_cache.get_stats()
    
    def get_image_by_code(self, blog_post_id: str, image_code: str) -> Optional[BlogImage]:
        """Obtiene una imagen por su código y post ID."""
        return self.db.query(BlogImage).filter(
            BlogImage.blog_post_id == blog_post_id,
            BlogImage.image_code == image_code
        ).first()
    
    def get_images_by_post(self, blog_post_id: str) -> List[BlogImage]:
        """Obtiene todas las imágenes de un post."""
        return self.db.query(BlogImage).filter(
            BlogImage.blog_post_id == blog_post_id
        ).order_by(BlogImage.image_code).all()
    
    @staticmethod
    def get_images_by_posts_batch(db: Session, post_ids: List[str]) -> Dict[str, List[BlogImage]]:
        """
        Obtiene todas las imágenes de múltiples posts en una sola query.
        Retorna un diccionario: post_id -> [imágenes]
        """
        if not post_ids:
            return {}
        
        images = db.query(BlogImage).filter(
            BlogImage.blog_post_id.in_(post_ids)
        ).order_by(BlogImage.blog_post_id, BlogImage.image_code).all()
        
        result = {}
        for img in images:
            if img.blog_post_id not in result:
                result[img.blog_post_id] = []
            result[img.blog_post_id].append(img)
        
        return result
    
    def delete_image(self, image_id: str) -> bool:
        """Elimina una imagen."""
        image = self.get_image_by_id(image_id)
        if not image:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Imagen no encontrada"
            )
        
        self.db.delete(image)
        self.db.commit()
        
        # Invalidar caché de la imagen eliminada
        self.invalidate_image_cache(image_id)
        
        logger.info(f"Imagen eliminada: {image_id} (post: {image.blog_post_id})")
        return True
    
    def _build_image_url(self, image_id: str) -> str:
        """Construye la URL para obtener la imagen."""
        return f"/api/v1/public/blog/images/{image_id}"

