import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.instances.models import WorkflowInstance


class AuditActionType(models.TextChoices):
    INSTANCE_CREATED = "instance_created", "Instance Created"
    TRANSITION = "transition", "Transition"
    TASK_ASSIGNED = "task_assigned", "Task Assigned"
    TASK_COMPLETED = "task_completed", "Task Completed"
    FORM_SUBMITTED = "form_submitted", "Form Submitted"
    RULE_FIRED = "rule_fired", "Rule Fired"
    COMMENT = "comment", "Comment"
    METADATA_UPDATED = "metadata_updated", "Metadata Updated"
    RELATIONSHIP_ADDED = "relationship_added", "Relationship Added"
    RELATIONSHIP_REMOVED = "relationship_removed", "Relationship Removed"
    SLA_BREACHED = "sla_breached", "SLA Breached"


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_instance = models.ForeignKey(
        WorkflowInstance,
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    action_type = models.CharField(max_length=40, choices=AuditActionType.choices)
    from_state = models.CharField(max_length=100, blank=True)
    to_state = models.CharField(max_length=100, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_log"
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
            raise ValidationError("AuditLog records are immutable and cannot be updated")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("AuditLog records are immutable and cannot be deleted")

    def __str__(self):
        return f"{self.action_type} @ {self.created_at}"
