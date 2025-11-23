"""
Endpoints públicos que no requieren autenticación.
"""
from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc, asc
from decimal import Decimal
from app.config.database import get_db
from app.models.product import Product
from app.models.user import User
from app.models.promotion import FlashOffer, DiscountType
from app.core.dependencies import PaginationParams, get_pagination_params
from app.schemas.product import ProductResponse, ProductListResponse, ProductSummary, FlashOfferInfo
from app.schemas.promotion import QuantityDiscountResponse
from app.core.dependencies import get_optional_current_user
from app.services.discount_service import DiscountService
from app.utils.timezone import get_ve_now

router = APIRouter(prefix="/public")


def get_active_flash_offers_for_products(
    db: Session, 
    product_ids: List[str], 
    product_skus: Dict[str, Optional[str]]
) -> Dict[str, FlashOffer]:
    """
    Obtiene flash offers activas para una lista de productos de manera optimizada.
    Busca tanto por product_id como por article_code (sku).
    
    Returns:
        Dict[str, FlashOffer]: Mapa de product_id -> FlashOffer (la más prioritaria si hay múltiples)
    """
    if not product_ids:
        return {}
    
    now = get_ve_now()
    
    # Obtener flash offers activas por product_id (una sola consulta)
    flash_offers_by_product_id = db.query(FlashOffer).filter(
        and_(
            FlashOffer.product_id.in_(product_ids),
            FlashOffer.is_active == True,
            FlashOffer.start_time <= now,
            FlashOffer.end_time >= now,
            or_(
                FlashOffer.max_quantity.is_(None),
                FlashOffer.used_quantity < FlashOffer.max_quantity
            )
        )
    ).all()
    
    # Crear mapa product_id -> FlashOffer
    result = {}
    for offer in flash_offers_by_product_id:
        if offer.product_id and offer.product_id not in result:
            result[offer.product_id] = offer
    
    # Obtener flash offers por article_code (sku) para productos que no tienen oferta por product_id
    # Solo buscar para productos que aún no tienen oferta
    products_without_offer = [pid for pid in product_ids if pid not in result]
    if products_without_offer:
        # Obtener SKUs de productos sin oferta
        article_codes = [
            sku.upper().strip() 
            for pid in products_without_offer 
            if product_skus.get(pid) and product_skus[pid]
        ]
        
        if article_codes:
            flash_offers_by_code = db.query(FlashOffer).filter(
                and_(
                    FlashOffer.article_code.in_(article_codes),
                    FlashOffer.is_active == True,
                    FlashOffer.start_time <= now,
                    FlashOffer.end_time >= now,
                    or_(
                        FlashOffer.max_quantity.is_(None),
                        FlashOffer.used_quantity < FlashOffer.max_quantity
                    )
                )
            ).all()
            
            # Mapear por product_id usando el sku
            sku_to_product_id = {
                sku.upper().strip(): pid 
                for pid, sku in product_skus.items() 
                if sku and pid in products_without_offer
            }
            
            for offer in flash_offers_by_code:
                normalized_code = (offer.article_code or "").upper().strip()
                product_id = sku_to_product_id.get(normalized_code)
                if product_id and product_id not in result:
                    result[product_id] = offer
    
    return result


def build_flash_offer_info(flash_offer: FlashOffer, product_price: Decimal) -> FlashOfferInfo:
    """Construye la información de flash offer para incluir en la respuesta del producto."""
    original_price = float(product_price)
    
    # Determinar el tipo de descuento
    discount_type_value = flash_offer.discount_type
    if hasattr(discount_type_value, 'value'):
        discount_type_value = discount_type_value.value
    
    # Calcular precio con descuento
    if discount_type_value == 'percentage' or discount_type_value == DiscountType.PERCENTAGE.value:
        discount_amount = original_price * (flash_offer.discount_value / 100)
        discount_percentage = flash_offer.discount_value
    else:  # fixed
        discount_amount = min(flash_offer.discount_value, original_price)
        discount_percentage = (discount_amount / original_price * 100) if original_price > 0 else 0
    
    offer_price = original_price - discount_amount
    
    return FlashOfferInfo(
        id=flash_offer.id,
        discount_type=discount_type_value,
        discount_value=flash_offer.discount_value,
        original_price=original_price,
        offer_price=round(offer_price, 2),
        discount_percentage=round(discount_percentage, 2),
        end_time=flash_offer.end_time.isoformat() if flash_offer.end_time else None,
        max_quantity=flash_offer.max_quantity,
        remaining_quantity=(
            (flash_offer.max_quantity - flash_offer.used_quantity) 
            if flash_offer.max_quantity else None
        )
    )

@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_public_product(
    product_id: str,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    Get product details for public.
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    
    product_dict = {
        **product.__dict__,
        'current_price': product.current_price,
        'discount_percentage': product.discount_percentage,
        'is_available': product.is_available
    }
    
    # Obtener flash offer activa para este producto
    flash_offers_map = get_active_flash_offers_for_products(
        db, 
        [product.id], 
        {product.id: product.sku}
    )
    flash_offer = flash_offers_map.get(product.id)
    
    if flash_offer:
        flash_offer_info = build_flash_offer_info(flash_offer, product.price)
        product_dict['flash_offer'] = flash_offer_info
        
        # Actualizar precio y descuento con la oferta
        product_dict['current_price'] = Decimal(str(flash_offer_info.offer_price))
        product_dict['is_offer'] = True
        product_dict['original_price'] = Decimal(str(flash_offer_info.original_price))
        product_dict['discount_percentage'] = Decimal(str(flash_offer_info.discount_percentage))
        if flash_offer.end_time:
            product_dict['offer_end_time'] = flash_offer.end_time
    
    # Handle empty strings for required fields
    if not product_dict.get('description') or len(product_dict.get('description', '').strip()) < 10:
        product_dict['description'] = 'Sin descripción disponible'
    
    # Handle images - prioritize images list, fallback to single image
    images = product_dict.get('images', [])
    if not images or not isinstance(images, list) or len(images) == 0:
        # If no images list, check single image field
        single_image = product_dict.get('image', '')
        if single_image and len(single_image.strip()) > 0:
            images = [single_image]
        else:
            images = ['/static/images/no-image.png']
    
    # Ensure we have at least one image
    if not images or len(images) == 0:
        images = ['/static/images/no-image.png']
    
    # Set both fields for consistency
    product_dict['images'] = images
    product_dict['image'] = images[0]  # First image as main image
    
    return ProductResponse.model_validate(product_dict)

# =============================================================================
# CATÁLOGO Y PRODUCTOS - PÚBLICO
# =============================================================================

@router.get("/products", response_model=ProductListResponse)
async def get_public_products(
    pagination: PaginationParams = Depends(get_pagination_params),
    category_id: Optional[str] = Query(None, description="Filtrar por categoría"),
    brand_id: Optional[str] = Query(None, description="Filtrar por marca"),
    search: Optional[str] = Query(None, description="Buscar productos"),
    min_price: Optional[float] = Query(None, ge=0, description="Precio mínimo"),
    max_price: Optional[float] = Query(None, ge=0, description="Precio máximo"),
    prescription_required: Optional[bool] = Query(None, description="Solo productos con/sin receta"),
    featured_only: Optional[bool] = Query(False, description="Solo productos destacados"),
    on_offer: Optional[bool] = Query(None, description="Solo productos en oferta"),
    sort_by: str = Query("name", description="Ordenar por: name, price_asc, price_desc, rating, newest"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    🛍️ **Catálogo de productos (Público) - Mejorado**
    
    Lista todos los productos disponibles con paginación completa, filtros avanzados y optimización de consultas.
    """
    # Base query with optimized filtering
    query = db.query(Product).filter(Product.in_stock == True)
    
    # Build filters dictionary for response
    applied_filters = {}
    
    # Apply filters
    if category_id:
        query = query.filter(Product.category_id == category_id)
        applied_filters["category_id"] = category_id
    
    if brand_id:
        query = query.filter(Product.brand_id == brand_id)
        applied_filters["brand_id"] = brand_id
    
    if search:
        search_filter = or_(
            Product.name.ilike(f"%{search}%"),
            Product.description.ilike(f"%{search}%"),
            Product.brand.ilike(f"%{search}%"),
            Product.sku.ilike(f"%{search}%"),  
            func.array_to_string(Product.ingredients, ' ').ilike(f"%{search}%")
        )
        query = query.filter(search_filter)
        applied_filters["search"] = search
    
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
        applied_filters["min_price"] = min_price
    
    if max_price is not None:
        query = query.filter(Product.price <= max_price)
        applied_filters["max_price"] = max_price
    
    if prescription_required is not None:
        query = query.filter(Product.prescription == prescription_required)
        applied_filters["prescription_required"] = prescription_required
    
    if featured_only:
        query = query.filter(Product.featured == True)
        applied_filters["featured_only"] = featured_only
    
    if on_offer is not None:
        query = query.filter(Product.is_offer == on_offer)
        applied_filters["on_offer"] = on_offer
    
    # Apply sorting
    if sort_by == "price_asc":
        query = query.order_by(asc(Product.price))
    elif sort_by == "price_desc":
        query = query.order_by(desc(Product.price))
    elif sort_by == "rating":
        query = query.order_by(desc(Product.rating))
    elif sort_by == "newest":
        query = query.order_by(desc(Product.created_at))
    else:  # default to name
        query = query.order_by(asc(Product.name))
    
    applied_filters["sort_by"] = sort_by
    
    # Get total count for pagination (optimized)
    if pagination.page == 1:
        # Primera página: hacer COUNT y buscar datos
        total = query.count()
        products = query.offset(pagination.skip).limit(pagination.limit).all()
    else:
        # Páginas siguientes: solo buscar datos, evitar COUNT
        products = query.offset(pagination.skip).limit(pagination.limit + 1).all()
        
        # Si trae más registros que el limit, hay más páginas
        has_more = len(products) > pagination.limit
        if has_more:
            products = products[:pagination.limit]
        
        # Estimar total basado en página actual
        total = (pagination.page - 1) * pagination.limit + len(products)
        if has_more:
            total += 1  # Indicar que hay más
    
    # Obtener flash offers activas de manera optimizada (una sola consulta)
    product_ids = [p.id for p in products]
    product_skus = {p.id: p.sku for p in products}
    flash_offers_map = get_active_flash_offers_for_products(db, product_ids, product_skus)
    
    # Convert to response models
    product_responses = []
    for product in products:
        product_dict = {
            **product.__dict__,
            'current_price': product.current_price,
            'discount_percentage': product.discount_percentage,
            'is_available': product.in_stock and product.stock > 0
        }
        
        # Agregar información de flash offer si existe
        flash_offer = flash_offers_map.get(product.id)
        if flash_offer:
            flash_offer_info = build_flash_offer_info(flash_offer, product.price)
            product_dict['flash_offer'] = flash_offer_info
            
            # Actualizar precio y descuento con la oferta
            product_dict['current_price'] = Decimal(str(flash_offer_info.offer_price))
            product_dict['is_offer'] = True
            product_dict['original_price'] = Decimal(str(flash_offer_info.original_price))
            product_dict['discount_percentage'] = Decimal(str(flash_offer_info.discount_percentage))
            if flash_offer.end_time:
                product_dict['offer_end_time'] = flash_offer.end_time
        
        # Handle empty strings for required fields
        if not product_dict.get('description') or len(product_dict.get('description', '').strip()) < 10:
            product_dict['description'] = 'Sin descripción disponible'
        
        # Handle images - prioritize images list, fallback to single image
        images = product_dict.get('images', [])
        if not images or not isinstance(images, list) or len(images) == 0:
            # If no images list, check single image field
            single_image = product_dict.get('image', '')
            if single_image and len(single_image.strip()) > 0:
                images = [single_image]
            else:
                images = ['/static/images/no-image.png']
        
        # Ensure we have at least one image
        if not images or len(images) == 0:
            images = ['/static/images/no-image.png']
        
        # Set both fields for consistency
        product_dict['images'] = images
        product_dict['image'] = images[0]  # First image as main image
        
        product_responses.append(ProductResponse.model_validate(product_dict))
    
    return ProductListResponse.create(
        products=product_responses,
        total=total,
        page=pagination.page,
        limit=pagination.limit,
        filters=applied_filters
    )

@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_public_product_detail(
    product_id: str,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    📦 **Detalle de producto (Público)**
    
    Obtiene información detallada de un producto específico.
    """
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.in_stock == True
    ).first()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado"
        )
    
    product_dict = {
        **product.__dict__,
        'current_price': product.current_price,
        'discount_percentage': product.discount_percentage,
        'is_available': product.in_stock and product.stock > 0
    }
    
    # Obtener flash offer activa para este producto
    flash_offers_map = get_active_flash_offers_for_products(
        db, 
        [product.id], 
        {product.id: product.sku}
    )
    flash_offer = flash_offers_map.get(product.id)
    
    if flash_offer:
        flash_offer_info = build_flash_offer_info(flash_offer, product.price)
        product_dict['flash_offer'] = flash_offer_info
        
        # Actualizar precio y descuento con la oferta
        product_dict['current_price'] = Decimal(str(flash_offer_info.offer_price))
        product_dict['is_offer'] = True
        product_dict['original_price'] = Decimal(str(flash_offer_info.original_price))
        product_dict['discount_percentage'] = Decimal(str(flash_offer_info.discount_percentage))
        if flash_offer.end_time:
            product_dict['offer_end_time'] = flash_offer.end_time
    
    # Handle empty strings for required fields
    if not product_dict.get('description') or len(product_dict.get('description', '').strip()) < 10:
        product_dict['description'] = 'Sin descripción disponible'
    
    # Handle images - prioritize images list, fallback to single image
    images = product_dict.get('images', [])
    if not images or not isinstance(images, list) or len(images) == 0:
        # If no images list, check single image field
        single_image = product_dict.get('image', '')
        if single_image and len(single_image.strip()) > 0:
            images = [single_image]
        else:
            images = ['/static/images/no-image.png']
    
    # Ensure we have at least one image
    if not images or len(images) == 0:
        images = ['/static/images/no-image.png']
    
    # Set both fields for consistency
    product_dict['images'] = images
    product_dict['image'] = images[0]  # First image as main image
    
    return ProductResponse.model_validate(product_dict)

@router.get("/products/search", response_model=ProductListResponse)
async def search_public_products(
    q: str = Query(..., min_length=2, description="Término de búsqueda"),
    pagination: PaginationParams = Depends(get_pagination_params),
    category_id: Optional[str] = Query(None, description="Filtrar por categoría"),
    sort_by: str = Query("relevance", description="Ordenar por: relevance, name, price_asc, price_desc, rating"),
    db: Session = Depends(get_db)
):
    """
    🔍 **Búsqueda de productos (Público) - Mejorado**
    
    Busca productos por nombre, descripción o marca con paginación completa y filtros.
    """
    # Base search query
    search_filter = or_(
        Product.name.ilike(f"%{q}%"),
        Product.description.ilike(f"%{q}%"),
        Product.brand.ilike(f"%{q}%"),
        Product.sku.ilike(f"%{q}%"),  # ← Agregar búsqueda por SKU
        func.array_to_string(Product.ingredients, ' ').ilike(f"%{q}%") if hasattr(Product, 'ingredients') else False
    )
    
    query = db.query(Product).filter(
        Product.in_stock == True,
        search_filter
    )
    
    # Apply category filter if provided
    applied_filters = {"search": q}
    if category_id:
        query = query.filter(Product.category_id == category_id)
        applied_filters["category_id"] = category_id
    
    # Apply sorting
    if sort_by == "price_asc":
        query = query.order_by(asc(Product.price))
    elif sort_by == "price_desc":
        query = query.order_by(desc(Product.price))
    elif sort_by == "rating":
        query = query.order_by(desc(Product.rating))
    elif sort_by == "name":
        query = query.order_by(asc(Product.name))
    else:  # relevance (default)
        # Simple relevance: exact matches first, then partial matches
        query = query.order_by(
            Product.name.ilike(f"{q}").desc(),  # Exact match first
            desc(Product.rating),  # Then by rating
            asc(Product.name)  # Then alphabetically
        )
    
    applied_filters["sort_by"] = sort_by
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    products = query.offset(pagination.skip).limit(pagination.limit).all()
    
    # Obtener flash offers activas de manera optimizada (una sola consulta)
    product_ids = [p.id for p in products]
    product_skus = {p.id: p.sku for p in products}
    flash_offers_map = get_active_flash_offers_for_products(db, product_ids, product_skus)
    
    # Convert to response models
    product_responses = []
    for product in products:
        product_dict = {
            **product.__dict__,
            'current_price': product.current_price,
            'discount_percentage': product.discount_percentage,
            'is_available': product.in_stock and product.stock > 0
        }
        
        # Agregar información de flash offer si existe
        flash_offer = flash_offers_map.get(product.id)
        if flash_offer:
            flash_offer_info = build_flash_offer_info(flash_offer, product.price)
            product_dict['flash_offer'] = flash_offer_info
            
            # Actualizar precio y descuento con la oferta
            product_dict['current_price'] = Decimal(str(flash_offer_info.offer_price))
            product_dict['is_offer'] = True
            product_dict['original_price'] = Decimal(str(flash_offer_info.original_price))
            product_dict['discount_percentage'] = Decimal(str(flash_offer_info.discount_percentage))
            if flash_offer.end_time:
                product_dict['offer_end_time'] = flash_offer.end_time
        
        # Handle empty strings for required fields
        if not product_dict.get('description') or len(product_dict.get('description', '').strip()) < 10:
            product_dict['description'] = 'Sin descripción disponible'
        
        # Handle images - prioritize images list, fallback to single image
        images = product_dict.get('images', [])
        if not images or not isinstance(images, list) or len(images) == 0:
            # If no images list, check single image field
            single_image = product_dict.get('image', '')
            if single_image and len(single_image.strip()) > 0:
                images = [single_image]
            else:
                images = ['/static/images/no-image.png']
        
        # Ensure we have at least one image
        if not images or len(images) == 0:
            images = ['/static/images/no-image.png']
        
        # Set both fields for consistency
        product_dict['images'] = images
        product_dict['image'] = images[0]  # First image as main image
        
        product_responses.append(ProductResponse.model_validate(product_dict))
    
    return ProductListResponse.create(
        products=product_responses,
        total=total,
        page=pagination.page,
        limit=pagination.limit,
        filters=applied_filters
    )

# =============================================================================
# INFORMACIÓN GENERAL - PÚBLICO
# =============================================================================


@router.get("/payment-methods")
async def get_payment_methods():
    """
    💳 **Métodos de pago disponibles**
    
    Obtiene los métodos de pago activos en el sistema.
    """
    methods = [
        {
            "id": "cash",
            "name": "Efectivo",
            "description": "Pago en efectivo contra entrega",
            "fee": 0.00,
            "active": True
        },
        {
            "id": "transfer",
            "name": "Transferencia Bancaria", 
            "description": "Transferencia a cuenta bancaria",
            "fee": 0.00,
            "active": True
        },
        {
            "id": "mobile_payment",
            "name": "Pago Móvil",
            "description": "Pago móvil interbancario",
            "fee": 0.00,
            "active": True
        }
    ]
    return {"payment_methods": methods}

@router.get("/categories")
async def get_public_categories(db: Session = Depends(get_db)):
    """
    📂 **Categorías de productos**
    
    Obtiene todas las categorías disponibles.
    """
    # Asumiendo que tienes un modelo Category
    # categories = db.query(Category).filter(Category.is_active == True).all()
    
    # Por ahora datos estáticos
    categories = [
        {"id": "analgesicos", "name": "Analgésicos", "description": "Medicamentos para el dolor"},
        {"id": "antibioticos", "name": "Antibióticos", "description": "Medicamentos antimicrobianos"},
        {"id": "vitaminas", "name": "Vitaminas", "description": "Suplementos vitamínicos"},
        {"id": "cuidado_personal", "name": "Cuidado Personal", "description": "Productos de higiene y cuidado"}
    ]
    
    return {"categories": categories}

@router.get("/brands")
async def get_public_brands(db: Session = Depends(get_db)):
    """
    🏷️ **Marcas de productos**
    
    Obtiene todas las marcas disponibles.
    """
    # Datos estáticos por ahora
    brands = [
        {"id": "bayer", "name": "Bayer", "country": "Alemania"},
        {"id": "pfizer", "name": "Pfizer", "country": "Estados Unidos"},
        {"id": "roche", "name": "Roche", "country": "Suiza"},
        {"id": "novartis", "name": "Novartis", "country": "Suiza"}
    ]
    
    return {"brands": brands}

# =============================================================================
# INFORMACIÓN DEL SISTEMA
# =============================================================================

@router.get("/health")
async def health_check():
    """
    ❤️ **Health Check**
    
    Endpoint para verificar que la API está funcionando.
    """
    return {
        "status": "healthy",
        "service": "Farmacia API",
        "version": "1.0.0"
    }

@router.get("/features")
async def get_public_features():
    """
    ⭐ **Características del sistema**
    
    Obtiene las características públicas del sistema.
    """
    return {
        "features": {
            "user_registration": True,
            "guest_checkout": False,
            "multiple_payment_methods": True,
            "prescription_upload": True,
            "delivery_tracking": True,
            "customer_reviews": True,
            "loyalty_program": False
        },
        "supported_currencies": ["VES", "USD"],
        "supported_languages": ["es"],
        "api_version": "v1"
    } 

# =============================================================================
# DESCUENTOS PÚBLICOS
# =============================================================================

@router.get("/quantity-discounts/applicable", response_model=Optional[QuantityDiscountResponse])
async def get_applicable_quantity_discount(
    total_quantity: int = Query(..., gt=0, description="Cantidad total de productos"),
    db: Session = Depends(get_db)
):
    """
    Obtener el descuento por cantidad aplicable para una cantidad dada.

    **Endpoint público** - No requiere autenticación.
    """
    service = DiscountService(db)
    discount = service.get_applicable_quantity_discount(total_quantity)
    return discount

# @router.get("/"):
#     ...