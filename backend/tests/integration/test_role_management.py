"""Role management API (docs/ROLES.md step 3).

Roles became data in steps 1 and 2, but nothing could create one: there was
no route, and `set_roles` validated against the old RoleName enum, so a
custom role could not even be assigned. This is what makes "a client can have
a Site Manager" true rather than theoretical.

The guards matter more than the CRUD. A role system that lets an
administrator lock themselves out, or lets a mid-tier user grant themselves
more than they hold, is worse than a fixed enum.
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import CAPABILITIES, Role, RoleName, User, UserRole


def _user(email, *role_keys, **kw):
    user = User.objects.create_user(
        email=email, password="StrongPass123!", first_name="T", last_name="U", **kw
    )
    for key in role_keys:
        role, _ = Role.objects.get_or_create(name=key)
        UserRole.objects.create(user=user, role=role)
    return user


def _client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


@pytest.fixture
def admin(db):
    return _user("admin@e.com", RoleName.PLATFORM_ADMIN)


@pytest.fixture
def designer(db):
    return _user("designer@e.com", RoleName.WORKFLOW_DESIGNER)


@pytest.fixture
def viewer(db):
    return _user("viewer@e.com", RoleName.VIEWER)


SITE_MANAGER = {
    "key": "site_manager",
    "label": "Site Manager",
    "capabilities": ["workflow.view", "instance.view", "instance.transition"],
    "rank": 25,
}


@pytest.mark.django_db
class TestListRoles:
    def test_any_signed_in_user_can_list(self, viewer):
        """Role pickers and badges render for everyone, so reading the list
        cannot require administration rights."""
        assert _client(viewer).get("/api/roles/").status_code == 200

    def test_anonymous_cannot(self):
        assert APIClient().get("/api/roles/").status_code in (401, 403)

    def test_lists_seeded_roles_with_their_capabilities(self, admin):
        body = _client(admin).get("/api/roles/").json()
        rows = body["results"] if isinstance(body, dict) else body
        admin_row = next(r for r in rows if r["key"] == "platform_admin")
        assert admin_row["is_system"] is True
        assert "workspace.manage" in admin_row["capabilities"]


@pytest.mark.django_db
class TestCreateRole:
    def test_admin_can_create_a_custom_role(self, admin):
        resp = _client(admin).post("/api/roles/", SITE_MANAGER, format="json")
        assert resp.status_code == 201, resp.data
        assert resp.data["is_system"] is False

    def test_created_role_is_not_a_system_role(self, admin):
        _client(admin).post("/api/roles/", SITE_MANAGER, format="json")
        assert Role.objects.get(key="site_manager").is_system is False

    def test_a_designer_cannot_create_roles(self, designer):
        """Designing workflows is not administering the workspace."""
        resp = _client(designer).post("/api/roles/", SITE_MANAGER, format="json")
        assert resp.status_code == 403

    def test_unknown_capabilities_are_rejected(self, admin):
        payload = {**SITE_MANAGER, "capabilities": ["workflow.view", "workflow.destroy"]}
        resp = _client(admin).post("/api/roles/", payload, format="json")
        assert resp.status_code == 400
        assert "workflow.destroy" in str(resp.data)

    def test_a_role_cannot_outrank_its_creator(self, admin):
        """Otherwise creating a role is a route to escalation: make one that
        outranks you, assign it to yourself, and the rank cap is meaningless."""
        payload = {**SITE_MANAGER, "rank": 99}
        resp = _client(admin).post("/api/roles/", payload, format="json")
        assert resp.status_code == 400

    def test_duplicate_key_is_rejected(self, admin):
        _client(admin).post("/api/roles/", SITE_MANAGER, format="json")
        resp = _client(admin).post("/api/roles/", SITE_MANAGER, format="json")
        assert resp.status_code == 400


@pytest.mark.django_db
class TestEditRole:
    def test_capabilities_can_be_changed(self, admin):
        c = _client(admin)
        c.post("/api/roles/", SITE_MANAGER, format="json")
        role = Role.objects.get(key="site_manager")
        resp = c.patch(f"/api/roles/{role.id}/",
                       {"capabilities": ["workflow.view"]}, format="json")
        assert resp.status_code == 200
        assert Role.objects.get(pk=role.pk).capabilities == ["workflow.view"]

    def test_a_system_role_cannot_be_edited(self, admin):
        """The built-in five are what every existing check assumes. Editing
        one silently changes the meaning of the whole install."""
        viewer_role, _ = Role.objects.get_or_create(name=RoleName.VIEWER)
        resp = _client(admin).patch(f"/api/roles/{viewer_role.id}/",
                                    {"capabilities": list(CAPABILITIES)}, format="json")
        assert resp.status_code == 403

    def test_the_key_cannot_be_changed(self, admin):
        """Bundles reference roles by key, so a rename silently breaks any
        app exported before it."""
        c = _client(admin)
        c.post("/api/roles/", SITE_MANAGER, format="json")
        role = Role.objects.get(key="site_manager")
        c.patch(f"/api/roles/{role.id}/", {"key": "renamed"}, format="json")
        assert Role.objects.get(pk=role.pk).key == "site_manager"


@pytest.mark.django_db
class TestDeleteRole:
    def test_an_unused_custom_role_can_be_deleted(self, admin):
        c = _client(admin)
        c.post("/api/roles/", SITE_MANAGER, format="json")
        role = Role.objects.get(key="site_manager")
        assert c.delete(f"/api/roles/{role.id}/").status_code == 204

    def test_a_system_role_cannot_be_deleted(self, admin):
        viewer_role, _ = Role.objects.get_or_create(name=RoleName.VIEWER)
        assert _client(admin).delete(f"/api/roles/{viewer_role.id}/").status_code == 403

    def test_a_role_in_use_cannot_be_deleted(self, admin):
        """Deleting an assigned role would strip permissions from people
        without anyone choosing to."""
        c = _client(admin)
        c.post("/api/roles/", SITE_MANAGER, format="json")
        role = Role.objects.get(key="site_manager")
        holder = _user("holder@e.com")
        UserRole.objects.create(user=holder, role=role)

        resp = c.delete(f"/api/roles/{role.id}/")
        assert resp.status_code == 409
        assert "in use" in str(resp.data).lower()


@pytest.mark.django_db
class TestAssignRoles:
    def test_a_custom_role_can_be_assigned(self, admin):
        """The whole point. This failed before, because set_roles validated
        against the RoleName enum rather than the table."""
        c = _client(admin)
        c.post("/api/roles/", SITE_MANAGER, format="json")
        target = _user("target@e.com", RoleName.VIEWER)

        resp = c.post(f"/api/users/{target.id}/roles/",
                      {"roles": ["site_manager"]}, format="json")
        assert resp.status_code == 200, resp.data
        assert set(UserRole.objects.filter(user=target)
                   .values_list("role__key", flat=True)) == {"site_manager"}

    def test_an_unknown_role_is_rejected(self, admin):
        target = _user("target2@e.com")
        resp = _client(admin).post(f"/api/users/{target.id}/roles/",
                                   {"roles": ["nonexistent"]}, format="json")
        assert resp.status_code == 400

    def test_nobody_can_assign_above_their_own_rank(self, db):
        """Without this, any role carrying user.assign_roles is a path to
        platform admin: grant yourself the higher role and you are done."""
        assigner = _user("assigner@e.com", RoleName.WORKFLOW_DESIGNER)
        Role.objects.get_or_create(name=RoleName.PLATFORM_ADMIN)
        target = _user("target3@e.com")

        resp = _client(assigner).post(f"/api/users/{target.id}/roles/",
                                      {"roles": ["platform_admin"]}, format="json")
        assert resp.status_code in (400, 403)
        assert not UserRole.objects.filter(user=target).exists()

    def test_the_last_administrator_cannot_be_demoted(self, admin):
        """Locking everyone out of role management is unrecoverable through
        the API, so it is refused rather than warned about."""
        Role.objects.get_or_create(name=RoleName.VIEWER)
        resp = _client(admin).post(f"/api/users/{admin.id}/roles/",
                                   {"roles": ["viewer"]}, format="json")
        assert resp.status_code == 409
        assert UserRole.objects.filter(user=admin, role__key="platform_admin").exists()

    def test_an_administrator_can_be_demoted_when_another_remains(self, admin):
        Role.objects.get_or_create(name=RoleName.VIEWER)
        _user("admin2@e.com", RoleName.PLATFORM_ADMIN)
        resp = _client(admin).post(f"/api/users/{admin.id}/roles/",
                                   {"roles": ["viewer"]}, format="json")
        assert resp.status_code == 200, resp.data


@pytest.mark.django_db
class TestKeyAndNameStayInSync:
    """`key` is what the API and bundles use; `name` is what get_user_roles
    and every legacy check read. A role created through the API sets only
    `key`, and previously left `name` blank, so its holder's roles serialised
    as [""] and no role-name check could ever match."""

    def test_creating_with_a_key_fills_the_name(self, admin):
        _client(admin).post("/api/roles/", SITE_MANAGER, format="json")
        role = Role.objects.get(key="site_manager")
        assert role.name == "site_manager"

    def test_creating_with_a_name_fills_the_key(self, db):
        role = Role.objects.create(name="ward_sister")
        assert role.key == "ward_sister"

    def test_an_assigned_custom_role_serialises_by_name(self, admin):
        from apps.accounts.serializers import UserSerializer

        c = _client(admin)
        c.post("/api/roles/", SITE_MANAGER, format="json")
        target = _user("named@e.com")
        c.post(f"/api/users/{target.id}/roles/", {"roles": ["site_manager"]}, format="json")

        assert UserSerializer(target).data["roles"] == ["site_manager"]

    def test_capability_lookup_works_for_a_custom_role(self, admin):
        """The end that matters: a custom role must actually grant things."""
        from apps.accounts.permissions import has_capability

        c = _client(admin)
        c.post("/api/roles/", SITE_MANAGER, format="json")
        target = _user("capable@e.com")
        c.post(f"/api/users/{target.id}/roles/", {"roles": ["site_manager"]}, format="json")

        target.refresh_from_db()
        assert has_capability(target, "instance.transition")
        assert not has_capability(target, "workflow.design")
