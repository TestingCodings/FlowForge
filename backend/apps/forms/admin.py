from django.contrib import admin

from .models import FormDefinition, FormSubmission


@admin.register(FormDefinition)
class FormDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "workflow_definition", "state", "version", "created_by", "created_at")
    list_filter = ("workflow_definition", "state")
    search_fields = ("name",)


@admin.register(FormSubmission)
class FormSubmissionAdmin(admin.ModelAdmin):
    list_display = ("form_definition", "workflow_instance", "submitted_by", "submitted_at")
    list_filter = ("form_definition",)
    search_fields = ("workflow_instance__reference_number",)
