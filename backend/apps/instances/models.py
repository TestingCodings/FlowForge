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


def generate_trigger_token():
    """A long, URL-safe secret; the token in the trigger URL is its credential."""
    import secrets

    return secrets.token_urlsafe(32)


class Trigger(models.Model):
    """
    An inbound integration point (VISION meta-model: the world → FlowForge).

    Addressed by a secret token in its own URL. Firing it either creates an
    instance of the bound workflow or fires a transition on an existing one,
    always through the engine so rules/approvals/forms still apply.
    """

    class Action(models.TextChoices):
        CREATE_INSTANCE = "create_instance", "Create instance"
        FIRE_TRANSITION = "fire_transition", "Fire transition"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    workflow_definition = models.ForeignKey(
        WorkflowDefinition, on_delete=models.CASCADE, related_name="triggers"
    )
    token = models.CharField(max_length=64, unique=True, default=generate_trigger_token, editable=False)
    action = models.CharField(max_length=20, choices=Action.choices)
    # Required when action=fire_transition: the transition to fire.
    transition = models.ForeignKey(
        "workflows.Transition", on_delete=models.CASCADE, null=True, blank=True, related_name="triggers"
    )
    # How to find the target instance for fire_transition:
    # "reference_number" or "metadata.<key>". The payload must carry the value.
    lookup_field = models.CharField(max_length=100, blank=True, default="reference_number")
    # Maps incoming payload keys → metadata keys, e.g. {"build": "build_number"}.
    # Empty = copy the whole payload into metadata verbatim.
    metadata_mapping = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_triggers",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_triggered_at = models.DateTimeField(null=True, blank=True)
    trigger_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "trigger"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.action})"

    def clean(self):
        if self.action == self.Action.FIRE_TRANSITION and not self.transition_id:
            raise ValidationError("fire_transition triggers require a transition.")
        if self.transition_id and self.transition.workflow_definition_id != self.workflow_definition_id:
            raise ValidationError("transition must belong to the trigger's workflow.")

    def apply_mapping(self, payload: dict) -> dict:
        """Resolve the payload into a metadata dict per metadata_mapping."""
        if not isinstance(payload, dict):
            return {}
        if not self.metadata_mapping:
            return dict(payload)
        out = {}
        for meta_key, payload_key in self.metadata_mapping.items():
            if payload_key in payload:
                out[meta_key] = payload[payload_key]
        return out
