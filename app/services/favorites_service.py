from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models.favorites import UserFavorite
from app.models.product import Product
from typing import List 
from fastapi import HTTPException, status

class FavoritesService:
    """Servicio para manejar operaciones de favoritos"""
    
    @staticmethod
    def add_to_favorites(db: Session, user_id: str, product_id: str) -> UserFavorite:
        """Agregar un producto a favoritos del usuario"""
        
        # Verificar que el producto existe
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Producto no encontrado"
            )
        
        # Verificar si ya está en favoritos
        existing_favorite = db.query(UserFavorite).filter(
            and_(
                UserFavorite.user_id == user_id,
                UserFavorite.product_id == product_id
            )
        ).first()
        
        if existing_favorite:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El producto ya está en tu lista de favoritos"
            )
        
        # Crear nuevo favorito
        new_favorite = UserFavorite(
            user_id=user_id,
            product_id=product_id
        )
        
        db.add(new_favorite)
        db.commit()
        db.refresh(new_favorite)
        
        return new_favorite
    
    @staticmethod
    def remove_from_favorites(db: Session, user_id: str, product_id: str) -> bool:
        """Quitar un producto de favoritos del usuario"""
        
        favorite = db.query(UserFavorite).filter(
            and_(
                UserFavorite.user_id == user_id,
                UserFavorite.product_id == product_id
            )
        ).first()
        
        if not favorite:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="El producto no está en tu lista de favoritos"
            )
        
        db.delete(favorite)
        db.commit()
        
        return True
    
    @staticmethod
    def get_user_favorites(
        db: Session, 
        user_id: str, 
        skip: int = 0, 
        limit: int = 20
    ) -> tuple[List[UserFavorite], int]:
        """Obtener lista de favoritos del usuario con paginación"""
        
        # Query base
        query = db.query(UserFavorite).filter(UserFavorite.user_id == user_id)
        
        # Contar total
        total_count = query.count()
        
        # Aplicar paginación y obtener resultados
        favorites = query.offset(skip).limit(limit).all()
        
        return favorites, total_count
    
    @staticmethod
    def is_favorite(db: Session, user_id: str, product_id: str) -> bool:
        """Verificar si un producto está en favoritos del usuario"""
        
        favorite = db.query(UserFavorite).filter(
            and_(
                UserFavorite.user_id == user_id,
                UserFavorite.product_id == product_id
            )
        ).first()
        
        return favorite is not None
    
    @staticmethod
    def get_favorite_count(db: Session, user_id: str) -> int:
        """Obtener el número total de favoritos del usuario"""
        
        return db.query(UserFavorite).filter(UserFavorite.user_id == user_id).count()
    
    @staticmethod
    def get_product_favorite_count(db: Session, product_id: str) -> int:
        """Obtener el número de usuarios que tienen este producto en favoritos"""
        
        return db.query(UserFavorite).filter(UserFavorite.product_id == product_id).count()
    
    @staticmethod
    def clear_user_favorites(db: Session, user_id: str) -> int:
        """Limpiar todos los favoritos de un usuario"""
        
        deleted_count = db.query(UserFavorite).filter(
            UserFavorite.user_id == user_id
        ).delete()
        
        db.commit()
        
        return deleted_count
    
    @staticmethod
    def get_favorites_with_products(
        db: Session, 
        user_id: str, 
        skip: int = 0, 
        limit: int = 20
    ) -> tuple[List[UserFavorite], int]:
        """Obtener favoritos con información completa del producto"""
        
        query = db.query(UserFavorite).filter(
            UserFavorite.user_id == user_id
        ).join(Product).filter(
            Product.in_stock == True  # Solo productos disponibles
        )
        
        total_count = query.count()
        
        favorites = query.offset(skip).limit(limit).all()
        
        return favorites, total_count 