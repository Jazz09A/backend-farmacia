from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.dependencies import get_admin_user
from app.models.user import User
from app.schemas.article_discount import (
    ArticleDiscountCreate,
    ArticleDiscountDetail,
    ArticleDiscountListResponse,
    ArticleDiscountResponse,
    ArticleDiscountUpdate,
)
from app.services.source_system_service import source_system_service
from app.utils.logging_helpers import log_internal_error
from app.utils.timezone import get_ve_now

router = APIRouter()


def _internal_error(request: Request, exc: Exception, op: str) -> HTTPException:
    """Helper: loggea el error internamente y devuelve 500 genérico al cliente."""
    tracking_id = log_internal_error(
        request, exc,
        context={"operation": op, "module": "article_discounts"},
    )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="No se pudo completar la operación. Intente nuevamente o contacte a soporte.",
        headers={"X-Tracking-ID": tracking_id},
    )

@router.post("/", response_model=ArticleDiscountResponse)
def create_article_discount(
    discount_in: ArticleDiscountCreate,
    current_user: User = Depends(get_admin_user),
) -> Any:
    """
    Crear o actualizar un descuento para un artículo (saDescArticulo).
    Requiere permisos de superusuario.
    """
    try:
        # Obtener perfil del cliente en Profit Plus (tip_cli, co_cli, etc.)
        customer_profile = source_system_service.get_profit_customer_profile(current_user.email)
        co_desc = source_system_service.generate_discount_code()
        profit_user_code = source_system_service.build_profit_user_code(customer_profile["customer_code"])

        discount_data = discount_in.model_dump(exclude_unset=True)
        
        # Determinar el tip_cli a usar
        tip_cli_to_use = discount_data.get("tip_cli") or customer_profile["tip_cli"]
        
        # Validar que el tip_cli existe en saTipoCliente
        if not source_system_service.validate_tip_cli(tip_cli_to_use):
            valid_codes = source_system_service.get_valid_tip_cli_codes()
            valid_codes_str = ", ".join([f"{c['tip_cli'].strip()} ({c.get('des_tipo', 'N/A').strip()})" for c in valid_codes])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El tipo de cliente '{tip_cli_to_use}' no es válido. Tipos válidos: {valid_codes_str}"
            )
        
        discount_data.update(
            {
                "co_desc": co_desc,
                "tip_cli": tip_cli_to_use,
                "co_us_in": profit_user_code,
                "co_us_mo": profit_user_code,
                "co_sucu_in": "CCS",
                "co_sucu_mo": "CCS",
            }
        )

        success = source_system_service.create_article_discount(discount_data)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No se pudo crear el descuento en Profit Plus"
            )
            
        return ArticleDiscountResponse(**discount_data)
        
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error de validación: {ve!s}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error creando descuento: {e!s}"
        )


@router.get("/valid-customer-types")
def get_valid_customer_types(
    current_user: User = Depends(get_admin_user),
) -> Any:
    """
    Obtiene los tipos de cliente válidos para descuentos.
    """
    try:
        valid_types = source_system_service.get_valid_tip_cli_codes()
        return {
            "success": True,
            "customer_types": valid_types
        }
    except Exception as e:
        raise _internal_error(request, e, "list_valid_tip_cli")


@router.get("/", response_model=ArticleDiscountListResponse)
def list_article_discounts(
    request: Request,
    co_art: str | None = Query(None, description="Filtrar por código de artículo"),
    tip_cli: str | None = Query(None, description="Filtrar por tipo de cliente"),
    only_active: bool = Query(False, description="Solo descuentos activos"),
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(50, ge=1, le=100, description="Registros por página"),
    current_user: User = Depends(get_admin_user),
) -> Any:
    """
    Lista todos los descuentos de artículos desde saDescArticulo.
    Permite filtrar por artículo, tipo de cliente y estado.
    """
    try:
        result = source_system_service.get_article_discounts(
            co_art=co_art,
            tip_cli=tip_cli,
            only_active=only_active,
            page=page,
            limit=limit
        )

        return ArticleDiscountListResponse(**result)

    except Exception as e:
        raise _internal_error(request, e, "list_article_discounts")


@router.get("/{co_art}", response_model=ArticleDiscountListResponse)
def get_article_discounts_by_code(
    request: Request,
    co_art: str,
    tip_cli: str | None = Query(None, description="Filtrar por tipo de cliente"),
    only_active: bool = Query(True, description="Solo descuentos activos"),
    current_user: User = Depends(get_admin_user),
) -> Any:
    """
    Obtiene los descuentos de un artículo específico.
    Por defecto solo muestra descuentos activos.
    """
    try:
        result = source_system_service.get_article_discounts(
            co_art=co_art,
            tip_cli=tip_cli,
            only_active=only_active,
            page=1,
            limit=100
        )

        return ArticleDiscountListResponse(**result)

    except Exception as e:
        raise _internal_error(request, e, "get_article_discounts_by_code")


@router.get("/code/{co_desc}", response_model=ArticleDiscountDetail)
def get_article_discount_detail(
    request: Request,
    co_desc: str,
    current_user: User = Depends(get_admin_user),
) -> Any:
    """
    Obtiene el detalle de un descuento específico por su código (co_desc).
    """
    try:
        discount = source_system_service.get_article_discount_by_code(co_desc)
        
        if not discount:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Descuento {co_desc} no encontrado"
            )
            
        # Calcular estado activo
        is_active = True
        now = get_ve_now()
        
        start = discount.get('fecha_ini')
        end = discount.get('fecha_fin')
        
        # Convertir strings ISO a datetime si es necesario para comparar
        from datetime import datetime
        
        # Asegurarse de que now tenga tzinfo
        if now.tzinfo is None:
             from app.utils.timezone import VE_TIMEZONE
             now = now.replace(tzinfo=VE_TIMEZONE)

        if isinstance(start, str):
            try: start = datetime.fromisoformat(start)
            except: pass
        
        if isinstance(end, str):
            try: end = datetime.fromisoformat(end)
            except: pass
            
        # Normalizar start/end a timezone-aware si son naive
        if start and isinstance(start, datetime) and start.tzinfo is None:
             from app.utils.timezone import VE_TIMEZONE
             start = start.replace(tzinfo=VE_TIMEZONE)
             
        if end and isinstance(end, datetime) and end.tzinfo is None:
             from app.utils.timezone import VE_TIMEZONE
             end = end.replace(tzinfo=VE_TIMEZONE)
            
        if start and start > now:
            is_active = False
        if end and end < now:
            is_active = False
            
        discount['is_active'] = is_active

        return ArticleDiscountDetail(**discount)

    except HTTPException:
        raise
    except Exception as e:
        raise _internal_error(request, e, "get_article_discount_detail")


@router.put("/code/{co_desc}", response_model=dict)
def update_article_discount(
    request: Request,
    co_desc: str,
    discount_in: ArticleDiscountUpdate,
    current_user: User = Depends(get_admin_user),
) -> Any:
    """
    Actualiza un descuento existente.
    """
    try:
        # Verificar existencia
        existing = source_system_service.get_article_discount_by_code(co_desc)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Descuento {co_desc} no encontrado"
            )
            
        update_data = discount_in.model_dump(exclude_unset=True)
        
        if not update_data:
            return {"success": True, "message": "No hay cambios para aplicar"}
            
        success = source_system_service.update_article_discount(co_desc, update_data)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No se pudo actualizar el descuento"
            )

        return {"success": True, "message": "Descuento actualizado exitosamente", "co_desc": co_desc}

    except HTTPException:
        raise
    except Exception as e:
        raise _internal_error(request, e, "update_article_discount")

