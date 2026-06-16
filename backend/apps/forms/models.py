import uuid

from django.conf import settings
from django.db import models

from apps.instances.models import WorkflowInstance
from apps.workflows.models import State, WorkflowDefinition


class FormDefinition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_definition = models.ForeignKey(
        WorkflowDefinition, on_delete=models.CASCADE, related_name="forms"
    )
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name="forms")
    name = models.CharField(max_length=200)
    schema = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_form_definitions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "form_definition"
        constraints = [
            models.UniqueConstraint(
                fields=["workflow_definition", "state", "version"],
                name="unique_form_version_per_state",
            )
        ]

    def __str__(self):
        return f"{self.name} v{self.version}"


class FormSubmission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_instance = models.ForeignKey(
        WorkflowInstance, on_delete=models.CASCADE, related_name="form_submissions"
    )
    form_definition = models.ForeignKey(
        FormDefinition, on_delete=models.PROTECT, related_name="submissions"
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_forms",
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    data = models.JSONField(default=dict)

    class Meta:
        db_table = "form_submission"
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.form_definition.name} for {self.workflow_instance.reference_number}"
