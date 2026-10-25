"""Tests de N+1: contar queries y verificar límites razonables."""

import uuid

import pytest
from sqlalchemy import event


@pytest.fixture
def query_counter():
    """Cuenta las queries ejecutadas en una sesión de SQLAlchemy."""
    from app.tests.conftest import TestingSessionLocal

    counter = {"count": 0, "statements": []}

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        counter["count"] += 1
        counter["statements"].append(statement[:200])

    engine = TestingSessionLocal().get_bind()
    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    yield counter
    event.remove(engine, "before_cursor_execute", before_cursor_execute)


class TestFavoritesNoN1:
    def test_get_favorites_with_products_does_n_plus_1(self, db, user_factory, query_counter):
        from app.models.favorites import UserFavorite
        from app.models.product import Product
        from app.services.favorites_service import FavoritesService
        from app.utils.timezone import get_ve_now

        user = user_factory()

        # Crear 5 productos favoritos del usuario
        for i in range(5):
            product = Product(
                id=str(uuid.uuid4()),
                name=f"Producto {i}",
                slug=f"producto-{i}",
                description=f"Desc {i}",
                image="default.png",
                price=10.0,
                in_stock=True,
                created_at=get_ve_now(),
            )
            db.add(product)
            db.flush()
            fav = UserFavorite(user_id=user.id, product_id=product.id)
            db.add(fav)
        db.commit()

        query_counter["count"] = 0
        favorites, _ = FavoritesService.get_favorites_with_products(db, user.id, skip=0, limit=20)
        # Para 5 favoritos: 1 count + 1 select + 1 selectinload = ~3
        # Sin selectinload sería 1 + 1 + 5 = 7
        assert query_counter["count"] <= 5, f"Posible N+1: {query_counter['count']} queries ejecutadas"
        assert len(favorites) == 5
