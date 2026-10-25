"""Tests del modelo User y del CacheService."""
import threading
import time
import uuid

import pytest

from app.models.user import User
from app.services.cache_service import CacheService


@pytest.fixture
def cache():
    """Cache singleton con `_enabled=True` para los tests."""
    c = CacheService()
    c._enabled = True
    c._cache.clear()
    c._stats = {
        "hits": 0,
        "misses": 0,
        "sets": 0,
        "invalidations": 0,
        "cleanups": 0,
    }
    return c


# =============================================================================
# User model
# =============================================================================


class TestUserModel:
    def test_password_is_hashed_not_plain(self, db, user_factory):
        user = user_factory()
        # El password NO debe estar en claro
        assert user.hashed_password != "Password1"
        assert user.hashed_password.startswith("$2")  # bcrypt
        # Pero debe poder verificarse
        from app.core.security import verify_password

        assert verify_password("Password1", user.hashed_password) is True
        assert verify_password("wrong", user.hashed_password) is False

    def test_inactive_user_is_flagged(self, db, user_factory):
        u = user_factory(is_active=False)
        assert u.is_active is False

    def test_full_name_for_natural(self, db, user_factory):
        u = user_factory(user_type="natural", first_name="Ana", last_name="Pérez")
        assert u.full_name == "Ana Pérez"

    def test_full_name_for_juridico(self, db, user_factory):
        u = user_factory(
            user_type="juridico",
            first_name=None,
            last_name=None,
            email="company@x.com",
        )
        # jurídico usa company_name
        u.company_name = "Mi Empresa"
        assert u.full_name == "Mi Empresa"

    def test_display_name_delegates_to_full_name(self, db, user_factory):
        u = user_factory(first_name="Pedro", last_name="Gómez")
        assert u.display_name == "Pedro Gómez"

    def test_repr_includes_email(self, db, user_factory):
        u = user_factory(email="x@y.com")
        assert "x@y.com" in repr(u)


# =============================================================================
# CacheService
# =============================================================================


class TestCacheService:
    def test_set_and_get(self, cache):
        cache.set("foo", "bar", ttl=60)
        assert cache.get("foo") == "bar"

    def test_get_missing_returns_none(self, cache):
        assert cache.get(f"nonexistent-{uuid.uuid4()}") is None

    def test_ttl_expiration(self, cache):
        cache.set(f"k-{uuid.uuid4()}", "v", ttl=1)
        time.sleep(1.1)
        assert cache.get(f"k-") is None  # ya expiró, o nunca estuvo

    def test_clear_prefix_only_affects_matching_keys(self, cache):
        unique = uuid.uuid4().hex
        cache.set(f"article:{unique}:1", "a")
        cache.set(f"article:{unique}:2", "b")
        cache.set(f"user:{unique}:1", "u")
        cache.invalidate_pattern(f"article:{unique}")
        assert cache.get(f"article:{unique}:1") is None
        assert cache.get(f"article:{unique}:2") is None
        assert cache.get(f"user:{unique}:1") == "u"

    def test_hit_miss_counters(self, cache):
        unique = uuid.uuid4().hex
        cache.set(f"k-{unique}", "v", ttl=60)
        cache.get(f"k-{unique}")  # hit
        cache.get(f"k-{unique}")  # hit
        cache.get(f"missing-{unique}")  # miss
        stats = cache.get_stats()
        assert stats["hits"] >= 2
        assert stats["misses"] >= 1

    def test_thread_safe_under_concurrent_writes(self, cache):
        errors: list[Exception] = []
        unique = uuid.uuid4().hex

        def writer(i: int):
            try:
                for j in range(50):
                    cache.set(f"key-{unique}-{i}-{j}", j, ttl=60)
                    _ = cache.get(f"key-{unique}-{i}-{j}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
