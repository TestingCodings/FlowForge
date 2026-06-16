from django.contrib import admin

from .models import WorkflowInstance


@admin.register(WorkflowInstance)
class WorkflowInstanceAdmin(admin.ModelAdmin):
    list_display = ("reference_number", "workflow_definition", "current_state", "created_by", "created_at")
    list_filter = ("workflow_definition",)
    search_fields = ("reference_number",)
