import uuid

from django.conf import settings
from django.db import models

from apps.instances.models import WorkflowInstance
from apps.workflows.models import WorkflowDefinition


class EventTrigger(models.TextChoices):
    INSTANCE_CREATED = "instance_created", "Instance Created"
    STATE_TRANSITION = "state_transition", "State Transition"
    COMMENT_ADDED = "comment_added", "Comment Added"
    RULE_BLOCKED = "rule_blocked", "Rule Blocked Transition"
    FORM_SUBMITTED = "form_submitted", "Form Submitted"
    SLA_BREACHED = "sla_breached", "SLA Breached"
    TASK_CREATED = "task_created", "Task Created"
    TASK_COMPLETED = "task_completed", "Task Completed"


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


class WebhookSubscription(models.Model):
    """An HTTP endpoint that receives signed JSON payloads for workflow events."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_definition = models.ForeignKey(
        WorkflowDefinition,
        on_delete=models.CASCADE,
        related_name="webhook_subscriptions",
        null=True,
        blank=True,
        help_text="Blank = fires for every workflow",
    )
    url = models.URLField(max_length=500)
    # Empty list = subscribe to all events
    events = models.JSONField(default=list, blank=True)
    secret = models.CharField(
        max_length=64,
        blank=True,
        help_text="Used to HMAC-SHA256 sign payloads (X-FlowForge-Signature)",
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="webhook_subscriptions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "webhook_subscription"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.url} ({'all' if not self.events else ','.join(self.events)})"


class NotificationLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_instance = models.ForeignKey(
        WorkflowInstance,
        on_delete=models.CASCADE,
        related_name="notification_logs",
    )
    event_trigger = models.CharField(max_length=50, blank=True)
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
