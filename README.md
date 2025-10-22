# 🚀 FarmaPlus Backend API

Sistema backend completo para farmacia online construido con FastAPI, PostgreSQL y diseñado para integrarse perfectamente con el frontend React.

## 📋 Características

- 🔐 **Autenticación JWT completa** (registro, login, verificación de email, recuperación de contraseña)
- 💊 **Gestión completa de productos farmacéuticos** con categorías, marcas y patologías
- 🛒 **Sistema de carrito de compras** persistente
- 📦 **Gestión de pedidos** con seguimiento y estados
- ⭐ **Sistema de reseñas y calificaciones**
- 💰 **Sistema unificado USD** (almacenamiento en USD, conversión VES en pagos)
- 🔗 **URLs obfuscadas para productos** (SEO-friendly)
- 🔍 **Búsqueda avanzada y filtros**
- 📧 **Sistema de notificaciones por email**
- 🐳 **Dockerizado** para fácil deployment
- 📚 **Documentación automática** con Swagger/OpenAPI

## 💱 Sistema Unificado de Monedas (USD)

### ¿Qué cambió?

El sistema ahora opera completamente en **USD** internamente:

- ✅ **Almacenamiento**: Todo se guarda en USD (precios, totales, créditos)
- ✅ **Conversión**: Solo cuando el usuario paga en VES (se convierte a USD)
- ✅ **Frontend**: Maneja la conversión USD→VES para display
- ✅ **Trazabilidad**: Se guarda la moneda original del pago y la tasa usada

### Cambios en los Endpoints

#### Crear Orden
```json
{
  "payment_currency": "VES",  // Nuevo campo: "USD" o "VES"
  "payment_method": "transfer",
  ...
}
```

#### Pago de Crédito
```json
{
  "amount": 2050.00,
  "payment_currency": "VES",  // Renombrado de "currency"
  ...
}
```

**📚 Documentación completa**: Ver [`GUIA_CAMBIOS_USD_UNIFICADO.md`](GUIA_CAMBIOS_USD_UNIFICADO.md)

## 🛠️ Tecnologías

- **FastAPI** - Framework web moderno y rápido
- **PostgreSQL** - Base de datos principal (SQLite en desarrollo)
- **SQLAlchemy** - ORM para Python
- **Pydantic** - Validación de datos
- **JWT** - Autenticación basada en tokens
- **Redis** - Cache y sesiones (opcional)
- **Docker** - Containerización
- **Alembic** - Migraciones de base de datos

## 🚀 Instalación

### Opción 1: Docker (Recomendado)

1. **Clona el repositorio:**
```bash
git clone <url-del-repo>
cd Backend-farmacia
```

2. **Configura las variables de entorno:**
```bash
# Copia el archivo de ejemplo y edítalo
cp env_example.txt .env
```

3. **Ejecuta con Docker Compose:**
```bash
docker-compose up -d
```

La API estará disponible en: `http://localhost:8000`

### Opción 2: Instalación Local

1. **Requisitos previos:**
   - Python 3.11+
   - PostgreSQL 12+
   - Redis (opcional)

2. **Instala las dependencias:**
```bash
pip install -r requirements.txt
```

3. **Configura la base de datos:**
```bash
# Crear base de datos PostgreSQL
createdb farmaplus
```

4. **Configura las variables de entorno:**
```bash
# Copia y edita el archivo .env
cp env_example.txt .env
```

5. **Ejecuta la aplicación:**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## ⚙️ Configuración

### Variables de Entorno

Crea un archivo `.env` en la raíz del proyecto con las siguientes variables:

```env
# Base de datos
DATABASE_URL=postgresql://farmaplus:password@localhost:5432/farmaplus

# Seguridad
SECRET_KEY=tu-clave-secreta-muy-segura
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS
ALLOWED_ORIGINS=["http://localhost:3000", "http://localhost:5173"]

# Email (opcional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu-email@gmail.com
SMTP_PASSWORD=tu-app-password

# Archivos
UPLOAD_DIR=uploads
MAX_FILE_SIZE=5242880

# Modo debug
DEBUG=True
```

## 📚 Documentación

### Documentación de la API

Una vez que la aplicación esté ejecutándose, puedes acceder a:

- **Documentación Swagger:** `http://localhost:8000/api/v1/docs`
- **Documentación ReDoc:** `http://localhost:8000/api/v1/redoc`
- **OpenAPI JSON:** `http://localhost:8000/api/v1/openapi.json`

### Documentación Técnica

- **[GUIA_CAMBIOS_USD_UNIFICADO.md](GUIA_CAMBIOS_USD_UNIFICADO.md)** - Guía completa de cambios del sistema unificado USD
  - Cambios en la base de datos
  - Cambios en los endpoints
  - Flujos de trabajo
  - Ejemplos de uso
  - Guía de migración para frontend

- **[PLAN_MIGRACION_USD.md](PLAN_MIGRACION_USD.md)** - Plan técnico detallado de la migración a USD
  - Estrategia de migración
  - Cambios en modelos y servicios
  - Scripts de migración
  - Procedimiento de rollback

## 🔌 Endpoints Principales

### Autenticación
```
POST   /api/v1/auth/register          # Registrar usuario
POST   /api/v1/auth/login             # Iniciar sesión
POST   /api/v1/auth/refresh           # Actualizar token
GET    /api/v1/auth/me                # Información del usuario
POST   /api/v1/auth/verify-email      # Verificar email
POST   /api/v1/auth/forgot-password   # Recuperar contraseña
POST   /api/v1/auth/reset-password    # Restablecer contraseña
```

### Productos (próximamente)
```
GET    /api/v1/products/              # Listar productos
GET    /api/v1/products/{id}          # Detalle de producto
GET    /api/v1/products/search        # Búsqueda de productos
GET    /api/v1/products/categories    # Categorías
GET    /api/v1/products/featured      # Productos destacados
GET    /api/v1/products/offers        # Ofertas
```

### Carrito (próximamente)
```
POST   /api/v1/cart/add               # Agregar al carrito
GET    /api/v1/cart/                  # Ver carrito
PUT    /api/v1/cart/update/{id}       # Actualizar cantidad
DELETE /api/v1/cart/remove/{id}       # Remover del carrito
```

## 🧪 Ejemplos de Uso

### Registro de Usuario

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "usuario@example.com",
    "name": "Juan Pérez",
    "password": "MiPassword123",
    "confirm_password": "MiPassword123",
    "user_type": "natural",
    "phone": "+58414123456",
    "preferred_currency": "VES"
  }'
```

### Iniciar Sesión

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "usuario@example.com",
    "password": "MiPassword123"
  }'
```

### Obtener Información del Usuario

```bash
curl -X GET "http://localhost:8000/api/v1/auth/me" \
  -H "Authorization: Bearer tu-access-token"
```

## 🏗️ Estructura del Proyecto

```
Backend-farmacia/
├── app/
│   ├── __init__.py
│   ├── main.py                    # Aplicación FastAPI principal
│   │   ├── config/
│   │   │   ├── settings.py            # Configuraciones
│   │   │   └── database.py            # Configuración DB
│   │   ├── core/
│   │   │   ├── security.py            # JWT, hashing
│   │   │   ├── dependencies.py        # Dependencias comunes
│   │   │   └── exceptions.py          # Excepciones personalizadas
│   │   ├── models/                    # Modelos SQLAlchemy
│   │   │   ├── user.py
│   │   │   ├── product.py
│   │   │   ├── order.py
│   │   │   └── ...
│   │   ├── schemas/                   # Esquemas Pydantic
│   │   │   ├── user.py
│   │   │   ├── product.py
│   │   │   ├── auth.py
│   │   │   └── ...
│   │   ├── api/v1/endpoints/          # Endpoints de la API
│   │   │   ├── auth.py
│   │   │   ├── products.py
│   │   │   └── ...
│   │   ├── services/                  # Lógica de negocio
│   │   │   ├── auth_service.py
│   │   │   ├── product_service.py
│   │   │   └── ...
│   │   └── utils/                     # Utilidades
│   │       ├── url_obfuscation.py
│   │       └── ...
│   ├── requirements.txt
│   ├── docker-compose.yml
│   ├── Dockerfile
│   └── README.md
```

## 🔧 Desarrollo

### Agregar Nuevos Endpoints

1. Crea el modelo en `app/models/`
2. Define los esquemas en `app/schemas/`
3. Implementa la lógica en `app/services/`
4. Crea los endpoints en `app/api/v1/endpoints/`
5. Registra el router en `app/api/v1/router.py`

### Migraciones de Base de Datos

```bash
# Crear migración
alembic revision --autogenerate -m "descripción"

# Aplicar migraciones
alembic upgrade head
```

## 🧪 Testing

```bash
# Ejecutar tests
pytest

# Con cobertura
pytest --cov=app
```

## 🚀 Deployment

### Producción con Docker

1. **Construye la imagen:**
```bash
docker build -t farmaplus-api .
```

2. **Ejecuta en producción:**
```bash
docker run -d \
  --name farmaplus-api \
  -p 8000:8000 \
  --env-file .env.production \
  farmaplus-api
```

### Variables de Entorno para Producción

```env
DEBUG=False
SECRET_KEY=tu-clave-super-secreta-en-produccion
DATABASE_URL=postgresql://user:pass@prod-db:5432/farmaplus
ALLOWED_ORIGINS=["https://tu-dominio.com"]
```

## 🤝 Contribuir

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/nueva-caracteristica`)
3. Commit tus cambios (`git commit -am 'Agrega nueva característica'`)
4. Push a la rama (`git push origin feature/nueva-caracteristica`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto está bajo la licencia MIT. Ver el archivo `LICENSE` para más detalles.

## 📞 Soporte

Para soporte o preguntas:
- Abre un issue en GitHub
- Contacta al equipo de desarrollo

---

**Hecho con ❤️ para FarmaPlus** 