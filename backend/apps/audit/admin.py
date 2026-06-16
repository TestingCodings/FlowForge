from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "action_type",
        "workflow_instance",
        "actor",
        "from_state",
        "to_state",
        "created_at",
    )
    list_filter = ("action_type", "created_at")
    search_fields = ("workflow_instance__reference_number", "actor__email")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
