"""Shared pytest configuration for backend tests."""

from apps.accounts.models import Role, RoleName, UserRole


def give_role(user, role_name: str):
    """Assign a role to a user, creating the Role row if needed."""
    role, _ = Role.objects.get_or_create(name=role_name)
    UserRole.objects.get_or_create(user=user, role=role)
    # Bust the per-request cache used by the permission layer
    if hasattr(user, "_ff_roles"):
        del user._ff_roles
    return user
