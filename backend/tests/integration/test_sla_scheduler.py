"""Integration tests for SLA scheduler Celery task."""
import pytest
from datetime import timedelta
from django.utils import timezone
from unittest.mock import patch, MagicMock

from django.db import OperationalError

from apps.accounts.models import Role, RoleName, User, UserRole
from apps.audit.models import AuditActionType, AuditLog
from apps.instances.models import WorkflowInstance
from apps.notifications.models import EventTrigger
from apps.notifications.tasks import check_slas_scheduled
from apps.workflows.models import State, WorkflowDefinition, Transition


@pytest.fixture
def setup_context(db):
    """Create test user, workflow, and instance."""
    designer = User.objects.create_user(
        email="designer@example.com",
        password="StrongPass123!",
        first_name="Designer",
        last_name="User",
    )

    role_designer = Role.objects.create(name=RoleName.WORKFLOW_DESIGNER)
    UserRole.objects.create(user=designer, role=role_designer)

    wf = WorkflowDefinition.objects.create(
        name="Test WF",
        created_by=designer,
    )

    # Create Draft state with no SLA
    draft_state = State.objects.create(
        workflow_definition=wf,
        name="Draft",
        is_initial=True,
        is_terminal=False,
        position_order=1,
        sla_config={},
    )

    # Create InProgress state with 1-hour SLA
    in_progress_state = State.objects.create(
        workflow_definition=wf,
        name="In Progress",
        is_initial=False,
        is_terminal=False,
        position_order=2,
        sla_config={"sla_hours": 1},
    )

    # Create Done state (terminal, no SLA)
    done_state = State.objects.create(
        workflow_definition=wf,
        name="Done",
        is_initial=False,
        is_terminal=True,
        position_order=3,
        sla_config={},
    )

    return designer, wf, draft_state, in_progress_state, done_state


@pytest.mark.django_db
def test_sla_scheduler_notifies_breached_instance(setup_context):
    """SLA scheduler should detect and notify on SLA breach."""
    designer, wf, draft_state, in_progress_state, done_state = setup_context

    # Create instance starting in Draft
    instance = WorkflowInstance.objects.create(
        workflow_definition=wf,
        current_state=draft_state,
        created_by=designer,
    )

    # Simulate transition to In Progress 2 hours ago (breaching the 1-hour SLA)
    instance.current_state = in_progress_state
    instance.save()

    transition_log = AuditLog.objects.create(
        workflow_instance=instance,
        actor=designer,
        action_type=AuditActionType.TRANSITION,
        from_state=draft_state.name,
        to_state=in_progress_state.name,
    )

    # Manually update created_at to 2 hours ago (bypass auto_now_add)
    transition_time = timezone.now() - timedelta(hours=2)
    AuditLog.objects.filter(id=transition_log.id).update(created_at=transition_time)

    # Run scheduler
    check_slas_scheduled()

    # Should have created SLA_BREACHED audit log
    breached_logs = AuditLog.objects.filter(
        workflow_instance=instance,
        action_type=AuditActionType.SLA_BREACHED,
    )
    assert breached_logs.exists()
    assert breached_logs.first().payload["sla_hours"] == 1


@pytest.mark.django_db
def test_sla_scheduler_idempotent(setup_context):
    """SLA scheduler should only notify once per state entry."""
    designer, wf, draft_state, in_progress_state, done_state = setup_context

    instance = WorkflowInstance.objects.create(
        workflow_definition=wf,
        current_state=draft_state,
        created_by=designer,
    )

    # Transition to In Progress 2 hours ago
    instance.current_state = in_progress_state
    instance.save()

    transition_log = AuditLog.objects.create(
        workflow_instance=instance,
        actor=designer,
        action_type=AuditActionType.TRANSITION,
        from_state=draft_state.name,
        to_state=in_progress_state.name,
    )

    # Manually update created_at to 2 hours ago (bypass auto_now_add)
    transition_time = timezone.now() - timedelta(hours=2)
    AuditLog.objects.filter(id=transition_log.id).update(created_at=transition_time)

    # Run scheduler first time
    check_slas_scheduled()
    first_breach_count = AuditLog.objects.filter(
        workflow_instance=instance,
        action_type=AuditActionType.SLA_BREACHED,
    ).count()
    assert first_breach_count == 1

    # Run scheduler again (should not create new audit log)
    check_slas_scheduled()
    second_breach_count = AuditLog.objects.filter(
        workflow_instance=instance,
        action_type=AuditActionType.SLA_BREACHED,
    ).count()
    assert second_breach_count == 1


@pytest.mark.django_db
def test_sla_scheduler_ignores_no_sla_states(setup_context):
    """SLA scheduler should not notify for states without SLA."""
    designer, wf, draft_state, in_progress_state, done_state = setup_context

    instance = WorkflowInstance.objects.create(
        workflow_definition=wf,
        current_state=draft_state,  # Draft has no SLA
        created_by=designer,
    )

    # Create a very old audit log so instance appears old, but state has no SLA
    old_time = timezone.now() - timedelta(hours=2)
    AuditLog.objects.filter(
        workflow_instance=instance
    ).update(created_at=old_time)

    # Run scheduler
    check_slas_scheduled()

    # Should NOT create SLA_BREACHED log (Draft state has no SLA)
    breached_logs = AuditLog.objects.filter(
        workflow_instance=instance,
        action_type=AuditActionType.SLA_BREACHED,
    )
    assert not breached_logs.exists()


@pytest.mark.django_db
def test_sla_scheduler_ignores_completed_instances(setup_context):
    """SLA scheduler should not notify for completed instances."""
    designer, wf, draft_state, in_progress_state, done_state = setup_context

    instance = WorkflowInstance.objects.create(
        workflow_definition=wf,
        current_state=in_progress_state,
        created_by=designer,
        completed_at=timezone.now(),  # Mark as completed
    )

    # Transition to In Progress 2 hours ago
    transition_log = AuditLog.objects.create(
        workflow_instance=instance,
        actor=designer,
        action_type=AuditActionType.TRANSITION,
        from_state=draft_state.name,
        to_state=in_progress_state.name,
    )

    # Manually update created_at to 2 hours ago (bypass auto_now_add)
    transition_time = timezone.now() - timedelta(hours=2)
    AuditLog.objects.filter(id=transition_log.id).update(created_at=transition_time)

    # Run scheduler
    check_slas_scheduled()

    # Should NOT create SLA_BREACHED log (instance is completed)
    breached_logs = AuditLog.objects.filter(
        workflow_instance=instance,
        action_type=AuditActionType.SLA_BREACHED,
    )
    assert not breached_logs.exists()


@pytest.mark.django_db
def test_sla_scheduler_ignores_within_sla(setup_context):
    """SLA scheduler should not notify if still within SLA."""
    designer, wf, draft_state, in_progress_state, done_state = setup_context

    instance = WorkflowInstance.objects.create(
        workflow_definition=wf,
        current_state=in_progress_state,  # 1-hour SLA
        created_by=designer,
    )

    # Transition to In Progress 30 minutes ago (within 1-hour SLA)
    transition_log = AuditLog.objects.create(
        workflow_instance=instance,
        actor=designer,
        action_type=AuditActionType.TRANSITION,
        from_state=draft_state.name,
        to_state=in_progress_state.name,
    )

    # Manually update created_at to 30 minutes ago (bypass auto_now_add)
    transition_time = timezone.now() - timedelta(minutes=30)
    AuditLog.objects.filter(id=transition_log.id).update(created_at=transition_time)

    # Run scheduler
    check_slas_scheduled()

    # Should NOT create SLA_BREACHED log (still within SLA)
    breached_logs = AuditLog.objects.filter(
        workflow_instance=instance,
        action_type=AuditActionType.SLA_BREACHED,
    )
    assert not breached_logs.exists()


@pytest.mark.django_db
def test_sla_scheduler_retries_on_db_lock(setup_context):
    """SLA scheduler should retry on transient DB lock errors."""
    designer, wf, draft_state, in_progress_state, done_state = setup_context

    instance = WorkflowInstance.objects.create(
        workflow_definition=wf,
        current_state=in_progress_state,
        created_by=designer,
    )

    # Transition to In Progress 2 hours ago
    transition_log = AuditLog.objects.create(
        workflow_instance=instance,
        actor=designer,
        action_type=AuditActionType.TRANSITION,
        from_state=draft_state.name,
        to_state=in_progress_state.name,
    )

    # Manually update created_at to 2 hours ago (bypass auto_now_add)
    transition_time = timezone.now() - timedelta(hours=2)
    AuditLog.objects.filter(id=transition_log.id).update(created_at=transition_time)

    # Mock queue_event_notifications to raise OperationalError (simulating DB lock)
    with patch("apps.notifications.tasks.queue_event_notifications") as mock_queue:
        mock_queue.side_effect = OperationalError("database is locked")

        # Should still process despite individual errors
        check_slas_scheduled()

        # The instance was processed (we got past the error in the loop)
        breached_logs = AuditLog.objects.filter(
            workflow_instance=instance,
            action_type=AuditActionType.SLA_BREACHED,
        )
        # Audit log should still be created, only queue notification failed
        assert breached_logs.exists()
