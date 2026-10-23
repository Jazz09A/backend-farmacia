"""Servicio de cache con backend Redis (redis.asyncio) y fallback a memoria.

Arquitectura:
- ``MemoryBackend``: cache en memoria thread-safe con TTL (driver 'memory' y fallback).
- ``RedisBackend``: cliente ``redis.asyncio`` serializando con orjson
  (driver 'redis', usado en producción).
- ``CacheService``: facade singleton con la API pública async
  (``get``, ``set``, ``invalidate``, ``invalidate_pattern``, ``clear``,
  ``cleanup_expired``, ``get_stats``, ``generate_key``) y puentes sync
  (``get_sync``, ``set_sync``, ...) para los servicios con DB síncrona
  (artículos, blog, recomendaciones). Los puentes sync ejecutan la operation
  async en un event-loop dedicado en un hilo daemon y bloquean el hilo
  llamador por lo que dura la operación de Redis (~milisegundos).

Fallback:
- Con ``CACHE_DRIVER=redis``, si Redis falla (ConnectionError/TimeoutError)
  el backend se degrada a memoria y se re-sondea cada
  ``CACHE_REDIS_HEALTH_INTERVAL`` segundos (la siguiente operación actuando
  como sonda). Cuando Redis responde de nuevo se vuelve a usar automáticamente.

Serialización (solo backend Redis):
- orjson + envelope tipado: los tipos no-JSON (datetime, Decimal, UUID,
  objetos ORM de SQLAlchemy) se envuelven en marcadores
  ``{"__val__": [tipo, ...]}`` / ``{"__orm_class__": ..., "__data__": ...}``
  para reproducirlos a su vuelta. El backend de memoria conserva los
  objetos tal cual (igual que antes de la migración).
- Deltas documentados con respecto al cache en memoria:
  las ``tuple`` reviven como ``list`` y los ``Decimal`` reviven como ``str``
  (los schemas pydantic que los consumen re-coercionan los valores).
"""

import asyncio
import hashlib
import threading
import time
import uuid
from datetime import date, datetime, time as dt_time
from decimal import Decimal
from threading import RLock
from typing import Any

import orjson

from app.config.logging_config import get_logger
from app.config.settings import Settings

settings = Settings()

_CACHE_STATS_FIELD = "__stats__"
_BRIDGE_TIMEOUT_SECONDS = 5.0


# ─────────────────────────────────────────────────────────────────────────────
# Serialización tipada (solo backend Redis)
# ─────────────────────────────────────────────────────────────────────────────


def _envelope(kind: str, payload: Any) -> dict[str, Any]:
    return {"__val__": [kind, payload]}


def to_jsonable(value: Any) -> Any:
    """Convierte un valor del cache a algo serializable por orjson.

    Preserva la identidad de los objetos que el cache en memoria mantiene
    tal cual: ORM de SQLAlchemy (via envelope), datetime/Decimal/UUID, etc.
    Las ``tuple`` se convierten en ``list`` (delta documentado).
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return _envelope("datetime", value.isoformat())
    if isinstance(value, date):
        return _envelope("date", value.isoformat())
    if isinstance(value, dt_time):
        return _envelope("time", value.isoformat())
    if isinstance(value, Decimal):
        return _envelope("decimal", str(value))
    if isinstance(value, uuid.UUID):
        return _envelope("uuid", str(value))
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(item) for item in value]
    # Instancia de modelo ORM de SQLAlchemy (contiene _sa_instance_state)
    if hasattr(value, "_sa_instance_state"):
        return _orm_to_envelope(value)
    # Último recurso documentado: representarlo como string.
    return str(value)


def _orm_to_envelope(obj: Any) -> dict[str, Any]:
    """Empaqueta un modelo ORM: clase + atributos cargados del __dict__."""
    data: dict[str, Any] = {}
    for attr, val in vars(obj).items():
        if attr == "_sa_instance_state":
            continue
        data[attr] = to_jsonable(val)
    return {"__orm_class__": type(obj).__name__, "__data__": data}


def from_jsonable(value: Any) -> Any:
    """Revierte ``to_jsonable`` (después de ``orjson.loads``)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [from_jsonable(item) for item in value]
    if isinstance(value, dict):
        if "__val__" in value:
            kind, payload = value["__val__"]
            return _revive_scalar(kind, payload)
        if "__orm_class__" in value:
            return _revive_orm(value["__orm_class__"], value["__data__"])
        return {k: from_jsonable(v) for k, v in value.items()}
    return value


def _revive_scalar(kind: str, payload: Any) -> Any:
    if kind == "datetime":
        return datetime.fromisoformat(payload)
    if kind == "date":
        return date.fromisoformat(payload)
    if kind == "time":
        return dt_time.fromisoformat(payload)
    if kind == "decimal":
        return Decimal(payload)
    if kind == "uuid":
        return uuid.UUID(payload)
    return payload


def _resolve_orm_class(class_name: str):
    """Resuelve una clase ORM por nombre desde el paquete de modelos."""
    import app.models as models_pkg

    return getattr(models_pkg, class_name, None)


def _revive_orm(class_name: str, data: dict[str, Any]) -> Any:
    """Reconstruye una instancia ORM detached con estado 'committed'.

    ``set_committed_value`` es la API oficial de SQLAlchemy para poblar
    atributos (columnas, escalares y relationships cargados) marcándolos
    ya sincronizados; así el objeto revive con atributos legibles sin
    depender de una Session activa. Los atributos que ya no existan en el
    modelo (envelope obsoleto tras evolución del schema) se descartan.
    """
    import sqlalchemy

    model_cls = _resolve_orm_class(class_name)
    if model_cls is None:
        raise ValueError(f"Clase ORM desconocida en el cache: {class_name}")

    mapped_keys: set[str]
    try:
        mapped_keys = {key for key in sqlalchemy.inspect(model_cls).attrs.keys()}
    except Exception:
        mapped_keys = set(data)

    obj = model_cls()  # init declarativo: crea _sa_instance_state (necesario)
    for attr, val in data.items():
        if attr in mapped_keys:
            sqlalchemy.orm.attributes.set_committed_value(obj, attr, from_jsonable(val))
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# Backend en memoria
# ─────────────────────────────────────────────────────────────────────────────


class _MemoryEntry:
    """Entrada de cache en memoria con TTL."""

    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, ttl: int):
        self.value = value
        self.expires_at: float | None = (time.monotonic() + ttl) if ttl > 0 else None

    def is_expired(self) -> bool:
        return self.expires_at is not None and time.monotonic() > self.expires_at


class MemoryBackend:
    """Cache en memoria thread-safe con soporte para TTL (driver local/fallback)."""

    def __init__(self):
        self._entries: dict[str, _MemoryEntry] = {}
        self._lock = RLock()

    async def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.is_expired():
                del self._entries[key]
                return None
            return entry.value

    async def set(self, key: str, value: Any, ttl: int) -> None:
        with self._lock:
            self._entries[key] = _MemoryEntry(value, ttl)

    async def delete(self, key: str) -> bool:
        with self._lock:
            return self._entries.pop(key, None) is not None

    async def delete_prefix(self, prefix: str) -> int:
        with self._lock:
            keys = [key for key in self._entries if key.startswith(prefix)]
            for key in keys:
                del self._entries[key]
            return len(keys)

    async def clear(self) -> int:
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            return count

    async def count(self) -> int:
        with self._lock:
            return len(self._entries)

    async def count_expired(self) -> int:
        with self._lock:
            return sum(1 for entry in self._entries.values() if entry.is_expired())

    async def cleanup_expired(self) -> int:
        with self._lock:
            expired = [key for key, entry in self._entries.items() if entry.is_expired()]
            for key in expired:
                del self._entries[key]
            return len(expired)


# ─────────────────────────────────────────────────────────────────────────────
# Backend Redis (redis.asyncio)
# ─────────────────────────────────────────────────────────────────────────────


class RedisConnectionError(Exception):
    """Redis no disponible o con error transitorio de conexión."""


class RedisBackend:
    """Backend Redis asíncrono con serialización orjson y namespace dedicado."""

    def __init__(self, url: str, key_prefix: str, client: Any | None = None):
        import redis
        import redis.asyncio as redis_asyncio

        self._redis_module = redis
        self._prefix = key_prefix
        # `client` permite inyectar un cliente fake en tests (fakeredis).
        self._client = (
            client
            if client is not None
            else redis_asyncio.from_url(
                url,
                decode_responses=False,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        )

    async def ping(self) -> bool:
        return bool(await self._client.ping())

    async def get(self, key: str) -> Any | None:
        try:
            raw = await self._client.get(self._full(key))
        except (self._redis_module.ConnectionError, self._redis_module.TimeoutError, OSError) as exc:
            raise RedisConnectionError(str(exc)) from exc
        if raw is None:
            return None
        return from_jsonable(orjson.loads(raw))

    async def set(self, key: str, value: Any, ttl: int) -> None:
        payload = orjson.dumps(to_jsonable(value), default=str)
        try:
            if ttl > 0:
                await self._client.set(self._full(key), payload, ex=ttl)
            else:
                await self._client.set(self._full(key), payload)
        except (self._redis_module.ConnectionError, self._redis_module.TimeoutError, OSError) as exc:
            raise RedisConnectionError(str(exc)) from exc

    async def delete(self, key: str) -> bool:
        try:
            removed = await self._client.delete(self._full(key))
        except (self._redis_module.ConnectionError, self._redis_module.TimeoutError, OSError) as exc:
            raise RedisConnectionError(str(exc)) from exc
        return removed > 0

    async def delete_prefix(self, prefix: str) -> int:
        """Elimina con SCAN (nunca KEYS) y UNLINK (no bloqueante)."""
        match = f"{self._full(prefix)}*"
        removed = 0
        try:
            cursor: int | str = 0
            while True:
                cursor, keys = await self._client.scan(cursor=cursor, match=match, count=500)
                if keys:
                    removed += await self._client.unlink(*keys)
                cursor = int(cursor)
                if cursor == 0:
                    break
        except (self._redis_module.ConnectionError, self._redis_module.TimeoutError, OSError) as exc:
            raise RedisConnectionError(str(exc)) from exc
        return removed

    async def clear(self) -> int:
        """Limpia todas las claves del namespace del app (sin tocar stats ni otras apps)."""
        match = f"{self._prefix}*"
        removed = 0
        try:
            cursor: int | str = 0
            while True:
                cursor, keys = await self._client.scan(cursor=cursor, match=match, count=500)
                deletable = [key for key in keys if _CACHE_STATS_FIELD.encode() not in key]
                if deletable:
                    removed += await self._client.unlink(*deletable)
                cursor = int(cursor)
                if cursor == 0:
                    break
        except (self._redis_module.ConnectionError, self._redis_module.TimeoutError, OSError) as exc:
            raise RedisConnectionError(str(exc)) from exc
        return removed

    async def count(self) -> int:
        result = 0
        cursor: int | str = 0
        match = f"{self._prefix}*"
        while True:
            cursor, keys = await self._client.scan(cursor=cursor, match=match, count=500)
            result += sum(1 for key in keys if _CACHE_STATS_FIELD.encode() not in key)
            cursor = int(cursor)
            if cursor == 0:
                break
        return result

    async def incr(self, field: str, amount: int = 1) -> None:
        """Contadores compartidos entre workers (stats hash aparte del cache)."""
        await self._client.hincrby(self._full(_CACHE_STATS_FIELD), field, amount)

    async def close(self) -> None:
        import redis.exceptions

        try:
            await self._client.aclose()
        except redis.exceptions.RedisError:
            pass

    def _full(self, key: str) -> str:
        return f"{self._prefix}{key}"


# ─────────────────────────────────────────────────────────────────────────────
# Puente sync → async (event loop dedicado en un hilo daemon)
# ─────────────────────────────────────────────────────────────────────────────


class _BackgroundEventLoop:
    """Loop dedicado para ejecutar coroutines del cache desde código sync.

    Los servicios con DB síncrona (artículos/blog/recomendaciones) no pueden
    hacer ``await``; este loop permite someter la operación al pool de Redis
    asíncrono desde cualquier contexto de hilo.
    """

    _instance: "_BackgroundEventLoop | None" = None
    _lock = RLock()
    _loop: asyncio.AbstractEventLoop | None = None
    _thread: threading.Thread | None = None

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def run(self, coro: Any, timeout: float = _BRIDGE_TIMEOUT_SECONDS) -> Any:
        loop = self._get_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is not None and not self._loop.is_closed():
            return self._loop
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, name="cache-redis-loop", daemon=True)
        thread.start()
        self._loop = loop
        self._thread = thread
        return loop


# ─────────────────────────────────────────────────────────────────────────────
# Facade CacheService (misma API pública que la versión en memoria)
# ─────────────────────────────────────────────────────────────────────────────


class CacheService:
    """
    Servicio de cache con backend Redis (redis.asyncio) y fallback a memoria.

    Características:
    - API async (endpoints y lifespan hacen ``await``) + puentes sync para
      servicios con DB síncrona.
    - Fallback automático a memoria cuando Redis falla, con re-sondeo
      cada ``CACHE_REDIS_HEALTH_INTERVAL`` segundos.
    - TTL configurable por prefijo (catalog:, article:, categories:, lines:)
      y por entrada.
    - Estadísticas locales por proceso + contadores compartidos en Redis.
    """

    _instance = None
    _instance_lock = RLock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return

        self.logger = get_logger("cache")
        self._enabled = getattr(settings, "CACHE_ENABLED", True)
        self._memory = MemoryBackend()
        self._redis: RedisBackend | None = None
        self._redis_down_until = 0.0  # monotonic; ventana de no reintentar Redis
        self._bg = _BackgroundEventLoop()

        driver = (getattr(settings, "CACHE_DRIVER", "memory") or "memory").lower()
        if driver == "redis":
            try:
                self._redis = RedisBackend(
                    url=getattr(settings, "REDIS_URL", "redis://localhost:6379/0"),
                    key_prefix=getattr(settings, "CACHE_REDIS_KEY_PREFIX", "farmacia:cache:"),
                )
                self.logger.info(f"CacheService: backend Redis configurado ({settings.REDIS_URL})")
            except Exception as exc:  # URL inválida u otra falla de configuración
                self.logger.error(f"CacheService: NO se pudo inicializar Redis ({exc}); usando memoria")
                self._redis = None

        # Estadísticas locales (además de los contadores compartidos en Redis)
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "invalidations": 0,
            "cleanups": 0,
        }

        self._initialized = True
        self.logger.info("CacheService inicializado (driver=%s)", driver)

    # ── helpers internos ──────────────────────────────────────────────────

    def _redis_active(self) -> bool:
        return self._redis is not None and time.monotonic() >= self._redis_down_until

    def _latch_redis_down(self, exc: Exception) -> None:
        interval = getattr(settings, "CACHE_REDIS_HEALTH_INTERVAL", 30)
        self._redis_down_until = time.monotonic() + interval
        self.logger.warning("Redis caído (%s); cache degradado a memoria por %ss", exc, interval)

    def _latch_redis_up(self) -> None:
        if self._redis_down_until:
            self._redis_down_until = 0.0
            self.logger.info("Redis responde de nuevo; cache volviendo del fallback a memoria")

    async def _bump(self, field: str, amount: int = 1) -> None:
        """Incrementa contadores locales (y compartidos en Redis si aplica)."""
        self._stats[field] = self._stats.get(field, 0) + amount
        if self._redis is not None:
            # El contador compartido no debe impedir la respuesta al usuario.
            try:
                await self._redis.incr(field, amount)
            except Exception:
                pass  # stats compartidas sin efecto en el flujo del usuario

    def _get_default_ttl(self, key: str) -> int:
        """Obtiene el TTL por defecto según el tipo de cache."""
        if key.startswith("catalog:"):
            return getattr(settings, "CACHE_CATALOG_TTL", 1800)  # 30 minutos
        elif key.startswith("article:"):
            return getattr(settings, "CACHE_DETAIL_TTL", 3600)  # 60 minutos
        elif key.startswith("categories:") or key.startswith("lines:"):
            return getattr(settings, "CACHE_STATIC_TTL", 7200)  # 2 horas
        else:
            return getattr(settings, "CACHE_DEFAULT_TTL", 1800)  # 30 minutos por defecto

    # ── generación de claves (no toca el backend) ────────────────────────

    def generate_key(self, prefix: str, *args: Any, **kwargs: Any) -> str:
        """
        Genera una clave de cache única basada en parámetros.

        Args:
            prefix: Prefijo para el tipo de cache (ej: 'catalog', 'article')
            *args: Argumentos posicionales a incluir en la clave
            **kwargs: Argumentos con nombre a incluir en la clave

        Returns:
            Clave de cache única
        """
        # Normalizar valores None a string vacío
        parts = [prefix]

        for arg in args:
            if arg is None:
                parts.append("")
            elif isinstance(arg, (int, float, str)):
                parts.append(str(arg))
            else:
                parts.append(str(arg))

        # Ordenar kwargs para consistencia
        sorted_kwargs = sorted(kwargs.items())
        for key, value in sorted_kwargs:
            if value is None:
                parts.append(f"{key}=")
            else:
                parts.append(f"{key}={value}")

        key_string = ":".join(parts)

        # Si la clave es muy larga, usar hash
        if len(key_string) > 200:
            key_hash = hashlib.md5(key_string.encode()).hexdigest()
            return f"{prefix}:hash:{key_hash}"

        return key_string

    # Alias de compatibilidad (recommendation_service lo usa).
    def _generate_key(self, prefix: str, *args: Any, **kwargs: Any) -> str:
        return self.generate_key(prefix, *args, **kwargs)

    # ── API async ────────────────────────────────────────────────────────

    async def get(self, key: str) -> Any | None:
        """
        Obtiene un valor del cache.

        Args:
            key: Clave de cache

        Returns:
            Valor cacheado o None si no existe o ha expirado
        """
        if not self._enabled:
            return None

        value: Any | None
        redis_backend = self._redis
        if redis_backend is not None and time.monotonic() >= self._redis_down_until:
            try:
                value = await redis_backend.get(key)
                self._latch_redis_up()
            except RedisConnectionError as exc:
                self._latch_redis_down(exc)
                value = await self._memory.get(key)
            except Exception as exc:  # error no transitorio: degradar solo esta op
                self.logger.error("Redis: error no esperado en GET %s (%s); usando memoria", key, exc)
                value = await self._memory.get(key)
        else:
            value = await self._memory.get(key)

        await self._bump("hits" if value is not None else "misses")
        return value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """
        Almacena un valor en el cache.

        Args:
            key: Clave de cache
            value: Valor a almacenar
            ttl: Tiempo de vida en segundos. Si es None, usa el TTL por defecto del tipo
        """
        if not self._enabled:
            return

        if ttl is None:
            ttl = self._get_default_ttl(key)

        redis_backend = self._redis
        if redis_backend is not None and time.monotonic() >= self._redis_down_until:
            try:
                await redis_backend.set(key, value, ttl)
                self._latch_redis_up()
                await self._bump("sets")
                return
            except RedisConnectionError as exc:
                self._latch_redis_down(exc)
            except Exception as exc:
                self.logger.error("Redis: error no esperado en SET %s (%s); almacenando en memoria", key, exc)
        await self._memory.set(key, value, ttl)
        await self._bump("sets")

    async def invalidate(self, key: str) -> bool:
        """
        Invalida una entrada específica del cache.

        Args:
            key: Clave de cache a invalidar

        Returns:
            True si se invalidó, False si no existía
        """
        redis_backend = self._redis
        if redis_backend is not None and time.monotonic() >= self._redis_down_until:
            try:
                removed = await redis_backend.delete(key)
                self._latch_redis_up()
                if removed:
                    await self._bump("invalidations")
                return removed
            except RedisConnectionError as exc:
                self._latch_redis_down(exc)
            except Exception as exc:
                self.logger.error("Redis: error no esperado en DELETE %s (%s); invalidando en memoria", key, exc)
        removed = await self._memory.delete(key)
        if removed:
            await self._bump("invalidations")
        return removed

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalida todas las entradas que coincidan con un patrón (prefijo).

        Args:
            pattern: Patrón de prefijo (ej: 'catalog:', 'article:ABC123')

        Returns:
            Número de entradas invalidadas
        """
        redis_backend = self._redis
        if redis_backend is not None and time.monotonic() >= self._redis_down_until:
            try:
                count = await redis_backend.delete_prefix(pattern)
                self._latch_redis_up()
                if count:
                    await self._bump("invalidations", count)
                return count
            except RedisConnectionError as exc:
                self._latch_redis_down(exc)
            except Exception as exc:
                self.logger.error(
                    "Redis: error no esperado en SCAN UNLINK %s (%s); invalidando en memoria", pattern, exc
                )
        count = await self._memory.delete_prefix(pattern)
        if count:
            await self._bump("invalidations", count)
        return count

    async def clear(self) -> int:
        """
        Limpia todo el cache.

        Returns:
            Número de entradas eliminadas
        """
        redis_backend = self._redis
        if redis_backend is not None and time.monotonic() >= self._redis_down_until:
            try:
                count = await redis_backend.clear()
                self._latch_redis_up()
                await self._bump("invalidations", count)
                return count
            except RedisConnectionError as exc:
                self._latch_redis_down(exc)
            except Exception as exc:
                self.logger.error("Redis: error no esperado en CLEAR (%s); limpiando en memoria", exc)
        count = await self._memory.clear()
        await self._bump("invalidations", count)
        return count

    async def cleanup_expired(self) -> int:
        """
        Limpia las entradas expiradas.

        Con backend Redis no hace falta: expira por TTL de forma nativa.
        Mantiene el contrato del endpoint admin y con driver 'memory' sí
        libera las entradas expiradas reales.

        Returns:
            Número de entradas eliminadas
        """
        count = await self._memory.cleanup_expired()
        if count:
            await self._bump("cleanups", count)
        return count

    async def get_stats(self) -> dict[str, Any]:
        """
        Obtiene estadísticas del cache.

        Returns:
            Diccionario con estadísticas (misma forma que la versión en memoria,
            con los campos extra del driver Redis: 'driver' y 'redis_*').
        """
        redis_backend = self._redis
        if redis_backend is not None and time.monotonic() >= self._redis_down_until:
            try:
                total_entries = await redis_backend.count()
                self._latch_redis_up()
            except Exception as exc:
                self.logger.error("Redis: error no esperado en stats (%s); reportando memoria", exc)
                total_entries = await self._memory.count()
        else:
            total_entries = await self._memory.count()

        expired_count = 0  # Redis expira nativamente; memoria se limpia en cleanup_expired
        active_entries = max(total_entries - expired_count, 0)

        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total_requests * 100) if total_requests > 0 else 0

        stats: dict[str, Any] = {
            "enabled": self._enabled,
            "driver": "redis" if self._redis is not None else "memory",
            "redis_active": self._redis_active(),
            "total_entries": total_entries,
            "expired_entries": expired_count,
            "active_entries": active_entries,
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "sets": self._stats["sets"],
            "invalidations": self._stats["invalidations"],
            "cleanups": self._stats["cleanups"],
            "hit_rate": round(hit_rate, 2),
            "total_requests": total_requests,
        }
        return stats

    async def close(self) -> None:
        """Cierra el pool de Redis (lifespan shutdown)."""
        if self._redis is not None:
            await self._redis.close()

    async def ping_redis(self) -> bool:
        """Ping al backend Redis (lifespan/health). False si driver=memory o caído."""
        if self._redis is None:
            return False
        try:
            ok = await self._redis.ping()
            if ok:
                self._latch_redis_up()
            return ok
        except Exception as exc:
            self._latch_redis_down(exc)
            return False

    def enable(self) -> None:
        """Habilita el cache (contrato sync igual que la versión anterior)."""
        self._enabled = True
        self.logger.info("Cache habilitado")

    def disable(self) -> None:
        """Deshabilita el cache (contrato sync igual que la versión anterior)."""
        self._enabled = False
        self.logger.info("Cache deshabilitado")

    # ── puentes sync (servicios con DB síncrona) ─────────────────────────

    def get_sync(self, key: str) -> Any | None:
        return self._bg.run(self.get(key))

    def set_sync(self, key: str, value: Any, ttl: int | None = None) -> None:
        self._bg.run(self.set(key, value, ttl))

    def invalidate_sync(self, key: str) -> bool:
        return bool(self._bg.run(self.invalidate(key)))

    def invalidate_pattern_sync(self, pattern: str) -> int:
        return int(self._bg.run(self.invalidate_pattern(pattern)))

    def clear_sync(self) -> int:
        return int(self._bg.run(self.clear()))

    def cleanup_expired_sync(self) -> int:
        return int(self._bg.run(self.cleanup_expired()))

    def get_stats_sync(self) -> dict[str, Any]:
        return dict(self._bg.run(self.get_stats()))


# Instancia singleton
cache_service = CacheService()
