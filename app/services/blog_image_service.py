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

logger = get_logger("blog_images")
settings = Settings()

# Thread pool para operaciones de base de datos bloqueantes
# Aumentado a 10 workers para mejor rendimiento
_db_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="blog_image_db")

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
        
        logger.info(f"Imagen eliminada: {image_id} (post: {image.blog_post_id})")
        return True
    
    def _build_image_url(self, image_id: str) -> str:
        """Construye la URL para obtener la imagen."""
        return f"/api/v1/public/blog/images/{image_id}"

