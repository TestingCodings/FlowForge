import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class WorkflowDefinition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    reference_prefix = models.CharField(max_length=10, default="WFF")
    version = models.PositiveIntegerField(default=1)
    published_at = models.DateTimeField(null=True, blank=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="child_versions",
    )
    is_active = models.BooleanField(default=False)
    # VISION Layer 2: presentation schema, e.g. {"shell": "kanban", "card_fields": [...]}
    ui_schema = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_workflow_definitions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
    display_name = models.CharField(max_length=200, blank=True)
    is_initial = models.BooleanField(default=False)
    is_terminal = models.BooleanField(default=False)
    position_order = models.PositiveIntegerField(default=1)
    # sla_config: {"sla_hours": 48, "sla_business_hours_only": false}
    sla_config = models.JSONField(default=dict, blank=True)
    # task_config: {"requires_task": true, "title_template": "...", "description": "...", "default_role": "handler"}
    task_config = models.JSONField(default=dict, blank=True)
    # Builder canvas coordinates: {"x": 120, "y": 80} — empty until placed in the visual builder
    canvas_position = models.JSONField(default=dict, blank=True)

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

    @property
    def requires_task(self):
        return self.task_config.get("requires_task", True) and not self.is_terminal

    @property
    def task_title(self):
        return self.task_config.get("title_template", "")

    @property
    def task_description(self):
        return self.task_config.get("description", "")

    @property
    def task_assigned_role(self):
        return self.task_config.get("default_role", "")

    @property
    def task_sla_hours(self):
        return self.sla_config.get("sla_hours", 48)


class Transition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_definition = models.ForeignKey(
        WorkflowDefinition, on_delete=models.CASCADE, related_name="transitions"
    )
    from_state = models.ForeignKey(State, on_delete=models.CASCADE, related_name="outgoing_transitions")
    to_state = models.ForeignKey(State, on_delete=models.CASCADE, related_name="incoming_transitions")
    name = models.CharField(max_length=150)
    display_name = models.CharField(max_length=200, blank=True)
    requires_approval = models.BooleanField(default=False)

    class Meta:
        db_table = "workflow_transition"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["from_state", "to_state"],
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


class Rule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_definition = models.ForeignKey(
        WorkflowDefinition,
        on_delete=models.CASCADE,
        related_name="rules",
    )
    transition = models.ForeignKey(
        Transition,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="rules",
    )
    condition = models.JSONField(default=dict)
    action = models.JSONField(default=dict)
    priority = models.PositiveIntegerField(default=100)

    class Meta:
        db_table = "workflow_rule"
        ordering = ["priority", "id"]

    def __str__(self):
        return f"Rule {self.id} ({self.priority})"
