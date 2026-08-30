from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import time
import os
import re
from contextlib import asynccontextmanager
from typing import Optional

from app.config.settings import Settings
from app.core.exceptions import FarmaException
from app.core.rate_limit import limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.config.logging_config import get_logger
from app.utils.logging_helpers import (
    set_request_context,
    clear_request_context,
    log_request,
    log_response,
    log_internal_error,
    log_security_event,
    new_request_id,
    redact_message,
)

settings = Settings()
logger = get_logger("app")

# Patterns used to scrub secrets from log payloads. Keep this list
# conservative: only redact values, never keys, and only when the key
# strongly suggests a credential. The goal is to avoid leaking SMTP
# passwords, DB passwords or token tails via unhandled exceptions.
_SECRET_QUERY_KEYS = {
    "password",
    "pass",
    "passwd",
    "pwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "smtp_password",
    "source_system_password",
    "api_key",
    "apikey",
}
_LONG_ALNUM = re.compile(r"[A-Za-z0-9_\-]{24,}")


def _redact_query_params(params: dict) -> dict:
    redacted = {}
    for key, value in params.items():
        if key.lower() in _SECRET_QUERY_KEYS:
            redacted[key] = "[REDACTED]"
        elif isinstance(value, str) and _LONG_ALNUM.fullmatch(value):
            redacted[key] = "[REDACTED]"
        else:
            redacted[key] = value
    return redacted


# Alias interno: la función ahora vive en logging_helpers.redact_message.
_redact_message = redact_message


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app_logger = get_logger("app")
    app_logger.info(
        f"Starting {settings.app.PROJECT_NAME} v{settings.app.VERSION}",
        extra={
            'project_name': settings.app.PROJECT_NAME,
            'version': settings.app.VERSION,
            'debug_mode': settings.app.DEBUG,
            'event': 'application_startup'
        }
    )
    yield
    # Shutdown
    app_logger.info(
        f"Shutting down {settings.app.PROJECT_NAME}",
        extra={'project_name': settings.app.PROJECT_NAME, 'event': 'application_shutdown'}
    )

# Create FastAPI app
app = FastAPI(
    title=settings.app.PROJECT_NAME,
    version=settings.app.VERSION,
    description="API Backend para FarmaPlus - Sistema de farmacia online",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    lifespan=lifespan
)

# Registrar limiter para slowapi (S2-T6)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    log_security_event(
        "rate_limit_exceeded",
        request=request,
        extra={"limit": str(getattr(exc, "detail", None))},
    )
    rid = getattr(request.state, "request_id", None) or new_request_id()
    return JSONResponse(
        status_code=429,
        headers={"X-Request-ID": rid},
        content={
            "detail": "Demasiadas solicitudes. Por favor intente de nuevo más tarde.",
            "success": False,
            "request_id": rid,
        },
    )

origins = settings.app.cors_origins_list

# Only enable credentials when an origin is explicitly allowed. With a single
# origin in the list the browser permits cookies; with `["*"]` the spec forbids
# it, so we set the value to False unless at least one explicit origin is set.
allow_credentials = bool(origins) and "*" not in origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# MIDDLEWARE GLOBAL: request_id, access log, performance header
# ============================================================================
@app.middleware("http")
async def request_middleware(request: Request, call_next):
    """
    Middleware aplicado a TODAS las requests (incluyendo producción):
    1. Asigna / respeta un request_id (cabecera X-Request-ID o nuevo UUID).
    2. Lo expone en `request.state.request_id` y en el ContextVar.
    3. Loggea request entrante + response saliente con duración.
    4. Añade `X-Request-ID` y `X-Process-Time` a la respuesta.
    5. Captura excepciones no controladas y devuelve 500 genérico.
    6. Limpia el ContextVar al terminar.
    """
    incoming_rid = request.headers.get("x-request-id")
    rid = incoming_rid if incoming_rid and len(incoming_rid) <= 64 else new_request_id()
    set_request_context(request_id=rid)
    request.state.request_id = rid

    start = log_request(request)

    try:
        response = await call_next(request)
    except Exception as exc:
        tracking_id = log_internal_error(request, exc, context={"phase": "call_next"})
        clear_request_context()
        return JSONResponse(
            status_code=500,
            headers={"X-Request-ID": rid},
            content={
                "detail": "Error interno del servidor",
                "success": False,
                "request_id": rid,
                "tracking_id": tracking_id,
            },
        )

    log_response(request, response, start)

    response.headers["X-Request-ID"] = rid
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Process-Time"] = f"{duration_ms:.2f}"
    clear_request_context()
    return response

# ============================================================================
# EXCEPTION HANDLERS
# ============================================================================
def _error_response(
    request: Request,
    status_code: int,
    detail,
    *,
    headers: Optional[dict] = None,
    extra: Optional[dict] = None,
) -> JSONResponse:
    rid = getattr(request.state, "request_id", None) or new_request_id()
    content = {"detail": detail, "success": False, "request_id": rid}
    if extra:
        content.update(extra)
    out_headers = {"X-Request-ID": rid}
    if headers:
        out_headers.update(headers)
    return JSONResponse(status_code=status_code, content=content, headers=out_headers)


# Global exception handlers
@app.exception_handler(FarmaException)
async def farma_exception_handler(request: Request, exc: FarmaException):
    """Errores de negocio: status ya viene correcto en exc.status_code."""
    return _error_response(
        request,
        exc.status_code,
        exc.detail,
        headers=exc.headers,
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        serializable_error = {}
        for key, value in error.items():
            if key == "ctx" and value:
                serializable_error[key] = str(value) if value else None
            else:
                serializable_error[key] = value
        errors.append(serializable_error)
    logger.info(
        "Request validation failed",
        extra={
            "status_code": 422,
            "errors_count": len(errors),
            "phase": "validation",
        },
    )
    return _error_response(
        request,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Error de validación en los datos enviados",
        extra={"errors": errors},
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    HTTPException explícitas (404, 401, 403, 400, etc.).
    Se loggean como warning (no son fallos del servidor).
    """
    logger.warning(
        f"HTTP {exc.status_code} at {request.method} {request.url.path}",
        extra={
            "status_code": exc.status_code,
            "detail": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            "phase": "http_exception",
        },
    )
    return _error_response(request, exc.status_code, exc.detail)

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """
    Catch-all para excepciones NO controladas (5xx).
    - Log interno COMPLETO con stack trace, contexto, headers redactados.
    - Respuesta al cliente GENÉRICA (no leak) + `tracking_id` para soporte.
    """
    tracking_id = log_internal_error(
        request,
        exc,
        context={"path": request.url.path, "method": request.method},
    )

    if _is_database_exception(exc):
        public_detail = "Error al acceder a la base de datos. Intente nuevamente en unos momentos."
    else:
        public_detail = "Error interno del servidor. Contacte a soporte con el tracking_id."

    return _error_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        public_detail,
        extra={"tracking_id": tracking_id},
    )


def _is_database_exception(exc: BaseException) -> bool:
    module = getattr(exc.__class__, "__module__", "") or ""
    name = exc.__class__.__name__
    if module.startswith("pymssql") or module.startswith("_mssql"):
        return True
    if module.startswith("psycopg2") or module.startswith("psycopg"):
        return True
    if name in {"OperationalError", "DatabaseError", "InterfaceError", "DataError"}:
        return True
    return False

# Include routers
from app.api.v1.router import api_router
app.include_router(api_router, prefix="/api/v1")

# Root endpoints
@app.get("/")
async def root():
    return {
        "message": f"🚀 {settings.app.PROJECT_NAME} v{settings.app.VERSION}",
        "status": "running",
        "docs": "/api/v1/docs",
        "redoc": "/api/v1/redoc",
        "success": True
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "version": settings.app.VERSION,
        "success": True
    }

@app.get("/health/db")
async def health_check_database():
    """
    Health check detallado incluyendo estado del pool de conexiones de SourceSystem.
    Útil para monitoreo y debugging de problemas de conexión.
    """
    from app.services.source_system_service import source_system_service
    
    try:
        source_health = source_system_service.health_check()
    except Exception as e:
        source_health = {"status": "error", "error": str(e)}
    
    return {
        "status": "healthy" if source_health.get("status") == "healthy" else "degraded",
        "timestamp": time.time(),
        "version": settings.app.VERSION,
        "source_system": source_health,
        "success": True
    }

@app.get("/api/v1/info")
async def api_info():
    return {
        "name": settings.app.PROJECT_NAME,
        "version": settings.app.VERSION,
        "description": "API Backend para FarmaPlus - Sistema de farmacia online",
        "endpoints": {
            "auth": "/api/v1/auth",
            "products": "/api/v1/products",
            "cart": "/api/v1/cart",
            "orders": "/api/v1/orders",
            "users": "/api/v1/users",
            "reviews": "/api/v1/reviews",
            "tracking": "/api/v1/orders/{order_id}/tracking"
        },
        "features": [
            "Autenticación JWT",
            "Gestión de productos",
            "Carrito de compras",
            "Sistema de pedidos",
            "Reseñas y calificaciones",
            "Gestión de usuarios",
            "Múltiples monedas (VES/USD)",
            "URLs obfuscadas para productos",
            "Búsqueda avanzada",
            "Sistema de categorías"
        ],
        "success": True
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=settings.app.DEBUG,
        log_level="info" if not settings.app.DEBUG else "debug"
    )