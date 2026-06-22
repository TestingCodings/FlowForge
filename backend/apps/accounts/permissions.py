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


# ── DRF Permission classes ─────────────────────────────────────────────────

class IsViewer(BasePermission):
    message = "At least viewer role required."

    def has_permission(self, request, view):
        return has_min_role(request.user, "viewer")


class IsParticipant(BasePermission):
    message = "At least participant role required."

    def has_permission(self, request, view):
        return has_min_role(request.user, "participant")


class IsApprover(BasePermission):
    message = "At least approver role required."

    def has_permission(self, request, view):
        return has_min_role(request.user, "approver")


class IsWorkflowDesigner(BasePermission):
    message = "At least workflow_designer role required."

    def has_permission(self, request, view):
        return has_min_role(request.user, "workflow_designer")


class IsPlatformAdmin(BasePermission):
    message = "Platform admin role required."

    def has_permission(self, request, view):
        return has_role(request.user, "platform_admin")


class ReadOnlyOrParticipant(BasePermission):
    """GET/HEAD/OPTIONS: viewer+. Writes: participant+."""
    message = "Participant role required to modify resources."

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return has_min_role(request.user, "viewer")
        return has_min_role(request.user, "participant")
