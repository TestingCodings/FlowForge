"""Step 2 of roles-as-data (docs/ROLES.md §2.3): capability checks, shadowing.

`require_capability` is introduced *alongside* the role checks, not in place
of them. The role checks stay authoritative for now; these tests assert the
two mechanisms agree for every built-in role and every capability. Only once
that holds for the whole matrix is it safe to flip, because a permissions
change is the one class where "mostly working" quietly grants or denies the
wrong thing.
"""
import pytest

from apps.accounts.models import CAPABILITIES, SYSTEM_ROLES, Role, RoleName, User, UserRole
from apps.accounts.permissions import (
    ROLE_HIERARCHY, capabilities_for, has_capability, has_min_role, require_capability,
)


def _user_with(email, *role_keys):
    user = User.objects.create_user(
        email=email, password="StrongPass123!", first_name="T", last_name="U",
    )
    for key in role_keys:
        role, _ = Role.objects.get_or_create(name=key)
        UserRole.objects.create(user=user, role=role)
    return user


@pytest.mark.django_db
class TestCapabilitiesFor:
    def test_unions_capabilities_across_roles(self):
        user = _user_with("multi@e.com", RoleName.VIEWER, RoleName.APPROVER)
        caps = capabilities_for(user)
        assert "instance.approve" in caps      # from approver
        assert "instance.view" in caps          # from both

    def test_a_user_with_no_roles_has_none(self):
        assert capabilities_for(_user_with("bare@e.com")) == set()

    def test_anonymous_has_none(self):
        from django.contrib.auth.models import AnonymousUser

        assert capabilities_for(AnonymousUser()) == set()

    def test_result_is_cached_on_the_request_user(self):
        """Resolved on every permission check, so it must not re-query."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        user = _user_with("cached@e.com", RoleName.APPROVER)
        with CaptureQueriesContext(connection) as ctx:
            capabilities_for(user)
            capabilities_for(user)
            capabilities_for(user)
        assert len(ctx.captured_queries) == 1


@pytest.mark.django_db
class TestRequireCapability:
    def test_permits_a_held_capability(self):
        require_capability(_user_with("ok@e.com", RoleName.APPROVER), "instance.approve")

    def test_denies_a_missing_one(self):
        from rest_framework.exceptions import PermissionDenied

        with pytest.raises(PermissionDenied):
            require_capability(_user_with("no@e.com", RoleName.VIEWER), "workflow.design")

    def test_denial_names_the_capability_and_the_action(self):
        from rest_framework.exceptions import PermissionDenied

        user = _user_with("why@e.com", RoleName.VIEWER)
        with pytest.raises(PermissionDenied) as exc:
            require_capability(user, "workflow.design", action="edit this workflow")
        message = str(exc.value)
        assert "workflow.design" in message and "edit this workflow" in message

    def test_an_unknown_capability_is_refused_not_granted(self):
        """A typo must fail closed. Granting on an unrecognised name would
        turn a mistake into an open door."""
        from rest_framework.exceptions import PermissionDenied

        admin = _user_with("admin@e.com", RoleName.PLATFORM_ADMIN)
        with pytest.raises(PermissionDenied):
            require_capability(admin, "workflow.destroy_everything")


@pytest.mark.django_db
class TestAgreesWithTheRoleHierarchy:
    """The shadow check. Until these agree across the whole matrix, the role
    checks must stay authoritative."""

    # Which capability each `require_min_role(...)` site is really asking
    # about — derived from what the guarded endpoints actually do.
    MIN_ROLE_TO_CAPABILITY = {
        "viewer": "workflow.view",
        "participant": "instance.create",
        "approver": "instance.approve",
        "workflow_designer": "workflow.design",
        "platform_admin": "workspace.manage",
    }

    @pytest.mark.parametrize("role_key", [r.value for r in RoleName])
    @pytest.mark.parametrize("minimum,capability", list(MIN_ROLE_TO_CAPABILITY.items()))
    def test_capability_matches_min_role(self, role_key, minimum, capability):
        user = _user_with(f"{role_key}-{minimum}@e.com", role_key)
        by_role = has_min_role(user, minimum)
        by_capability = has_capability(user, capability)
        assert by_role == by_capability, (
            f"{role_key}: has_min_role({minimum})={by_role} but "
            f"has_capability({capability})={by_capability} — the two "
            f"mechanisms disagree, so flipping would change who is permitted"
        )

    def test_every_capability_is_held_by_someone(self):
        """A capability no role grants is dead — it would deny everyone once
        the checks are flipped."""
        granted = set()
        for spec in SYSTEM_ROLES.values():
            granted |= set(spec["capabilities"])
        assert set(CAPABILITIES) == granted

    def test_hierarchy_and_rank_order_agree(self):
        by_rank = sorted(SYSTEM_ROLES.items(), key=lambda kv: kv[1]["rank"])
        assert [k for k, _ in by_rank] == ROLE_HIERARCHY
