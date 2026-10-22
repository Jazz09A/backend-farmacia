# """
# Middleware personalizado para logging y monitoreo de requests.
# """

# import time
# import uuid
# from typing import Callable
# from fastapi import Request, Response
# from starlette.middleware.base import BaseHTTPMiddleware

# from app.config.logging_config import get_logger, log_request_info, log_response_info

# # Obtener loggers específicos
# app_logger = get_logger("app")
# performance_logger = get_logger("performance")
# activity_logger = get_logger("activity")


# class LoggingMiddleware(BaseHTTPMiddleware):
#     """
#     Middleware para logging automático de todas las requests y responses.
#     Captura métricas de performance y actividad de usuarios.
#     """

#     async def dispatch(self, request: Request, call_next: Callable) -> Response:
#         if request.method == "OPTIONS":
#             return await call_next(request)
#         # Generar ID único para el request
#         request_id = str(uuid.uuid4())

#         # Capturar tiempo de inicio
#         start_time = time.time()

#         # Intentar obtener user_id y email del token si está presente
#         user_id = None
#         user_email = None
#         try:
#             # Si hay un token de autorización, intentar extraer el user_id y email
#             auth_header = request.headers.get("authorization")
#             if auth_header and auth_header.startswith("Bearer "):
#                 # Aquí podrías decodificar el token para obtener el user_id y email
#                 # Por ahora dejamos como None, pero en producción deberías decodificar el JWT
#                 pass
#         except Exception:
#             pass

#         # Intentar obtener email de los parámetros de query o body para endpoints públicos
#         if not user_email:
#             try:
#                 # Para endpoints de login/registro, el email suele estar en el body
#                 if request.method == "POST" and request.url.path in ["/api/v1/auth/login", "/api/v1/auth/register"]:
#                     # Intentar leer el body para obtener el email
#                     body = await request.body()
#                     if body:
#                         import json
#                         try:
#                             data = json.loads(body.decode())
#                             user_email = data.get('email')
#                         except:
#                             pass
#             except Exception:
#                 pass

#         # Loggear información del request
#         log_request_info(
#             app_logger,
#             request,
#             user_id=user_id,
#             user_email=user_email,
#             request_id=request_id
#         )

#         # Loggear actividad específica para ciertos endpoints
#         if self._is_important_endpoint(request.url.path):
#             activity_logger.info(
#                 f"User activity: {request.method} {request.url.path}",
#                 extra={
#                     'user_id': user_id,
#                     'user_email': user_email,
#                     'request_id': request_id,
#                     'endpoint': str(request.url.path),
#                     'method': request.method,
#                     'ip_address': request.client.host if request.client else None,
#                     'user_agent': request.headers.get('user-agent')
#                 }
#             )

#         # Procesar request
#         response = await call_next(request)

#         # Calcular duración
#         duration_ms = (time.time() - start_time) * 1000

#         # Loggear información del response
#         log_response_info(
#             app_logger,
#             request,
#             response,
#             duration_ms,
#             user_id=user_id,
#             user_email=user_email,
#             request_id=request_id
#         )

#         # Loggear métricas de performance
#         if duration_ms > 1000:  # Requests lentos (>1 segundo)
#             performance_logger.warning(
#                 f"Slow request detected: {request.method} {request.url.path}",
#                 extra={
#                     'endpoint': str(request.url.path),
#                     'method': request.method,
#                     'duration': duration_ms,
#                     'user_id': user_id,
#                     'user_email': user_email,
#                     'request_id': request_id,
#                     'status_code': response.status_code
#                 }
#             )
#         elif self._is_important_endpoint(request.url.path):
#             performance_logger.info(
#                 f"Performance: {request.method} {request.url.path}",
#                 extra={
#                     'endpoint': str(request.url.path),
#                     'method': request.method,
#                     'duration': duration_ms,
#                     'user_id': user_id,
#                     'user_email': user_email,
#                     'request_id': request_id,
#                     'status_code': response.status_code
#                 }
#             )

#         # Agregar headers de tracking
#         response.headers["X-Request-ID"] = request_id
#         response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"

#         return response

#     def _is_important_endpoint(self, path: str) -> bool:
#         """
#         Determina si un endpoint es importante para logging detallado.

#         Args:
#             path: Ruta del endpoint

#         Returns:
#             True si es un endpoint importante
#         """
#         important_paths = [
#             "/api/v1/auth/",
#             "/api/v1/orders/",
#             "/api/v1/admin/",
#             "/api/v1/users/",
#             "/api/v1/cart/",
#             "/api/v1/favorites/"
#         ]

#         return any(path.startswith(important_path) for important_path in important_paths)


# class SecurityMiddleware(BaseHTTPMiddleware):
#     """
#     Middleware para logging de eventos de seguridad.
#     """

#     async def dispatch(self, request: Request, call_next: Callable) -> Response:
#         # Capturar información de seguridad
#         auth_header = request.headers.get("authorization")
#         user_agent = request.headers.get("user-agent", "")
#         ip_address = request.client.host if request.client else "unknown"

#         # Detectar patrones sospechosos
#         suspicious_patterns = [
#             "script", "alert", "javascript:", "vbscript:", "onload=", "onerror=",
#             "../", "..\\", "/etc/passwd", "cmd.exe", "powershell"
#         ]

#         # Revisar parámetros de query por patrones sospechosos
#         query_string = str(request.url.query)
#         if any(pattern in query_string.lower() for pattern in suspicious_patterns):
#             security_logger = get_logger("errors")
#             security_logger.warning(
#                 f"Suspicious query parameters detected",
#                 extra={
#                     'ip_address': ip_address,
#                     'user_agent': user_agent,
#                     'endpoint': str(request.url.path),
#                     'query_string': query_string,
#                     'security_event': 'suspicious_query'
#                 }
#             )

#         # Detectar intentos de acceso sin autorización a endpoints protegidos
#         protected_paths = ["/api/v1/admin/", "/api/v1/users/me"]
#         if any(request.url.path.startswith(path) for path in protected_paths):
#             if not auth_header:
#                 security_logger = get_logger("auth")
#                 security_logger.warning(
#                     f"Unauthorized access attempt to protected endpoint",
#                     extra={
#                         'ip_address': ip_address,
#                         'user_agent': user_agent,
#                         'endpoint': str(request.url.path),
#                         'security_event': 'unauthorized_access_attempt'
#                     }
#                 )

#         response = await call_next(request)

#         # Loggear eventos de autenticación fallida
#         if response.status_code == 401:
#             security_logger = get_logger("auth")
#             security_logger.warning(
#                 f"Authentication failed",
#                 extra={
#                     'ip_address': ip_address,
#                     'user_agent': user_agent,
#                     'endpoint': str(request.url.path),
#                     'method': request.method,
#                     'security_event': 'authentication_failed'
#                 }
#             )

#         return response
