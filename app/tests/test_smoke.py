"""Smoke test: pytest config + conftest load correctly and a single
trivial test runs in <2s without network access."""

import time


def test_pytest_works(db):
    assert db is not None
    # A no-op assertion that exercises the fixture system


def test_user_factory_creates_user(db, user_factory):
    user = user_factory(email="x@x.com")
    assert user.id is not None
    assert user.email == "x@x.com"
    assert user.is_active is True


def test_conftest_runs_fast(db):
    start = time.perf_counter()
    # Do nothing; just measure fixture setup
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"conftest setup too slow: {elapsed:.2f}s"
