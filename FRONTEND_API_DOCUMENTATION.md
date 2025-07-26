# 📖 Documentación API Backend FarmaPlus - Para Equipo Frontend

## 🌐 URL Base y Configuración

**URL Base:** `http://localhost:8000/api/v1`

**Documentación Interactiva:**
- Swagger UI: `http://localhost:8000/api/v1/docs`
- ReDoc: `http://localhost:8000/api/v1/redoc`

## 🔑 Autenticación

La API utiliza **JWT (JSON Web Tokens)** para autenticación. Para endpoints protegidos, incluir el token en el header:

```javascript
headers: {
  'Authorization': 'Bearer YOUR_JWT_TOKEN',
  'Content-Type': 'application/json'
}
```

---

## 📄 PAGINACIÓN MEJORADA

### Estructura de Respuesta Paginada

Todos los endpoints que devuelven listas ahora incluyen metadatos de paginación:

```json
{
  "products": [...],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 156,
    "total_pages": 8,
    "has_next": true,
    "has_prev": false,
    "next_page": 2,
    "prev_page": null
  },
  "filters_applied": {
    "search": "vitamina",
    "category_id": "suplementos",
    "sort_by": "price_asc"
  },
  "total": 156
}
```

### Parámetros de Paginación

- `page` (opcional): Número de página (default: 1)
- `limit` (opcional): Items por página (default: 20, máximo: 100)

---

## 🔓 ENDPOINTS PÚBLICOS (Sin Autenticación)

### 📋 Información General

#### 1. Health Check
```http
GET /public/health
```
**Propósito:** Verificar que la API está funcionando  
**Respuesta:**
```json
{
  "status": "healthy",
  "service": "Farmacia API",
  "version": "1.0.0"
}
```

#### 2. Características del Sistema
```http
GET /public/features
```
**Propósito:** Obtener características y configuraciones públicas del sistema

---

### 🛍️ Catálogo de Productos (MEJORADO)

#### 3. Listar Productos (Catálogo Principal)
```http
GET /public/products?page=1&limit=12&category_id=analgesicos&search=vitamina&sort_by=price_asc
```
**Propósito:** Obtener catálogo completo de productos con filtros avanzados y paginación completa

**Parámetros Query (NUEVOS):**
- `page` (opcional): Número de página (default: 1)
- `limit` (opcional): Productos por página (default: 20, máximo: 100)
- `category_id` (opcional): Filtrar por categoría específica
- `brand_id` (opcional): Filtrar por marca específica
- `search` (opcional): Buscar por nombre, descripción o marca
- `min_price` (opcional): Precio mínimo en VES
- `max_price` (opcional): Precio máximo en VES
- `prescription_required` (opcional): true/false - Solo productos con/sin receta
- `featured_only` (opcional): true/false - Solo productos destacados
- `on_offer` (opcional): true/false - Solo productos en oferta
- `sort_by` (opcional): Ordenamiento
  - `name` - Por nombre (A-Z)
  - `price_asc` - Por precio ascendente
  - `price_desc` - Por precio descendente
  - `rating` - Por calificación (mayor a menor)
  - `newest` - Por fecha de creación (más reciente primero)

**Respuesta Mejorada:**
```json
{
  "products": [
    {
      "id": "uuid-del-producto",
      "name": "Vitamina C 500mg",
      "brand": "Bayer",
      "category": "Vitaminas",
      "price_ves": 25.50,
      "price_ref": 1.20,
      "current_price": 25.50,
      "discount_percentage": 0,
      "image": "https://example.com/image.jpg",
      "rating": 4.5,
      "review_count": 23,
      "in_stock": true,
      "is_available": true,
      "prescription": false,
      "is_offer": false,
      "featured": true,
      "slug": "vitamina-c-500mg-bayer",
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 12,
    "total": 89,
    "total_pages": 8,
    "has_next": true,
    "has_prev": false,
    "next_page": 2,
    "prev_page": null
  },
  "filters_applied": {
    "category_id": "vitaminas",
    "search": "vitamina",
    "sort_by": "price_asc"
  },
  "total": 89
}
```

#### 4. Búsqueda de Productos (MEJORADO)
```http
GET /public/products/search?q=vitamina&page=1&limit=10&category_id=suplementos&sort_by=relevance
```
**Propósito:** Buscar productos con filtros y ordenamiento avanzado

**Parámetros Query (NUEVOS):**
- `q` (requerido): Término de búsqueda (mínimo 2 caracteres)
- `page` (opcional): Número de página
- `limit` (opcional): Resultados por página
- `category_id` (opcional): Filtrar por categoría
- `sort_by` (opcional): Ordenamiento
  - `relevance` - Por relevancia (default)
  - `name` - Por nombre
  - `price_asc` - Por precio ascendente
  - `price_desc` - Por precio descendente
  - `rating` - Por calificación

**Respuesta:** Misma estructura que el catálogo principal

---

### 📂 Categorías y Marcas

#### 6. Listar Categorías
```http
GET /public/categories
```
**Propósito:** Obtener todas las categorías para navegación  
**Uso:** Menús de navegación, filtros

**Respuesta:**
```json
{
  "categories": [
    {
      "id": "analgesicos",
      "name": "Analgésicos",
      "description": "Medicamentos para el dolor"
    }
  ]
}
```

#### 7. Listar Marcas
```http
GET /public/brands
```
**Propósito:** Obtener todas las marcas disponibles  
**Uso:** Filtros por marca

---

### 🚚 Información de Envío y Pago

#### 8. Zonas de Envío
```http
GET /public/shipping-zones
```
**Propósito:** Obtener zonas de envío disponibles y precios  
**Uso:** Calculadora de envío, checkout

**Respuesta:**
```json
{
  "shipping_zones": [
    {
      "id": "caracas",
      "name": "Caracas",
      "price": 5.00,
      "delivery_days": "1-2"
    }
  ]
}
```

#### 9. Métodos de Pago
```http
GET /public/payment-methods
```
**Propósito:** Obtener métodos de pago disponibles  
**Uso:** Proceso de checkout

---

## 🔐 ENDPOINTS DE AUTENTICACIÓN

### 👤 Registro y Login

#### 10. Registro Usuario Natural (Persona)
```http
POST /auth/register/natural
```
**Body:**
```json
{
  "email": "usuario@email.com",
  "first_name": "Juan",
  "last_name": "Pérez",
  "cedula": "12345678",
  "password": "contraseña123",
  "phone": "+58-414-1234567",
  "preferred_currency": "VES",
  "birth_date": "1990-01-01",
  "address": "Dirección completa"
}
```

#### 11. Registro Usuario Jurídico (Empresa/Farmacia)
```http
POST /auth/register/juridico
```
**Body:**
```json
{
  "email": "empresa@email.com",
  "company_name": "Farmacia ABC",
  "rif": "J-12345678-9",
  "password": "contraseña123",
  "phone": "+58-212-1234567",
  "representante_legal_nombre": "Dr. Carlos González",
  "representante_legal_cedula": "87654321",
  "direccion_establecimiento": "Av. Principal 123"
}
```

#### 12. Iniciar Sesión
```http
POST /auth/login
```
**Body:**
```json
{
  "email": "usuario@email.com",
  "password": "contraseña123"
}
```

**Respuesta:**
```json
{
  "access_token": "jwt-token-aqui",
  "refresh_token": "refresh-token-aqui",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "user-id",
    "email": "usuario@email.com",
    "name": "Juan Pérez",
    "role": "user"
  }
}
```

#### 13. Refrescar Token
```http
POST /auth/refresh
```
**Body:**
```json
{
  "refresh_token": "refresh-token-aqui"
}
```

#### 14. Obtener Información del Usuario Actual
```http
GET /auth/me
```
**Headers:** `Authorization: Bearer jwt-token`

---

## 🔒 ENDPOINTS PARA USUARIOS AUTENTICADOS

### ❤️ Favoritos

#### 15. Obtener Lista de Favoritos
```http
GET /api/v1/favorites
```
**Headers:** `Authorization: Bearer jwt-token`  
**Propósito:** Obtener productos favoritos del usuario

#### 16. Agregar a Favoritos
```http
POST /api/v1/favorites
```
**Headers:** `Authorization: Bearer jwt-token`  
**Body:**
```json
{
  "product_id": "uuid-del-producto"
}
```

#### 17. Eliminar de Favoritos
```http
DELETE /api/v1/favorites/{favorite_id}
```
**Headers:** `Authorization: Bearer jwt-token`

### 🛒 Carrito de Compras (Pendiente de implementación)
*Estos endpoints están planificados pero aún no implementados:*

#### 18. Ver Carrito
```http
GET /cart
```

#### 19. Agregar al Carrito
```http
POST /cart/items
```

#### 20. Actualizar Cantidad
```http
PUT /cart/items/{item_id}
```

#### 21. Eliminar del Carrito
```http
DELETE /cart/items/{item_id}
```

---

## 👑 ENDPOINTS DE ADMINISTRADOR

*Requieren rol de administrador*

### 📊 Dashboard Administrativo

#### 22. Dashboard de Administración
```http
GET /admin/dashboard
```
**Headers:** `Authorization: Bearer admin-jwt-token`  
**Propósito:** Obtener métricas y estadísticas generales

#### 23. Listar Todos los Usuarios
```http
GET /admin/users?page=1&limit=20&role_filter=user
```
**Headers:** `Authorization: Bearer admin-jwt-token`

#### 24. Gestión de Roles
```http
POST /admin/users/{user_id}/promote
PUT /admin/users/{user_id}/ban
PUT /admin/users/{user_id}/unban
```

---

## 🔧 CÓDIGOS DE RESPUESTA HTTP

- **200 OK**: Operación exitosa
- **201 Created**: Recurso creado exitosamente
- **400 Bad Request**: Error en los datos enviados
- **401 Unauthorized**: Token inválido o faltante
- **403 Forbidden**: Sin permisos para la operación
- **404 Not Found**: Recurso no encontrado
- **422 Unprocessable Entity**: Error de validación
- **500 Internal Server Error**: Error interno del servidor

## 📝 Estructura de Respuestas de Error

```json
{
  "detail": "Descripción del error",
  "success": false,
  "errors": [
    {
      "field": "email",
      "message": "Email ya está registrado"
    }
  ]
}
```

---

## 🚀 GUÍA DE IMPLEMENTACIÓN PARA FRONTEND

### 1. Configuración Inicial

```javascript
// config/api.js
const API_BASE_URL = 'http://localhost:8000/api/v1';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor para añadir token automáticamente
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```

### 2. Servicio de Productos

```javascript
// services/productService.js
export const productService = {
  // Obtener catálogo
  async getProducts(filters = {}) {
    const params = new URLSearchParams(filters);
    const response = await apiClient.get(`/public/products?${params}`);
    return response.data;
  },

  // Obtener detalle
  async getProduct(productId) {
    const response = await apiClient.get(`/public/products/${productId}`);
    return response.data;
  },

  // Buscar productos
  async searchProducts(query, page = 1, limit = 12) {
    const response = await apiClient.get(`/public/products/search`, {
      params: { q: query, page, limit }
    });
    return response.data;
  }
};
```

### 3. Servicio de Autenticación

```javascript
// services/authService.js
export const authService = {
  async login(email, password) {
    const response = await apiClient.post('/auth/login', {
      email,
      password
    });
    
    if (response.data.access_token) {
      localStorage.setItem('access_token', response.data.access_token);
      localStorage.setItem('refresh_token', response.data.refresh_token);
    }
    
    return response.data;
  },

  async register(userData) {
    const response = await apiClient.post('/auth/register/natural', userData);
    return response.data;
  },

  async getCurrentUser() {
    const response = await apiClient.get('/auth/me');
    return response.data;
  },

  logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  }
};
```

### 4. Servicio de Favoritos

```javascript
// services/favoritesService.js
export const favoritesService = {
  async getFavorites() {
    const response = await apiClient.get('/api/v1/favorites');
    return response.data;
  },

  async addToFavorites(productId) {
    const response = await apiClient.post('/api/v1/favorites', {
      product_id: productId
    });
    return response.data;
  },

  async removeFromFavorites(favoriteId) {
    const response = await apiClient.delete(`/api/v1/favorites/${favoriteId}`);
    return response.data;
  }
};
```

---

## 🎯 CASOS DE USO PRINCIPALES

### 1. **Página de Inicio**
- Obtener productos destacados: `GET /public/products?featured=true`
- Obtener categorías: `GET /public/categories`
- Obtener ofertas: `GET /public/products?is_offer=true`

### 2. **Catálogo de Productos**
- Listar productos con paginación: `GET /public/products?page=1&limit=12`
- Filtrar por categoría: `GET /public/products?category_id=analgesicos`
- Buscar productos: `GET /public/products/search?q=vitamina`

### 3. **Detalle de Producto**
- Obtener información completa: `GET /public/products/{id}`
- Agregar a favoritos (usuario logueado): `POST /api/v1/favorites`

### 4. **Registro/Login**
- Registro: `POST /auth/register/natural`
- Login: `POST /auth/login`
- Obtener perfil: `GET /auth/me`

### 5. **Lista de Favoritos**
- Ver favoritos: `GET /api/v1/favorites`
- Eliminar favorito: `DELETE /api/v1/favorites/{id}`

---

## 🔄 MANEJO DE ESTADOS Y ERRORES

```javascript
// Ejemplo de manejo de estados en React
const [products, setProducts] = useState([]);
const [loading, setLoading] = useState(false);
const [error, setError] = useState(null);

const fetchProducts = async (filters = {}) => {
  try {
    setLoading(true);
    setError(null);
    const data = await productService.getProducts(filters);
    setProducts(data);
  } catch (err) {
    setError(err.response?.data?.detail || 'Error al cargar productos');
  } finally {
    setLoading(false);
  }
};
```

---

## 📧 INFORMACIÓN DE CONTACTO Y SOPORTE

**Usuario Administrador de Prueba:**
- **Email:** `admin@admin.com`
- **Password:** `admin`

**Para Desarrollo:**
- Documentación Swagger: `http://localhost:8000/api/v1/docs`
- Health Check: `http://localhost:8000/public/health`

---

## 🚨 NOTAS IMPORTANTES

1. **Tokens JWT:** Expiran en 1 hora, usar refresh token para renovar
2. **Paginación:** Por defecto 12 elementos por página
3. **Imágenes:** URLs de placeholder, reemplazar con imágenes reales
4. **Monedas:** Soporte para VES (Bolívares) y USD (Dólares)
5. **CORS:** Configurado para desarrollo local
6. **Validaciones:** La API valida todos los datos de entrada

## 🛠️ PRÓXIMAS FUNCIONALIDADES

- Carrito de compras completo
- Sistema de órdenes/pedidos
- Reseñas y calificaciones
- Sistema de notificaciones
- Gestión de direcciones
- Historial de compras