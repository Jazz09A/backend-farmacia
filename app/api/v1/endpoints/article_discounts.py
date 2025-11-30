from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.services.source_system_service import source_system_service
from app.schemas.article_discount import (
    ArticleDiscountCreate,
    ArticleDiscountResponse,
    ArticleDiscountListResponse,
    ArticleDiscountDetail
)
from app.core.dependencies import get_admin_user
from app.models.user import User

router = APIRouter()

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
            detail=f"Error de validación: {str(ve)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error creando descuento: {str(e)}"
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo tipos de cliente: {str(e)}"
        )


@router.get("/", response_model=ArticleDiscountListResponse)
def list_article_discounts(
    co_art: Optional[str] = Query(None, description="Filtrar por código de artículo"),
    tip_cli: Optional[str] = Query(None, description="Filtrar por tipo de cliente"),
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo descuentos: {str(e)}"
        )


@router.get("/{co_art}", response_model=ArticleDiscountListResponse)
def get_article_discounts_by_code(
    co_art: str,
    tip_cli: Optional[str] = Query(None, description="Filtrar por tipo de cliente"),
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo descuentos del artículo {co_art}: {str(e)}"
        )

