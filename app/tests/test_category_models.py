"""
Tests para los modelos Category y Brand
"""
import pytest
from sqlalchemy.orm import Session
from app.models.category import Category, Brand
from app.models.product import Product


class TestCategoryModel:
    """Tests para el modelo Category."""
    
    def test_create_category(self, db: Session):
        """Test crear una categoría básica."""
        category = Category(
            name="Analgésicos",
            slug="analgesicos",
            description="Medicamentos para el dolor",
            icon="pain-relief",
            color="#FF5722"
        )
        
        db.add(category)
        db.commit()
        db.refresh(category)
        
        assert category.id is not None
        assert category.name == "Analgésicos"
        assert category.slug == "analgesicos"
        assert category.description == "Medicamentos para el dolor"
        assert category.icon == "pain-relief"
        assert category.color == "#FF5722"
        assert category.is_active is True
        assert category.sort_order == 0
        assert category.parent_id is None
    
    def test_create_subcategory(self, db: Session):
        """Test crear una subcategoría."""
        # Crear categoría padre
        parent_category = Category(
            name="Medicamentos",
            slug="medicamentos",
            description="Categoría principal de medicamentos"
        )
        db.add(parent_category)
        db.commit()
        db.refresh(parent_category)
        
        # Crear subcategoría
        subcategory = Category(
            name="Analgésicos",
            slug="analgesicos",
            description="Medicamentos para el dolor",
            parent_id=parent_category.id
        )
        db.add(subcategory)
        db.commit()
        db.refresh(subcategory)
        
        assert subcategory.parent_id == parent_category.id
        assert subcategory.parent.name == "Medicamentos"
        assert len(parent_category.subcategories) == 1
        assert parent_category.subcategories[0].name == "Analgésicos"
    
    def test_category_full_path(self, db: Session):
        """Test el método full_path de las categorías."""
        # Crear categoría padre
        parent = Category(
            name="Medicamentos",
            slug="medicamentos"
        )
        db.add(parent)
        db.commit()
        db.refresh(parent)
        
        # Crear subcategoría
        child = Category(
            name="Analgésicos",
            slug="analgesicos",
            parent_id=parent.id
        )
        db.add(child)
        db.commit()
        db.refresh(child)
        
        assert parent.full_path == "Medicamentos"
        assert child.full_path == "Medicamentos > Analgésicos"
    
    def test_category_unique_slug(self, db: Session):
        """Test que el slug de categoría debe ser único."""
        category1 = Category(name="Test 1", slug="test-category")
        category2 = Category(name="Test 2", slug="test-category")
        
        db.add(category1)
        db.commit()
        
        db.add(category2)
        
        # Debería fallar por slug duplicado
        with pytest.raises(Exception):
            db.commit()
    
    def test_category_product_relationship(self, db: Session):
        """Test relación entre categoría y productos."""
        category = Category(name="Vitaminas", slug="vitaminas")
        db.add(category)
        db.commit()
        db.refresh(category)
        
        product = Product(
            name="Vitamina C",
            brand="Test Brand",
            category="Legacy Category",  # Legacy field
            category_id=category.id,  # New relationship
            price_ves=25.50,
            price_ref=5.00,
            description="Vitamina C 1000mg",
            image="vitamin-c.jpg"
        )
        db.add(product)
        db.commit()
        
        assert len(category.products) == 1
        assert category.products[0].name == "Vitamina C"
        assert product.category_obj.name == "Vitaminas"


class TestBrandModel:
    """Tests para el modelo Brand."""
    
    def test_create_brand(self, db: Session):
        """Test crear una marca básica."""
        brand = Brand(
            name="Bayer",
            slug="bayer",
            logo_url="https://example.com/bayer-logo.png",
            description="Farmacéutica alemana",
            is_featured=True
        )
        
        db.add(brand)
        db.commit()
        db.refresh(brand)
        
        assert brand.id is not None
        assert brand.name == "Bayer"
        assert brand.slug == "bayer"
        assert brand.logo_url == "https://example.com/bayer-logo.png"
        assert brand.description == "Farmacéutica alemana"
        assert brand.is_featured is True
        assert brand.is_active is True
    
    def test_brand_unique_slug(self, db: Session):
        """Test que el slug de marca debe ser único."""
        brand1 = Brand(name="Bayer", slug="bayer")
        brand2 = Brand(name="Bayer Corp", slug="bayer")
        
        db.add(brand1)
        db.commit()
        
        db.add(brand2)
        
        # Debería fallar por slug duplicado
        with pytest.raises(Exception):
            db.commit()
    
    def test_brand_product_relationship(self, db: Session):
        """Test relación entre marca y productos."""
        brand = Brand(name="Pfizer", slug="pfizer")
        db.add(brand)
        db.commit()
        db.refresh(brand)
        
        product = Product(
            name="Aspirina",
            brand="Legacy Brand",  # Legacy field
            brand_id=brand.id,  # New relationship
            category="Analgésicos",
            price_ves=15.00,
            price_ref=3.00,
            description="Aspirina 500mg",
            image="aspirina.jpg"
        )
        db.add(product)
        db.commit()
        
        assert len(brand.products) == 1
        assert brand.products[0].name == "Aspirina"
        assert product.brand_obj.name == "Pfizer"
    
    def test_brand_defaults(self, db: Session):
        """Test valores por defecto de la marca."""
        brand = Brand(name="Test Brand", slug="test-brand")
        
        db.add(brand)
        db.commit()
        db.refresh(brand)
        
        assert brand.is_featured is False
        assert brand.is_active is True
        assert brand.logo_url is None
        assert brand.description is None


class TestCategoryBrandIntegration:
    """Tests de integración entre categorías, marcas y productos."""
    
    def test_product_with_category_and_brand(self, db: Session):
        """Test producto con categoría y marca."""
        # Crear categoría
        category = Category(name="Antibióticos", slug="antibioticos")
        db.add(category)
        db.commit()
        db.refresh(category)
        
        # Crear marca
        brand = Brand(name="Novartis", slug="novartis")
        db.add(brand)
        db.commit()
        db.refresh(brand)
        
        # Crear producto con ambas relaciones
        product = Product(
            name="Amoxicilina",
            brand="Legacy Brand",  # Legacy
            category="Legacy Category",  # Legacy
            brand_id=brand.id,
            category_id=category.id,
            price_ves=45.00,
            price_ref=9.00,
            description="Amoxicilina 500mg",
            image="amoxicilina.jpg"
        )
        db.add(product)
        db.commit()
        
        # Verificar relaciones
        assert product.brand_obj.name == "Novartis"
        assert product.category_obj.name == "Antibióticos"
        assert len(brand.products) == 1
        assert len(category.products) == 1
    
    def test_category_hierarchy_with_products(self, db: Session):
        """Test jerarquía de categorías con productos."""
        # Crear categoría padre
        parent = Category(name="Medicamentos", slug="medicamentos")
        db.add(parent)
        db.commit()
        db.refresh(parent)
        
        # Crear subcategorías
        sub1 = Category(name="Analgésicos", slug="analgesicos", parent_id=parent.id)
        sub2 = Category(name="Antibióticos", slug="antibioticos", parent_id=parent.id)
        db.add_all([sub1, sub2])
        db.commit()
        db.refresh(sub1)
        db.refresh(sub2)
        
        # Crear productos en subcategorías
        product1 = Product(
            name="Aspirina",
            brand="Bayer",
            category="Analgésicos",
            category_id=sub1.id,
            price_ves=20.00,
            price_ref=4.00,
            description="Aspirina 500mg",
            image="aspirina.jpg"
        )
        
        product2 = Product(
            name="Amoxicilina",
            brand="Novartis",
            category="Antibióticos", 
            category_id=sub2.id,
            price_ves=35.00,
            price_ref=7.00,
            description="Amoxicilina 250mg",
            image="amoxicilina.jpg"
        )
        
        db.add_all([product1, product2])
        db.commit()
        
        # Verificar estructura
        assert len(parent.subcategories) == 2
        assert len(sub1.products) == 1
        assert len(sub2.products) == 1
        assert sub1.products[0].name == "Aspirina"
        assert sub2.products[0].name == "Amoxicilina" 