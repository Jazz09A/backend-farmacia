"""
Servicio para manejo de carga masiva de productos desde CSV/Excel
"""
import pandas as pd
import re
import uuid
from typing import List, Dict, Any, Union, Optional, Tuple
from io import BytesIO
from sqlalchemy.orm import Session
from fastapi import HTTPException, UploadFile
import logging

from app.schemas.product import ProductBulkUploadItem, ProductValidationError, ProductBulkUploadResult
from app.models.product import Product

logger = logging.getLogger(__name__)

class ProductBulkService:
    """Servicio para carga masiva de productos"""
    
    # Mapeo de columnas esperadas (nombre en archivo -> nombre en schema)
    COLUMN_MAPPING = {
        # Campos requeridos
        'name': ['nombre', 'name', 'producto', 'product_name'],
        'price_ves': ['precio_ves', 'price_ves', 'precio_bolivares', 'precio_bs', 'precio'],
        'price_ref': ['precio_ref', 'price_ref', 'precio_usd', 'precio_dolares', 'price_usd'],
        'description': ['descripcion', 'description', 'desc'],
        
        # Campos opcionales
        'brand': ['marca', 'brand', 'fabricante'],
        'category': ['categoria', 'category', 'cat'],
        'subcategory': ['subcategoria', 'subcategory', 'subcat'],
        'patology': ['patologia', 'patology', 'indicacion', 'indication'],
        'image': ['imagen', 'image', 'foto', 'photo'],
        'images': ['imagenes', 'images', 'fotos', 'photos'],
        'ingredients': ['ingredientes', 'ingredients', 'componentes', 'components'],
        'in_stock': ['en_stock', 'in_stock', 'disponible', 'available'],
        'stock': ['stock', 'inventario', 'cantidad', 'quantity'],
        'prescription': ['receta', 'prescription', 'prescripcion', 'rx'],
        'dosage': ['dosis', 'dosage', 'dosificacion'],
        'presentation': ['presentacion', 'presentation', 'formato'],
        'laboratorio': ['laboratorio', 'laboratory', 'lab'],
        'registro_sanitario': ['registro_sanitario', 'sanitary_registry', 'registro'],
        'contraindicaciones': ['contraindicaciones', 'contraindications'],
        'efectos_secundarios': ['efectos_secundarios', 'side_effects', 'efectos'],
        'sku': ['sku', 'codigo', 'code'],
        'featured': ['destacado', 'featured', 'principal'],
        'is_offer': ['oferta', 'is_offer', 'promocion', 'promotion'],
        'original_price': ['precio_original', 'original_price', 'precio_antes']
    }
    
    @staticmethod
    def _normalize_column_name(column: str) -> str:
        """Normaliza el nombre de una columna"""
        return column.lower().strip().replace(' ', '_').replace('-', '_')
    
    @staticmethod
    def _map_columns(df_columns: List[str]) -> Dict[str, str]:
        """Mapea las columnas del DataFrame a los nombres esperados"""
        column_map = {}
        normalized_columns = {ProductBulkService._normalize_column_name(col): col for col in df_columns}
        
        for schema_field, possible_names in ProductBulkService.COLUMN_MAPPING.items():
            for possible_name in possible_names:
                normalized_name = ProductBulkService._normalize_column_name(possible_name)
                if normalized_name in normalized_columns:
                    column_map[schema_field] = normalized_columns[normalized_name]
                    break
        
        return column_map
    
    @staticmethod
    def _parse_list_field(value: Any) -> List[str]:
        """Parsea un campo que debería ser una lista"""
        if pd.isna(value) or value is None:
            return []
        
        if isinstance(value, list):
            return [str(item).strip() for item in value if item]
        
        if isinstance(value, str):
            # Intenta separar por comas, punto y coma, o pipes
            separators = [',', ';', '|']
            for sep in separators:
                if sep in value:
                    return [item.strip() for item in value.split(sep) if item.strip()]
            # Si no hay separadores, retorna como lista de un elemento
            return [value.strip()] if value.strip() else []
        
        return [str(value).strip()] if str(value).strip() else []
    
    @staticmethod
    def _parse_boolean_field(value: Any) -> bool:
        """Parsea un campo booleano desde diferentes formatos"""
        if pd.isna(value) or value is None:
            return False
        
        if isinstance(value, bool):
            return value
        
        if isinstance(value, (int, float)):
            return bool(value)
        
        if isinstance(value, str):
            value_lower = value.lower().strip()
            true_values = ['true', 'yes', 'si', 'sí', '1', 'verdadero', 'activo', 'enabled']
            false_values = ['false', 'no', '0', 'falso', 'inactivo', 'disabled']
            
            if value_lower in true_values:
                return True
            elif value_lower in false_values:
                return False
        
        return False
    
    @staticmethod
    def _parse_numeric_field(value: Any, field_name: str) -> Optional[float]:
        """Parsea un campo numérico con validación"""
        if pd.isna(value) or value is None or value == '':
            return None
        
        try:
            # Limpia el valor de caracteres no numéricos comunes
            if isinstance(value, str):
                # Remueve espacios, comas como separadores de miles, y símbolos de moneda
                cleaned_value = re.sub(r'[^\d.,\-+]', '', value.strip())
                # Reemplaza coma por punto para decimales
                cleaned_value = cleaned_value.replace(',', '.')
                value = cleaned_value
            
            numeric_value = float(value)
            
            # Validaciones específicas para precios
            if field_name in ['price_ves', 'price_ref', 'original_price'] and numeric_value <= 0:
                raise ValueError(f"El precio debe ser mayor que 0")
            
            if field_name == 'stock' and numeric_value < 0:
                raise ValueError(f"El stock no puede ser negativo")
            
            return numeric_value
        except (ValueError, TypeError) as e:
            raise ValueError(f"Valor numérico inválido para {field_name}: {value}")
    
    @staticmethod
    def _sanitize_text_field(value: Any, max_length: Optional[int] = None) -> Optional[str]:
        """Sanitiza un campo de texto"""
        if pd.isna(value) or value is None:
            return None
        
        # Convierte a string y limpia
        text = str(value).strip()
        
        # Remueve caracteres de control y caracteres especiales peligrosos
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        
        # Escapa caracteres HTML básicos para prevenir XSS
        text = (text.replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('"', '&quot;')
                   .replace("'", '&#x27;'))
        
        # Aplica límite de longitud si se especifica
        if max_length and len(text) > max_length:
            text = text[:max_length]
        
        return text if text else None
    
    @staticmethod
    def _generate_slug(name: str, existing_slugs: set) -> str:
        """Genera un slug único para el producto"""
        base_slug = re.sub(r'[^a-zA-Z0-9\s-]', '', name.lower())
        base_slug = re.sub(r'\s+', '-', base_slug.strip())
        
        slug = base_slug
        counter = 1
        while slug in existing_slugs:
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        existing_slugs.add(slug)
        return slug
    
    @staticmethod
    def read_file(file: UploadFile) -> pd.DataFrame:
        """Lee un archivo CSV o Excel y retorna un DataFrame"""
        try:
            content = file.file.read()
            file_extension = file.filename.lower().split('.')[-1]
            
            if file_extension == 'csv':
                # Intenta diferentes encodings para CSV
                encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
                df = None
                
                for encoding in encodings:
                    try:
                        df = pd.read_csv(BytesIO(content), encoding=encoding)
                        break
                    except UnicodeDecodeError:
                        continue
                
                if df is None:
                    raise HTTPException(
                        status_code=400,
                        detail="No se pudo leer el archivo CSV. Verifica la codificación."
                    )
                    
            elif file_extension in ['xlsx', 'xls']:
                df = pd.read_excel(BytesIO(content))
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Formato de archivo no soportado. Use CSV o Excel."
                )
            
            if df.empty:
                raise HTTPException(
                    status_code=400,
                    detail="El archivo está vacío."
                )
            
            return df
            
        except Exception as e:
            logger.error(f"Error reading file: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail=f"Error al leer el archivo: {str(e)}"
            )
    
    @staticmethod
    def process_bulk_upload(
        file: UploadFile,
        db: Session,
        max_rows: int = 1000
    ) -> ProductBulkUploadResult:
        """Procesa la carga masiva de productos desde un archivo"""
        
        # Lee el archivo
        df = ProductBulkService.read_file(file)
        
        # Limita el número de filas
        if len(df) > max_rows:
            df = df.head(max_rows)
        
        # Mapea las columnas
        column_map = ProductBulkService._map_columns(df.columns.tolist())
        
        # Verifica que existan las columnas requeridas
        required_fields = ['name', 'price_ves', 'price_ref', 'description']
        missing_fields = [field for field in required_fields if field not in column_map]
        
        if missing_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Faltan columnas requeridas: {', '.join(missing_fields)}"
            )
        
        # Obtiene slugs existentes para evitar duplicados
        existing_slugs = set(slug[0] for slug in db.query(Product.slug).filter(Product.slug.isnot(None)).all())
        
        valid_products = []
        validation_errors = []
        warnings = []
        
        for index, row in df.iterrows():
            row_number = index + 2  # +2 porque pandas usa 0-based index y asumimos header en fila 1
            
            try:
                # Extrae y valida los datos
                product_data = {}
                
                # Campos requeridos
                for field in required_fields:
                    if field in column_map:
                        value = row[column_map[field]]
                        
                        if field in ['price_ves', 'price_ref']:
                            product_data[field] = ProductBulkService._parse_numeric_field(value, field)
                        else:
                            product_data[field] = ProductBulkService._sanitize_text_field(value)
                
                # Campos opcionales
                optional_fields = {
                    'brand': 100, 'category': 100, 'subcategory': 100, 'patology': 100,
                    'dosage': 100, 'presentation': 100, 'laboratorio': 100,
                    'registro_sanitario': 100, 'sku': 50
                }
                
                for field, max_len in optional_fields.items():
                    if field in column_map:
                        value = row[column_map[field]]
                        product_data[field] = ProductBulkService._sanitize_text_field(value, max_len)
                
                # Campos de texto largo
                for field in ['contraindicaciones', 'efectos_secundarios']:
                    if field in column_map:
                        value = row[column_map[field]]
                        product_data[field] = ProductBulkService._sanitize_text_field(value)
                
                # Campos de lista
                for field in ['ingredients', 'images']:
                    if field in column_map:
                        value = row[column_map[field]]
                        product_data[field] = ProductBulkService._parse_list_field(value)
                
                # Campos booleanos
                for field in ['in_stock', 'prescription', 'featured', 'is_offer']:
                    if field in column_map:
                        value = row[column_map[field]]
                        product_data[field] = ProductBulkService._parse_boolean_field(value)
                
                # Campos numéricos opcionales
                for field in ['stock', 'original_price']:
                    if field in column_map:
                        value = row[column_map[field]]
                        if not pd.isna(value) and value != '':
                            product_data[field] = ProductBulkService._parse_numeric_field(value, field)
                
                # Campo de imagen principal
                if 'image' in column_map:
                    value = row[column_map['image']]
                    product_data['image'] = ProductBulkService._sanitize_text_field(value)
                
                # Genera slug único
                if product_data.get('name'):
                    product_data['slug'] = ProductBulkService._generate_slug(
                        product_data['name'], existing_slugs
                    )
                
                # Agrega número de fila para referencia
                product_data['row_number'] = row_number
                
                # Valida usando el schema
                product_item = ProductBulkUploadItem(**product_data)
                valid_products.append(product_item)
                
            except Exception as e:
                # TODO BORRAR
                print("ERROR IN PROCESS BULK UPLOAD: " + str(e))
                error_msg = str(e)
                field = "general"
                
                # Intenta extraer el campo específico del error
                if "price" in error_msg.lower():
                    field = "price"
                elif "name" in error_msg.lower():
                    field = "name"
                elif "description" in error_msg.lower():
                    field = "description"
                
                validation_errors.append(ProductValidationError(
                    row_number=row_number,
                    field=field,
                    value=str(row.get(column_map.get(field, ''), '')),
                    error_message=error_msg
                ))
        
        # Agrega advertencias si hay problemas menores
        if len(df) > max_rows:
            warnings.append(f"Se procesaron solo las primeras {max_rows} filas del archivo")
        
        return ProductBulkUploadResult(
            total_rows=len(df),
            valid_products=valid_products,
            validation_errors=validation_errors,
            processed_count=len(valid_products),
            error_count=len(validation_errors),
            warnings=warnings
        )
