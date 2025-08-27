"""
Configuración centralizada de logging para la aplicación.
Implementa buenas prácticas de logging con diferentes niveles y formateo estructurado.
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import json

from app.config.settings import settings


class JSONFormatter(logging.Formatter):
    """
    Formateador JSON para logs estructurados.
    Facilita el análisis de logs con herramientas de monitoreo.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Agregar información adicional si está disponible
        if hasattr(record, 'user_id'):
            log_entry['user_id'] = record.user_id
        if hasattr(record, 'user_email'):
            log_entry['user_email'] = record.user_email
        if hasattr(record, 'request_id'):
            log_entry['request_id'] = record.request_id
        if hasattr(record, 'endpoint'):
            log_entry['endpoint'] = record.endpoint
        if hasattr(record, 'method'):
            log_entry['method'] = record.method
        if hasattr(record, 'status_code'):
            log_entry['status_code'] = record.status_code
        if hasattr(record, 'duration'):
            log_entry['duration_ms'] = record.duration
        if hasattr(record, 'error_type'):
            log_entry['error_type'] = record.error_type
        
        # Agregar información de excepción si existe
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry, ensure_ascii=False)


class ColoredFormatter(logging.Formatter):
    """
    Formateador con colores para logs en consola.
    Mejora la legibilidad durante el desarrollo.
    """
    
    # Códigos de color ANSI
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[41m',   # Red background
        'RESET': '\033[0m'        # Reset
    }
    
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset = self.COLORS['RESET']
        
        # Formatear el mensaje base
        formatted = super().format(record)
        
        # Aplicar color solo al nivel de log
        formatted = formatted.replace(
            record.levelname,
            f"{color}{record.levelname}{reset}"
        )
        
        return formatted


def setup_logging() -> Dict[str, logging.Logger]:
    """
    Configura el sistema de logging de la aplicación.
    
    Returns:
        Dict con los loggers configurados para diferentes módulos
    """
    
    # Crear directorio de logs si no existe
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Configuración base
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO
    
    # ============================================================================
    # LOGGER PRINCIPAL DE LA APLICACIÓN
    # ============================================================================
    
    app_logger = logging.getLogger("farmaplus")
    app_logger.setLevel(log_level)
    app_logger.handlers.clear()  # Limpiar handlers existentes
    
    # Handler para consola (desarrollo)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = ColoredFormatter(
        fmt='%(asctime)s | %(name)s | %(levelname)s | %(module)s:%(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    app_logger.addHandler(console_handler)
    
    # Handler para archivo general (JSON estructurado)
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / "app.log",
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(JSONFormatter())
    app_logger.addHandler(file_handler)
    
    # ============================================================================
    # LOGGER PARA AUTENTICACIÓN Y SEGURIDAD
    # ============================================================================
    
    auth_logger = logging.getLogger("farmaplus.auth")
    auth_logger.setLevel(log_level)
    auth_logger.handlers.clear()
    
    # Handler específico para eventos de autenticación
    auth_handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / "auth.log",
        maxBytes=5*1024*1024,  # 5MB
        backupCount=10,
        encoding='utf-8'
    )
    auth_handler.setLevel(logging.INFO)
    auth_handler.setFormatter(JSONFormatter())
    auth_logger.addHandler(auth_handler)
    auth_logger.addHandler(console_handler)  # También a consola
    
    # ============================================================================
    # LOGGER PARA ÓRDENES Y TRANSACCIONES
    # ============================================================================
    
    orders_logger = logging.getLogger("farmaplus.orders")
    orders_logger.setLevel(log_level)
    orders_logger.handlers.clear()
    
    orders_handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / "orders.log",
        maxBytes=5*1024*1024,  # 5MB
        backupCount=10,
        encoding='utf-8'
    )
    orders_handler.setLevel(logging.INFO)
    orders_handler.setFormatter(JSONFormatter())
    orders_logger.addHandler(orders_handler)
    orders_logger.addHandler(console_handler)
    
    # ============================================================================
    # LOGGER PARA EMAILS
    # ============================================================================
    
    email_logger = logging.getLogger("farmaplus.email")
    email_logger.setLevel(log_level)
    email_logger.handlers.clear()
    
    email_handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / "email.log",
        maxBytes=2*1024*1024,  # 2MB
        backupCount=5,
        encoding='utf-8'
    )
    email_handler.setLevel(logging.INFO)
    email_handler.setFormatter(JSONFormatter())
    email_logger.addHandler(email_handler)
    email_logger.addHandler(console_handler)
    
    # ============================================================================
    # LOGGER PARA ERRORES CRÍTICOS
    # ============================================================================
    
    error_logger = logging.getLogger("farmaplus.errors")
    error_logger.setLevel(logging.ERROR)
    error_logger.handlers.clear()
    
    error_handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / "errors.log",
        maxBytes=10*1024*1024,  # 10MB
        backupCount=20,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    error_logger.addHandler(error_handler)
    error_logger.addHandler(console_handler)
    
    # ============================================================================
    # LOGGER PARA PERFORMANCE Y MÉTRICAS
    # ============================================================================
    
    perf_logger = logging.getLogger("farmaplus.performance")
    perf_logger.setLevel(logging.INFO)
    perf_logger.handlers.clear()
    
    perf_handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / "performance.log",
        maxBytes=5*1024*1024,  # 5MB
        backupCount=5,
        encoding='utf-8'
    )
    perf_handler.setLevel(logging.INFO)
    perf_handler.setFormatter(JSONFormatter())
    perf_logger.addHandler(perf_handler)
    
    # ============================================================================
    # LOGGER PARA ACTIVIDAD DE USUARIOS
    # ============================================================================
    
    activity_logger = logging.getLogger("farmaplus.activity")
    activity_logger.setLevel(logging.INFO)
    activity_logger.handlers.clear()
    
    activity_handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / "user_activity.log",
        maxBytes=5*1024*1024,  # 5MB
        backupCount=10,
        encoding='utf-8'
    )
    activity_handler.setLevel(logging.INFO)
    activity_handler.setFormatter(JSONFormatter())
    activity_logger.addHandler(activity_handler)
    
    # Prevenir propagación duplicada
    for logger in [app_logger, auth_logger, orders_logger, email_logger, error_logger, perf_logger, activity_logger]:
        logger.propagate = False
    
    return {
        'app': app_logger,
        'auth': auth_logger,
        'orders': orders_logger,
        'email': email_logger,
        'errors': error_logger,
        'performance': perf_logger,
        'activity': activity_logger
    }


def get_logger(name: str = "farmaplus") -> logging.Logger:
    """
    Obtiene un logger específico.
    
    Args:
        name: Nombre del logger (app, auth, orders, email, errors, performance, activity)
        
    Returns:
        Logger configurado
    """
    logger_name = f"farmaplus.{name}" if name != "farmaplus" else name
    return logging.getLogger(logger_name)


def log_request_info(logger: logging.Logger, request, user_id: str = None, user_email: str = None, request_id: str = None):
    """
    Helper para loggear información de requests HTTP.
    
    Args:
        logger: Logger a usar
        request: Request object de FastAPI
        user_id: ID del usuario si está autenticado
        user_email: Email del usuario (siempre que esté disponible)
        request_id: ID único del request
    """
    extra = {
        'endpoint': str(request.url.path),
        'method': request.method,
        'user_id': user_id,
        'user_email': user_email,
        'request_id': request_id,
        'user_agent': request.headers.get('user-agent'),
        'ip_address': request.client.host if request.client else None
    }
    
    logger.info(
        f"Request: {request.method} {request.url.path}",
        extra=extra
    )


def log_response_info(logger: logging.Logger, request, response, duration_ms: float, user_id: str = None, user_email: str = None, request_id: str = None):
    """
    Helper para loggear información de responses HTTP.
    
    Args:
        logger: Logger a usar
        request: Request object de FastAPI
        response: Response object
        duration_ms: Duración del request en milisegundos
        user_id: ID del usuario si está autenticado
        user_email: Email del usuario (siempre que esté disponible)
        request_id: ID único del request
    """
    extra = {
        'endpoint': str(request.url.path),
        'method': request.method,
        'status_code': response.status_code,
        'duration': duration_ms,
        'user_id': user_id,
        'user_email': user_email,
        'request_id': request_id,
        'response': response.body if response.body else None
    }
    
    level = logging.WARNING if response.status_code >= 400 else logging.INFO
    logger.log(
        level,
        f"Response: {request.method} {request.url.path} - {response.status_code} ({duration_ms:.2f}ms) resp: {response}",
        extra=extra
    )


def log_error(logger: logging.Logger, error: Exception, context: Dict[str, Any] = None, user_id: str = None, user_email: str = None):
    """
    Helper para loggear errores de manera consistente.
    
    Args:
        logger: Logger a usar
        error: Excepción capturada
        context: Contexto adicional del error
        user_id: ID del usuario si aplica
        user_email: Email del usuario si aplica
    """
    extra = {
        'error_type': type(error).__name__,
        'user_id': user_id,
        'user_email': user_email,
        **(context or {})
    }
    
    logger.error(
        f"Error: {str(error)}",
        extra=extra,
        exc_info=True
    )


# Inicializar loggers al importar el módulo
LOGGERS = setup_logging()

# Exportar loggers principales para uso directo
app_logger = LOGGERS['app']
auth_logger = LOGGERS['auth']
orders_logger = LOGGERS['orders']
email_logger = LOGGERS['email']
error_logger = LOGGERS['errors']
performance_logger = LOGGERS['performance']
activity_logger = LOGGERS['activity']
