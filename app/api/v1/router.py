from fastapi import APIRouter

from app.api.v1.endpoints import auth

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Autenticación"],
)

# Note: We'll add more routers as we create them
# api_router.include_router(
#     products.router,
#     prefix="/products",
#     tags=["Productos"],
# )

# api_router.include_router(
#     cart.router,
#     prefix="/cart",
#     tags=["Carrito"],
# )

# api_router.include_router(
#     orders.router,
#     prefix="/orders",
#     tags=["Pedidos"],
# )

# api_router.include_router(
#     users.router,
#     prefix="/users",
#     tags=["Usuarios"],
# )

# api_router.include_router(
#     reviews.router,
#     prefix="/reviews",
#     tags=["Reseñas"],
# ) 