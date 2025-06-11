# 🧪 **GUÍA DE TESTING - FARMAPLUS BACKEND**

Esta guía te ayudará a entender y usar el sistema de testing implementado para el backend de FarmaPlus.

## 📋 **ÍNDICE**

1. [Configuración](#configuración)
2. [Estructura de Testing](#estructura-de-testing)
3. [Tipos de Tests](#tipos-de-tests)
4. [Ejecutar Tests](#ejecutar-tests)
5. [Fixtures Disponibles](#fixtures-disponibles)
6. [Buenas Prácticas](#buenas-prácticas)
7. [Agregar Nuevos Tests](#agregar-nuevos-tests)
8. [Coverage](#coverage)

---

## 🛠️ **CONFIGURACIÓN**

### Instalar Dependencias

```bash
pip install -r requirements.txt
```

### Dependencias de Testing

- **pytest**: Framework principal de testing
- **pytest-asyncio**: Soporte para tests asíncronos
- **pytest-cov**: Cobertura de código
- **pytest-mock**: Mocking avanzado
- **httpx**: Cliente HTTP para tests de FastAPI
- **faker**: Generación de datos falsos

---

## 📁 **ESTRUCTURA DE TESTING**

```
app/tests/
├── __init__.py              # Package init
├── conftest.py              # Configuración y fixtures globales
├── test_endpoints.py        # Tests de endpoints HTTP
├── test_models.py           # Tests de modelos SQLAlchemy
├── test_services.py         # Tests de servicios de negocio
└── test_integration.py      # Tests de integración

pytest.ini                  # Configuración de pytest
run_tests.py                # Script para ejecutar tests
```

---

## 🎯 **TIPOS DE TESTS**

### **Tests Unitarios** (`@pytest.mark.unit`)
- Prueban funciones individuales
- Sin dependencias externas
- Rápidos de ejecutar

### **Tests de Integración** (`@pytest.mark.integration`)
- Prueban flujos completos
- Incluyen base de datos
- Simulan comportamiento real

### **Tests de Endpoints** (`@pytest.mark.auth`)
- Prueban API endpoints
- Verifican responses HTTP
- Validan autenticación

---

## 🚀 **EJECUTAR TESTS**

### **Usando el Script**

```bash
# Ver opciones disponibles
python run_tests.py

# Ejecutar todos los tests
python run_tests.py all

# Tests de autenticación únicamente
python run_tests.py auth

# Tests con cobertura
python run_tests.py coverage

# Tests rápidos (sin los marcados como 'slow')
python run_tests.py fast
```

### **Usando pytest directamente**

```bash
# Todos los tests
pytest app/tests/ -v

# Tests específicos por archivo
pytest app/tests/test_endpoints.py -v

# Tests específicos por clase
pytest app/tests/test_endpoints.py::TestAuthEndpoints -v

# Tests específicos por función
pytest app/tests/test_endpoints.py::TestAuthEndpoints::test_register_success -v

# Tests por marcador
pytest app/tests/ -m "auth" -v
pytest app/tests/ -m "unit" -v
pytest app/tests/ -m "not slow" -v

# Con output detallado
pytest app/tests/ -v -s

# Con cobertura
pytest app/tests/ --cov=app --cov-report=html -v
```

---

## 🔧 **FIXTURES DISPONIBLES**

### **Base de Datos**
- `db`: Sesión de base de datos SQLite en memoria
- `client`: Cliente de pruebas FastAPI

### **Usuarios de Prueba**
- `test_user_data`: Datos para registro de usuario natural
- `test_user_data_juridico`: Datos para registro de usuario jurídico
- `test_user`: Usuario creado en BD (natural)
- `test_admin_user`: Usuario administrador

### **Autenticación**
- `access_token`: Token de acceso para usuario de prueba
- `auth_headers`: Headers con autorización Bearer
- `admin_auth_headers`: Headers con token de admin
- `test_login_data`: Credenciales válidas
- `invalid_login_data`: Credenciales inválidas

### **Datos de Ejemplo**
- `sample_product_data`: Datos de producto
- `sample_order_data`: Datos de pedido

---

## ✅ **BUENAS PRÁCTICAS**

### **Naming Conventions**

```python
# Archivos de test
test_feature.py

# Clases de test
class TestFeatureName:

# Funciones de test
def test_specific_behavior(self):
def test_edge_case_scenario(self):
def test_error_handling(self):
```

### **Estructura de Test**

```python
def test_feature_behavior(self, client, fixture):
    """Test descripción clara de qué se está probando"""
    
    # Arrange - Preparar datos
    test_data = {"key": "value"}
    
    # Act - Ejecutar acción
    response = client.post("/endpoint", json=test_data)
    
    # Assert - Verificar resultados
    assert response.status_code == 200
    assert response.json()["success"] is True
```

### **Tests Descriptivos**

```python
# ✅ Bien
def test_user_registration_with_valid_data_creates_active_user(self):
    
# ❌ Mal
def test_register(self):
```

### **Usar Marcadores**

```python
@pytest.mark.unit
def test_password_hashing():
    pass

@pytest.mark.integration
def test_complete_registration_flow():
    pass

@pytest.mark.slow
def test_heavy_database_operation():
    pass
```

---

## 🆕 **AGREGAR NUEVOS TESTS**

### **1. Para Nuevos Endpoints**

```python
# En test_endpoints.py
class TestNewFeatureEndpoints:
    """Tests para endpoints de nueva funcionalidad"""
    
    def test_create_feature_success(self, client, auth_headers):
        """Test creación exitosa de feature"""
        data = {"name": "Test Feature"}
        response = client.post("/api/v1/features", json=data, headers=auth_headers)
        
        assert response.status_code == 201
        assert response.json()["name"] == "Test Feature"
    
    def test_create_feature_unauthorized(self, client):
        """Test creación sin autorización"""
        data = {"name": "Test Feature"}
        response = client.post("/api/v1/features", json=data)
        
        assert response.status_code == 403
```

### **2. Para Nuevos Modelos**

```python
# En test_models.py
class TestNewModel:
    """Tests para nuevo modelo"""
    
    def test_create_model_instance(self, db):
        """Test crear instancia del modelo"""
        instance = NewModel(name="Test", value=123)
        db.add(instance)
        db.commit()
        
        assert instance.id is not None
        assert instance.name == "Test"
    
    def test_model_validation(self, db):
        """Test validaciones del modelo"""
        with pytest.raises(ValueError):
            NewModel(name="", value=-1)
```

### **3. Para Nuevos Servicios**

```python
# En test_services.py
class TestNewService:
    """Tests para nuevo servicio"""
    
    @pytest.mark.asyncio
    async def test_service_method_success(self, db):
        """Test método exitoso del servicio"""
        result = await NewService.method_name(db, "param")
        
        assert result.success is True
        assert result.data is not None
```

---

## 📊 **COVERAGE**

### **Generar Reporte de Cobertura**

```bash
# Ejecutar tests con coverage
python run_tests.py coverage

# O directamente con pytest
pytest app/tests/ --cov=app --cov-report=html --cov-report=term-missing
```

### **Ver Reporte HTML**

```bash
# Se genera en htmlcov/index.html
open htmlcov/index.html  # macOS
start htmlcov/index.html # Windows
```

### **Objetivos de Coverage**

- **Mínimo**: 80% de cobertura general
- **Objetivo**: 90% de cobertura general
- **Crítico**: 95% en módulos de autenticación y seguridad

---

## 🎯 **EJEMPLOS COMPLETOS**

### **Test de Endpoint Completo**

```python
class TestProductEndpoints:
    """Tests para endpoints de productos"""
    
    def test_create_product_success(self, client, admin_auth_headers, sample_product_data):
        """Test creación exitosa de producto"""
        response = client.post(
            "/api/v1/products", 
            json=sample_product_data, 
            headers=admin_auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        
        assert data["name"] == sample_product_data["name"]
        assert data["price_ves"] == sample_product_data["price_ves"]
        assert "id" in data
        assert "created_at" in data
    
    def test_get_products_pagination(self, client):
        """Test paginación de productos"""
        response = client.get("/api/v1/products?page=1&size=10")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "size" in data
```

### **Test de Flujo de Integración**

```python
@pytest.mark.integration
def test_complete_purchase_flow(self, client, test_user, sample_product_data):
    """Test flujo completo de compra"""
    
    # 1. Login
    login_response = client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "testpass123"
    })
    tokens = login_response.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    
    # 2. Agregar al carrito
    cart_response = client.post("/api/v1/cart/add", json={
        "product_id": "product-123",
        "quantity": 2
    }, headers=headers)
    assert cart_response.status_code == 200
    
    # 3. Crear orden
    order_response = client.post("/api/v1/orders", json={
        "payment_method": "credit_card"
    }, headers=headers)
    assert order_response.status_code == 201
    
    # 4. Verificar estado
    order_data = order_response.json()
    status_response = client.get(f"/api/v1/orders/{order_data['id']}", headers=headers)
    assert status_response.status_code == 200
```

---

## 🔄 **FLUJO DE DESARROLLO CON TESTS**

### **1. Test-Driven Development (TDD)**

```python
# 1. Escribir test que falle
def test_new_feature_should_return_success():
    # Arrange
    data = {"input": "test"}
    
    # Act
    result = new_feature_function(data)
    
    # Assert
    assert result.success is True

# 2. Implementar funcionalidad mínima
def new_feature_function(data):
    return {"success": True}

# 3. Refactorizar y mejorar
def new_feature_function(data):
    # Implementación completa
    if not data:
        raise ValueError("Data required")
    return ProcessedResult(success=True, data=process(data))
```

### **2. Testing de Nuevas Features**

1. **Crear tests primero**: Define el comportamiento esperado
2. **Implementar funcionalidad**: Hacer que los tests pasen
3. **Refactorizar**: Mejorar código manteniendo tests verdes
4. **Agregar edge cases**: Tests para casos límite y errores

---

## 🛡️ **TESTING SEGURIDAD**

### **Tests de Autenticación**

```python
def test_endpoint_requires_authentication(self, client):
    """Verificar que endpoint requiere autenticación"""
    response = client.get("/api/v1/protected-endpoint")
    assert response.status_code == 403

def test_invalid_token_rejected(self, client):
    """Verificar que tokens inválidos son rechazados"""
    headers = {"Authorization": "Bearer invalid_token"}
    response = client.get("/api/v1/protected-endpoint", headers=headers)
    assert response.status_code == 401
```

### **Tests de Autorización**

```python
def test_admin_only_endpoint(self, client, auth_headers):
    """Verificar que endpoint solo permite admins"""
    response = client.delete("/api/v1/admin/users/123", headers=auth_headers)
    assert response.status_code == 403  # User is not admin

def test_user_can_only_access_own_data(self, client, auth_headers):
    """Verificar que usuario solo accede a sus datos"""
    response = client.get("/api/v1/users/other-user-id", headers=auth_headers)
    assert response.status_code == 403
```

---

## 📝 **COMANDOS ÚTILES**

```bash
# Ejecutar tests específicos con verbose
pytest app/tests/test_endpoints.py::TestAuthEndpoints::test_register_success -v -s

# Ejecutar tests que contengan una palabra clave
pytest app/tests/ -k "register" -v

# Ejecutar tests pero parar en el primer error
pytest app/tests/ -x

# Ejecutar tests en paralelo (si tienes pytest-xdist)
pytest app/tests/ -n auto

# Ver tests sin ejecutarlos
pytest app/tests/ --collect-only

# Ejecutar solo tests que fallaron la última vez
pytest app/tests/ --lf

# Mostrar los 10 tests más lentos
pytest app/tests/ --durations=10
```

---

¡Con esta guía tienes todo lo necesario para implementar testing como buena práctica en el desarrollo del backend de FarmaPlus! 🚀 