import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.instances.models import WorkflowInstance
from apps.workflows.models import State, Transition


class TaskStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETE = "complete", "Complete"
    OVERDUE = "overdue", "Overdue"


class TaskPriority(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"


class Task(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_instance = models.ForeignKey(
        WorkflowInstance, on_delete=models.CASCADE, related_name="tasks"
    )
    state = models.ForeignKey(State, on_delete=models.PROTECT, related_name="tasks")
    transition = models.ForeignKey(
        Transition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    assigned_to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tasks",
    )
    assigned_to_role = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=TaskStatus.choices, default=TaskStatus.PENDING)
    priority = models.CharField(max_length=10, choices=TaskPriority.choices, default=TaskPriority.MEDIUM)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completed_tasks",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "task"
        ordering = ["status", "due_at", "created_at"]

    def __str__(self):
        return self.title

    @property
    def is_open(self):
        return self.status in {TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.OVERDUE}

    @classmethod
    def build_due_date(cls, hours_from_now=48):
        return timezone.now() + timedelta(hours=hours_from_now)
