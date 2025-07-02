from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from .product import ProductResponse

class FavoriteAddRequest(BaseModel):
    """Request para agregar un producto a favoritos"""
    product_id: str
    
class FavoriteResponse(BaseModel):
    """Response para un favorito"""
    id: str
    user_id: str
    product_id: str
    created_at: datetime
    product: Optional[ProductResponse] = None
    
    class Config:
        from_attributes = True
        
class FavoriteListResponse(BaseModel):
    """Response para lista de favoritos"""
    favorites: list[FavoriteResponse]
    total_count: int
    
class FavoriteStatusResponse(BaseModel):
    """Response para estado de favorito"""
    is_favorite: bool
    message: str 