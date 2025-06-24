from fastapi import APIRouter

from app.api.v1.endpoints import auth, admin, user, public, categories, brands

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
    prefix="/api/v1",
    tags=["📂 Categorías"],
)

# Marcas
api_router.include_router(
    brands.router,
    prefix="/api/v1",
    tags=["🏷️ Marcas"],
) 