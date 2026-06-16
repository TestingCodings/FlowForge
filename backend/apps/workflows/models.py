import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class WorkflowDefinition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_workflow_definitions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "workflow_definition"
        ordering = ["name"]

    def __str__(self):
        return self.name


class State(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_definition = models.ForeignKey(
        WorkflowDefinition, on_delete=models.CASCADE, related_name="states"
    )
    name = models.CharField(max_length=100)
    display_name = models.CharField(max_length=150, blank=True)
    is_initial = models.BooleanField(default=False)
    is_terminal = models.BooleanField(default=False)
    position_order = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "workflow_state"
        ordering = ["position_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["workflow_definition", "name"],
                name="unique_state_name_per_workflow",
            ),
            models.UniqueConstraint(
                fields=["workflow_definition", "position_order"],
                name="unique_state_order_per_workflow",
            ),
        ]

    def __str__(self):
        return f"{self.workflow_definition.name}: {self.name}"


class Transition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_definition = models.ForeignKey(
        WorkflowDefinition, on_delete=models.CASCADE, related_name="transitions"
    )
    from_state = models.ForeignKey(State, on_delete=models.CASCADE, related_name="outgoing_transitions")
    to_state = models.ForeignKey(State, on_delete=models.CASCADE, related_name="incoming_transitions")
    name = models.CharField(max_length=150)
    requires_approval = models.BooleanField(default=False)

    class Meta:
        db_table = "workflow_transition"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["workflow_definition", "from_state", "to_state", "name"],
                name="unique_transition_per_path",
            )
        ]

    def clean(self):
        if self.from_state_id and self.from_state.workflow_definition_id != self.workflow_definition_id:
            raise ValidationError("from_state must belong to workflow_definition")
        if self.to_state_id and self.to_state.workflow_definition_id != self.workflow_definition_id:
            raise ValidationError("to_state must belong to workflow_definition")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name}: {self.from_state.name} -> {self.to_state.name}"
