from django.contrib import admin

from .models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "workflow_instance",
        "state",
        "assigned_to_user",
        "assigned_to_role",
        "status",
        "due_at",
    )
    list_filter = ("status", "priority", "assigned_to_role")
    search_fields = ("title", "workflow_instance__reference_number")
