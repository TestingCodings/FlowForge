from django.contrib import admin

from .models import Rule, State, Transition, WorkflowDefinition


@admin.register(WorkflowDefinition)
class WorkflowDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "is_active", "created_by", "created_at")
    list_filter = ("is_active", "version")
    search_fields = ("name",)


@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    list_display = ("name", "workflow_definition", "is_initial", "is_terminal", "position_order")
    list_filter = ("is_initial", "is_terminal")
    search_fields = ("name", "workflow_definition__name")


@admin.register(Transition)
class TransitionAdmin(admin.ModelAdmin):
    list_display = ("name", "workflow_definition", "from_state", "to_state", "requires_approval")
    list_filter = ("requires_approval",)
    search_fields = ("name", "workflow_definition__name")


@admin.register(Rule)
class RuleAdmin(admin.ModelAdmin):
    list_display = ("workflow_definition", "transition", "priority")
    list_filter = ("workflow_definition",)
