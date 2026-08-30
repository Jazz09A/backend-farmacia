"""
Helpers para logging estructurado de requests, responses y errores.

Diseño:
- Cada request recibe un `request_id` único (X-Request-ID header o UUID4).
- El request_id se inyecta en `contextvars` para que todos los logs
  automáticos (vía `get_logger` o loggers ad-hoc) lo incluyan sin pasarlo
  manualmente.
- Las funciones `log_request`, `log_response` y `log_internal_error`
  producen entradas consistentes en el logger `farmaplus.access`.
- Las funciones son seguras: nunca loggean cuerpos de respuesta, ni
  Authorization headers, ni query params con claves sensibles.
"""
from __future__ import annotations

import re
import time
import uuid
from contextvars import ContextVar
from typing import Any

from fastapi import Request
from starlette.responses import Response

from app.config.logging_config import get_logger

# ContextVar que vive durante todo el ciclo de un request (incluyendo
# tareas en background lanzadas con asyncio.create_task dentro del mismo
# request, mientras no se crucen event loops).
_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
_user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)
_user_email_var: ContextVar[str | None] = ContextVar("user_email", default=None)


ACCESS_LOGGER_NAME = "access"
INTERNAL_ERROR_LOGGER_NAME = "errors.internal"
SECURITY_LOGGER_NAME = "security"

# Patrones para redacción de secretos en mensajes de error.
_SECRET_LIKE = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|token|access[_-]?token|refresh[_-]?token)"
    r"\s*[:=]\s*([^\s,;\"'<>]{4,})"
)
# Conexiones embebidas en strings de error tipo SQLAlchemy.
_DB_URL_REDACT = re.compile(r"(?i)(server|host|database|initial[_-]?catalog)\s*=\s*[^;,\s]+")
# IDs / hashes largos -> redactar para no filtrar rowids internos.
_LONG_ALNUM = re.compile(r"[A-Za-z0-9_\-]{32,}")


def _truncate(s: str, max_len: int = 200) -> str:
    if s is None:
        return ""
    s = str(s)
    if len(s) <= max_len:
        return s
    return s[:max_len] + f"...(+{len(s) - max_len} chars)"


def new_request_id() -> str:
    """Genera un request_id corto pero único (16 chars hex)."""
    return uuid.uuid4().hex[:16]


def set_request_context(
    request_id: str | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
) -> str:
    """Inicializa el contexto del request actual. Devuelve el request_id."""
    rid = request_id or new_request_id()
    _request_id_var.set(rid)
    if user_id is not None:
        _user_id_var.set(user_id)
    if user_email is not None:
        _user_email_var.set(user_email)
    return rid


def clear_request_context() -> None:
    _request_id_var.set(None)
    _user_id_var.set(None)
    _user_email_var.set(None)


def get_current_request_id() -> str | None:
    return _request_id_var.get()


def get_current_user_id() -> str | None:
    return _user_id_var.get()


def get_current_user_email() -> str | None:
    return _user_email_var.get()


def _base_extra(request: Request | None = None) -> dict[str, Any]:
    extra: dict[str, Any] = {
        "request_id": get_current_request_id(),
        "user_id": get_current_user_id(),
        "user_email": get_current_user_email(),
    }
    if request is not None:
        extra["method"] = request.method
        extra["path"] = request.url.path
        extra["client"] = request.client.host if request.client else None
    return extra


def log_request(request: Request) -> float:
    """
    Registra el inicio del request. Devuelve el timestamp de inicio
    (perf_counter) para calcular duración en `log_response`.
    """
    start = time.perf_counter()
    logger = get_logger(ACCESS_LOGGER_NAME)
    logger.info(
        f"→ {request.method} {request.url.path}",
        extra={
            **_base_extra(request),
            "query": _truncate(str(request.query_params), 200),
            "user_agent": _truncate(request.headers.get("user-agent", ""), 120),
            "phase": "request",
        },
    )
    return start


def log_response(request: Request, response: Response, start_time: float) -> None:
    """
    Registra el fin del request con status code y duración.
    NO loggea el body de la respuesta (puede contener PII / payloads grandes).
    """
    duration_ms = (time.perf_counter() - start_time) * 1000
    status_code = getattr(response, "status_code", 0)
    level = "info"
    if status_code >= 500:
        level = "error"
    elif status_code >= 400:
        level = "warning"

    logger = get_logger(ACCESS_LOGGER_NAME)
    getattr(logger, level)(
        f"← {request.method} {request.url.path} {status_code} ({duration_ms:.1f}ms)",
        extra={
            **_base_extra(request),
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            "phase": "response",
        },
    )

    # Log de performance aparte si la request fue lenta (>2s).
    if duration_ms > 2000:
        get_logger("performance").warning(
            f"Slow request: {request.method} {request.url.path} ({duration_ms:.1f}ms)",
            extra={
                **_base_extra(request),
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )


def redact_message(message: str) -> str:
    """Scrub básico de credenciales embebidas en mensajes de error."""
    if not message:
        return message
    message = _SECRET_LIKE.sub(lambda m: f"{m.group(1)}=[REDACTED]", message)
    message = _DB_URL_REDACT.sub(lambda m: f"{m.group(1)}=[REDACTED]", message)
    # Redactar cadenas alfanuméricas largas (tokens, IDs, etc.)
    message = _LONG_ALNUM.sub("[REDACTED]", message)
    return message


def log_internal_error(
    request: Request | None,
    exc: BaseException,
    *,
    context: dict[str, Any] | None = None,
) -> str:
    """
    Loggea un error interno (5xx) con todos los detalles para debugging,
    incluyendo stack trace. Devuelve un `tracking_id` que el cliente puede
    usar para correlacionar el problema con los logs.

    El tracking_id es el mismo que el `request_id` actual; si no hay
    request activo, se genera uno nuevo.
    """
    tracking_id = get_current_request_id() or new_request_id()
    logger = get_logger(INTERNAL_ERROR_LOGGER_NAME)

    safe_context: dict[str, Any] = {"tracking_id": tracking_id}
    if context:
        for k, v in context.items():
            if isinstance(v, str):
                safe_context[k] = _truncate(redact_message(v), 500)
            else:
                safe_context[k] = v

    if request is not None:
        safe_context.setdefault("method", request.method)
        safe_context.setdefault("path", request.url.path)
        # Nunca loggear headers completos, solo flags booleanos.
        safe_context["headers_summary"] = {
            "has_authorization": bool(request.headers.get("authorization")),
            "content_type": request.headers.get("content-type"),
            "x_source_system": request.headers.get("x-source-system"),
        }

    logger.error(
        f"INTERNAL ERROR: {exc.__class__.__name__}: {redact_message(str(exc))}",
        extra={
            **_base_extra(request),
            "exception_type": exc.__class__.__name__,
            "exception_module": getattr(exc.__class__, "__module__", ""),
            "redacted_message": _truncate(redact_message(str(exc)), 500),
            "context": safe_context,
        },
    )
    return tracking_id


def log_security_event(
    event: str,
    *,
    request: Request | None = None,
    user_email: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """
    Loggea eventos de seguridad (login fallido, rate limit, intento
    sospechoso, etc.) en un canal dedicado `farmaplus.security`.
    """
    logger = get_logger(SECURITY_LOGGER_NAME)
    payload = {
        **_base_extra(request),
        "event": event,
        "user_email": user_email or get_current_user_email(),
    }
    if extra:
        payload.update({k: v for k, v in extra.items() if v is not None})
    logger.warning(f"security: {event}", extra=payload)
