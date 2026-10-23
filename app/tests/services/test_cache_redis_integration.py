"""
Tests de integración del backend Redis (servidor REAL).

Contrato que se verifica (por qué importa):
- El TTL se aplica de verdad en el servidor (PTTL), no solo en el cliente.
- ``invalidate_pattern`` usa SCAN y borra únicamente el namespace del app;
  borrar claves de otras apps en un Redis compartido sería un incidente.
- Los contadores de stats se comparten con INCR (multi-worker).
- No intenta operaciones bloqueantes (KEYS, FLUSHDB): en producción el
  evento Redis es compartido y bloquear la instancia completa no es aceptable.

Estos tests se marcan ``integration`` + ``redis`` y se SKIP-ean si no hay
servidor Redis accesible en REDIS_URL (por eso el CI puede correr la suite
hermética sin Redis).
"""

import asyncio

import pytest
import redis.asyncio as redis_asyncio

from app.config.settings import Settings
from app.services import cache_service as cache_module

REDIS_URL = Settings().REDIS_URL
PREFIX = "farmacia:cache:test:integra:"


@pytest.fixture
async def redis_client():
    """Cliente Redis real (BD del REDIS_URL configurado). SKIP si no hay servidor."""
    import redis.exceptions as rerr

    client = redis_asyncio.from_url(REDIS_URL, decode_responses=False)
    try:
        await client.ping()
    except (rerr.ConnectionError, rerr.TimeoutError, OSError):
        pytest.skip("Redis no disponible para tests de integración")

    # Limpieza inicial: solo el namespace de pruebas de esta BD
    keys = [key async for key in client.scan_iter(match=PREFIX + "*")]
    if keys:
        await client.delete(*keys)
    yield client
    keys = [key async for key in client.scan_iter(match=PREFIX + "*")]
    if keys:
        await client.delete(*keys)
    await client.aclose()


@pytest.fixture
async def facade_redis(redis_client):
    """Facade CacheService limpio montado sobre Redis real."""
    svc = object.__new__(cache_module.CacheService)
    svc.logger = cache_module.get_logger("cache-integration")
    svc._enabled = True
    svc._memory = cache_module.MemoryBackend()
    svc._redis = cache_module.RedisBackend(url=REDIS_URL, key_prefix=PREFIX, client=redis_client)
    svc._redis_down_until = 0.0
    svc._bg = cache_module._BackgroundEventLoop()
    svc._stats = {"hits": 0, "misses": 0, "sets": 0, "invalidations": 0, "cleanups": 0}
    return svc


@pytest.mark.integration
@pytest.mark.cache
@pytest.mark.redis
class TestRedisIntegration:
    async def test_roundtrip_real_server(self, facade_redis):
        value = {"page": 1, "total": 10, "items": [{"co_art": "A1", "price": "99.50"}]}
        await facade_redis.set("catalog:p1", value, ttl=60)
        assert await facade_redis.get("catalog:p1") == value

    async def test_ttl_is_real_on_server(self, facade_redis, redis_client):
        await facade_redis.set("catalog:ttl", 1, ttl=120)
        pttl = await redis_client.pttl(PREFIX + "catalog:ttl")
        assert 0 < pttl <= 120_000

    async def test_invalidate_pattern_scans_and_deletes_scope_only(self, facade_redis, redis_client):
        await facade_redis.set("catalog:1", 1, ttl=60)
        await facade_redis.set("catalog:2", 2, ttl=60)
        await facade_redis.set("article:Z", 3, ttl=60)
        # Clave de OTRA app: jamás debe morir por nuestras invalidaciones.
        foreign_key = "otra-app:muchos-mas:clave"
        await redis_client.set(foreign_key, "keep", ex=60)

        count = await facade_redis.invalidate_pattern("catalog:")
        assert count == 2
        assert await redis_client.get(foreign_key) == b"keep"

    async def test_clear_scopes_to_app_namespace_and_keeps_stats(self, facade_redis, redis_client):
        await facade_redis.set("a", 1, ttl=60)
        await facade_redis.set("b", 2, ttl=60)
        await facade_redis.get("a")  # genera contadores compartidos (stats hash)
        foreign_key = "otra-app:clave"
        await redis_client.set(foreign_key, "keep", ex=60)

        removed = await facade_redis.clear()
        assert removed == 2
        # Stats hash sobrevive (es meta-datos del app, no entradas de cache).
        stats_key = PREFIX + cache_module._CACHE_STATS_FIELD
        assert await redis_client.hlen(stats_key) >= 1
        assert await redis_client.get(foreign_key) == b"keep"

    async def test_counters_are_shared_with_incr(self, facade_redis, redis_client):
        await facade_redis.set("hit:k", "v", ttl=60)
        await facade_redis.get("hit:k")
        await facade_redis.get("no:existe")
        stats_key = PREFIX + cache_module._CACHE_STATS_FIELD
        hits = await redis_client.hget(stats_key, "hits")
        misses = await redis_client.hget(stats_key, "misses")
        assert int(hits) == 1
        assert int(misses) == 1

    async def test_concurrent_operations_are_safe(self, facade_redis):
        async def writer(i: int):
            await facade_redis.set(f"conc:{i}", {"i": i}, ttl=60)

        async def reader(i: int):
            return await facade_redis.get(f"conc:{i}")

        await asyncio.gather(*(writer(i) for i in range(30)))
        results = await asyncio.gather(*(reader(i) for i in range(30)))
        assert results == [{"i": i} for i in range(30)]

    async def test_stats_shape_matches_original_contract(self, facade_redis):
        await facade_redis.set("s:k", "v", ttl=60)
        await facade_redis.get("s:k")
        stats = await facade_redis.get_stats()
        assert stats["enabled"] is True
        assert stats["driver"] == "redis"
        assert stats["redis_active"] is True
        assert stats["total_entries"] >= 1
        assert stats["hits"] >= 1

    async def test_cleanup_expired_is_noop_metadata(self, facade_redis):
        # Con driver Redis, cleanup_expired solo limpia fallback en memoria:
        # Redis expira nativamente (contrato del endpoint admin).
        cleaned = await facade_redis.cleanup_expired()
        assert cleaned == 0
