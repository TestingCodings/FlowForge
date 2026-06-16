from apps.audit.models import AuditActionType, AuditLog


def write_audit_event(
    workflow_instance,
    action_type,
    actor=None,
    from_state="",
    to_state="",
    payload=None,
    ip_address="",
    user_agent="",
):
    return AuditLog.objects.create(
        workflow_instance=workflow_instance,
        actor=actor,
        action_type=action_type,
        from_state=from_state,
        to_state=to_state,
        payload=payload or {},
        ip_address=ip_address or None,
        user_agent=(user_agent or "")[:255],
    )


def instance_created(workflow_instance, actor=None, payload=None, ip_address="", user_agent=""):
    return write_audit_event(
        workflow_instance=workflow_instance,
        action_type=AuditActionType.INSTANCE_CREATED,
        actor=actor,
        to_state=workflow_instance.current_state.name,
        payload=payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def transition_applied(workflow_instance, actor=None, from_state="", to_state="", payload=None, ip_address="", user_agent=""):
    return write_audit_event(
        workflow_instance=workflow_instance,
        action_type=AuditActionType.TRANSITION,
        actor=actor,
        from_state=from_state,
        to_state=to_state,
        payload=payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def task_assigned(workflow_instance, actor=None, payload=None):
    return write_audit_event(
        workflow_instance=workflow_instance,
        action_type=AuditActionType.TASK_ASSIGNED,
        actor=actor,
        payload=payload,
    )


def task_completed(workflow_instance, actor=None, payload=None):
    return write_audit_event(
        workflow_instance=workflow_instance,
        action_type=AuditActionType.TASK_COMPLETED,
        actor=actor,
        payload=payload,
    )


def form_submitted(workflow_instance, actor=None, payload=None):
    return write_audit_event(
        workflow_instance=workflow_instance,
        action_type=AuditActionType.FORM_SUBMITTED,
        actor=actor,
        payload=payload,
    )


def rule_fired(workflow_instance, actor=None, payload=None):
    return write_audit_event(
        workflow_instance=workflow_instance,
        action_type=AuditActionType.RULE_FIRED,
        actor=actor,
        payload=payload,
    )
