"""Tests del modelo User (los del CacheService viven en test_cache_service.py)."""


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
