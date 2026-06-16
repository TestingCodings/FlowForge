import uuid

from django.db import models

from apps.instances.models import WorkflowInstance
from apps.workflows.models import WorkflowDefinition


class NotificationChannel(models.TextChoices):
    EMAIL = "email", "Email"
    SLACK = "slack", "Slack"
    WEBHOOK = "webhook", "Webhook"


class NotificationStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"


class NotificationTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_definition = models.ForeignKey(
        WorkflowDefinition,
        on_delete=models.CASCADE,
        related_name="notification_templates",
        null=True,
        blank=True,
    )
    channel = models.CharField(max_length=20, choices=NotificationChannel.choices)
    event_trigger = models.CharField(max_length=50)
    subject_template = models.CharField(max_length=255, blank=True)
    body_template = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notification_template"
        ordering = ["event_trigger", "channel"]

    def __str__(self):
        return f"{self.event_trigger} ({self.channel})"


class NotificationLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_instance = models.ForeignKey(
        WorkflowInstance,
        on_delete=models.CASCADE,
        related_name="notification_logs",
    )
    channel = models.CharField(max_length=20, choices=NotificationChannel.choices)
    recipient = models.CharField(max_length=255, blank=True)
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=NotificationStatus.choices, default=NotificationStatus.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notification_log"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.channel} {self.status}"
