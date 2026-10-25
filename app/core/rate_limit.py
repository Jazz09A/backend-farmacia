"""Rate limiting con slowapi.

Backend en memoria (suficiente para un solo proceso; migrar a Redis en
producción multi-worker si se requiere). Los límites se aplican por IP.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    # Backend memory: si la app corre con varios workers, los contadores
    # son por-worker. Aceptable como mitigación de fuerza bruta a corto
    # plazo; ver R21 en el backlog para migrar a Redis.
    storage_uri="memory://",
    default_limits=[],
)


__all__ = ["limiter"]
