from fastapi import APIRouter

from app.api.v1.endpoints import auth, admin, user, public, categories, brands, favorites, shipping

api_router = APIRouter()

# =============================================================================
# 🔓 RUTAS PÚBLICAS (Sin Autenticación)
# =============================================================================

# Información general y catálogo
api_router.include_router(
    public.router,
    tags=["🔓 Público"],
)

# Autenticación
api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["🔓 Autenticación"],
)

# =============================================================================
# 🔐 RUTAS AUTENTICADAS (Usuario Logueado)
# =============================================================================

# Funciones de usuario autenticado
api_router.include_router(
    user.router,
    tags=["🔐 Usuario Autenticado"],
)

# Lista de favoritos
api_router.include_router(
    favorites.router,
    prefix="/favorites",
    tags=["❤️ Favoritos"],
)

# =============================================================================
# 👑 RUTAS DE ADMINISTRADOR
# =============================================================================

# Panel de administración
api_router.include_router(
    admin.router,
    tags=["👑 Administrador"],
)

# =============================================================================
# 🛍️ RUTAS DE CATÁLOGO
# =============================================================================

# Categorías
api_router.include_router(
    categories.router,
    prefix="/categories",
    tags=["📂 Categorías"],
)

# Marcas
api_router.include_router(
    brands.router,
    prefix="/brands",
    tags=["🏷️ Marcas"],
)

# Zonas de Envío
api_router.include_router(
    shipping.router,
    tags=["🚚 Zonas de Envío"],
) 