"""`/api/auth/me/` reports the caller's resolved capabilities.

The UI decides which controls to render, and it used to do that with a
role-to-capability map kept in the frontend. That map was written before
roles were data, so it only knew the five built-ins: a custom role came back
in `roles`, matched nothing, and its holder was shown the interface of
someone with no permissions at all.

Serving the resolved set removes the second copy. These assertions are
mostly about that: what the endpoint returns has to track the role table,
including for roles that did not exist when the frontend was written.

None of this is a security boundary. The API enforces every capability on
the request itself, which test_roles_as_data.py and test_role_management.py
cover; this endpoint only tells a client what to bother drawing.
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleName, User, UserRole


def _user(email, *role_keys):
    user = User.objects.create_user(
        email=email, password="StrongPass123!", first_name="T", last_name="U"
    )
    for key in role_keys:
        role, _ = Role.objects.get_or_create(name=key)
        UserRole.objects.create(user=user, role=role)
    return user


def _me(user):
    client = APIClient()
    client.force_authenticate(user)
    resp = client.get("/api/auth/me/")
    assert resp.status_code == 200, resp.data
    return resp.data


@pytest.mark.django_db
class TestCapabilitiesAreReported:
    def test_the_field_is_present(self):
        assert "capabilities" in _me(_user("a@e.com", RoleName.VIEWER))

    def test_an_admin_holds_workspace_manage(self):
        assert "workspace.manage" in _me(_user("b@e.com", RoleName.PLATFORM_ADMIN))["capabilities"]

    def test_a_viewer_does_not(self):
        assert "workspace.manage" not in _me(_user("c@e.com", RoleName.VIEWER))["capabilities"]

    def test_a_user_with_no_roles_holds_nothing(self):
        """Fail closed. An account mid-onboarding should see a bare shell,
        not every control on the assumption that empty means unrestricted."""
        assert _me(_user("d@e.com"))["capabilities"] == []

    def test_the_set_is_the_union_across_roles(self):
        both = _user("e@e.com", RoleName.APPROVER, RoleName.WORKFLOW_DESIGNER)
        caps = set(_me(both)["capabilities"])
        approver = set(Role.objects.get(key="approver").capabilities)
        designer = set(Role.objects.get(key="workflow_designer").capabilities)
        assert caps == approver | designer

    def test_it_is_sorted(self):
        caps = _me(_user("f@e.com", RoleName.PLATFORM_ADMIN))["capabilities"]
        assert caps == sorted(caps)

    def test_anonymous_callers_are_refused(self):
        assert APIClient().get("/api/auth/me/").status_code in (401, 403)


@pytest.mark.django_db
class TestCustomRoles:
    """The reason this endpoint exists."""

    def test_a_custom_role_grants_its_capabilities(self):
        Role.objects.create(
            name="site_manager",
            label="Site Manager",
            capabilities=["workflow.view", "instance.transition"],
            rank=25,
        )
        caps = _me(_user("g@e.com", "site_manager"))["capabilities"]
        assert set(caps) == {"workflow.view", "instance.transition"}

    def test_it_grants_nothing_it_was_not_given(self):
        Role.objects.create(
            name="ward_sister", label="Ward Sister",
            capabilities=["instance.view"], rank=20,
        )
        assert _me(_user("h@e.com", "ward_sister"))["capabilities"] == ["instance.view"]

    def test_editing_a_role_changes_what_its_holders_report(self):
        """No frontend change should be needed to widen a role. This is what
        the hardcoded map made impossible."""
        role = Role.objects.create(
            name="deputy", label="Deputy", capabilities=["instance.view"], rank=20,
        )
        holder = _user("i@e.com", "deputy")
        assert _me(holder)["capabilities"] == ["instance.view"]

        role.capabilities = ["instance.view", "instance.approve"]
        role.save()

        # A fresh User instance, not refresh_from_db(). capabilities_for()
        # memoises on the object as `_ff_capabilities` so that a request
        # consulting it on every permission check does not re-query, and
        # refresh_from_db() only reloads fields — it leaves that attribute
        # sitting there. Each real request builds the user from its token, so
        # this is what the next one actually sees.
        next_request = User.objects.get(pk=holder.pk)
        assert set(_me(next_request)["capabilities"]) == {"instance.view", "instance.approve"}


@pytest.mark.django_db
class TestOtherUsersAreUnaffected:
    def test_the_user_list_does_not_carry_capabilities(self):
        """Only ever the caller's own. Listing everyone's would say who is
        worth attacking, and cost a query per row to do it."""
        admin = _user("j@e.com", RoleName.PLATFORM_ADMIN)
        _user("k@e.com", RoleName.VIEWER)

        client = APIClient()
        client.force_authenticate(admin)
        body = client.get("/api/users/").json()
        rows = body["results"] if isinstance(body, dict) else body

        assert rows, "no users returned"
        for row in rows:
            assert "capabilities" not in row
