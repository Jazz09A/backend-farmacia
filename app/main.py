from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import time
import os

from app.config.settings import settings
from app.config.database import engine, Base, create_tables
from app.core.exceptions import FarmaException

# Create database tables
try:
    create_tables()
    print("✅ Database tables created successfully")
except Exception as e:
    print(f"❌ Error creating database tables: {e}")

# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="API Backend para FarmaPlus - Sistema de farmacia online",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc"
)

# Create uploads directory if it doesn't exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
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
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "success": False}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    if settings.DEBUG:
        import traceback
        traceback.print_exc()
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Error interno del servidor",
            "success": False
        }
    )

# Static files
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

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
            "reviews": "/api/v1/reviews"
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

# Startup event
@app.on_event("startup")
async def startup_event():
    print(f"🚀 Starting {settings.PROJECT_NAME} v{settings.VERSION}")
    print(f"📊 Debug mode: {settings.DEBUG}")
    print(f"🌐 CORS origins: {settings.ALLOWED_ORIGINS}")
    print(f"📁 Upload directory: {settings.UPLOAD_DIR}")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    print(f"🛑 Shutting down {settings.PROJECT_NAME}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info" if not settings.DEBUG else "debug"
    ) 