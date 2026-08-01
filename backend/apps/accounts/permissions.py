"""
Centralised role-based permission classes for FlowForge.

Hierarchy (each tier includes all tiers below it):
  platform_admin > workflow_designer > approver > participant > viewer

Usage in views:
    permission_classes = [IsAuthenticated, IsParticipant]
    # or inline for action-specific gating:
    require_role(request.user, "approver", action="approve this transition")
    require_min_role(request.user, "participant", action="create an instance")
"""

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

# Retained for the shadow tests and for `has_min_role`, which is now only a
# convenience for "this role or above" comparisons — not a permission gate.
# Every gate goes through capabilities. This list disappears once nothing
# reads it.
ROLE_HIERARCHY = [
    "viewer",
    "participant",
    "approver",
    "workflow_designer",
    "platform_admin",
]


def get_user_roles(user) -> set:
    """Return the set of role names for a user. Result cached on the user object."""
    if not hasattr(user, "_ff_roles"):
        user._ff_roles = set(
            user.user_roles.select_related("role").values_list("role__name", flat=True)
        )
    return user._ff_roles


def has_role(user, *required_roles: str) -> bool:
    """True if the user holds at least one of the given roles."""
    if not user or not user.is_authenticated:
        return False
    return bool(get_user_roles(user).intersection(required_roles))


def has_min_role(user, minimum: str) -> bool:
    """True if the user holds any role at or above `minimum` in the hierarchy."""
    if not user or not user.is_authenticated:
        return False
    try:
        min_index = ROLE_HIERARCHY.index(minimum)
    except ValueError:
        return False
    roles = get_user_roles(user)
    return any(
        ROLE_HIERARCHY.index(r) >= min_index
        for r in roles
        if r in ROLE_HIERARCHY
    )


def require_role(user, *required_roles: str, action: str = "perform this action") -> None:
    """Raise 403 PermissionDenied if the user holds none of the required roles."""
    if not has_role(user, *required_roles):
        held = ", ".join(sorted(get_user_roles(user))) or "none"
        needed = " or ".join(required_roles)
        raise PermissionDenied(
            f"Role required to {action}: {needed}. Your current roles: {held}."
        )


def require_min_role(user, minimum: str, action: str = "perform this action") -> None:
    """Raise 403 PermissionDenied if user is below `minimum` in the hierarchy."""
    if not has_min_role(user, minimum):
        held = ", ".join(sorted(get_user_roles(user))) or "none"
        raise PermissionDenied(
            f"Minimum role to {action}: {minimum}. Your current roles: {held}."
        )


# ── Capability checks (docs/ROLES.md §2.3) ─────────────────────────────────
#
# Introduced *alongside* the role checks above, which remain authoritative.
# Nothing calls these to gate a request yet: step 2 is about proving the two
# mechanisms agree for every role and capability, so that step 3 can flip
# them without changing who is permitted what. A permissions migration is the
# one place where a silent disagreement is unacceptable, so it gets a shadow
# period rather than a cutover.
#
# Once roles are fully data-driven these replace has_min_role entirely, and
# the ROLE_HIERARCHY list above goes with them.


def capabilities_for(user) -> set:
    """Every capability the user holds, unioned across their roles.

    Cached on the user object for the life of the request, like
    get_user_roles: this is consulted on every permission check, and a
    per-check query would put the database in the hot path of every view.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return set()
    if not hasattr(user, "_ff_capabilities"):
        caps: set = set()
        for role_caps in user.user_roles.select_related("role").values_list(
            "role__capabilities", flat=True
        ):
            caps |= set(role_caps or [])
        user._ff_capabilities = caps
    return user._ff_capabilities


def has_capability(user, capability: str) -> bool:
    """True if the user holds `capability`.

    An unrecognised capability is always False. Failing closed matters: a
    typo at a call site should deny everyone loudly, not grant everyone
    silently.
    """
    from apps.accounts.models import CAPABILITIES

    if capability not in CAPABILITIES:
        return False
    return capability in capabilities_for(user)


def require_capability(user, capability: str, action: str = "perform this action") -> None:
    """Raise 403 unless the user holds `capability`."""
    if not has_capability(user, capability):
        held = ", ".join(sorted(get_user_roles(user))) or "none"
        raise PermissionDenied(
            f"You need the '{capability}' capability to {action}. "
            f"Your current roles: {held}."
        )


# ── DRF Permission classes ─────────────────────────────────────────────────
#
# These now check capabilities rather than positions in ROLE_HIERARCHY. The
# capability chosen for each is the one the guarded endpoints actually need,
# and each is granted to exactly the roles the old hierarchy check admitted —
# so this changes who is permitted nothing. The class names are kept because
# they read well at the call site and appear in a dozen viewsets; what they
# mean underneath is now data.


class IsViewer(BasePermission):
    message = "You do not have permission to view this."

    def has_permission(self, request, view):
        return has_capability(request.user, "workflow.view")


class IsParticipant(BasePermission):
    message = "You do not have permission to create or modify instances."

    def has_permission(self, request, view):
        return has_capability(request.user, "instance.create")


class IsApprover(BasePermission):
    message = "You do not have permission to approve."

    def has_permission(self, request, view):
        return has_capability(request.user, "instance.approve")


class IsWorkflowDesigner(BasePermission):
    message = "You do not have permission to design workflows."

    def has_permission(self, request, view):
        return has_capability(request.user, "workflow.design")


class IsPlatformAdmin(BasePermission):
    message = "You do not have permission to administer the workspace."

    def has_permission(self, request, view):
        return has_capability(request.user, "workspace.manage")


class ReadOnlyOrParticipant(BasePermission):
    """Reads need workflow.view; writes need instance.create."""
    message = "You do not have permission to modify this."

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return has_capability(request.user, "workflow.view")
        return has_capability(request.user, "instance.create")
