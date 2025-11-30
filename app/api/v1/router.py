from fastapi import APIRouter

from app.api.v1.endpoints import auth, admin, user, public, categories, brands, favorites, shipping, dashboard, flash_offers, orders, credit, quantity_discounts, article_discounts
from app.api.v1.endpoints import quotes
from app.api.v1.endpoints import exchange_rate
from app.api.v1.endpoints import articles
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

# Órdenes del usuario
api_router.include_router(
    orders.router,
    prefix="/orders",
    tags=["📦 Órdenes"],
)

# Sistema de crédito
api_router.include_router(
    credit.router,
    prefix="/credit",
    tags=["💳 Crédito"],
)

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

# =============================================================================
# ⚡ RUTAS DE PROMOCIONES
# =============================================================================

# Flash Offers
api_router.include_router(
    flash_offers.router,
    prefix="/admin",
    tags=["⚡ Flash Offers"],
)

# Quantity Discounts
api_router.include_router(
    quantity_discounts.router,
    prefix="/admin",
    tags=["💰 Descuentos por Cantidad"],
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