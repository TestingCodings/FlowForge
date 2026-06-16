import re
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.workflows.models import State, WorkflowDefinition


def _workflow_prefix(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", name or "")
    prefix = (cleaned[:3] or "WFF").upper()
    return prefix.ljust(3, "X")


class WorkflowInstance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_definition = models.ForeignKey(
        WorkflowDefinition, on_delete=models.PROTECT, related_name="instances"
    )
    current_state = models.ForeignKey(State, on_delete=models.PROTECT, related_name="instances")
    reference_number = models.CharField(max_length=30, unique=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_workflow_instances",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "workflow_instance"
        ordering = ["-created_at"]

    def __str__(self):
        return self.reference_number

    def clean(self):
        if self.current_state_id and self.current_state.workflow_definition_id != self.workflow_definition_id:
            raise ValidationError("current_state must belong to workflow_definition")

    def save(self, *args, **kwargs):
        if not self.current_state_id and self.workflow_definition_id:
            initial_state = self.workflow_definition.states.filter(is_initial=True).first()
            if not initial_state:
                raise ValidationError("WorkflowDefinition has no initial state")
            self.current_state = initial_state

        if not self.reference_number and self.workflow_definition_id:
            from django.utils import timezone

            year = timezone.now().year
            sequence = (
                WorkflowInstance.objects.filter(
                    workflow_definition=self.workflow_definition,
                    created_at__year=year,
                ).count()
                + 1
            )
            self.reference_number = f"{_workflow_prefix(self.workflow_definition.name)}-{year}-{sequence:05d}"

        self.full_clean()
        super().save(*args, **kwargs)
