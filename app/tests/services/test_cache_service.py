"""
Tests unitarios del sistema de cache (migración a Redis).

Contrato que se verifica (por qué importa):
- MemoryBackend implementa la semántica EXACTA del cache original (dict + TTL),
  porque es el fallback que sostiene el API cuando Redis falla.
- La serialización tipada de Redis debe reproducir los objetos que los
  productores reales escriben (ORM del blog, Decimal del catálogo, datetime),
  si no, el cache entregaría datos corruptos con driver 'redis'.
- El fallback Redis→memoria debe activarse sin fallar la request del usuario
  y Redis debe volver a usarse solo después del intervalo de salud;
  un fallback que nunca vuelve a Redis degradaría el hit rate para siempre.
"""

import time
import uuid
from datetime import date, datetime, time as dt_time
from decimal import Decimal

import fakeredis
import pytest

from app.services import cache_service as cache_module


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def make_redis_backend(prefix: str = "farmacia:cache:") -> cache_module.RedisBackend:
    """RedisBackend con un cliente fakeredis inyectado (sin servidor real)."""
    fake_async = fakeredis.aioredis.FakeRedis()
    return cache_module.RedisBackend(url="redis://test", key_prefix=prefix, client=fake_async)


def make_facade_with_redis(prefix: str = "farmacia:cache:") -> tuple[cache_module.CacheService, object]:
    """Facade limpio (nou singleton) montado en driver 'redis' con fakeredis."""
    svc = object.__new__(cache_module.CacheService)
    svc.logger = cache_module.get_logger("cache-test")
    svc._enabled = True
    svc._memory = cache_module.MemoryBackend()
    svc._redis = make_redis_backend(prefix)
    svc._redis_down_until = 0.0
    svc._bg = cache_module._BackgroundEventLoop()
    svc._stats = {"hits": 0, "misses": 0, "sets": 0, "invalidations": 0, "cleanups": 0}
    return svc, svc._redis


# ─────────────────────────────────────────────────────────────────────────────
# MemoryBackend: semántica de referencia (igual que el cache original)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.cache
class TestMemoryBackend:
    async def test_set_get_roundtrip(self):
        backend = cache_module.MemoryBackend()
        await backend.set("k", {"a": 1}, ttl=60)
        assert await backend.get("k") == {"a": 1}

    async def test_get_missing_returns_none(self):
        backend = cache_module.MemoryBackend()
        assert await backend.get("no-existe") is None

    async def test_overwrite(self):
        backend = cache_module.MemoryBackend()
        await backend.set("k", "v1", ttl=60)
        await backend.set("k", "v2", ttl=60)
        assert await backend.get("k") == "v2"

    async def test_ttl_expires(self, monkeypatch):
        backend = cache_module.MemoryBackend()
        await backend.set("k", "v", ttl=10)
        now = time.monotonic()
        monkeypatch.setattr(cache_module.time, "monotonic", lambda: now + 60)
        assert await backend.get("k") is None

    async def test_ttl_zero_never_expires(self, monkeypatch):
        backend = cache_module.MemoryBackend()
        await backend.set("k", "v", ttl=0)
        now = time.monotonic()
        monkeypatch.setattr(cache_module.time, "monotonic", lambda: now + 10_000_000)
        assert await backend.get("k") == "v"

    async def test_delete_true_false(self):
        backend = cache_module.MemoryBackend()
        await backend.set("k", 1, ttl=60)
        assert await backend.delete("k") is True
        assert await backend.delete("k") is False

    async def test_delete_prefix_counts_and_is_scoped(self):
        backend = cache_module.MemoryBackend()
        await backend.set("catalog:1", 1, ttl=60)
        await backend.set("catalog:2", 2, ttl=60)
        await backend.set("article:X", 3, ttl=60)
        assert await backend.delete_prefix("catalog:") == 2
        assert await backend.get("article:X") == 3

    async def test_clear_counts(self):
        backend = cache_module.MemoryBackend()
        await backend.set("a", 1, ttl=60)
        await backend.set("b", 2, ttl=60)
        assert await backend.clear() == 2
        assert await backend.count() == 0

    async def test_cleanup_expired_removes_only_expired(self, monkeypatch):
        backend = cache_module.MemoryBackend()
        await backend.set("vivo", 1, ttl=100)
        await backend.set("muerto", 2, ttl=1)
        now = time.monotonic()
        monkeypatch.setattr(cache_module.time, "monotonic", lambda: now + 50)
        assert await backend.cleanup_expired() == 1
        assert await backend.get("vivo") == 1
        assert await backend.get("muerto") is None

    async def test_count_active(self):
        backend = cache_module.MemoryBackend()
        await backend.set("a", 1, ttl=60)
        await backend.set("b", 2, ttl=60)
        assert await backend.count() == 2


# ─────────────────────────────────────────────────────────────────────────────
# Serialización tipada (orjson + envelope): fidelidad de los productores reales
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.cache
class TestSerialization:
    async def test_primitives_and_containers(self):
        value = {"a": 1, "b": [1, 2, 3], "c": "x", "d": None, "e": True, "f": 1.5}
        assert cache_module.to_jsonable(value) == value
        assert cache_module.from_jsonable(value) == value

    async def test_tuple_revives_as_list(self):
        # Delta documentado: el cache en memoria conservaba tuplas; vía Redis
        # reviven como list. Los consumidores de blog (posts, total) hacen
        # unpacking, que es compatible con list.
        assert cache_module.from_jsonable(cache_module.to_jsonable((1, 2))) == [1, 2]

    async def test_datetime_revives_as_datetime(self):
        value = {"at": datetime(2026, 1, 2, 3, 4, 5)}
        revived = cache_module.from_jsonable(cache_module.to_jsonable(value))
        assert revived == {"at": datetime(2026, 1, 2, 3, 4, 5)}

    async def test_date_and_time_revive(self):
        assert cache_module.from_jsonable(cache_module.to_jsonable(date(2026, 1, 2))) == date(2026, 1, 2)
        assert cache_module.from_jsonable(cache_module.to_jsonable(dt_time(3, 4, 5))) == dt_time(3, 4, 5)

    async def test_decimal_revives_as_decimal(self):
        # Los precios del catálogo vienen como Decimal; si revivieran como str,
        # los schemas que validan precios fallarían por coerción inesperada.
        value = {"price": Decimal("123.45")}
        revived = cache_module.from_jsonable(cache_module.to_jsonable(value))
        assert revived == {"price": Decimal("123.45")}

    async def test_uuid_revives_as_uuid(self):
        uid = uuid.uuid4()
        assert cache_module.from_jsonable(cache_module.to_jsonable({"id": uid})) == {"id": uid}

    async def test_unknown_object_falls_back_to_str(self):
        # Último recurso documentado: repr como str (no rompe la operación).
        revived = cache_module.from_jsonable(cache_module.to_jsonable(object()))
        assert isinstance(revived, str)

    async def test_orm_envelope_roundtrip_blog_category(self):
        from app.models.blog import BlogCategory

        category = BlogCategory(name="Nutrición", slug="nutricion", description="Pan 100% integral", deleted=False)

        revived = cache_module.from_jsonable(cache_module.to_jsonable(category))
        assert type(revived) is BlogCategory
        assert revived.name == "Nutrición"
        assert revived.slug == "nutricion"
        assert revived.description == "Pan 100% integral"
        assert revived.deleted is False

    async def test_orm_envelope_roundtrip_blog_post_with_nested_category_and_datetime(self):
        # El producer get_published_posts arma BlogPost y le attacha .category
        # (más created_at/published_at como datetime); el cache de Redis debe
        # reproducirlos para los consumers que leen post.category.name.
        from datetime import datetime

        from sqlalchemy.orm import attributes as orm_attributes

        from app.models.blog import BlogCategory, BlogPost

        category = BlogCategory(name="Deporte", slug="deporte")
        post = BlogPost(title="Titulo", slug="titulo", content="contenido")
        orm_attributes.set_committed_value(post, "category", category)
        orm_attributes.set_committed_value(post, "created_at", datetime(2026, 2, 1, 10, 30))

        revived = cache_module.from_jsonable(cache_module.to_jsonable(post))
        assert type(revived) is BlogPost
        assert revived.title == "Titulo"
        assert revived.category.name == "Deporte"
        assert revived.created_at == datetime(2026, 2, 1, 10, 30)

    async def test_unknown_orm_class_raises(self):
        payload = {"__orm_class__": "ClaseQueNoExiste", "__data__": {}}
        with pytest.raises(ValueError):
            cache_module.from_jsonable(payload)


# ─────────────────────────────────────────────────────────────────────────────
# RedisBackend con fakeredis: claves, TTL y contadores
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.cache
class TestRedisBackendFake:
    async def test_namespace_and_roundtrip(self):
        backend = make_redis_backend(prefix="prueba:cache:")
        await backend.set("catalog:p1", {"x": 1}, ttl=60)
        assert await backend.get("catalog:p1") == {"x": 1}
        raw_key = "prueba:cache:catalog:p1"
        assert await backend._client.exists(raw_key) == 1

    async def test_ttl_is_applied(self):
        backend = make_redis_backend()
        await backend.set("k", 1, ttl=120)
        pttl = await backend._client.pttl(backend._full("k"))
        assert 0 < pttl <= 120_000

    async def test_ttl_zero_is_persistent(self):
        backend = make_redis_backend()
        await backend.set("k", 1, ttl=0)
        assert await backend._client.pttl(backend._full("k")) == -1

    async def test_delete_and_scan_delete_prefix(self):
        backend = make_redis_backend()
        await backend.set("catalog:1", 1, ttl=60)
        await backend.set("catalog:2", 2, ttl=60)
        await backend.set("article:Z", 3, ttl=60)
        assert await backend.delete("catalog:1") is True
        assert await backend.delete_prefix("catalog:") == 1
        assert await backend.get("article:Z") == 3

    async def test_incr_counters(self):
        backend = make_redis_backend()
        await backend.incr("hits", 3)
        await backend.incr("hits")
        assert await backend._client.hget(backend._full("__stats__"), "hits") == b"4"


# ─────────────────────────────────────────────────────────────────────────────
# Facade: TTL por defecto, API pública y gating
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.cache
class TestFacade:
    def test_default_ttls_by_prefix(self):
        svc = cache_module.cache_service
        s = cache_module.settings
        assert svc._get_default_ttl("catalog:page=1") == s.CACHE_CATALOG_TTL
        assert svc._get_default_ttl("article:AB123") == s.CACHE_DETAIL_TTL
        assert svc._get_default_ttl("categories:all") == s.CACHE_STATIC_TTL
        assert svc._get_default_ttl("lines:LIN") == s.CACHE_STATIC_TTL
        assert svc._get_default_ttl("otro:x") == s.CACHE_DEFAULT_TTL

    def test_generate_key_deterministic(self):
        svc = cache_module.cache_service
        a = svc.generate_key("catalog", page=1, limit=20)
        b = svc.generate_key("catalog", page=1, limit=20)
        c = svc.generate_key("catalog", page=2, limit=20)
        assert a == b
        assert a != c

    def test_generate_key_hash_on_long_keys(self):
        svc = cache_module.cache_service
        long_key = svc.generate_key("catalog", search="x" * 300)
        assert long_key.startswith("catalog:hash:") and len(long_key) < 60

    def test_generate_key_alias_still_works(self):
        # recommendation_service usa _generate_key (compatibilidad pública).
        svc = cache_module.cache_service
        assert svc._generate_key("article", "CO1") == svc.generate_key("article", "CO1")

    async def test_disable_gates_get_and_set(self):
        svc, _ = make_facade_with_redis()
        await svc.set("k", "v", ttl=60)
        svc.disable()
        assert await svc.get("k") is None
        await svc.set("k2", "v2", ttl=60)
        assert await svc._memory.get("k2") is None
        svc.enable()
        assert await svc.get("k") == "v"

    async def test_get_stats_shape_original_contract(self):
        svc, _ = make_facade_with_redis()
        await svc.set("k", "v", ttl=60)
        await svc.get("k")  # hit
        await svc.get("no")  # miss
        stats = await svc.get_stats()
        # Campos del contrato original (CacheStatsResponse) siempre presentes.
        for field in (
            "enabled",
            "total_entries",
            "expired_entries",
            "active_entries",
            "hits",
            "misses",
            "sets",
            "invalidations",
            "cleanups",
            "hit_rate",
            "total_requests",
        ):
            assert field in stats
        assert stats["hits"] == 1 and stats["misses"] == 1
        assert stats["sets"] == 1
        assert stats["total_entries"] == 1
        assert stats["driver"] == "redis" and stats["redis_active"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Puentes sync (servicios con DB síncrona usan *_sync)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.cache
class TestSyncBridge:
    async def test_sync_roundtrip(self):
        svc, _ = make_facade_with_redis()
        svc.set_sync("bridge:k", {"v": 1})
        assert svc.get_sync("bridge:k") == {"v": 1}
        assert svc.invalidate_sync("bridge:k") is True
        assert svc.invalidate_sync("bridge:k") is False

    async def test_sync_pattern_and_clear(self):
        svc, _ = make_facade_with_redis()
        for i in range(3):
            svc.set_sync(f"catalog:{i}", i, ttl=60)
        assert svc.invalidate_pattern_sync("catalog:") == 3
        svc.set_sync("x", 1, ttl=60)
        assert svc.clear_sync() == 1

    async def test_bg_loop_thread_alive_and_named(self):
        svc, _ = make_facade_with_redis()
        svc.get_sync("warm:x")  # fuerza la creación del loop
        assert svc._bg._thread is not None
        assert svc._bg._thread.name == "cache-redis-loop"
        assert svc._bg._thread.is_alive()


# ─────────────────────────────────────────────────────────────────────────────
# Fallback Redis → memoria, con ventana de salud y retorno automático
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.cache
class TestFallback:
    async def test_redis_failure_degrades_to_memory_without_failing(self, monkeypatch):
        svc, redis_backend = make_facade_with_redis()
        # Respaldo previo en memoria: solo el路径 de escritura a Redis falló.
        await svc._memory.set("f:k", "mem-value", ttl=60)

        async def broken_get(_key: str):
            raise cache_module.RedisConnectionError("boom")

        orig_get = redis_backend.get  # noqa: F841  # se preserva para restaurar manualmente si hace falta
        monkeypatch.setattr(redis_backend, "get", broken_get)

        assert await svc.get("f:k") == "mem-value"  # ❗ no lanza: la request del usuario no se cae
        assert svc._redis_down_until > time.monotonic()  # ventana de salud activada

        monkeypatch.undo()

    async def test_redis_recovers_after_health_interval(self, monkeypatch):
        svc, redis_backend = make_facade_with_redis()

        # 1) Redis caído: la siguiente op falla y actúa de sonda.
        async def broken_set(_key, _value, _ttl):
            raise cache_module.RedisConnectionError("boom")

        monkeypatch.setattr(redis_backend, "set", broken_set)
        await svc.set("r:k", "v1", ttl=60)
        assert svc._redis_down_until > time.monotonic()
        monkeypatch.undo()

        # Con la ventana activa, un SET va a memoria (no intenta Redis).
        await svc.set("r:k2", "mem", ttl=60)
        assert await svc._memory.get("r:k2") == "mem"

        # 2) Escala el intervalo de salud: la siguiente op vuelve a Redis.
        fake_clock = time.monotonic()
        monkeypatch.setattr(cache_module.time, "monotonic", lambda: fake_clock + 10_000)
        await svc.set("r:k3", "redis", ttl=60)
        assert await redis_backend.get("r:k3") == "redis"
        assert svc._redis_down_until == 0.0

    async def test_stats_report_redis_active_false_when_down(self, monkeypatch):
        svc, _ = make_facade_with_redis()
        svc._redis_down_until = time.monotonic() + 100
        stats = await svc.get_stats()
        assert stats["redis_active"] is False
