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


class WebhookDeliveryStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    DELIVERED = "delivered", "Delivered"
    FAILED = "failed", "Failed (Retrying)"
    DEAD_LETTER = "dead_letter", "Dead Letter (Max Retries Exceeded)"


class WebhookDeliveryLog(models.Model):
    """Track webhook delivery attempts with exponential backoff retry logic."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    webhook_subscription = models.ForeignKey(
        WebhookSubscription,
        on_delete=models.CASCADE,
        related_name="delivery_logs",
    )
    workflow_instance = models.ForeignKey(
        WorkflowInstance,
        on_delete=models.CASCADE,
        related_name="webhook_delivery_logs",
    )
    event_trigger = models.CharField(max_length=50)
    payload = models.JSONField()  # Full JSON body being sent
    status = models.CharField(
        max_length=20,
        choices=WebhookDeliveryStatus.choices,
        default=WebhookDeliveryStatus.QUEUED,
    )
    attempt = models.PositiveSmallIntegerField(default=0)  # Current attempt (0-indexed)
    http_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "webhook_delivery_log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "next_retry_at"]),
            models.Index(fields=["webhook_subscription", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.webhook_subscription.url} {self.event_trigger} ({self.status})"


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


class TransitionHook(models.Model):
    """
    An action hook on a transition (docs/HOOKS.md Part 2).

    `after` hooks fire once a transition has committed — they call an external
    system asynchronously (reusing the webhook delivery machinery) and can
    write the response back into instance metadata via `output_to`. `before`
    hooks (gating, synchronous) are a later step; the field is here so the
    model is stable.
    """

    class Trigger(models.TextChoices):
        BEFORE = "before", "Before (gates the transition)"
        AFTER = "after", "After (fires once committed)"

    class Action(models.TextChoices):
        HTTP_REQUEST = "http_request", "HTTP request"
        PROBE = "probe", "Probe (GET, assert reachable)"

    class OnFailure(models.TextChoices):
        BLOCK = "block", "Block the transition"
        WARN = "warn", "Warn but proceed"
        IGNORE = "ignore", "Ignore"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transition = models.ForeignKey(
        "workflows.Transition", on_delete=models.CASCADE, related_name="hooks"
    )
    trigger = models.CharField(max_length=10, choices=Trigger.choices, default=Trigger.AFTER)
    action = models.CharField(max_length=20, choices=Action.choices, default=Action.HTTP_REQUEST)
    # {url, method, headers: {k:v}, body_template: str, timeout: int, expect_status: int}
    config = models.JSONField(default=dict)
    on_failure = models.CharField(max_length=10, choices=OnFailure.choices, default=OnFailure.WARN)
    # "metadata.<key>" — where the response (or a json path of it) is written.
    output_to = models.CharField(max_length=100, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_hooks",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "transition_hook"
        ordering = ["transition_id", "order", "created_at"]

    def __str__(self):
        return f"{self.trigger} {self.action} on {self.transition_id}"


class HookExecutionLog(models.Model):
    """One execution of a TransitionHook — observability + replay (mirrors WebhookDeliveryLog)."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed (Retrying)"
        DEAD_LETTER = "dead_letter", "Dead Letter"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hook = models.ForeignKey(TransitionHook, on_delete=models.CASCADE, related_name="executions")
    workflow_instance = models.ForeignKey(
        WorkflowInstance, on_delete=models.CASCADE, related_name="hook_executions"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    attempt = models.PositiveSmallIntegerField(default=0)
    http_status_code = models.PositiveIntegerField(null=True, blank=True)
    # Request/response are redacted of any secret values before saving.
    request_summary = models.TextField(blank=True)
    response_summary = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "hook_execution_log"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.hook_id} {self.status}"
