from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    article_discounts,
    articles,
    auth,
    blog_admin,
    dashboard,
    exchange_rate,
    flash_offers,
    public,
    quotes,
    user,
)

# Nota FE Fase 1 (aprobada): el frontend no montará crédito ni llamará APIs
# legacy de orders/quantity-discounts/addresses; flujo comercial = cotizaciones.
# No reactivar routers de crédito solo por código BE existente sin acuerdo FE/BE.
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



# Órdenes del usuario


# Cotizaciones - creación desde checkout
api_router.include_router(
    quotes.router,
    prefix="/quotes",
    tags=["📝 Cotizaciones"],
)

# Cotizaciones - vistas del usuario autenticado
api_router.include_router(
    quotes.user_quotes_router,
    prefix="/user/quotes",
    tags=["📝 Cotizaciones"],
)

# Artículos (Profit Plus) - Requiere autenticación
api_router.include_router(
    articles.router,
    prefix="/articles",
    tags=["📦 Artículos (Profit Plus)"],
)

# =============================================================================
# 👑 RUTAS DE ADMINISTRADOR
# =============================================================================

# Panel de administración
api_router.include_router(
    admin.router,
    tags=["👑 Administrador"],
)

# Panel de dashboard
api_router.include_router(
    dashboard.router,
    prefix="/admin",
    tags=["📊 Dashboard"],
)


# Flash Offers
api_router.include_router(
    flash_offers.router,
    prefix="/admin",
    tags=["⚡ Flash Offers"],
)

# Article Discounts (Profit Plus Native)
api_router.include_router(
    article_discounts.router,
    prefix="/admin/article-discounts",
    tags=["🏷️ Descuentos por Artículo (Profit Plus)"],
)

# Exchange Rate
api_router.include_router(
    exchange_rate.router,
    prefix="/exchange_rate",
    tags=["💰 Exchange Rate"],
)

# Blog Admin
api_router.include_router(
    blog_admin.router,
    tags=["👑 Admin - Blog"],
)