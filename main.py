from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import time
import os
import re
from contextlib import asynccontextmanager

from app.config.settings import Settings
from app.core.exceptions import FarmaException
from app.core.rate_limit import limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.config.logging_config import (
    get_logger,
    log_request_info,
    log_response_info,
    log_error,
)

settings = Settings()
logger = get_logger(__name__)

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


def _redact_message(message: str) -> str:
    """Best-effort scrub of credential-like substrings in error messages."""
    if not message:
        return message
    for pattern in (
        r"(?i)password\s*=\s*[^;,\s]+",
        r"(?i)user\s*=\s*[^;,\s]+",
        r"(?i)uid\s*=\s*[^;,\s]+",
        r"(?i)pwd\s*=\s*[^;,\s]+",
        r"(?i)server\s*=\s*[^;,\s]+",
    ):
        message = re.sub(pattern, lambda m: m.group(0).split("=", 1)[0] + "=[REDACTED]", message)
    message = _LONG_ALNUM.sub("[REDACTED]", message)
    return message


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app_logger = get_logger("app")
    app_logger.info(
        f"Starting {settings.PROJECT_NAME} v{settings.VERSION}",
        extra={
            'project_name': settings.PROJECT_NAME,
            'version': settings.VERSION,
            'debug_mode': settings.DEBUG,
            'event': 'application_startup'
        }
    )
    yield
    # Shutdown
    app_logger.info(
        f"Shutting down {settings.PROJECT_NAME}",
        extra={'project_name': settings.PROJECT_NAME, 'event': 'application_shutdown'}
    )

# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
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
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Demasiadas solicitudes. Por favor intente de nuevo más tarde.",
            "success": False,
        },
    )

origins = settings.cors_origins_list

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

# Debug middleware - only active when DEBUG is True. Never log Authorization
# header tails in production. Tokens must never appear in logs.
if settings.DEBUG:
    @app.middleware("http")
    async def debug_middleware(request: Request, call_next):
        start_time = time.perf_counter()
        log_request_info(logger, request)

        content_type = request.headers.get('content-type')
        x_source_system = request.headers.get('x-source-system')

        logger.debug(
            "Detalles adicionales del request",
            extra={
                "authorization_present": bool(request.headers.get('authorization')),
                "x_source_system": x_source_system,
                "content_type": content_type,
            },
        )

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000
        log_response_info(logger, request, response, duration_ms=duration_ms)
        logger.debug(
            "Detalles de respuesta",
            extra={
                "status_code": response.status_code,
                "has_body": hasattr(response, 'body'),
                "duration_ms": f"{duration_ms:.2f}",
            },
        )

        return response
else:
    @app.middleware("http")
    async def request_timing_middleware(request: Request, call_next):
        start_time = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000
        response.headers["X-Process-Time"] = f"{duration_ms:.2f}"
        return response

# Global exception handlers
@app.exception_handler(FarmaException)
async def farma_exception_handler(request: Request, exc: FarmaException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "success": False},
        headers=exc.headers
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Convert errors to JSON-serializable format
    errors = []
    for error in exc.errors():
        # Convert any non-JSON serializable values to strings
        serializable_error = {}
        for key, value in error.items():
            if key == 'ctx' and value:
                # Handle context objects that might not be serializable
                serializable_error[key] = str(value) if value else None
            else:
                serializable_error[key] = value
        errors.append(serializable_error)
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Error de validación en los datos enviados",
            "errors": errors,
            "success": False
        }
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.warning(
        "HTTPException atrapada",
        extra={
            "status_code": exc.status_code,
            "detail": exc.detail,
            "path": request.url.path,
            "method": request.method,
            "query_params": _redact_query_params(dict(request.query_params)),
            "authorization_present": bool(request.headers.get('authorization')),
            "x_source_system": request.headers.get('x-source-system'),
            "content_type": request.headers.get('content-type'),
        },
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "success": False}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    redacted_message = _redact_message(str(exc))

    log_error(
        logger,
        exc,
        context={
            "path": request.url.path,
            "method": request.method,
            "query_params": _redact_query_params(dict(request.query_params)),
            "exception_type": exc.__class__.__name__,
            "redacted_message": redacted_message,
        },
    )

    detail = "Error interno del servidor"
    if _is_database_exception(exc):
        detail = "Error al acceder a la base de datos"

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": detail,
            "success": False
        }
    )


def _is_database_exception(exc: BaseException) -> bool:
    module = getattr(exc.__class__, "__module__", "") or ""
    name = exc.__class__.__name__
    if module.startswith("pymssql") or module.startswith("_mssql"):
        return True
    if name in {"OperationalError", "DatabaseError", "InterfaceError"}:
        return True
    return False

# Include routers
from app.api.v1.router import api_router
app.include_router(api_router, prefix="/api/v1")

# Root endpoints
@app.get("/")
async def root():
    return {
        "message": f"🚀 {settings.PROJECT_NAME} v{settings.VERSION}",
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
        "version": settings.VERSION,
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
        "version": settings.VERSION,
        "source_system": source_health,
        "success": True
    }

@app.get("/api/v1/info")
async def api_info():
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
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
        port=os.getenv("PORT", 8000),
        reload=settings.DEBUG,
        log_level="info" if not settings.DEBUG else "debug"
    ) 