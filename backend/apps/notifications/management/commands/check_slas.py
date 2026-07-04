"""
Scan open instances for SLA breaches and fire sla_breached notifications.

Run periodically (cron / Celery beat / Task Scheduler):
    python manage.py check_slas --settings=config.settings.local_sqlite

Idempotent: an instance is notified at most once per state entry.
"""

from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime

from apps.audit.models import AuditActionType, AuditLog
from apps.instances.models import WorkflowInstance
from apps.instances.serializers import _sla_status
from apps.notifications.models import EventTrigger
from apps.notifications.services import queue_event_notifications


class Command(BaseCommand):
    help = "Flag SLA-breached instances and dispatch sla_breached notifications"

    def handle(self, *args, **options):
        open_instances = WorkflowInstance.objects.filter(
            completed_at__isnull=True
        ).select_related("workflow_definition", "current_state")

        checked = breached = notified = 0
        for instance in open_instances:
            sla = _sla_status(instance)
            checked += 1
            if not sla or sla["status"] != "breached":
                continue
            breached += 1

            # Dedupe: the audit log records one breach per entry into the state
            already_notified = AuditLog.objects.filter(
                workflow_instance=instance,
                action_type=AuditActionType.SLA_BREACHED,
                created_at__gte=parse_datetime(sla["entered_at"]),
            ).exists()
            if already_notified:
                continue

            AuditLog.objects.create(
                workflow_instance=instance,
                actor=None,
                action_type=AuditActionType.SLA_BREACHED,
                from_state=instance.current_state.name,
                payload={
                    "sla_hours": sla["sla_hours"],
                    "elapsed_hours": sla["elapsed_hours"],
                },
            )
            queue_event_notifications(
                workflow_instance=instance,
                event_trigger=EventTrigger.SLA_BREACHED,
                context_data={
                    "instance": {"reference_number": instance.reference_number},
                    "state": instance.current_state.name,
                    "sla_hours": sla["sla_hours"],
                    "elapsed_hours": sla["elapsed_hours"],
                },
            )
            notified += 1
            self.stdout.write(
                f"  {instance.reference_number} breached in '{instance.current_state.name}' "
                f"({sla['elapsed_hours']}h / {sla['sla_hours']}h SLA)"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Checked {checked} open instances: {breached} breached, {notified} newly notified."
            )
        )
