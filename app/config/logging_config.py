"""
Configuración centralizada de logging para la aplicación.
Implementa buenas prácticas de logging con diferentes niveles y formateo estructurado.
"""

import json
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

from app.config.settings import Settings
from app.utils.timezone import get_ve_now

settings = Settings()


def _current_request_id() -> str | None:
    """Lee el request_id del ContextVar si está disponible."""
    try:
        from app.utils.logging_helpers import get_current_request_id
        return get_current_request_id()
    except Exception:
        return None


def _current_user_id() -> str | None:
    try:
        from app.utils.logging_helpers import get_current_user_id
        return get_current_user_id()
    except Exception:
        return None


def _current_user_email() -> str | None:
    try:
        from app.utils.logging_helpers import get_current_user_email
        return get_current_user_email()
    except Exception:
        return None

class JSONFormatter(logging.Formatter):
    """
    Formateador JSON para logs estructurados.
    Facilita el análisis de logs con herramientas de monitoreo.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": get_ve_now().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Inyectar request_id del ContextVar si no fue pasado en extra.
        _rid = _current_request_id()
        if _rid and "request_id" not in record.__dict__:
            log_entry["request_id"] = _rid
        _uid = _current_user_id()
        if _uid and "user_id" not in record.__dict__:
            log_entry["user_id"] = _uid
        _umail = _current_user_email()
        if _umail and "user_email" not in record.__dict__:
            log_entry["user_email"] = _umail

        # Atributos explícitos (pisan los del ContextVar si se pasan).
        for attr in (
            "user_id", "user_email", "request_id", "endpoint", "method",
            "status_code", "duration_ms", "error_type", "exception_type",
            "tracking_id", "event", "phase", "query", "user_agent",
            "client", "ip_address", "redacted_message", "context",
        ):
            if attr in record.__dict__:
                log_entry[attr] = record.__dict__[attr]

        # Agregar información de excepción si existe
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

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


def setup_logging() -> dict[str, logging.Logger]:
    """
    Configura el sistema de logging de la aplicación.

    Returns:
        Dict con los loggers configurados para diferentes módulos
    """

    # Crear directorio de logs si no existe
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Configuración base
    log_level = logging.DEBUG if settings.app.DEBUG else logging.INFO

    # ============================================================================
    # HANDLERS COMPARTIDOS
    # ============================================================================

    def _build_console_handler() -> logging.Handler:
        h = logging.StreamHandler(sys.stdout)
        h.setLevel(log_level)
        h.setFormatter(ColoredFormatter(
            fmt='%(asctime)s | %(name)s | %(levelname)s | %(module)s:%(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        return h

    def _build_file_handler(name: str, max_bytes: int, backups: int, level: int) -> logging.Handler:
        h = logging.handlers.RotatingFileHandler(
            filename=log_dir / name,
            maxBytes=max_bytes,
            backupCount=backups,
            encoding='utf-8'
        )
        h.setLevel(level)
        h.setFormatter(JSONFormatter())
        return h

    # Una única instancia de cada handler para evitar duplicación cuando
    # varios loggers comparten el mismo handler.
    _CONSOLE_HANDLER = _build_console_handler()

    # ============================================================================
    # LOGGER PRINCIPAL DE LA APLICACIÓN
    # ============================================================================

    app_logger = logging.getLogger("farmaplus")
    app_logger.setLevel(log_level)
    app_logger.handlers.clear()
    app_logger.addHandler(_CONSOLE_HANDLER)
    app_logger.addHandler(_build_file_handler("app.log", 10 * 1024 * 1024, 5, logging.INFO))

    # ============================================================================
    # LOGGER DE ACCESO (request/response automáticos)
    # ============================================================================

    access_logger = logging.getLogger("farmaplus.access")
    access_logger.setLevel(logging.INFO)
    access_logger.handlers.clear()
    access_logger.addHandler(_CONSOLE_HANDLER)
    access_logger.addHandler(_build_file_handler("access.log", 10 * 1024 * 1024, 10, logging.INFO))

    # ============================================================================
    # LOGGER PARA AUTENTICACIÓN Y SEGURIDAD
    # ============================================================================

    auth_logger = logging.getLogger("farmaplus.auth")
    auth_logger.setLevel(log_level)
    auth_logger.handlers.clear()
    auth_logger.addHandler(_CONSOLE_HANDLER)
    auth_logger.addHandler(_build_file_handler("auth.log", 5 * 1024 * 1024, 10, logging.INFO))

    security_logger = logging.getLogger("farmaplus.security")
    security_logger.setLevel(logging.INFO)
    security_logger.handlers.clear()
    security_logger.addHandler(_CONSOLE_HANDLER)
    security_logger.addHandler(_build_file_handler("security.log", 5 * 1024 * 1024, 20, logging.INFO))

    # ============================================================================
    # LOGGER PARA ÓRDENES Y TRANSACCIONES
    # ============================================================================

    orders_logger = logging.getLogger("farmaplus.orders")
    orders_logger.setLevel(log_level)
    orders_logger.handlers.clear()
    orders_logger.addHandler(_CONSOLE_HANDLER)
    orders_logger.addHandler(_build_file_handler("orders.log", 5 * 1024 * 1024, 10, logging.INFO))

    # ============================================================================
    # LOGGER PARA EMAILS
    # ============================================================================

    email_logger = logging.getLogger("farmaplus.email")
    email_logger.setLevel(log_level)
    email_logger.handlers.clear()
    email_logger.addHandler(_CONSOLE_HANDLER)
    email_logger.addHandler(_build_file_handler("email.log", 2 * 1024 * 1024, 5, logging.INFO))

    # ============================================================================
    # LOGGER PARA ERRORES CRÍTICOS (500, excepciones no controladas)
    # ============================================================================

    error_logger = logging.getLogger("farmaplus.errors")
    error_logger.setLevel(logging.ERROR)
    error_logger.handlers.clear()
    error_logger.addHandler(_CONSOLE_HANDLER)
    error_logger.addHandler(_build_file_handler("errors.log", 10 * 1024 * 1024, 20, logging.ERROR))

    internal_error_logger = logging.getLogger("farmaplus.errors.internal")
    internal_error_logger.setLevel(logging.ERROR)
    internal_error_logger.handlers.clear()
    internal_error_logger.addHandler(_CONSOLE_HANDLER)
    internal_error_logger.addHandler(_build_file_handler("internal_errors.log", 10 * 1024 * 1024, 20, logging.ERROR))

    # ============================================================================
    # LOGGER PARA PERFORMANCE Y MÉTRICAS
    # ============================================================================

    perf_logger = logging.getLogger("farmaplus.performance")
    perf_logger.setLevel(logging.INFO)
    perf_logger.handlers.clear()
    perf_logger.addHandler(_CONSOLE_HANDLER)
    perf_logger.addHandler(_build_file_handler("performance.log", 5 * 1024 * 1024, 5, logging.INFO))

    # ============================================================================
    # LOGGER PARA ACTIVIDAD DE USUARIOS
    # ============================================================================

    activity_logger = logging.getLogger("farmaplus.activity")
    activity_logger.setLevel(logging.INFO)
    activity_logger.handlers.clear()
    activity_logger.addHandler(_CONSOLE_HANDLER)
    activity_logger.addHandler(_build_file_handler("user_activity.log", 5 * 1024 * 1024, 10, logging.INFO))

    # Prevenir propagación duplicada
    for logger in (
        app_logger, access_logger, auth_logger, security_logger, orders_logger,
        email_logger, error_logger, internal_error_logger, perf_logger, activity_logger,
    ):
        logger.propagate = False

    return {
        'app': app_logger,
        'access': access_logger,
        'auth': auth_logger,
        'security': security_logger,
        'orders': orders_logger,
        'email': email_logger,
        'errors': error_logger,
        'errors_internal': internal_error_logger,
        'performance': perf_logger,
        'activity': activity_logger,
    }


def get_logger(name: str = "farmaplus") -> logging.Logger:
    """
    Obtiene un logger específico.

    Args:
        name: Nombre del logger (app, access, auth, security, orders, email,
              errors, errors_internal, performance, activity)

    Returns:
        Logger configurado
    """
    if name in ("farmaplus", ""):
        return logging.getLogger("farmaplus")
    return logging.getLogger(f"farmaplus.{name}")


def log_request_info(logger: logging.Logger, request, user_id: str | None = None, user_email: str | None = None, request_id: str | None = None):
    """
    DEPRECATED: usar `app.utils.logging_helpers.log_request` que además
    inyecta request_id en contextvars para correlación automática.
    Se conserva por compatibilidad temporal.
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


def log_response_info(logger: logging.Logger, request, response, duration_ms: float, user_id: str | None = None, user_email: str | None = None, request_id: str | None = None):
    """
    DEPRECATED: usar `app.utils.logging_helpers.log_response`.
    """
    extra = {
        'endpoint': str(request.url.path),
        'method': request.method,
        'status_code': response.status_code,
        'duration': duration_ms,
        'user_id': user_id,
        'user_email': user_email,
        'request_id': request_id,
    }
    level = logging.WARNING if response.status_code >= 400 else logging.INFO
    logger.log(
        level,
        f"Response: {request.method} {request.url.path} - {response.status_code} ({duration_ms:.2f}ms)",
        extra=extra
    )


def log_error(logger: logging.Logger, error: Exception, context: dict[str, Any] | None = None, user_id: str | None = None, user_email: str | None = None):
    """
    DEPRECATED: usar `app.utils.logging_helpers.log_internal_error` que
    genera un tracking_id y aplica redacción de secretos.
    """
    extra = {
        'error_type': type(error).__name__,
        'user_id': user_id,
        'user_email': user_email,
        **(context or {})
    }
    logger.error(
        f"Error: {error!s}",
        extra=extra
    )


# Inicializar loggers al importar el módulo
LOGGERS = setup_logging()

# Exportar loggers principales para uso directo
app_logger = LOGGERS['app']
access_logger = LOGGERS['access']
auth_logger = LOGGERS['auth']
security_logger = LOGGERS['security']
orders_logger = LOGGERS['orders']
email_logger = LOGGERS['email']
error_logger = LOGGERS['errors']
internal_error_logger = LOGGERS['errors_internal']
performance_logger = LOGGERS['performance']
activity_logger = LOGGERS['activity']
