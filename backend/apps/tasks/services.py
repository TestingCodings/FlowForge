from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import task_assigned, task_completed
from apps.workflows.engine import perform_transition
from apps.workflows.models import Transition

from .models import Task, TaskPriority, TaskStatus


def create_tasks_for_state(instance, actions=None):
    state = instance.current_state
    if not state.requires_task or state.is_terminal:
        return []

    if instance.tasks.filter(state=state, status__in=[TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.OVERDUE]).exists():
        return []

    transition = (
        Transition.objects.filter(
            workflow_definition=instance.workflow_definition,
            from_state=state,
        )
        .order_by("name")
        .first()
    )

    title = state.task_title or f"{instance.workflow_definition.name} - {state.name}"

    role_override = ""
    for action in actions or []:
        if action.get("type") == "assign_role" and action.get("role"):
            role_override = action["role"]
            break

    task = Task.objects.create(
        workflow_instance=instance,
        state=state,
        transition=transition,
        title=title,
        description=state.task_description,
        assigned_to_role=role_override or state.task_assigned_role,
        status=TaskStatus.PENDING,
        priority=TaskPriority.MEDIUM,
        due_at=Task.build_due_date(state.task_sla_hours),
    )
    task_assigned(
        workflow_instance=instance,
        actor=None,
        payload={"task_id": str(task.id), "title": task.title, "state": state.name},
    )
    return [task]


def _can_complete_task(task, user):
    if task.assigned_to_user_id and task.assigned_to_user_id == user.id:
        return True
    if task.assigned_to_role:
        user_roles = set(user.user_roles.values_list("role__name", flat=True))
        return task.assigned_to_role in user_roles
    return True


@transaction.atomic
def complete_task(task, user):
    if not _can_complete_task(task, user):
        raise PermissionError("You are not allowed to complete this task")

    if task.status == TaskStatus.COMPLETE:
        return task

    task.status = TaskStatus.COMPLETE
    task.completed_at = timezone.now()
    task.completed_by = user
    task.save(update_fields=["status", "completed_at", "completed_by"])
    task_completed(
        workflow_instance=task.workflow_instance,
        actor=user,
        payload={"task_id": str(task.id), "title": task.title},
    )

    remaining = task.workflow_instance.tasks.filter(
        state=task.state,
    ).exclude(status=TaskStatus.COMPLETE)

    if not remaining.exists() and task.transition_id:
        result = perform_transition(task.workflow_instance, task.transition_id)
        create_tasks_for_state(task.workflow_instance, actions=result.actions)

    return task


def mark_overdue_tasks():
    updated_count = Task.objects.filter(
        Q(status=TaskStatus.PENDING) | Q(status=TaskStatus.IN_PROGRESS),
        due_at__lt=timezone.now(),
    ).update(status=TaskStatus.OVERDUE)
    return updated_count
