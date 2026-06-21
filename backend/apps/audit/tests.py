import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleName, User, UserRole
from apps.audit.models import AuditActionType, AuditLog
from apps.forms.models import FormDefinition
from apps.instances.models import WorkflowInstance
from apps.workflows.models import Rule, State, Transition, WorkflowDefinition


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user_and_client(api_client):
    user = User.objects.create_user(
        email="audit@example.com",
        password="StrongPass123!",
        first_name="Audit",
        last_name="User",
    )
    login = api_client.post(
        reverse("auth-login"),
        {"email": user.email, "password": "StrongPass123!"},
        format="json",
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return user, api_client


@pytest.mark.django_db
def test_transition_blocked_by_rule_and_audit_logged(user_and_client):
    user, client = user_and_client

    wf = WorkflowDefinition.objects.create(
        name="Rule Audit WF",
        description="",
        version=1,
        is_active=True,
        created_by=user,
    )
    s1 = State.objects.create(
        workflow_definition=wf,
        name="Draft",
        is_initial=True,
        is_terminal=False,
        position_order=1,
    )
    s2 = State.objects.create(
        workflow_definition=wf,
        name="Approved",
        is_initial=False,
        is_terminal=True,
        position_order=2,
    )
    transition = Transition.objects.create(
        workflow_definition=wf,
        from_state=s1,
        to_state=s2,
        name="Approve",
    )
    Rule.objects.create(
        workflow_definition=wf,
        transition=transition,
        condition={"field": "claim_value", "operator": "gt", "value": 5000},
        action={"type": "block_transition", "reason": "Requires director sign-off"},
        priority=1,
    )

    instance = WorkflowInstance.objects.create(
        workflow_definition=wf,
        created_by=user,
        metadata_json={"claim_value": 7000},
    )

    response = client.post(
        f"/api/instances/{instance.id}/transition/",
        {"transition_id": str(transition.id)},
        format="json",
    )
    assert response.status_code == 400
    assert "Requires director sign-off" in str(response.data)

    # No state change since rule blocked transition.
    instance.refresh_from_db()
    assert instance.current_state_id == s1.id


@pytest.mark.django_db
def test_audit_trail_endpoint_and_immutability(user_and_client):
    user, client = user_and_client
    wf = WorkflowDefinition.objects.create(
        name="Audit Trail WF",
        description="",
        version=1,
        is_active=True,
        created_by=user,
    )
    s1 = State.objects.create(
        workflow_definition=wf,
        name="Draft",
        is_initial=True,
        is_terminal=False,
        position_order=1,
    )

    instance = WorkflowInstance.objects.create(workflow_definition=wf, created_by=user)
    AuditLog.objects.create(
        workflow_instance=instance,
        actor=user,
        action_type=AuditActionType.INSTANCE_CREATED,
        to_state=s1.name,
        payload={"seed": True},
    )

    trail = client.get(f"/api/audit/{instance.id}/")
    assert trail.status_code == 200
    assert len(trail.data["results"]) >= 1

    audit_entry = AuditLog.objects.filter(workflow_instance=instance).first()
    audit_entry.payload = {"changed": True}
    with pytest.raises(Exception):
        audit_entry.save()


@pytest.mark.django_db
def test_admin_audit_endpoint_requires_platform_admin(api_client):
    user = User.objects.create_user(
        email="nonadmin@example.com",
        password="StrongPass123!",
        first_name="Non",
        last_name="Admin",
    )
    login = api_client.post(
        reverse("auth-login"),
        {"email": user.email, "password": "StrongPass123!"},
        format="json",
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    denied = api_client.get("/api/audit/")
    assert denied.status_code == 403

    role = Role.objects.create(name=RoleName.PLATFORM_ADMIN)
    UserRole.objects.create(user=user, role=role)
    allowed = api_client.get("/api/audit/")
    assert allowed.status_code == 200


@pytest.mark.django_db
def test_rule_assign_role_applies_to_created_task(user_and_client):
    user, client = user_and_client
    wf = WorkflowDefinition.objects.create(
        name="Assign Role WF",
        description="",
        version=1,
        is_active=True,
        created_by=user,
    )
    s1 = State.objects.create(
        workflow_definition=wf,
        name="Draft",
        is_initial=True,
        is_terminal=False,
        position_order=1,
        task_config={"requires_task": False},
    )
    s2 = State.objects.create(
        workflow_definition=wf,
        name="Review",
        is_initial=False,
        is_terminal=False,
        position_order=2,
        task_config={"requires_task": True},
    )
    transition = Transition.objects.create(
        workflow_definition=wf,
        from_state=s1,
        to_state=s2,
        name="Move",
    )
    Rule.objects.create(
        workflow_definition=wf,
        transition=transition,
        condition={"field": "claim_value", "operator": "gt", "value": 5000},
        action={"type": "assign_role", "role": "director"},
        priority=1,
    )

    instance = WorkflowInstance.objects.create(
        workflow_definition=wf,
        created_by=user,
        metadata_json={"claim_value": 7000},
    )

    response = client.post(
        f"/api/instances/{instance.id}/transition/",
        {"transition_id": str(transition.id)},
        format="json",
    )
    assert response.status_code == 200

    tasks = client.get("/api/tasks/")
    assert tasks.status_code == 200
    assert tasks.data["count"] == 0

    from apps.tasks.models import Task

    review_task = Task.objects.get(workflow_instance=instance, state=s2)
    assert review_task.assigned_to_role == "director"
