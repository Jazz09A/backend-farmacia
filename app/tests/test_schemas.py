"""
Tests para los schemas de categorías, marcas y promociones
"""
import pytest
from datetime import datetime, timedelta
from pydantic import ValidationError
from app.schemas.category import (
    CategoryCreate, CategoryUpdate, BrandCreate, BrandUpdate
)
from app.schemas.promotion import (
    FlashOfferCreate, FlashOfferUpdate, PromotionalCodeCreate,
    PromotionalCodeUpdate, ValidatePromotionalCodeRequest,
    DiscountTypeEnum
)


class TestCategorySchemas:
    """Tests para schemas de categorías."""
    
    def test_category_create_valid(self):
        """Test crear categoría con datos válidos."""
        data = {
            "name": "Analgésicos",
            "slug": "analgesicos",
            "description": "Medicamentos para el dolor",
            "icon": "pain-relief",
            "color": "#FF5722",
            "is_active": True,
            "sort_order": 1
        }
        
        schema = CategoryCreate(**data)
        
        assert schema.name == "Analgésicos"
        assert schema.slug == "analgesicos"
        assert schema.description == "Medicamentos para el dolor"
        assert schema.icon == "pain-relief"
        assert schema.color == "#FF5722"
        assert schema.is_active is True
        assert schema.sort_order == 1
    
    def test_category_create_slug_validation(self):
        """Test validación de slug en categoría."""
        # Slug válido con guiones y números
        valid_data = {
            "name": "Test Category",
            "slug": "test-category-123"
        }
        schema = CategoryCreate(**valid_data)
        assert schema.slug == "test-category-123"
        
        # Slug con caracteres especiales inválidos
        invalid_data = {
            "name": "Test Category",
            "slug": "test@category!"
        }
        
        with pytest.raises(ValidationError) as exc_info:
            CategoryCreate(**invalid_data)
        
        assert "Slug debe contener solo letras" in str(exc_info.value)
    
    def test_category_create_required_fields(self):
        """Test campos requeridos en categoría."""
        # Sin name
        with pytest.raises(ValidationError):
            CategoryCreate(slug="test")
        
        # Sin slug
        with pytest.raises(ValidationError):
            CategoryCreate(name="Test")
    
    def test_category_update_partial(self):
        """Test actualización parcial de categoría."""
        data = {
            "name": "Nuevo Nombre",
            "description": "Nueva descripción"
            # slug e is_active no incluidos
        }
        
        schema = CategoryUpdate(**data)
        
        assert schema.name == "Nuevo Nombre"
        assert schema.description == "Nueva descripción"
        assert schema.slug is None
        assert schema.is_active is None


class TestBrandSchemas:
    """Tests para schemas de marcas."""
    
    def test_brand_create_valid(self):
        """Test crear marca con datos válidos."""
        data = {
            "name": "Bayer",
            "slug": "bayer",
            "logo_url": "https://example.com/bayer-logo.png",
            "description": "Farmacéutica alemana",
            "is_featured": True,
            "is_active": True
        }
        
        schema = BrandCreate(**data)
        
        assert schema.name == "Bayer"
        assert schema.slug == "bayer"
        assert schema.logo_url == "https://example.com/bayer-logo.png"
        assert schema.description == "Farmacéutica alemana"
        assert schema.is_featured is True
        assert schema.is_active is True
    
    def test_brand_create_slug_validation(self):
        """Test validación de slug en marca."""
        # Slug válido
        valid_data = {
            "name": "Test Brand",
            "slug": "test-brand_123"
        }
        schema = BrandCreate(**valid_data)
        assert schema.slug == "test-brand_123"
        
        # Slug inválido
        invalid_data = {
            "name": "Test Brand",
            "slug": "test brand spaces"
        }
        
        with pytest.raises(ValidationError):
            BrandCreate(**invalid_data)
    
    def test_brand_defaults(self):
        """Test valores por defecto en marca."""
        data = {
            "name": "Test Brand",
            "slug": "test-brand"
        }
        
        schema = BrandCreate(**data)
        
        assert schema.is_featured is False
        assert schema.is_active is True
        assert schema.logo_url is None
        assert schema.description is None


class TestPromotionSchemas:
    """Tests para schemas de promociones."""
    
    def test_flash_offer_create_valid(self):
        """Test crear flash offer con datos válidos."""
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(hours=24)
        
        data = {
            "product_id": "product-123",
            "discount_type": DiscountTypeEnum.PERCENTAGE,
            "discount_value": 20.0,
            "start_time": start_time,
            "end_time": end_time,
            "max_quantity": 100,
            "is_active": True
        }
        
        schema = FlashOfferCreate(**data)
        
        assert schema.product_id == "product-123"
        assert schema.discount_type == DiscountTypeEnum.PERCENTAGE
        assert schema.discount_value == 20.0
        assert schema.max_quantity == 100
        assert schema.is_active is True
    
    def test_flash_offer_time_validation(self):
        """Test validación de fechas en flash offer."""
        start_time = datetime.utcnow()
        end_time = start_time - timedelta(hours=1)  # Fin antes que inicio
        
        data = {
            "product_id": "product-123",
            "discount_value": 20.0,
            "start_time": start_time,
            "end_time": end_time
        }
        
        with pytest.raises(ValidationError) as exc_info:
            FlashOfferCreate(**data)
        
        assert "debe ser posterior" in str(exc_info.value)
    
    def test_flash_offer_percentage_validation(self):
        """Test validación de descuento porcentual."""
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(hours=1)
        
        # Descuento porcentual > 100%
        data = {
            "product_id": "product-123",
            "discount_type": DiscountTypeEnum.PERCENTAGE,
            "discount_value": 150.0,  # Inválido
            "start_time": start_time,
            "end_time": end_time
        }
        
        with pytest.raises(ValidationError) as exc_info:
            FlashOfferCreate(**data)
        
        assert "no puede ser mayor a 100%" in str(exc_info.value)
    
    def test_promotional_code_create_valid(self):
        """Test crear código promocional con datos válidos."""
        valid_from = datetime.utcnow()
        valid_until = valid_from + timedelta(days=30)
        
        data = {
            "code": "save20",
            "description": "Descuento 20%",
            "discount_type": DiscountTypeEnum.PERCENTAGE,
            "discount_value": 20.0,
            "min_amount": 50.0,
            "max_discount": 100.0,
            "usage_limit": 1000,
            "user_limit": 1,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "applicable_categories": ["vitaminas", "analgesicos"],
            "applicable_products": ["product-1", "product-2"],
            "is_active": True
        }
        
        schema = PromotionalCodeCreate(**data)
        
        assert schema.code == "SAVE20"  # Debe convertirse a mayúsculas
        assert schema.description == "Descuento 20%"
        assert schema.discount_type == DiscountTypeEnum.PERCENTAGE
        assert schema.discount_value == 20.0
        assert schema.min_amount == 50.0
        assert schema.max_discount == 100.0
        assert schema.usage_limit == 1000
        assert schema.user_limit == 1
        assert schema.applicable_categories == ["vitaminas", "analgesicos"]
        assert schema.applicable_products == ["product-1", "product-2"]
    
    def test_promotional_code_validation(self):
        """Test validaciones de código promocional."""
        valid_from = datetime.utcnow()
        valid_until = valid_from - timedelta(days=1)  # Fin antes que inicio
        
        # Fechas inválidas
        data = {
            "code": "TEST",
            "discount_value": 10.0,
            "valid_from": valid_from,
            "valid_until": valid_until
        }
        
        with pytest.raises(ValidationError) as exc_info:
            PromotionalCodeCreate(**data)
        
        assert "debe ser posterior" in str(exc_info.value)
        
        # Descuento porcentual inválido
        data2 = {
            "code": "TEST2",
            "discount_type": DiscountTypeEnum.PERCENTAGE,
            "discount_value": 120.0,  # > 100%
            "valid_from": datetime.utcnow(),
            "valid_until": datetime.utcnow() + timedelta(days=1)
        }
        
        with pytest.raises(ValidationError):
            PromotionalCodeCreate(**data2)
    
    def test_promotional_code_update(self):
        """Test actualización de código promocional."""
        data = {
            "description": "Nueva descripción",
            "discount_value": 25.0,
            "is_active": False
        }
        
        schema = PromotionalCodeUpdate(**data)
        
        assert schema.description == "Nueva descripción"
        assert schema.discount_value == 25.0
        assert schema.is_active is False
        assert schema.code is None  # No incluido en update
    
    def test_validate_promotional_code_request(self):
        """Test schema de validación de código promocional."""
        data = {
            "code": "TEST20",
            "order_amount": 100.0,
            "applicable_products": ["product-1", "product-2"],
            "applicable_categories": ["vitaminas"]
        }
        
        schema = ValidatePromotionalCodeRequest(**data)
        
        assert schema.code == "TEST20"
        assert schema.order_amount == 100.0
        assert schema.applicable_products == ["product-1", "product-2"]
        assert schema.applicable_categories == ["vitaminas"]
    
    def test_validate_promotional_code_request_minimal(self):
        """Test schema de validación con datos mínimos."""
        data = {
            "code": "MINIMAL",
            "order_amount": 50.0
        }
        
        schema = ValidatePromotionalCodeRequest(**data)
        
        assert schema.code == "MINIMAL"
        assert schema.order_amount == 50.0
        assert schema.applicable_products is None
        assert schema.applicable_categories is None


class TestSchemaValidations:
    """Tests adicionales de validaciones en schemas."""
    
    def test_positive_values_validation(self):
        """Test validación de valores positivos."""
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(hours=1)
        
        # Discount value negativo
        with pytest.raises(ValidationError):
            FlashOfferCreate(
                product_id="test",
                discount_value=-5.0,
                start_time=start_time,
                end_time=end_time
            )
        
        # Order amount negativo en validación
        with pytest.raises(ValidationError):
            ValidatePromotionalCodeRequest(
                code="TEST",
                order_amount=-10.0
            )
    
    def test_string_length_validations(self):
        """Test validaciones de longitud de strings."""
        # Código muy corto
        valid_from = datetime.utcnow()
        valid_until = valid_from + timedelta(days=1)
        
        with pytest.raises(ValidationError):
            PromotionalCodeCreate(
                code="AB",  # Menos de 3 caracteres
                discount_value=10.0,
                valid_from=valid_from,
                valid_until=valid_until
            )
        
        # Código muy largo
        with pytest.raises(ValidationError):
            PromotionalCodeCreate(
                code="A" * 51,  # Más de 50 caracteres
                discount_value=10.0,
                valid_from=valid_from,
                valid_until=valid_until
            )
    
    def test_enum_validation(self):
        """Test validación de enums."""
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(hours=1)
        
        # Tipo de descuento válido
        schema = FlashOfferCreate(
            product_id="test",
            discount_type=DiscountTypeEnum.FIXED,
            discount_value=10.0,
            start_time=start_time,
            end_time=end_time
        )
        assert schema.discount_type == DiscountTypeEnum.FIXED
        
        # Tipo de descuento como string válido
        schema2 = FlashOfferCreate(
            product_id="test",
            discount_type="percentage",  # String válido
            discount_value=10.0,
            start_time=start_time,
            end_time=end_time
        )
        assert schema2.discount_type == DiscountTypeEnum.PERCENTAGE 