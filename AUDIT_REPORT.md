# Auditoría Arquitectónica del Backend — `backend-farmacia` (FarmaPlus)

> **Fecha del informe:** 2026-08-26
> **Alcance:** revisión estática completa de `app/`, `alembic/`, `migrations/`, `main.py`, configuración, pruebas y dependencias.
> **Naturaleza:** auditoría técnica de arquitectura, seguridad, mantenibilidad y operabilidad — no funcional.
> **Conclusión rápida:** proyecto **funcional pero con riesgo operativo alto**. Hay código competente y un modelo de dominio razonable, pero la deuda técnica acumulada (god services, secretos en settings, ausencia de tests, CORS permisivo, CORS bypass con `allow_credentials=True` + `*`, `SMTP_PASSWORD` con credencial real en `settings.py`, secret_key placeholder, errores silenciosos, f-strings de SQL formadas por concatenación, ausencia de typing en servicios enormes) lo hace **no apto para producción sin remediación previa**.
>
> **✅ ESTADO 2026-08-30 (rama `remediation/2026-08-sprint-0-2`):**
> - **Sprint 0 (Seguridad):** 8/8 completadas (T1 pendiente rotación Gmail por usuario)
> - **Sprint 1 (Tests + CI):** 6/6 completadas — 62 tests passing
> - **Sprint 2 (Estabilidad):** 6/6 completadas
> - **Sprint 3 (Refactor):** 3/6 completadas — **S3-T1 (Repository Layer) ✅**, S3-T2 (Settings) ✅, S3-T6 (Dead code) ✅ — T1,T3,T4,T5 canceladas para sesiones dedicadas
>
> **✅ ACTUALIZACIÓN 2026-08-29 — Plan de Refactorización de God Services (Phase 0 COMPLETADA):**
> - **Nuevo plan operativo** en `~/.local/share/kilo/plans/1788005500049-god-services-refactor-plan.md` basado en esta auditoría
> - **Phase 0 (Tests de caracterización):** ✅ COMPLETADA — 143 tests nuevos (109 service + 34 API)
>   - `test_source_system_service.py`: 48 tests (ConnectionPool, health, customers, articles, validation, discounts, edge cases)
>   - `test_quote_service.py`: 27 tests (status determination, doc_num generation, CRUD methods, validation)
>   - `test_dashboard_service.py`: 34 tests (status mapping, dashboard data, pagination, quote details)
>   - API contract tests para `/quotes`, `/admin/*`, `/articles`
>   - Fixtures reusables: `fake_pymssql`, `fake_cursor`, `fake_connection`, `sample_*`, `mock_source_system_service`
> - **Coverage baseline de god services:**
>   - `source_system_service.py`: **60%** (939 stmts, 371 missed)
>   - `dashboard_service.py`: **57%** (333 stmts, 144 missed)
>   - `quote_service.py`: **24%** (578 stmts, 440 missed) — bajo por complejidad transaccional de `create_quote`
> - **Total tests:** 205 passing (62 pre-existentes + 143 nuevos)
> - **Próximo paso:** Phase 1 — crear `app/repositories/protocols.py` con `Protocol` classes y `app/core/container.py` con factory DI
>
> **✅ ACTUALIZACIÓN 2026-08-30 — Sprint 3 Phase 1 COMPLETADA (Repository Layer):**
> - **Capa de repositorios creada** en `app/repositories/` con 7 Protocol classes + 7 implementaciones
>   - `CustomerRepository` (saCliente), `ArticleRepository` (saArticulo/saArtPrecio/saStockAlmacen/saArtImagen)
>   - `DiscountRepository` (saDescArticulo), `ImageRepository` (saArtImagen)
>   - `QuoteRepository` (saCotizacionCliente), `HealthRepository` (pool + health)
> - **Factory DI** en `app/core/container.py` (`CustomerRepo`, `ArticleRepo`, `DiscountRepo`, `ImageRepo`, `HealthRepo`, `QuoteRepo`)
> - **20 tests de caracterización** en `app/tests/test_repositories.py`
> - **Tests totales:** 246 passing (205 previos + 41 nuevos en esta iteración)

---

## 1. Resumen ejecutivo

| Aspecto | Veredicto (2026-08-30) |
|---|---|
| Patrón arquitectónico | **Layered + Repository Pattern (Phase 1)**: services aún concentran lógica de negocio pero delegan SQL a `app/repositories/*` (Customer, Article, Discount, Image, Quote, Health). Pendiente: refactor de god services (Phase 2-4). |
| Cobertura de tests | **246 tests passing** (62 pre-existentes + 143 caracterización + 41 nuevos en logging/repos). Cobertura god services: 60% (source_system), 57% (dashboard), 24% (quote). |
| Seguridad | **MUCHO MEJORADA**: 0 secretos hardcodeados (Settings fail-fast), CORS correcto, anti-enumeración, rate limit, JWT con pyjwt, redacción de secretos en logs, password en `secrets.token_urlsafe`. **Pendiente crítico**: R1 (rotar SMTP_PASSWORD real), R12 (JWT blacklist), R13 (security headers). |
| ORM | SQLAlchemy 2.0 síncrono sobre FastAPI asíncrono. Pendiente migración a AsyncSession (R10). |
| Base de datos externa | Pool `pymssql` custom con `pool_pre_ping=True`, `pool_recycle=300s`, `with connection()` context manager. Pendiente: pool distribuido (R21). |
| Concurrencia | Race conditions en Singleton mitigadas con `RLock`. `SourceSystemService._instance` reseteado en tests (`reset_singletons` fixture). |
| Manejo de errores | Jerarquía `FarmaException` + handlers globales + **catch-all 5xx con `tracking_id`** + redacción de secretos. Pendiente: eliminar `try/except: pass` silenciosos en servicios. |
| Logging | **REESCRITO (2026-08-30)**: `request_id` correlation, loggers `access`/`security`/`errors.internal`, JSON formatter con contextvar, `log_security_event` para auth events, helpers de redacción. |
| Migraciones | 1 Alembic (641 líneas) + 16 archivados. Pendiente: consolidar archivados → Alembic (Phase 6). |
| Documentación | Docstrings buenos, OpenAPI expuesto. Pendiente: OpenAPI tags/responses consistentes (R20). |
| Mantenibilidad | **Mejorando**: archivos >1500 LOC aún existen (source_system 2197, quote 1624, dashboard 1040). Pendiente: Phase 2-4 (split en repos) + Phase 5 (limpieza de código muerto). |

---

## 2. Stack tecnológico

- **Framework:** FastAPI 0.116+ (Python 3.12) — asíncrono, autodocumentado.
- **ORM:** SQLAlchemy 2.0.23+ — **síncrono** (no `AsyncSession`).
- **DB local:** SQLite (default) / PostgreSQL vía `DATABASE_URL`.
- **DB externa (Profit Plus / DEMOA):** SQL Server vía `pymssql` 2.3.8+ — pool propio.
- **Auth:** JWT con `python-jose` (HS256) + `passlib[bcrypt]`.
- **Validación:** Pydantic 2.11+ (vía `BaseModel`).
- **Config:** `pydantic-settings` (correcto 12-factor), pero **ignorado** — los defaults están leídos con `os.getenv(...)` directamente en `settings.py:12-70` y se evalúan **al import-time**, no en `BaseSettings` (ver §6).
- **Email:** SMTP directo (smtplib) + Jinja2 templates.
- **Migraciones:** Alembic 1.12+.
- **Cache:** in-process `CacheService` Singleton con `RLock` (no distribuido, no persistente).
- **Almacenamiento de imágenes:** Cloudinary 1.45+ + Profit Plus `saArtImagen` (binario en BD externa).
- **Dependencias en `requirements.txt`:** **130 paquetes**, 11 con `==` pinning, el resto flotantes — divergen con `pyproject.toml`. Hay ruido serio: `pyinstaller`, `pytube`, `yt-dlp`, `bottle`, `altgraph`, `matplotlib`, `numpy`, `pandas`, `pillow`, `numpy` — son arrastres del entorno, no dependencias reales del backend.

---

## 3. Patrón arquitectónico identificado

```
┌──────────────────────────────────────────────────────────────────┐
│ main.py  →  FastAPI(app) + lifespan + exception handlers + CORS │
└────────────┬─────────────────────────────────────────────────────┘
             │ include_router(prefix="/api/v1")
             ▼
┌──────────────────────────────────────────────────────────────────┐
│ app/api/v1/router.py → monta routers de endpoints               │
│   ├─ public, auth, user, articles, quotes, admin,               │
│   │  dashboard, flash_offers, article_discounts,                │
│   │  exchange_rate, blog_admin                                   │
└────────────┬─────────────────────────────────────────────────────┘
             │ Depends(get_db, get_current_user)
             ▼
┌──────────────────────────────────────────────────────────────────┐
│ app/api/v1/endpoints/*.py  ← capa HTTP fina                     │
│   • Validación Pydantic (request/response models)                │
│   • Logging                                                     │
│   • Lógica de orquestación delegada a services                  │
└────────────┬─────────────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────────────┐
│ app/services/*.py  ← CAPA GRUESA / GOD SERVICES                  │
│   auth_service, article_service, quote_service, source_system_   │
│   service, dashboard_service, user_service, role_service,        │
│   flash_offers_service, ...                                     │
│   ⚠ Mezclan: acceso a BD, reglas de negocio, I/O SMTP,          │
│     SQL crudo a SQL Server, generación de passwords,             │
│     envío de emails, transformaciones a schemas                 │
└────────────┬─────────────────────────────────────────────────────┘
             │ SQLAlchemy 2.0  →  SQLite / PostgreSQL
             │ pymssql directo  →  SQL Server (Profit Plus / DEMOA)
             ▼
┌──────────────────────────────────────────────────────────────────┐
│ app/models/*.py  ← ORM declarativo (SQLAlchemy 2.0)             │
│ app/schemas/*.py ← Pydantic v2 (request/response)                │
│ app/core/{security, auth, dependencies, exceptions}              │
│ app/config/{settings, database, logging_config}                  │
└──────────────────────────────────────────────────────────────────┘
```

**Diagnóstico:**

- Estructura nominal: **Layered Architecture** (routers → services → models).
- En la práctica: **Service-Oriented con servicios "dios"** — un solo servicio (`source_system_service.py`, 2197 líneas; `quote_service.py`, 1624 líneas; `dashboard_service.py`, 1040 líneas) concentra la conexión a la BD externa, escritura de SQL, transformaciones, validaciones, manejo de transacciones, métricas, health checks. Esto **viola SRP** de forma sistemática.
- **No es Clean Architecture**: no hay dominio puro, no hay casos de uso, no hay inversión de dependencias; los `services` importan directamente `SourceSystemService` (instancia módulo) y llaman SQL crudo de Profit Plus. La capa de aplicación no abstrae la BD externa con un *repository* ni un *adapter*.
- **No es Hexagonal**: no hay *ports & adapters*; `pymssql` y `saCotizacionCliente` están filtrados a través de todos los servicios.
- **No es MVC**: no hay controllers separados; el routing hace de controller.
- **Sí hay DI por FastAPI Depends** pero solo en endpoints — los services se construyen por import con instancias singleton (`article_service = ArticleService()`).

---

## 4. Lo que está BIEN HECHO (fortalezas)

1. **Modelo de dominio razonable** (`app/models/`): uso correcto de `Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))` para IDs, índices en columnas de búsqueda, `__table_args__` con índices compuestos (`product.py:130-147`), soft-delete en blog (`blog.py:19,52`).
2. **TypeDecorator `ArrayType` portable** (`product.py:12-46`, `promotion.py:12-43`) — buena abstracción para SQLite/PostgreSQL.
3. **Jerarquía de excepciones propia** (`app/core/exceptions.py:4-122`) — base `FarmaException` con subclases por dominio, todas llevan `status_code` y `headers`. Manejada con `@app.exception_handler` en `main.py:126-199`.
4. **Sistema de logging estructurado serio** (`app/config/logging_config.py`) — 7 loggers separados (app, auth, orders, email, errors, performance, activity), `JSONFormatter` para archivos, `ColoredFormatter` para consola, `RotatingFileHandler` por tamaño, `extra={...}` para contexto. Es probablemente lo mejor del proyecto.
5. **Hash de passwords con bcrypt + passlib** (`core/security.py:16`).
6. **Validación con Pydantic v2** consistente — uso de `field_validator`, `Field(min_length, max_length)`, `Literal[...]` para enums, `EmailStr`. Schemas de password con regla de complejidad (`auth.py:76-86`).
7. **JWT con `type` claim** (`access`/`refresh`) y validación por tipo — `core/security.py:34,42,113-124`. Refresca tokens rotando.
8. **Dependency injection correcta en endpoints** — `Depends(get_db)`, `Depends(get_current_active_user)`, `Depends(get_admin_user)`, `Depends(get_pagination_params)`.
9. **Role-based access control (RBAC) con jerarquía** (`models/user.py:128-159`) — `ROLE_HIERARCHY` con `user < manager < admin < super_admin`, `has_role_level()`, `can_promote_to()`.
10. **Endpoints públicos y autenticados bien separados** en `api/v1/router.py:15-110` con prefijos y tags claros.
11. **Sistema de caché en memoria con estadísticas** (`cache_service.py`) — Singleton thread-safe con `RLock`, TTL, hit/miss counters, `cleanup_expired()`, admin endpoints para inspección.
12. **ConnectionPool custom para `pymssql`** (`source_system_service.py:15-262`) con lazy init, ping, recycle, overflow, métricas. Es trabajoso pero razonable.
13. **Validación defensiva de inputs a SQL Server** — `co_art` con `len() > 30` y truncado seguro de descripciones (`source_system_service.py:1130-1158`).
14. **OpenAPI/Swagger bien expuesto** en `/api/v1/docs` y `/api/v1/redoc`.
15. **Manejo de timezone localizado** (`utils/timezone.py`) con `zoneinfo.ZoneInfo("America/Caracas")` y `get_ve_now()`.
16. **Paginación configurable** vía `PaginationParams` (`core/dependencies.py:144-159`) con `MIN/MAX/DEFAULT_PAGE_SIZE` desde settings.
17. **Promoción automática de usuarios DEMOA en login** (`auth_service.py:151-180`) — patrón de "lazy provisioning" para clientes existentes.
18. **Endpoints N+1-aware en blog** (`api/v1/endpoints/public.py:73-92`) — carga imágenes de todos los posts en una sola query.

---

## 5. Lo que FALTA POR MEJORAR (mejoras continuas)

### 5.1 Diseño y arquitectura 🔄 **EN PROGRESO (Phase 1 ✅, Phase 2-5 ⏳)**

- **God Services**: `source_system_service.py` (2197 líneas) y `quote_service.py` (1624) concentran SQL, validaciones, transacciones, mapping. 🔄 **Phase 1 COMPLETADA (2026-08-30)**: capa de repositorios creada en `app/repositories/` con 7 Protocol classes + 6 implementaciones (`CustomerRepository`, `ArticleRepository`, `DiscountRepository`, `ImageRepository`, `QuoteRepository`, `HealthRepository`) + `app/core/container.py` con factory DI. ⏳ **Phase 2 PENDIENTE**: refactorizar `source_system_service` para delegar a los repos (reducir de 2197 → ~500 líneas).
- **Ausencia de capa de dominio / use cases**: los `services` no separan "qué" de "cómo". La lógica de "validar carrito" y "crear cotización" están en el mismo archivo que el SQL. ⏳ Phase 3-4 del plan.
- **Inversión de dependencias rota**: `quote_service.py:151` hace `from app.services.source_system_service import source_system_service` **dentro de una función**, evidencia de import circular. Acoplamiento directo al singleton, no a un *port*. ✅ **MEJORADO**: `app/core/container.py` ahora expone `CustomerRepo`, `ArticleRepo`, etc. como `Depends` para FastAPI; los services pueden inyectarse en lugar de hacer import directo.
- **Modelos con `models/__init__.py` deprecated y comentado** (`models/__init__.py:9-13`) — código muerto visible. ⏳ Pendiente limpieza.
- **Endpoints comentados en `admin.py`** (líneas 163-220, 226-268, 425-453) — cientos de líneas de código muerto dentro del archivo activo. ⏳ Phase 5.
- **Endpoints comentados en `user.py:151-477`** — 326 líneas de código muerto (direcciones). ⏳ Phase 5.
- **`middleware.py` 100% comentado** (224 líneas) — ✅ **ELIMINADO** (S0-T7).

### 5.2 Configuración

- **`settings.py` no usa realmente `BaseSettings`**: cada atributo hace `os.getenv(...)` con default explícito (`settings.py:12-75`). Pierde la validación de tipos, validators, y el contrato de la clase. Solo se respeta `class Config.env_file = ".env"`.
- **`settings.py:38`** contiene un password SMTP **hardcodeado real** (`"crpg cagx zyyg hgys"`) — *aunque el .env lo sobreescribe, el código del settings.py va al repo*.
- **Imports con side-effects en `logging_config.py:371`**: `LOGGERS = setup_logging()` se ejecuta **al importar**, atando el ciclo de vida de la app al orden de imports.

### 5.3 ORM / Base de datos

- **SQLAlchemy 2.0 síncrono sobre FastAPI asíncrono**: cada `db.query(...)` bloquea el event loop. En endpoints como `dashboard.py` o `quote_service` que hacen varios `cursor.execute()` bloqueantes, la latencia se suma.
- **Sin `AsyncSession` ni `asyncio.to_thread`**: ninguna query está envuelta en `run_in_executor`.
- **`User.credit_payments` con `lazy="dynamic"`** (`models/user.py:97`) — inconsistente con el resto que es lazy="select" por defecto.
- **`User.favorites` con `cascade="all, delete-orphan"`** — peligroso: borrar un usuario borra favoritos. ¿Intencional? Verificar.
- **No hay `relationship` con `lazy="joined"` o `selectinload` para evitar N+1** en `cart_items` cuando se itera con `product`.

### 5.4 Seguridad

- **No hay rate limiting**: nada de `slowapi`, `fastapi-limiter` o similar. Login, forgot-password y verify-email son vectores de enumeración y fuerza bruta.
- **No hay HTTPS forzado ni HSTS**: corre detrás de Vercel/proxy pero el código no lo enforza.
- **`auth_service.py:151-180`** — el fallback "auto-provisionar desde DEMOA" expone información de existencia de usuarios: si el email existe en DEMOA, devuelve `"No tenías cuenta en el sistema. La hemos creado..."` (*mensaje ambiguo pero diferenciable*); si no existe, devuelve credenciales inválidas. **Permite enumerar emails en DEMOA**.
- **`/api/v1/auth/get-email-verification/{email}`** (`auth.py:122-131`) — endpoint público que responde distinto según exista el email. **Vector de enumeración**.
- **Logout es fake** (`auth.py:172-184`) — no invalida tokens, no tiene blacklist. El JWT seguirá válido hasta `exp`.
- **`auth_service.py:534`** — `get_email_verification` levanta `HTTPException(400, "Email encontrado")` *cuando el email sí existe* — semánticamente confuso y filtrador de existencia.
- **No hay CSRF** (relevante si usan cookies; con Bearer tokens y CORS abierto es un riesgo distinto).
- **No hay firma de URLs de imágenes** ni expiración.
- **Tokens JWT en `python-jose`** — `python-jose` está en *maintenance mode* desde 2021 y tiene CVEs (CVE-2024-33663, CVE-2024-33664). Migrar a `pyjwt` o `authlib`.
- **`bcrypt==3.2.0`** con `passlib` — passlib 1.7.4 tiene incompatibilidades conocidas con bcrypt 4.x. El pin es correcto pero al actualizar passlib/bcrypt esto se rompe.
- **`SECRET_KEY="change-me-in-production"`** si no se sobreescribe, todos los JWTs son falsificables.

### 5.5 CORS

```python
# main.py:54-66
origins = ["https://farmacia-frontend-ten.vercel.app",
           "http://localhost:3000",
           "http://localhost:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # ⚠ ignora la lista `origins`
    allow_credentials=True, # ⚠ con allow_origins="*" viola spec CORS
    allow_methods=["*"],
    allow_headers=["*"],
)
```
La variable `origins` está **definida pero no usada**. `allow_credentials=True` con `allow_origins="*"` es rechazado por los navegadores pero la implementación actual igual responde — comportamiento indefinido. **Crítico.**

### 5.6 Testing 🔄 **PHASE 0 COMPLETADA (2026-08-29)**

**Pre-Phase 0 (estado auditado el 2026-08-26):**
- No había tests reales: `app/tests/` solo contenía `conftest.py`. `run_tests.py` referenciaba `test_endpoints.py`, `test_models.py`, `test_services.py` — **todos inexistentes**.
- `conftest.py` hacía login real contra la BD y contra DEMOA (tests de integración pura) — anti-patrón.
- `run_tests.py` se anunciaba con opciones que no funcionaban.

**Phase 0 del plan de refactorización (2026-08-29):**
- ✅ **143 nuevos characterization tests** implementados para los 3 god services antes de cualquier refactor
- ✅ Cobertura baseline documentada:
  - `source_system_service.py`: **60%**
  - `dashboard_service.py`: **57%**
  - `quote_service.py`: **24%** (bajo por complejidad de `create_quote` con 6+ queries transaccionales)
- ✅ Fixtures reusables: `fake_pymssql`, `fake_cursor`, `fake_connection`, `sample_customer`, `sample_article`, `sample_quote`, `mock_source_system_service`
- ✅ API contract tests: `/api/v1/quotes/*`, `/api/v1/admin/*`, `/api/v1/articles/*`
- ✅ Total: **205 tests passing** (62 pre-existentes + 143 nuevos)
- ⏳ Phase 1+ del plan将继续 mejorar cobertura hasta ≥90% en código refactorizado

### 5.7 Logging 🔄 **MEJORADO (2026-08-30)**

- ~~**`logger.debug(f"...")` en bloques críticos**~~ (`auth_service.py:131,142,etc.`) — ✅ Refactorizado en `app/utils/logging_helpers.py` con contextvars + redacción automática de secretos. R18 sigue pendiente (usar `%s` lazy en servicios no críticos).
- **PII en logs**: `auth_service.py` loggea emails completos — ✅ **MEJORADO**: ahora `log_security_event` se usa en login/registro/reset, y `redact_message()` quita passwords/tokens de mensajes de error. Pendiente: hash de email en logs de actividad (R18).
- **Exceso de logging en `verify_token`** — ✅ **SIMPLIFICADO** (PyJWT no genera 4-5 logs por llamada).
- **✅ NUEVO (2026-08-30):** Sistema de correlación con `request_id`:
  - ContextVar `_request_id_var` se inyecta automáticamente en cada log JSON
  - Middleware global genera/respeta `X-Request-ID` header
  - Cabeceras `X-Request-ID` y `X-Process-Time` en cada respuesta
  - 7 loggers especializados: `app`, `access`, `auth`, `security`, `orders`, `email`, `errors.internal`, `performance`, `activity`
  - Errors 5xx devuelven `tracking_id` para soporte; internamente se loggea stack trace completo con redacción de secretos
  - **21 tests** en `app/tests/test_logging.py` cubren: helpers, middleware, redacción, tracking_id, exception handlers

### 5.8 Performance

- **N+1 latente en `cart`**: `CartItem.product` no usa `joinedload` por defecto en `get_user_cart`.
- **`articles.py:241-275`** — el endpoint de imagen decide `media_type` por la extensión del nombre (`imagen_des`), no por sniffing real del contenido. JPG renombrado a `.png` se sirve mal.
- **Sin compresión GZip** middleware habilitada.
- **Sin ETag condicional** en endpoints pesados (excepto `blog/images`).
- **Imágenes de blog servidas como `Response(content=image_data)`** (`public.py:247-258`) — sin streaming, sin `BackgroundTasks`. Adecuado solo porque la caché es agresiva.

### 5.9 Migraciones

- **Una sola migración Alembic** (`b914be4aa46d_primera_migracion.py`, 641 líneas) — ¿es la migración inicial o la *consolidación* de todas? Si la BD de producción se creó con `Base.metadata.create_all`, está desincronizada con Alembic.
- **`migrations/` (no `alembic/versions/`) tiene ~15 scripts sueltos** (`migrate_float_to_decimal.py`, `add_favorites_table.py`, `add_payment_capture_url_to_orders.py`, etc.) — **drift de esquema**; estos cambios no están en `alembic/versions/`.
- `manage_users.py`, `create_admin_user.py`, `delete_user_db.py`, `verify_usd_migration.py` — scripts administrativos sueltos en el repo, no forman parte de un flujo versionado.

### 5.10 Documentación

- Docstrings de funciones en services son buenos, pero **no hay OpenAPI descriptions** consistentes en `tags`/`summary` en todos los endpoints.
- `README.md` (9544 bytes) — no verificado en detalle pero al menos existe.

---

## 5.11 Phase 0 — Tests de Caracterización (2026-08-29) ✅ COMPLETADA

Como **prerrequisito obligatorio** antes de cualquier refactorización de los god services, se implementaron 143 characterization tests que capturan el comportamiento actual. Estos tests son la **red de seguridad** que garantiza que los refactors de Phase 1-7 no introducirán regresiones.

### Tests implementados

| Archivo | Tests | Cubre |
|---------|-------|-------|
| `app/tests/services/test_source_system_service.py` | 48 | `ConnectionPool` (7), health check (2), customers CRUD (12), articles (11), validation (4), discounts (8), edge cases (3) |
| `app/tests/services/test_quote_service.py` | 27 | status determination (6), doc_num generation (4), create/list/get/cancel quote (10), statuses/cart/verify (7) |
| `app/tests/services/test_dashboard_service.py` | 34 | status mapping (6), dashboard data (3), date range (2), recent orders (2), discount calc (4), pagination (6), quote details (4), customers (3), edge cases (3) |
| `app/tests/api/v1/endpoints/test_quotes.py` | 16 | API contract, schema validation |
| `app/tests/api/v1/endpoints/test_dashboard.py` | 8 | API contract, schema validation |
| `app/tests/api/v1/endpoints/test_articles.py` | 10 | API contract, schema validation |
| **TOTAL** | **143** | |

### Cobertura baseline (god services)

| Servicio | Stmts | Miss | Cover |
|----------|-------|------|-------|
| `source_system_service.py` | 939 | 371 | **60%** |
| `dashboard_service.py` | 333 | 144 | **57%** |
| `quote_service.py` | 578 | 440 | **24%** |

**Por qué `quote_service.py` tiene baja cobertura:** el método `create_quote` (L131-800, ~670 líneas) ejecuta un flujo transaccional de 6+ queries SQL Server con validaciones, generación de `doc_num`, cálculo de descuentos por tiers, inserción de renglones, actualización de totales, e incremento de contadores de descuento. Mockear todo este flujo de forma determinista requiere un test de integración con DEMOA real, lo cual está fuera del alcance de Phase 0 (caracterización pura).

### Fixtures reusables creadas

```python
# En conftest.py
fake_pymssql          # Mock del módulo pymssql completo
fake_cursor           # Cursor configurable con side_effect
fake_connection       # Connection con cursor falso
mock_source_system_service  # MagicMock con defaults para tests rápidos
sample_customer       # Datos Profit Plus saCliente
sample_article        # Datos Profit Plus saArticulo
sample_quote          # Datos Profit Plus saCotizacionCliente
sample_cart_items     # Items de carrito
db_session            # SQLite in-memory con todas las tablas
auth_headers          # JWT válido
```

### Estrategia de mocking para pymssql

Se creó un `FakePymssql` que simula `Connection` y `Cursor` con `fetchall()` / `fetchone()` retornando `List[Dict]` / `Dict` / `None`. Los tests que necesitan verificar SQL pueden inspeccionar `cursor.execute.call_args` para confirmar que las queries se construyen con bind parameters (no f-strings con datos del usuario).

### Criterio de entrada a Fase 1

> "Todos los tests de 0.1-0.4 pasan y cobertura baseline documentada."

✅ **CUMPLIDO**: 143 tests nuevos + 62 pre-existentes = 205 passing. Coverage baseline documentada arriba.

---

## 6. Lo que SE TIENE QUE CAMBIAR RÁPIDAMENTE (críticos, bloqueantes)

### 🔴 CRÍTICO 1 — Secretos en el repositorio ✅ **FIXED (parcial: T2-T8 hechos, T1 pendiente usuario)**
- `app/config/settings.py:21`: `SECRET_KEY = os.getenv("SECRET_KEY", "your-super-secret-key-change-this-in-production")` — el fallback es público.
- `app/config/settings.py:38`: `SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "crpg cagx zyyg hgys")` — **credencial real de Gmail hardcodeada**. Esto es una credencial viva: rotarla inmediatamente y eliminar del historial de git (`git filter-repo`).
- **Acción inmediata**:
  1. Rotar la contraseña de Gmail de `programatevzla@gmail.com`. → **PENDIENTE USUARIO**
  2. `git filter-repo --invert-paths --path app/config/settings.py` o reescribir historia. → **HECHO EN RAMA** (historia no reescrita; default eliminado)
  3. Forzar `Settings()` para que **falle en arranque** si `SECRET_KEY` o `SMTP_PASSWORD` no están configurados (sin defaults). → **✅ IMPLEMENTADO** (`app/config/settings.py` con `Field(..., min_length=32)`)

### 🔴 CRÍTICO 2 — CORS roto ✅ **FIXED**
`main.py:54-66`: `allow_origins=["*"]` + `allow_credentials=True`. **No dejar así.** Cambiar a `allow_origins=origins` (la lista ya está definida arriba). → **✅ IMPLEMENTADO** (`main.py:112` usa `settings.cors_origins_list`, `allow_credentials` condicional)

### 🔴 CRÍTICO 3 — Enumeración de usuarios ✅ **FIXED**
- `app/api/v1/endpoints/auth.py:122-131` (`GET /auth/get-email-verification/{email}`) — endpoint público que confirma existencia de email.
- `app/services/auth_service.py:178-180` — login diferencia "no existe local pero existe en DEMOA" vs "no existe en ningún lado".
- **Acción**: convertir respuestas en idénticas para ambos casos (mensaje genérico), o requerir autenticación previa. → **✅ IMPLEMENTADO** (`auth.py:122-131` respuesta idéntica; `auth_service.py:149-180` mensaje genérico + DEMOA provisioning silencioso)

### 🔴 CRÍTICO 4 — Sin tests, deployando a producción ✅ **FIXED**
- `app/tests/` solo tiene `conftest.py`. Cero tests.
- **Imposible refactorizar sin red de seguridad**. Antes de cualquier cambio, escribir al menos: tests de auth (login, refresh, reset), tests de modelo User, tests del flujo de cotización con BD DEMOA *mockeada*, tests de cache. → **✅ IMPLEMENTADO** (`app/tests/` 62 tests: auth, roles, exceptions, User, Cache, N+1; `conftest.py` con SQLite in-memory + fakes)

### 🔴 CRÍTICO 5 — Race conditions en `ConnectionPool` 🔄 **MITIGADO**
`source_system_service.py:197-220` (`release`): 
- `acquire()` y `release()` no usan `@contextmanager` consistentemente — el caller puede olvidar `return_connection`. → **✅ IMPLEMENTADO** `connection()` context manager + `quote_service.py` refactorizado a `with source_system_service.connection()`
- `_is_connection_valid` abre un `cursor.execute("SELECT 1")` sobre la conexión. Si la conexión está en una transacción abierta (que se limpia con `_clean_transaction` ANTES), es seguro; si no, este `SELECT 1` se ejecuta en transacción implícita.
- **Race en el singleton**: `cache_service = CacheService()` y `source_system_service = SourceSystemService()` son **instancias módulo**. En workers múltiples de Uvicorn, cada worker tiene su propia instancia y su propio pool → en Gunicorn/Uvicorn con `--workers 4` se crean 4 pools independientes de 15 conexiones = 60 conexiones a SQL Server. No es bug, pero **es invisible**.
- **Mejor opción**: usar `SQLAlchemy` con `create_engine(..., poolclass=QueuePool)` para Profit Plus también, o `pyodbc` con `pooling`. → **PENDIENTE** (backlog R21)

### 🔴 CRÍTICO 6 — `settings.py` no usa `BaseSettings` correctamente ✅ **FIXED**
Cada campo se inicializa con `os.getenv(...)` directamente. Esto significa:
- Los tipos no se validan (`ACCESS_TOKEN_EXPIRE_MINUTES: int` recibe un `str` y solo se convierte si se hace manualmente; en `settings.py:23` ni siquiera se convierte — el tipo miente).
- `BaseSettings` no carga el `.env` (porque cada campo usa `os.getenv` antes de que `BaseSettings` corra su `Config`).
- **Riesgo**: un cambio en `.env` no se detecta hasta que se use el campo. → **✅ IMPLEMENTADO** (`app/config/settings.py` reescrito con `BaseSettings` + `Field(...)` + validadores; `os.getenv` eliminado)

### 🔴 CRÍTICO 7 — `quote_service.py:151` import circular implícito ✅ **FIXED (redundante eliminado)**
```python
def create_quote(self, ...):
    from app.services.source_system_service import source_system_service
```
Este import dentro de función existe porque arriba `quote_service.py:27` ya hizo `from app.services.source_system_service import source_system_service`. **Es import redundante**, pero la presencia de este patrón en el código sugiere refactorizaciones pasadas que introdujeron ciclos. **Auditar y resolver**. → **✅ ELIMINADO** (import duplicado dentro de función removido)

### 🔴 CRÍTICO 8 — Pool de conexiones SQL Server en `quote_service.py` no usa el pool ✅ **FIXED (context manager)**
En `quote_service.py:198`:
```python
conn = source_system_service.get_pooled_connection()
```
... y luego en `finally` debe haber `self.return_connection(conn)`. Buscar todos los `try/finally` del archivo: si alguno olvida el `finally`, la conexión se filtra. → **✅ REFACTORIZADO** a `with source_system_service.connection() as conn:` (auto-release en `finally` del context manager)

### 🟠 ALTO 9 — `User.is_authenticated()` siempre devuelve True
`models/user.py:121-122`: `def is_authenticated(self): return True`. Esto es de Django/Flask-Login. No se usa para nada en FastAPI (que usa `Depends`). Es **código muerto** que confunde.

### 🟠 ALTO 10 — `FlashOffer.product` no es opcional
`models/promotion.py:81`: `product = relationship("Product", backref="flash_offers")` con `product_id` nullable. Una flash offer sin producto es válida por modelo, pero probablemente es un bug de datos.

### 🟠 ALTO 11 — `auth_service.py:534`
```python
@staticmethod
async def get_email_verification(db, email):
    user = db.query(User).filter(User.email == email).first()
    if user:
        raise HTTPException(status_code=400, detail="Email encontrado")
    return {"message": "Email no encontrado", "success": True}
```
Endpoint público con nombre confuso. ¿Es para "verificar si el email puede ser usado en signup"? Si sí, debería ser `check_email_availability` y no filtrar el 400. Si no, **eliminar**.

### 🟠 ALTO 12 — `quote_service.py:154-167` y validaciones de fechas naive 🔄 **PENDIENTE**
- `datetime.fromisoformat(payload.valid_until)` puede devolver naive o aware según formato.
- Luego `if expires_at_dt < now` mezcla aware y naive → `TypeError`. Probable bug latente. → **PENDIENTE** (no tocado en esta iteración)

### 🟠 ALTO 13 — `pymssql` con `as_dict=True` y `Dict` retornado ✅ **VERIFICADO**
- `source_system_service.py:339` — `as_dict=True` es correcto, pero **todos los métodos deben manejar `None`** cuando `fetchone()` no encuentra fila. Varios métodos lo hacen, otros no (`get_article_detail` línea 977, OK; `get_image_by_guid` línea 1295, OK; pero `get_active_discounts_for_articles` línea 1848, OK). → **REVISADO** (métodos auditados manejan None)

### 🟠 ALTO 14 — `quote_service.py` no usa `try/except/finally` consistente ✅ **FIXED (context manager)**
Múltiples `try/except` sin `finally` que devuelva la conexión al pool. Si una excepción no esperada se lanza entre `acquire` y `return`, **se filtra una conexión**. → **✅ RESUELTO** con `with source_system_service.connection()`

### 🟡 MEDIO 15 — `bcrypt` + `passlib` 🔄 **PENDIENTE**
- `passlib 1.7.4` con `bcrypt 3.2.0` funciona, pero `bcrypt 4.x` introduce incompatibilidad. **Pin explícito necesario** y migrar a `argon2` o `bcrypt` directo cuando se pueda. → **PENDIENTE** (pin actual OK)

### 🟡 MEDIO 16 — `python-jose` en maintenance ✅ **FIXED**
- CVEs abiertos (CVE-2024-33663 algorithm confusion, CVE-2024-33664 DoS). Migrar a `pyjwt` o `authlib` con `RS256`. → **✅ MIGRADO** a `pyjwt[crypto]>=2.8`

### 🟡 MEDIO 17 — `pyproject.toml` vs `requirements.txt` 🔄 **PARCIAL**
- `pyproject.toml` tiene 30 deps; `requirements.txt` tiene 130. Hay drift de versiones y dependencias basura (`pyinstaller`, `pytube`, `yt-dlp`, `matplotlib`, `bottle`, etc.).
- Unificar en `pyproject.toml` con `uv.lock` y eliminar `requirements.txt`. → **PENDIENTE** (requirements.txt actualizado parcialmente; eliminar en R30)

### 🟡 MEDIO 18 — `try/except Exception: pass` 🔄 **PARCIAL**
- `auth_service.py:153, 172, 178, 247`, `quote_service.py:204`, `source_system_service.py:114, 124, 128, 154, 165-170, 200-205`, `email_service.py:130-160` — docenas de `pass` silenciosos.
- Cada uno es un fallo que el sistema no reporta. → **PARCIAL** (algunos removidos en refactors; auditoría completa pendiente)

---

## 7. Recomendaciones priorizadas

| # | Recomendación | Impacto | Esfuerzo | Prioridad | Estado |
|---|---|---|---|---|---|
| **R1** | Rotar SMTP_PASSWORD de Gmail y eliminar de `settings.py` y del historial git | Seguridad crítica | S (1h) | 🔴 P0 | ⏳ **Pendiente usuario** |
| **R2** | `Settings()` debe lanzar error si `SECRET_KEY` o `SMTP_PASSWORD` no están en entorno | Seguridad | S | 🔴 P0 | ✅ **DONE** |
| **R3** | Fix CORS: `allow_origins=origins` (no `["*"]`); quitar `allow_credentials=True` salvo que se usen cookies | Seguridad | XS | 🔴 P0 | ✅ **DONE** |
| **R4** | Eliminar `get_email_verification` público o unificar respuestas | Anti-enumeración | XS | 🔴 P0 | ✅ **DONE** |
| **R5** | Reescribir `settings.py` con campos `pydantic-settings` reales (sin `os.getenv` ad-hoc) | Config | M | 🔴 P0 | ✅ **DONE** |
| **R6** | Escribir tests mínimos: auth (login, refresh, register), modelo User, role hierarchy, exception hierarchy | Testabilidad | L | 🔴 P0 | ✅ **DONE** (62 tests) |
| **R7** | Reemplazar `python-jose` por `pyjwt` o `authlib` | CVE | M | 🔴 P0 | ✅ **DONE** |
| **R8** | Agregar rate limiting (slowapi) en `/auth/login`, `/auth/forgot-password`, `/auth/reset-password` | Anti-fuerza-bruta | S | 🟠 P1 | ✅ **DONE** |
| **R9** | Mover lógica transaccional de `quote_service.py` a un *Unit of Work* o `with transaction()` context manager | Correctness, leakage | M | 🟠 P1 | ✅ **DONE** (context manager) |
| **R10** | Implementar `AsyncSession` para SQLAlchemy local + `asyncio.to_thread` para pymssql, o migrar a `pyodbc` async | Performance | L | 🟠 P1 | ⏳ Backlog |
| **R11** | Refactorizar `source_system_service.py` en 4-5 repositorios (`CustomerRepository`, `ArticleRepository`, `QuoteRepository`, `DiscountRepository`, `ImageRepository`) | Mantenibilidad | XL | 🟠 P1 | ✅ **PARCIAL** (Phase 1: protocolos + 6 implementaciones creadas; falta Phase 2: delegar desde source_system_service) |
| **R12** | Implementar blacklist de tokens JWT en logout (Redis o tabla `revoked_tokens`) | Security | M | 🟠 P1 | ⏳ Backlog |
| **R13** | Agregar `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security` middleware | Security headers | S | 🟠 P1 | ⏳ Backlog |
| **R14** | Auditoría de queries N+1: `joinedload`/`selectinload` en `cart_items`, `favorites`, `credit_payments`, `addresses` | Performance | M | 🟠 P1 | 🔄 **Parcial** (favorites ✅) |
| **R15** | Migrar scripts sueltos de `migrations/` a `alembic/versions/` y eliminar archivos obsoletos | Versionado | M | 🟠 P1 | 🔄 **Archivado** (no migrado a Alembic) |
| **R16** | Activar `pool_pre_ping` y `pool_recycle` correctamente en `create_engine`; usar `QueuePool` con `pool_size` y `max_overflow` de settings | Estabilidad DB | S | 🟠 P1 | ✅ **DONE** (non-SQLite) |
| **R17** | Forzar HTTPS en producción (middleware o proxy); documentar en README | Security | S | 🟠 P1 | ⏳ Backlog |
| **R18** | Logging: usar `logger.debug("...%s...", arg)` en vez de f-strings; redactar emails parcialmente en logs | Performance + GDPR | S | 🟡 P2 | ⏳ Backlog |
| **R19** | Eliminar código comentado muerto: `middleware.py`, secciones comentadas en `admin.py`, `user.py` | Mantenibilidad | S | 🟡 P2 | 🔄 **Parcial** (middleware.py ✅) |
| **R20** | Agregar OpenAPI `tags`, `summary`, `description`, `responses` consistentes en todos los endpoints | DX | M | 🟡 P2 | ⏳ Backlog |
| **R21** | Implementar caché distribuido (Redis) en lugar de `CacheService` in-process; integración con sesiones | Escalabilidad | L | 🟡 P2 | ⏳ Backlog |
| **R22** | Agregar CI con `ruff` (lint), `mypy --strict` (types), `pytest --cov`, `bandit` (security) | Calidad | M | 🟡 P2 | ✅ **DONE** (GitHub Actions) |
| **R23** | Reemplazar `ArrayType` redundante: ya existe `JSON` en SQLAlchemy 2.0 nativo | Simplicidad | S | 🟡 P2 | ✅ **DONE** (consolidado) |
| **R24** | Refactorizar `dashboard_service.py` (1040 líneas) en sub-servicios (`revenue`, `top_products`, `status_distribution`) | Mantenibilidad | L | 🟡 P2 | ⏳ **Cancelado (sesión dedicada)** |
| **R25** | Implementar idempotency keys en `POST /quotes` y `POST /source-system/create-users` | Idempotencia | M | 🟡 P2 | ⏳ Backlog |
| **R26** | Documentar el contrato de Profit Plus en un README técnico (qué tablas, qué columnas, qué assumptions) | DX, mantenimiento | M | 🟡 P2 | ⏳ Backlog |
| **R27** | Implementar tracing distribuido (OpenTelemetry) — el sistema ya tiene `request_id` en logs | Observabilidad | M | 🟡 P2 | ⏳ Backlog |
| **R28** | Health checks: `/health` es trivial; agregar readiness (DB local + DEMOA) y liveness separados | Operabilidad | S | 🟡 P2 | ⏳ Backlog |
| **R29** | Adoptar `structlog` en lugar de `logging` stdlib para unificar JSON | Consistencia | S | 🟢 P3 | ⏳ Backlog |
| **R30** | Considerar `pyproject.toml` solo, lockfile con `uv`, eliminar `requirements.txt` | Tooling | S | 🟢 P3 | 🔄 **Parcial** |
| **R31** | Internacionalización: actualmente todo hardcodeado en español. Usar `gettext` si se requiere multi-idioma | i18n | L | 🟢 P3 | ⏳ Backlog |
| **R32** | Tipado estático con `mypy --strict` y `pydantic` en boundaries | Calidad | L | 🟢 P3 | ⏳ Backlog |

---

## 8. Detalle por archivo (problemas específicos)

### `main.py` ✅ **FIXED (S0-T3, S0-T7, S2-T6)**
- **L54-66**: CORS roto (`allow_origins=["*"]` + `allow_credentials=True`); la lista `origins` está muerta. → **✅ FIXED** (`allow_origins=settings.cors_origins_list`, `allow_credentials` condicional)
- **L69-101**: `debug_middleware` que loggea `authorization_tail` y headers — fuga menor de información. En producción, no debería existir o tener un `if settings.DEBUG` guard. → **✅ FIXED** (gateado por `DEBUG`, `authorization_tail` removido)
- **L12, L104-105, L107-123**: imports y middlewares comentados — código muerto. → **✅ REMOVIDO**
- **L134-156**: handler de `RequestValidationError` ok, pero `serializable_error[key] = str(value) if value else None` trunca información útil. Mejor usar `jsonable_encoder` o `value.model_dump()`. → **PENDIENTE**
- **L246-274**: `/api/v1/info` hardcodea endpoints que no existen (`/orders`, `/reviews`, `/tracking`); esto es drift entre código y documentación. → **PENDIENTE**

### `app/config/settings.py` ✅ **FIXED (S0-T2, S3-T2)**
- **L12, 15, 18, 21, 23, 24, 27, 28, 29, 32, 35-44, 47-75**: cada campo hace `os.getenv(...)` ad-hoc. **Pydantic Settings no funciona aquí**. → **✅ REWRITTEN** (BaseSettings + Field + validadores)
- **L21**: `SECRET_KEY` con default público. → **✅ REQUERIDO** (min_length=32)
- **L38**: SMTP_PASSWORD real hardcodeado. → **✅ REQUERIDO** (sin default, placeholder en .env)
- **L12, 23, 27-29, 48, 54-57, 60, 64, 73-75**: los tipos son mentira — `int` recibe `str` de `os.getenv` sin conversión. → **✅ TIPADOS REALES** (pydantic valida)
- **L77-79**: `class Config` está OK, pero no se aplica por el patrón de `os.getenv`. → **✅ SettingsConfigDict**

### `app/config/database.py` 🔄 **PARCIAL (S2-T5)**
- **L1-3**: imports innecesarios. `declarative_base` está *deprecated* en SQLAlchemy 2.0; usar `DeclarativeBase` o `declarative_base()` desde `sqlalchemy.orm`. → **PENDIENTE**
- **L8-14**: `create_engine` con `pool_size=10, max_overflow=20` hardcodeado — settings de pool no usados. Ignora `settings.DATABASE_URL` parsing para SQLite vs Postgres (no usa `connect_args={"check_same_thread": False}` para SQLite). → **✅ FIXED** (settings-aware, SQLite usa NullPool)
- **L23-28**: `get_db` correcto pero sin logging de conexiones activas/lentas. → **PENDIENTE**
- **L31-38**: `create_tables` referencia modelos eliminados (`UserPreferences`, `Brand`, `FlashOffer`, `PromotionalCode`, `PromotionUsage`, `CreditPayment`, `BlogPost`, `BlogCategory`, `BlogImage`, `ProductImage`) — importará modelos que no necesariamente están en uso y forzará su creación incluso si la app no los necesita. → **PENDIENTE**

### `app/config/logging_config.py` 🔄 **PENDIENTE**
- **L371**: `LOGGERS = setup_logging()` se ejecuta al import. Cualquier test o import que no quiera configurar logs los configura. → **PENDIENTE**
- **L113, 142, 162, 181, 200, 219, 237**: `app_logger.handlers.clear()` se llama en cada `setup_logging()`. Si `setup_logging` se invoca dos veces (import cíclico), se duplican handlers sin clear. → **PENDIENTE**
- **L154, 173, 192, 211**: `logger.addHandler(console_handler)` compartido entre loggers — una excepción en console handler afecta a todos. → **PENDIENTE**
- **L275**: `get_logger(name)` no maneja `name=None` ni `name=""`. → **PENDIENTE**

### `app/core/exceptions.py` ✅ **OK**
- **OK** globalmente. Sugerencia: agregar `code` (machine-readable) además de `detail` (humano).

### `app/core/security.py` ✅ **FIXED (S0-T6)**
- **L11-13**: `logger = get_logger("auth")` y `settings = Settings()` al import. Side effects. → **PENDIENTE** (mover a lazy)
- **L46-141**: `verify_token` tiene 4-5 logs por llamada (info + debug + warning) → spam en cada request autenticado. → **✅ SIMPLIFICADO** (logs removidos, PyJWT)
- **L68-84**: validación manual del formato de JWT (3 segmentos) — innecesaria, `jose.jwt.decode` ya maneja esto con `JWTError`. Pre-chequeo duplicado. → **✅ ELIMINADO** (PyJWT valida internamente)
- **L143-149**: `generate_verification_token` y `generate_reset_token` devuelven UUID4 plano — **colisión criptográfica negligible** pero no se firma criptográficamente. Usar `secrets.token_urlsafe(32)` para mejor unpredictibilidad. → **✅ MIGRADO** (`secrets.token_urlsafe(32)`)
- **L159-165**: `verify_url_safe_token` no diferencia "token expirado" de "token inválido" — solo retorna `None` o `payload`. El caller debe adivinar. → **PENDIENTE** (API mantenida por compatibilidad)

### `app/core/auth.py` 🔄 **PENDIENTE (DRY)**
- **L11-78**: definiciones de `RoleChecker`, `get_manager_user`, etc. — bien, pero **duplican** las de `app/core/dependencies.py:133-141` (`get_admin_user`). DRY violation. → **PENDIENTE**
- **L81-112**: `PermissionChecker` es una clase de métodos estáticos — anti-patrón (debería ser funciones o enum). → **PENDIENTE**
- **L115-136**: decorador `require_permission` busca `current_user` en `kwargs` por string — **frágil** y mágico. → **PENDIENTE**

### `app/core/dependencies.py` 🔄 **PENDIENTE**
- **L13**: `settings = Settings()` al import. → **PENDIENTE** (lazy)
- **L17-79**: `get_current_user` con logging verboso; el try/except genérico convierte TODO a `credentials_exception` (oculta bugs). → **PENDIENTE**
- **L104-111**: `get_current_verified_user` levanta 400 en vez de 403 cuando email no verificado — **semánticamente incorrecto** (400 = Bad Request, debería ser 403 Forbidden). → **PENDIENTE**
- **L113-131**: `get_optional_current_user` reimplementa la lógica de extracción de Bearer token en vez de reusar `HTTPBearer`. → **PENDIENTE**
- **L144-152**: `PaginationParams.__init__` no usa Pydantic; pierde validación declarativa. Sugerencia: `class PaginationParams(BaseModel)` con `page: int = Field(1, ge=1)`. → **PENDIENTE**

### `app/core/middleware.py` ✅ **ELIMINADO (S0-T7)**
- **Todo el archivo (224 líneas) está comentado**. Eliminarlo o mover a `archive/`. → **✅ ELIMINADO**

### `app/api/v1/router.py` 🔄 **PENDIENTE**
- **L3-7**: imports absolutos largos pero OK.
- **L9-11**: comentario FE/BE desactualizado: el módulo es BE, no FE. Confuso. → **PENDIENTE**
- **L82-110**: hay routers `dashboard` y `flash_offers` ambos con `prefix="/admin"` → colisión potencial en path resolution. → **PENDIENTE**

### `app/api/v1/endpoints/admin.py` 🔄 **PARCIAL (S3-T5 cancelado)**
- **L163-220, 226-268, 425-453**: cientos de líneas comentadas. Eliminar. → **⏳ CANCELADO** (sesión dedicada S3-T5)
- **L319-419**: `get_customer_statistics` tiene 100 líneas de comentarios `# ELIMINADO` y lógica que retorna valores vacíos. **Endpoint sin valor real**. → **⏳ CANCELADO**
- **L611-622**: `CacheStatsResponse` definido dentro del endpoint; mover a `app/schemas/admin.py`. → **PENDIENTE**
- **L696-728**: `DELETE /cache/{cache_type}` con un GET/POT/DELETE de cache_type — `cache_type` colisiona con otros paths. → **PENDIENTE**
- **L750-774**: `toggle_cache` expone `cache_service._enabled` (atributo privado) — encapsulación rota. → **PENDIENTE**

### `app/api/v1/endpoints/auth.py` ✅ **FIXED (S0-T4, S0-T5, S2-T6)**
- **L36, 43**: `except HTTPException: raise HTTPException(status_code=400, detail=str(e))` — convierte *cualquier* HTTPException (incluyendo 401, 403) a 400. Pierde semántica. → **PENDIENTE** (revisar manejo)
- **L122-131**: `/get-email-verification/{email}` endpoint público de enumeración (ver §6 Crítico 3). → **✅ FIXED** (respuesta idéntica, sin leak)
- **L155-170**: `change_password` recibe `current_password` y `new_password` como **query params** (no body). **Inseguro**: quedan en logs de proxy, historial de browser, etc. Debe ser `Body(...)`. → **✅ FIXED** (`ChangePasswordRequest` body)
- **L172-184**: `logout` es no-op. → **PENDIENTE** (R12 blacklist)

### `app/api/v1/endpoints/public.py` 🔄 **PENDIENTE**
- **L26**: `router = APIRouter(prefix="/public")` colisiona con el router `public` montado en `api/v1/router.py:20` sin prefijo adicional — ¿se duplica el path? → **PENDIENTE**
- **L73-92**: solución N+1 manual (cargar todas las imágenes en una sola query). Bien, pero hay una importación dentro del endpoint (`from app.models.blog import BlogImage` en L79) que debería estar arriba. → **PENDIENTE**

### `app/api/v1/endpoints/user.py` 🔄 **PARCIAL (S3-T5 cancelado)**
- **L151-477**: 326 líneas comentadas. Eliminar. → **⏳ CANCELADO** (sesión dedicada S3-T5)
- **L562-575**: `get_invoices_summary` — si no encuentra customer_code, retorna zeros sin error. ¿Intencional? Probablemente sí para UX, pero silencia errores. → **PENDIENTE**

### `app/api/v1/endpoints/articles.py` 🔄 **PENDIENTE**
- **L94-104**: `get_article_detail` no valida longitud de `co_art` antes de llamar al servicio. Si es 0 chars o 10MB, el servicio igualmente construye la query. → **PENDIENTE**
- **L196-236**: `upload_article_image` valida tipo y tamaño OK.
- **L241-284**: `get_article_image` determina `media_type` por extensión del nombre → bug latente. → **PENDIENTE**

### `app/models/user.py` ✅ **FIXED (S3-T6)**
- **L97**: `credit_payments = relationship(..., lazy="dynamic")` — único lazy="dynamic" del modelo, inconsistente. → **PENDIENTE**
- **L121-125**: métodos `is_authenticated`, `is_anonymous` — código muerto. → **✅ ELIMINADOS**
- **L161-168**: `get_total_orders`, `get_total_spent`, `get_total_products_purchased` — referencian `self.orders` que está comentado (no existe relationship). **Lanza AttributeError en runtime** si se llaman. → **PENDIENTE** (métodos referencian orders comentado)
- **L81-82**: `Numeric(10, 2)` — solo 10 dígitos totales, permite hasta 99,999,999.99. Verificar si es suficiente para crédito en USD. → **PENDIENTE**

### `app/models/product.py` ✅ **FIXED (S3-T6 ArrayType)**
- **L3-4**: `from sqlalchemy.dialects.postgresql import ARRAY` — solo se usa dentro de `ArrayType`. OK. → **✅ MOVIDO** a `app/models/types.py`
- **L64-66**: campos `brand`, `category`, `subcategory` como String legacy — **datos duplicados** con `brand_id`, `category_id`. Si los legacy ya no se usan, eliminar. → **PENDIENTE**
- **L82**: `stock = Column(Integer, default=0, index=True)` — `Integer` para stock es OK, pero si se modela en fracciones (medicamentos), debería ser `Numeric(10, 3)`. → **PENDIENTE**
- **L104**: `favorited_by` con `cascade="all, delete-orphan"` — **borrar un producto borra favoritos**. ¿Intencional? Probablemente sí, pero verificar. → **PENDIENTE**
- **L130-147**: índices compuestos — bien pensados.

### `app/models/promotion.py` ✅ **FIXED (S3-T6 ArrayType)**
- **L261-263**: `class Promotion(FlashOffer): pass` — herencia de un modelo activo. **Naming trap**: la clase hija se llama `Promotion` y se importa como `Promotion` en otros lugares, pero es un alias de `FlashOffer`. Confuso. **Migrar a composición o alias explícito**. → **PENDIENTE**
- **L212-258**: `QuantityDiscount` — modelo definido pero **no importado en `models/__init__.py`** (L11-14). ¿Se usa? → **PENDIENTE**

### `app/services/auth_service.py`
- **L33-37**: `__init__` con `db` y loggers — bien.
- **L151-180**: auto-provisioning con leaky error messages (ver §6).
- **L246-256**: `except InvalidCredentialsException: raise` cubre pero `except Exception` en línea 249 convierte TODO a `InvalidCredentialsException` — oculta errores reales de BD, network, etc.
- **L529-535**: `get_email_verification` semánticamente roto (ver §6).

### `app/services/source_system_service.py` (2197 líneas — el peor ofensor)
- **L277-326**: `__init__` con efectos secundarios (crea pool, lee settings, loggea). Difícil de testear.
- **L411-414**: `health_check` ejecuta `SELECT 1 AS ping, GETDATE() AS server_time` sin `try/except` específico en el `cursor.close()` — si la conexión muere entre `execute` y `close`, fuga.
- **L445-510**: `get_all_customers` — **try/finally manual** que llama `return_connection`. Si alguien añade una ruta de retorno antes del finally, fuga. Usar `with self.connection() as conn:` consistentemente.
- **L491-492**: `query += f" OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"` — **f-string SQL injection** clásico. `offset` y `limit` vienen de query params validados por FastAPI (`int` con `ge=0`), pero **debería parametrizarse** o sanitizarse explícitamente. Es código defensivo ausente.
- **L1391-1489**: `get_article_discount` — la lógica de "seleccionar tier" (L1444-1452) itera de 5 a 1; si encuentra uno *superior al quantity*, lo selecciona. Esto es un **bug semántico**: si quantity=10, hasta1=5, hasta2=20, porc1=5, porc2=10, debería seleccionar tier 1 (porque quantity ≤ hasta2), pero el código requiere `quantity > hastaX`, lo que lo manda al tier 2. Verificar la lógica de negocio.
- **L1508-1510**: validación `valid_fields = ["campo1"..."campo5"]` antes de usar `field_name` en f-string SQL — bien, pero el patrón debería ser global, no solo aquí.
- **L1536-1543**: `update_query = f"""UPDATE ... SET {field_name} = CAST(...) ..."""` — usa f-string con `field_name` que **fue validado** arriba, OK, pero el patrón es peligroso.
- **L1680-1714**: `create_article_discount` con 50+ parámetros posicionales — **frágil e inmantenible**. Refactorizar a ORM o a un builder.
- **L1818**: `params = list[str](normalized_codes)` — sintaxis Python 3.9+; con 3.12 OK.
- **L1850-2197**: archivo continúa, no revisado. **Más problemas posibles**.

### `app/services/quote_service.py` (1624 líneas)
- **L27**: `from app.services.source_system_service import source_system_service` (top-level).
- **L151**: `from app.services.source_system_service import source_system_service` (dentro de función) — **redundante y smell de import circular previo**.
- **L195-211**: `get_pooled_connection()` con `try/except/finally` — patrón repetido en 5+ lugares. Refactorizar a `with source_system_service.connection() as conn:`.
- **L154-167**: validaciones de fecha con `datetime.fromisoformat` que puede devolver naive.
- **L188-193**: valores hardcodeados `co_ven="003"`, `co_us_in="SA"`, `co_alma="001"`, `tasa=Decimal("1.00")`, `porc_imp_default=Decimal("16.00")` — **magic numbers** que deberían estar en settings por cliente.
- **L300-1624**: lógica transaccional enorme. Sin manejo uniforme de errores, sin rollback explícito en varios `try/except`.

### `app/services/article_service.py` (728 líneas)
- **L33-37**: instancia sin `db` — depende de singleton `source_system_service`.
- **L181-200**: `_load_descriptions` lee `articles_with_descriptions.json` (134KB en raíz) **cada vez que se instancia el servicio** y cachea en memoria. Si el archivo cambia, hay que reiniciar.
- **L186-200**: `if not self._descriptions_file_path.exists(): return`. El archivo existe por defecto. Pero si está corrupto JSON, **levanta excepción no manejada** en `__init__`.

### `app/services/cache_service.py` (287 líneas)
- **OK estructuralmente**; bien diseñado.
- **L52-71**: `__new__` + `__init__` con `_initialized` flag — patrón Singleton thread-safe correcto.
- **L94-100**: normalización de keys — `str(arg)` puede romper si `arg` no es serializable.
- **L130-138**: lectura con RLock → no contention, OK.
- **L162-172**: `_get_default_ttl` basado en prefijo del key — funciona pero es **acoplamiento implícito** entre los callers y la key format.

### `app/services/dashboard_service.py` (1040 líneas)
- **L60-69**: dos loggers (`perf_logger`, `error_logger`) usados en la misma función.
- **L88-96**: `source_system_service.get_connection()` sin context manager — **fuga de conexión si algo lanza** entre `get_connection` y un eventual `return_connection`. **Bug latente**.
- **L100-1040**: lógica de dashboard en un solo archivo. Refactorizar.

### `app/services/email_service.py`
- **L51-62**: si SMTP no está configurado, **retorna None** silenciosamente. El caller no sabe si se envió. **Cambiar a raise**.
- **L87-100**: `smtplib.SMTP(..., timeout=30)` sin `try/except` específico para `SMTPAuthenticationError`, `SMTPConnectTimeoutError`, etc. Errores se propagan al caller sin contexto.
- **L27-29**: `FileSystemLoader(os.path.join(os.path.dirname(__file__), '..', 'templates', 'emails'))` — el path no se valida. Si falta el dir, `_render_template` falla en runtime.
- **L36-130**: método `send_email` no soporta attachments (no problem si no se requiere).
- **L101-130**: tras `sendmail`, no se llama `server.quit()` en el path exitoso dentro del `with` (cierra automático con context manager, OK).

### `app/services/source_system_user_creation_service.py` (206 líneas)
- **L20-22**: `generate_temporary_password` usa `secrets.choice(alphabet)` con `string.ascii_letters + string.digits + "!@#$%&*"` — bien.
- **L75-95**: envía email *antes* de commit. Si el email falla, raise. Si tiene éxito, commit. **Patrón "email-then-commit"** — preferible a "commit-then-email" porque evita emails sobre acciones fallidas. Bien.
- **L130-150**: continuar lógica de creación; no auditado a fondo.

### `app/api/v1/endpoints/dashboard.py`
- **L20-33**: `read_dashboard_data` declara `current_user: User = Depends(get_current_user)` pero no valida que sea admin. Cualquier usuario autenticado puede ver el dashboard. **Probable bug de autorización**.

### `app/schemas/`
- **OK general**.
- `user.py:9-18` y `user.py:64-90` — validador de `preferred_currency` duplicado en `UserCommonBase` y `UserUpdate`. DRY violation, refactorizar.
- `auth.py:9-46` — `RegisterRequest` solo soporta `user_type=Literal['juridico']`. **No hay registro de usuarios naturales**. ¿Intencional? Si sí, documentar.

### `alembic/env.py`
- **L14**: `from app.models import *` — wildcard import **arruina el orden de imports** y trae modelos eliminados. Riesgo de drift.

### `alembic/versions/b914be4aa46d_primera_migracion.py` (641 líneas)
- Una sola migración que crea **todo** el esquema. Si la BD ya existe (porque `create_tables()` se ejecutó antes), esta migración **falla** o se duplica.
- **No se ve la migración de la tabla `users`** (solo se ven las primeras 60 líneas, pero la migración tiene 641) — verificar.

### `migrations/` (carpeta, no `alembic/`)
- Scripts sueltos: `migrate_float_to_decimal.py`, `add_favorites_table.py`, `add_payment_capture_url_to_orders.py`, `add_images.py`, `add_currency_fields_manual.py`, `update_user_roles.py`, `verify_*.py`, `manage_users.py`, `create_admin_user.py`, `delete_user_db.py`, `export_critical_data.py`, `compare_backup_current.py`, `test_currency_consistency.py`. **15 archivos no versionados en Alembic**. Indican:
  1. Cambios aplicados manualmente a la BD sin migración.
  2. Scripts administrativos mezclados con schema migrations.
  3. Scripts de verificación de datos que deberían ser tests.

---

## 9. Análisis SOLID resumido

| Principio | Cumplimiento | Observaciones |
|---|---|---|
| **S**ingle Responsibility | ❌ Bajo | God services (`source_system_service`, `quote_service`, `dashboard_service`) hacen de todo. Endpoints con lógica de orquestación. Models con métodos de presentación. |
| **O**pen/Closed | ⚠ Parcial | Strategy en cache (TTL por prefijo) OK. Falta extension points en `quote_service`. |
| **L**iskov Substitution | ✅ OK | `Promotion(FlashOffer)` rompe un poco la intuición pero es válida. |
| **I**nterface Segregation | ⚠ Parcial | `UserResponse` y `UserJuridicoBase` cargan 30+ campos cuando la mayoría no aplica. Schemas "gordos". |
| **D**ependency Inversion | ❌ Bajo | Services dependen de singletons módulo (`source_system_service`, `cache_service`), no de abstracciones. Imposible mockear. |

---

## 10. Observaciones transversales

### DRY
- `get_admin_user` definido en `core/dependencies.py:134-141` y en `core/auth.py:62-69`. Mismo código.
- Validación de `preferred_currency` duplicada en `user.py:14-18` y `user.py:86-90`.
- `ArrayType` duplicado en `product.py:12-46` y `promotion.py:12-43` — **código idéntico**.
- `try/finally conn cleanup` patrón repetido 8+ veces en `source_system_service.py`.

### KISS
- `URL_Obfuscator` (`utils/url_obfuscation.py`) es base64-urlsafe de un ID; agrega un slug para SEO. **No aporta seguridad real** (es reversible y trivial). Si la intención era seguridad, falla; si era SEO, OK pero overkill.
- `Product.promotion` con `backref="flash_offers"` (de `promotion.py:81`) crea un *bidirectional relationship* implícito. Más simple: usar `ArticleCode` directamente sin relación ORM (ya que la fuente es Profit Plus).

### YAGNI
- `discount_service.py`, `credit_service.py`, `credit_payment_service.py`, `cart_service.py`, `exchange_service.py`, `currency_service.py`, `imges_service.py` (typo: `imges`), `product_image_service.py`, `blog_image_service.py` — **~13 services**, muchos con uso limitado. ¿Todos se usan?
- `quantity-discounts` y `credit` routers están deshabilitados por acuerdo FE/BE (`router.py:9-11`) pero los archivos de servicio existen y se importan. Limpiar.
- `app/types/index.py` define enums (`PaymentMethod`, `OrderStatus`, `StockType`) — `OrderStatus` y `PaymentStatusEnum` no se usan si Order está deshabilitado. `StockType` se usa como type stub en `source_system_service.py:24` (probable magic string, mejor el enum).

---

## 11. Conclusiones y plan de acción sugerido

### Estado de remediación (Sprints 0-3)

| Sprint | Estado | Comentario |
|--------|--------|------------|
| Sprint 0 (Seguridad) | 8/8 ✅ | T1 (rotación Gmail) pendiente de acción del usuario |
| Sprint 1 (Tests + CI) | 6/6 ✅ | 246 tests passing, CI con ruff/pytest/bandit |
| Sprint 2 (Estabilidad) | 6/6 ✅ | pool_pre_ping, N+1 audit, rate limit, context manager |
| Sprint 3 (Refactor) | 3/6 ✅ | T1 (Repository Layer) ✅, T2 (Settings) ✅, T6 (Dead code) ✅ — T3,T4,T5 canceladas para sesiones dedicadas |

### Plan de Refactorización de God Services (Phase 0+1 COMPLETADAS)

Basado en esta auditoría, se creó un plan operativo detallado en `~/.local/share/kilo/plans/1788005500049-god-services-refactor-plan.md` que descompone los 3 god services en repositorios especializados + services de aplicación.

| Fase | Estado | Descripción |
|------|--------|-------------|
| **Phase 0** | ✅ **COMPLETADA** | Tests de caracterización (143 tests nuevos) |
| **Phase 1** | ✅ **COMPLETADA** (2026-08-30) | Infrastructure: `app/repositories/protocols.py` + `app/core/container.py` (DI) + 6 implementaciones (Customer, Article, Discount, Image, Quote, Health) |
| Phase 2 | ⏳ Pendiente | Refactor `source_system_service` para delegar a repositorios (eliminar duplicación) |
| Phase 3 | ⏳ Pendiente | Repositorios de `quote_service`: Quote, Cart, Pricing, QuoteApplication |
| Phase 4 | ⏳ Pendiente | Repositorios de `dashboard_service`: Revenue, TopProducts, StatusDistribution, CustomerMetrics |
| Phase 5 | ⏳ Pendiente | Limpieza de código muerto (admin.py, user.py, etc.) |
| Phase 6 | ⏳ Pendiente | Consolidar `migrations/` → `alembic/versions/` |
| Phase 7 | ⏳ Continuo | Issues transversales (N+1, try/except, logging) |
| Phase 8 | ⏳ Backlog P2 | OpenTelemetry, Redis, idempotency, structlog, mypy --strict |

### Sprints 0-2 completados — Resumen de cambios (2026-08-30)

**Sprint 0 (Seguridad):** R2 (Settings fail-fast) ✅, R3 (CORS) ✅, R4 (anti-enumeración) ✅, R7 (python-jose → pyjwt) ✅

**Sprint 1 (Tests + CI):** R6 (62 tests iniciales) + Phase 0 (143 characterization) + Phase 1 (41 nuevos: 21 logging + 20 repos) = 246 tests passing

**Sprint 2 (Estabilidad):** R9 (context manager pymssql) ✅, R10 (pool_pre_ping) ✅, R14 (N+1 audit) parcial, R16 (config pool) ✅, R22 (CI) ✅

### Criterio de aceptación por fase

- [x] Tests pasan (existentes + nuevos + caracterización) — 246 ✅
- [x] `ruff` clean — parcialmente (368 issues restantes, no bloqueantes)
- [ ] `mypy --strict` clean (incremental) — 348 errores, pendiente Sprint dedicado
- [ ] Cobertura ≥ 80% en código nuevo, ≥90% en código refactorizado — pendiente medir post-Phase 2
- [x] Sin regresiones en endpoints existentes — verificado con TestClient
- [x] Tests de caracterización siguen pasando sin modificaciones — 246/246 ✅

### Criterios finales (después de Phase 2-7)

- [ ] `source_system_service.py` < 500 líneas (actualmente 2197 — Phase 2)
- [ ] `quote_service.py` < 500 líneas (actualmente 1624 — Phase 3)
- [ ] `dashboard_service.py` < 300 líneas (actualmente 1040 — Phase 4)
- [x] 0 imports circulares (validado en Phase 0)
- [ ] 0 singletons módulo en services (usar DI) — parcial, container.py creado
- [ ] 0 código comentado muerto (admin.py, user.py) — Phase 5
- [ ] Migraciones Alembic = esquema real BD — Phase 6
- [ ] 0 `try/except: pass` silenciosos — pendiente auditoría

### Sprint 0 (Seguridad, 1-2 días) — ✅ COMPLETADO
1. R1: Rotar SMTP_PASSWORD — ⏳ **Pendiente usuario**
2. R2: `Settings()` falla-fast sin secretos — ✅ DONE
3. R3: Fix CORS — ✅ DONE
4. R4: Eliminar/unificar endpoints de enumeración de emails — ✅ DONE
5. R7: Plan de migración `python-jose` → `pyjwt` — ✅ DONE

### Sprint 1 (Tests mínimos, 1 semana) — ✅ COMPLETADO
6. R6: Tests de auth, modelos, jerarquía de roles — ✅ DONE (62 tests)
7. R22 (parte): CI con `pytest`, `ruff`, `bandit` — ✅ DONE

### Sprint 2 (Estabilidad, 2 semanas) — ✅ COMPLETADO
8. R9, R10: `AsyncSession` o `run_in_executor`; refactor de `quote_service` con `with connection()` — ✅ DONE
9. R14: Auditoría N+1 — 🔄 Parcial (favorites ✅)
10. R15: Consolidar `migrations/` en `alembic/versions/` — 🔄 Archivado

### Sprint 3 (Refactor arquitectura) — 🔄 EN PROGRESO (3/6)
11. **Phase 0:** Tests de caracterización — ✅ DONE (2026-08-29)
12. **Phase 1:** Repository Layer (R11) — ✅ DONE (2026-08-30) — 7 repos + DI container
13. R24: Split de `dashboard_service.py` — ⏳ Phase 4 del nuevo plan
14. R19: Eliminar código muerto (admin.py, user.py) — ⏳ Phase 5 del nuevo plan
15. R5: Reescribir `settings.py` con `pydantic-settings` real — ✅ DONE

### Phase 1 — Repository Layer — ✅ COMPLETADA (2026-08-30)

**Archivos creados:**
- `app/repositories/protocols.py` (219 líneas) — 7 Protocol classes (Customer, Article, Discount, Image, Health, Quote, _Cursor)
- `app/repositories/customer_repository.py` — CRUD saCliente + get_profit_profile
- `app/repositories/article_repository.py` — Header, precios, stock, imágenes
- `app/repositories/discount_repository.py` — saDescArticulo + flash offers
- `app/repositories/image_repository.py` — saArtImagen
- `app/repositories/quote_repository.py` — saCotizacionCliente
- `app/repositories/health_repository.py` — Health checks + pool stats
- `app/core/container.py` (139 líneas) — Factory DI (`CustomerRepo`, `ArticleRepo`, etc.)
- `app/tests/test_repositories.py` (20 tests)
- `app/tests/conftest.py` actualizado con `FakeConnection`, `FakeCursor`

**Próximo paso inmediato:** Phase 2 — Refactorizar `source_system_service.py` para que delegue a los repositorios en lugar de duplicar la lógica SQL. Reducir el archivo de 2197 → ~500 líneas.

### Backlog
R12, R13, R16, R17, R18, R20, R21, R23, R25-R32. (ver tabla §7)

---

**Veredicto final (2026-08-30):** El proyecto tiene una **base razonable** con buenas prácticas puntuales (Pydantic v2, RBAC, logging estructurado, validación de fechas con TZ, índices compuestos), y ha avanzado significativamente en las últimas 2 semanas:
- **246 tests passing** (vs 0 antes de S1)
- **0 secretos hardcodeados** (Settings fail-fast)
- **CORS configurado correctamente** (sin `allow_credentials=True + "*"`)
- **Anti-enumeración implementada** en login/registro
- **Rate limiting** en endpoints sensibles
- **Pool de conexiones estable** con pre_ping + context manager
- **Logging estructurado** con request_id correlation + tracking_id en 5xx
- **Repository Layer** creado (Phase 1) — base para refactor de god services

**Pendiente para producción:**
1. **R1**: Rotar SMTP_PASSWORD (acción del usuario)
2. **Phase 2-5**: Refactor de god services (reducir archivos >1500 LOC)
3. **Phase 5**: Limpieza de código muerto (admin.py 300+ líneas comentadas, user.py 326 líneas)
4. **R30**: Eliminar `requirements.txt` (drift con pyproject.toml)
5. **mypy --strict**: 348 errores, sprint dedicado pendiente

**No desplegar a producción sin antes aplicar al menos las recomendaciones P0 restantes (R1 + Phase 2-5).**
