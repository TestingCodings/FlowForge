import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.workflows.models import State, WorkflowDefinition


class InstanceRelationship(models.Model):
    """Directional link between two workflow instances (e.g. Bug 'reported_in' Test Run)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_instance = models.ForeignKey(
        "WorkflowInstance", on_delete=models.CASCADE, related_name="outgoing_relationships"
    )
    to_instance = models.ForeignKey(
        "WorkflowInstance", on_delete=models.CASCADE, related_name="incoming_relationships"
    )
    rel_type = models.CharField(max_length=100)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_relationships",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "instance_relationship"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["from_instance", "to_instance", "rel_type"],
                name="unique_relationship",
            )
        ]

    def __str__(self):
        return (
            f"{self.from_instance.reference_number}"
            f" –[{self.rel_type}]→ "
            f"{self.to_instance.reference_number}"
        )


def generate_reference_number(workflow_definition):
    """
    Thread-safe reference number generator using select_for_update().
    Format: {PREFIX}-{YEAR}-{SEQUENCE:05d}  e.g. CLM-2026-00042
    """
    from django.utils import timezone

    year = timezone.now().year
    prefix = (workflow_definition.reference_prefix or "WFF").upper()[:10]

    with transaction.atomic():
        # Sequence per prefix (not per definition): only the prefix appears in
        # the reference string, so definitions sharing a prefix must share the
        # sequence or they collide on the unique constraint.
        count = (
            WorkflowInstance.objects.select_for_update()
            .filter(workflow_definition__reference_prefix=prefix, created_at__year=year)
            .count()
        )
        return f"{prefix}-{year}-{count + 1:05d}"


class WorkflowInstance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_definition = models.ForeignKey(
        WorkflowDefinition, on_delete=models.PROTECT, related_name="instances"
    )
    current_state = models.ForeignKey(State, on_delete=models.PROTECT, related_name="instances")
    # Containment (docs/UX.md section 3): first-class hierarchy with invariants
    # typed relationships can't provide (single parent, no cycles, PROTECT).
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    child_order = models.PositiveIntegerField(default=0)
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
    completed_at = models.DateTimeField(null=True, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "workflow_instance"
        ordering = ["-created_at"]

    def __str__(self):
        return self.reference_number

    def clean(self):
        if self.current_state_id and self.current_state.workflow_definition_id != self.workflow_definition_id:
            raise ValidationError("current_state must belong to workflow_definition")
        if self.parent_id:
            if self.parent_id == self.id:
                raise ValidationError("An instance cannot be its own parent")
            # Walk up to reject cycles (trees are shallow; bounded walk)
            seen = {self.id}
            ancestor = self.parent
            while ancestor is not None:
                if ancestor.id in seen:
                    raise ValidationError("Moving this instance would create a cycle")
                seen.add(ancestor.id)
                ancestor = ancestor.parent

    def save(self, *args, **kwargs):
        if not self.current_state_id and self.workflow_definition_id:
            initial_state = self.workflow_definition.states.filter(is_initial=True).first()
            if not initial_state:
                raise ValidationError("WorkflowDefinition has no initial state")
            self.current_state = initial_state

        if not self.reference_number and self.workflow_definition_id:
            self.reference_number = generate_reference_number(self.workflow_definition)

        self.full_clean()
        super().save(*args, **kwargs)
