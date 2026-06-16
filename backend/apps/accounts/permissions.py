from rest_framework.permissions import BasePermission

from .models import RoleName


class IsPlatformAdmin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.user_roles.filter(role__name=RoleName.PLATFORM_ADMIN).exists()
        )


class IsWorkflowDesigner(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.user_roles.filter(
                role__name__in=[RoleName.PLATFORM_ADMIN, RoleName.WORKFLOW_DESIGNER]
            ).exists()
        )
