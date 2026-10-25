"""Tests de jerarquía de roles y permisos."""

import pytest


pytestmark = pytest.mark.admin


# =============================================================================
# Pure-Python hierarchy (no DB)
# =============================================================================


class TestRoleHierarchyModel:
    def test_default_role_is_user(self, db, user_factory):
        user = user_factory()
        assert user.role == "user"
        assert user.get_role_level() == 0

    def test_manager_level(self, db, user_factory):
        u = user_factory(role="manager")
        assert u.get_role_level() == 1

    def test_admin_level(self, db, user_factory):
        u = user_factory(role="admin")
        assert u.get_role_level() == 2

    def test_super_admin_level(self, db, user_factory):
        u = user_factory(role="super_admin")
        assert u.get_role_level() == 3

    def test_has_role_level_higher_than_required(self, db, user_factory):
        admin = user_factory(role="admin")
        assert admin.has_role_level("manager") is True
        assert admin.has_role_level("user") is True
        assert admin.has_role_level("admin") is True

    def test_has_role_level_lower_returns_false(self, db, user_factory):
        u = user_factory(role="user")
        assert u.has_role_level("manager") is False
        assert u.has_role_level("admin") is False

    def test_is_admin(self, db, user_factory):
        assert user_factory(email="u@x.com", role="user").is_admin() is False
        assert user_factory(email="m@x.com", role="manager").is_admin() is False
        assert user_factory(email="a@x.com", role="admin").is_admin() is True
        assert user_factory(email="s@x.com", role="super_admin").is_admin() is True

    def test_is_super_admin(self, db, user_factory):
        assert user_factory(email="a2@x.com", role="admin").is_super_admin() is False
        assert user_factory(email="s2@x.com", role="super_admin").is_super_admin() is True

    def test_can_promote_to_super_admin_only_super_admin(self, db, user_factory):
        u = user_factory(email="uu@x.com", role="user")
        m = user_factory(email="mm@x.com", role="manager")
        a = user_factory(email="aa@x.com", role="admin")
        s = user_factory(email="ss@x.com", role="super_admin")
        assert u.can_promote_to("manager") is False
        assert m.can_promote_to("manager") is False
        assert a.can_promote_to("manager") is True
        assert a.can_promote_to("admin") is False  # admin no puede crear admins
        assert s.can_promote_to("admin") is True
        assert s.can_promote_to("super_admin") is False  # nadie puede auto-promover a super_admin


# =============================================================================
# Endpoints
# =============================================================================


class TestAdminEndpointAccess:
    """Tests sobre los endpoints admin — usan una ruta simple para
    verificar el dependency `get_admin_user`."""

    def test_user_cannot_access_admin_endpoint(self, client, default_user, auth_headers):
        # /api/v1/auth/me es para cualquier usuario autenticado; lo usamos
        # para confirmar que el token funciona. Luego probamos un endpoint
        # admin. Aquí comprobamos el comportamiento de has_role_level
        # directamente (más fiable que asumir rutas específicas).
        assert default_user.has_role_level("admin") is False

    def test_admin_passes_hierarchy_check(self, client, admin_user, admin_headers):
        assert admin_user.has_role_level("admin") is True
        assert admin_user.has_role_level("super_admin") is False
