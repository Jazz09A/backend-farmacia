"""
Modelo para imágenes de productos almacenadas en Cloudinary.

Esta tabla almacena las referencias a las imágenes de productos
que están alojadas en Cloudinary, relacionadas con los artículos
de Profit Plus mediante el código de artículo (co_art).
"""

from sqlalchemy import Boolean, Column, Integer, Text

from app.config.database import Base


class ProductImage(Base):
    """
    Modelo para almacenar referencias de imágenes de productos en Cloudinary.
    
    La relación con productos de Profit Plus se hace mediante co_art_profit,
    que corresponde al código del artículo en el sistema Profit Plus.
    
    NOTA: Esta tabla puede ya existir con columnas básicas (id, co_art_profit, 
    cloudinary_url, is_main). Los campos adicionales son opcionales y se 
    agregarán mediante migraciones si es necesario.
    """
    __tablename__ = "products_images"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Código del artículo en Profit Plus (relación con saArticulo)
    # Usando Text para compatibilidad con la tabla existente
    co_art_profit = Column(Text, nullable=False, index=True)
    
    # URL de la imagen en Cloudinary
    # Usando Text para compatibilidad con la tabla existente
    cloudinary_url = Column(Text, nullable=False)
    
    # Indica si es la imagen principal del producto
    is_main = Column(Boolean, default=False)
    
    # Campos opcionales (pueden no existir en la tabla actual)
    # Se pueden agregar mediante migración si es necesario
    
    # Public ID de Cloudinary (para operaciones como eliminar)
    # cloudinary_public_id = Column(String(255), nullable=True)
    
    # Orden de la imagen (para múltiples imágenes)
    # display_order = Column(Integer, default=0)
    
    # Descripción o alt text de la imagen
    # description = Column(String(255), nullable=True)
    
    # Timestamps
    # created_at = Column(DateTime, default=get_ve_now)
    # updated_at = Column(DateTime, default=get_ve_now, onupdate=get_ve_now)
    
    # Usuario que subió la imagen
    # created_by = Column(String(100), nullable=True)
    
    def __repr__(self):
        return f"<ProductImage(id={self.id}, co_art={self.co_art_profit}, is_main={self.is_main})>"
