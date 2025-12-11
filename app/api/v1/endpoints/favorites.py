# from fastapi import APIRouter, Depends, HTTPException, status, Query
# from sqlalchemy.orm import Session
# from typing import List

# from app.config.database import get_db
# from app.core.dependencies import get_current_user
# from app.models.user import User
# from app.schemas.favorites import (
#     FavoriteAddRequest, 
#     FavoriteResponse, 
#     FavoriteListResponse,
#     FavoriteStatusResponse
# )
# from app.services.favorites_service import FavoritesService

# router = APIRouter(
#     prefix="/favorites",
#     tags=["favorites"],
#     dependencies=[Depends(get_current_user)]
# )

# @router.post("/add", response_model=FavoriteStatusResponse)
# async def add_to_favorites(
#     request: FavoriteAddRequest,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     ❤️ **Agregar producto a favoritos**
    
#     Agrega un producto específico a la lista de favoritos del usuario autenticado.
#     """
#     try:
#         favorite = FavoritesService.add_to_favorites(
#             db=db,
#             user_id=current_user.id,
#             product_id=request.product_id
#         )
        
#         return FavoriteStatusResponse(
#             is_favorite=True,
#             message="Producto agregado a favoritos exitosamente"
#         )
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Error interno del servidor"
#         )

# @router.delete("/remove/{product_id}", response_model=FavoriteStatusResponse)
# async def remove_from_favorites(
#     product_id: str,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     💔 **Quitar producto de favoritos**
    
#     Remueve un producto específico de la lista de favoritos del usuario autenticado.
#     """
#     try:
#         FavoritesService.remove_from_favorites(
#             db=db,
#             user_id=current_user.id,
#             product_id=product_id
#         )
        
#         return FavoriteStatusResponse(
#             is_favorite=False,
#             message="Producto removido de favoritos exitosamente"
#         )
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Error interno del servidor"
#         )

# @router.get("/", response_model=FavoriteListResponse)
# async def get_my_favorites(
#     skip: int = Query(0, ge=0, description="Número de elementos a omitir"),
#     limit: int = Query(20, ge=1, le=100, description="Número de elementos a retornar"),
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     📋 **Obtener mis favoritos**
    
#     Obtiene la lista de productos favoritos del usuario autenticado con paginación.
#     """
#     try:
#         favorites, total_count = FavoritesService.get_favorites_with_products(
#             db=db,
#             user_id=current_user.id,
#             skip=skip,
#             limit=limit
#         )
        
#         # Convertir a FavoriteResponse
#         favorite_responses = []
#         for favorite in favorites:
#             favorite_response = FavoriteResponse(
#                 id=favorite.id,
#                 user_id=favorite.user_id,
#                 product_id=favorite.product_id,
#                 created_at=favorite.created_at,
#                 product=favorite.product
#             )
#             favorite_responses.append(favorite_response)
        
#         return FavoriteListResponse(
#             favorites=favorite_responses,
#             total_count=total_count
#         )
        
#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Error interno del servidor"
#         )

# @router.get("/check/{product_id}", response_model=FavoriteStatusResponse)
# async def check_favorite_status(
#     product_id: str,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     🔍 **Verificar estado de favorito**
    
#     Verifica si un producto específico está en la lista de favoritos del usuario.
#     """
#     try:
#         is_favorite = FavoritesService.is_favorite(
#             db=db,
#             user_id=current_user.id,
#             product_id=product_id
#         )
        
#         return FavoriteStatusResponse(
#             is_favorite=is_favorite,
#             message="Producto en favoritos" if is_favorite else "Producto no está en favoritos"
#         )
        
#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Error interno del servidor"
#         )

# @router.get("/count", response_model=dict)
# async def get_favorites_count(
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     🔢 **Obtener contador de favoritos**
    
#     Obtiene el número total de productos en la lista de favoritos del usuario.
#     """
#     try:
#         count = FavoritesService.get_favorite_count(
#             db=db,
#             user_id=current_user.id
#         )
        
#         return {
#             "total_favorites": count,
#             "message": f"Tienes {count} productos en favoritos"
#         }
        
#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Error interno del servidor"
#         )

# @router.delete("/clear", response_model=dict)
# async def clear_all_favorites(
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     🗑️ **Limpiar todos los favoritos**
    
#     Remueve todos los productos de la lista de favoritos del usuario.
#     """
#     try:
#         deleted_count = FavoritesService.clear_user_favorites(
#             db=db,
#             user_id=current_user.id
#         )
        
#         return {
#             "deleted_count": deleted_count,
#             "message": f"Se eliminaron {deleted_count} productos de favoritos"
#         }
        
#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Error interno del servidor"
#         ) 