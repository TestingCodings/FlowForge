"""
python manage.py seed                  — idempotent: skips rows that already exist
python manage.py seed --reset          — wipe all demo data first, then re-seed
python manage.py seed --quiet          — suppress per-row output
"""
from django.core.management.base import BaseCommand

from apps.accounts.models import Role, RoleName, User, UserRole
from apps.workflows.models import Rule, State, Transition, WorkflowDefinition
from apps.instances.models import WorkflowInstance
from apps.workflows.engine import perform_transition
from apps.audit.services import instance_created, transition_applied


DEMO_USERS = [
    {"email": "admin@flowforge.dev",  "password": "Admin1234!",  "first_name": "Admin",  "last_name": "User",    "is_staff": True, "is_superuser": True,  "role": RoleName.PLATFORM_ADMIN},
    {"email": "alice@flowforge.dev",  "password": "Alice1234!",  "first_name": "Alice",  "last_name": "Manager", "is_staff": False, "is_superuser": False, "role": RoleName.APPROVER},
    {"email": "bob@flowforge.dev",    "password": "Bob12345!",   "first_name": "Bob",    "last_name": "Smith",   "is_staff": False, "is_superuser": False, "role": RoleName.PARTICIPANT},
    {"email": "carol@flowforge.dev",  "password": "Carol123!",   "first_name": "Carol",  "last_name": "Director","is_staff": False, "is_superuser": False, "role": RoleName.APPROVER},
]

LEAVE_WORKFLOW = {
    "name": "Employee Leave Request",
    "prefix": "LVE",
    "description": "Standard leave approval flow for HR",
    "states": [
        {"name": "Draft",          "display_name": "Draft",          "is_initial": True,  "is_terminal": False, "position_order": 1,
         "task_config": {"requires_task": True, "title_template": "Complete leave request form",  "default_role": "participant"}, "sla_config": {"sla_hours": 48}},
        {"name": "Manager Review", "display_name": "Manager Review", "is_initial": False, "is_terminal": False, "position_order": 2,
         "task_config": {"requires_task": True, "title_template": "Review and approve leave",      "default_role": "approver"},   "sla_config": {"sla_hours": 24}},
        {"name": "Approved",       "display_name": "Approved",       "is_initial": False, "is_terminal": True,  "position_order": 3,
         "task_config": {"requires_task": False}, "sla_config": {}},
    ],
    "transitions": [
        {"name": "Submit",  "from": "Draft",          "to": "Manager Review"},
        {"name": "Approve", "from": "Manager Review", "to": "Approved", "requires_approval": True},
    ],
    "rules": [],
    "instances": [
        {"creator": "bob@flowforge.dev",   "meta": {"employee": "Bob Smith",     "days_requested": 5,  "reason": "Annual holiday"},       "advance": []},
        {"creator": "bob@flowforge.dev",   "meta": {"employee": "Bob Smith",     "days_requested": 3,  "reason": "Medical appointment"},   "advance": ["Submit"]},
        {"creator": "alice@flowforge.dev", "meta": {"employee": "Alice Manager", "days_requested": 10, "reason": "Paternity leave"},        "advance": ["Submit", "Approve"]},
    ],
}

CLAIM_WORKFLOW = {
    "name": "Insurance Claim",
    "prefix": "CLM",
    "description": "Multi-tier claim assessment with value-based routing and escalation",
    "states": [
        {"name": "New Claim",         "display_name": "New Claim",         "is_initial": True,  "is_terminal": False, "position_order": 1,
         "task_config": {"requires_task": True, "title_template": "Capture claim details and supporting documents", "default_role": "participant"}, "sla_config": {"sla_hours": 24}},
        {"name": "Under Review",      "display_name": "Under Review",      "is_initial": False, "is_terminal": False, "position_order": 2,
         "task_config": {"requires_task": True, "title_template": "Assess claim validity and value",                 "default_role": "approver"},   "sla_config": {"sla_hours": 48}},
        {"name": "Director Approval", "display_name": "Director Approval", "is_initial": False, "is_terminal": False, "position_order": 3,
         "task_config": {"requires_task": True, "title_template": "High-value claim - Director sign-off required",   "default_role": "approver"},   "sla_config": {"sla_hours": 24}},
        {"name": "Approved",          "display_name": "Approved",          "is_initial": False, "is_terminal": True,  "position_order": 4,
         "task_config": {"requires_task": False}, "sla_config": {}},
        {"name": "Rejected",          "display_name": "Rejected",          "is_initial": False, "is_terminal": True,  "position_order": 5,
         "task_config": {"requires_task": False}, "sla_config": {}},
        {"name": "Paid Out",          "display_name": "Paid Out",          "is_initial": False, "is_terminal": True,  "position_order": 6,
         "task_config": {"requires_task": False}, "sla_config": {}},
    ],
    "transitions": [
        {"name": "Submit Claim",     "from": "New Claim",         "to": "Under Review"},
        {"name": "Escalate",         "from": "Under Review",      "to": "Director Approval"},
        {"name": "Approve Standard", "from": "Under Review",      "to": "Approved",          "requires_approval": True},
        {"name": "Reject",           "from": "Under Review",      "to": "Rejected"},
        {"name": "Director Approve", "from": "Director Approval", "to": "Approved",          "requires_approval": True},
        {"name": "Director Reject",  "from": "Director Approval", "to": "Rejected"},
        {"name": "Pay Out",          "from": "Approved",          "to": "Paid Out"},
    ],
    "rules": [
        {"transition": "Approve Standard",
         "condition": {"field": "claim_value", "operator": "gt", "value": 10000},
         "action": {"type": "block_transition", "reason": "Claims over £10,000 require Director approval. Use Escalate instead."},
         "priority": 1},
    ],
    "instances": [
        {"creator": "bob@flowforge.dev",   "meta": {"claim_value": 850,   "category": "Property",   "claimant": "Bob Smith",      "description": "Roof damage from storm"},          "advance": []},
        {"creator": "bob@flowforge.dev",   "meta": {"claim_value": 3200,  "category": "Vehicle",    "claimant": "Bob Smith",      "description": "Car repair after collision"},       "advance": ["Submit Claim"]},
        {"creator": "alice@flowforge.dev", "meta": {"claim_value": 14750, "category": "Liability",  "claimant": "Alice Manager",  "description": "Third-party liability claim"},      "advance": ["Submit Claim", "Escalate"]},
        {"creator": "bob@flowforge.dev",   "meta": {"claim_value": 1100,  "category": "Property",   "claimant": "Bob Smith",      "description": "Window replacement"},              "advance": ["Submit Claim", "Approve Standard", "Pay Out"]},
        {"creator": "carol@flowforge.dev", "meta": {"claim_value": 500,   "category": "Health",     "claimant": "Carol Director", "description": "Dental treatment"},                "advance": ["Submit Claim", "Reject"]},
    ],
}


class Command(BaseCommand):
    help = "Seed FlowForge with demo workflows and instances."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing demo data before seeding")
        parser.add_argument("--quiet", action="store_true", help="Suppress per-row output")

    def handle(self, *args, **options):
        quiet = options["quiet"]

        if options["reset"]:
            self.stdout.write(self.style.WARNING("Resetting demo data..."))
            WorkflowInstance.objects.filter(workflow_definition__name__in=[LEAVE_WORKFLOW["name"], CLAIM_WORKFLOW["name"]]).delete()
            WorkflowDefinition.objects.filter(name__in=[LEAVE_WORKFLOW["name"], CLAIM_WORKFLOW["name"]]).delete()
            for spec in DEMO_USERS:
                User.objects.filter(email=spec["email"]).delete()

        self._seed_users(quiet)
        self._seed_workflow(LEAVE_WORKFLOW, quiet)
        self._seed_workflow(CLAIM_WORKFLOW, quiet)

        self.stdout.write(self.style.SUCCESS("\nSeed complete."))
        self.stdout.write("")
        self.stdout.write("Login credentials:")
        for u in DEMO_USERS:
            self.stdout.write(f"  {u['email']:<30} / {u['password']}")
        self.stdout.write("")
        self.stdout.write("App: http://localhost:5173")

    def _seed_users(self, quiet):
        for spec in DEMO_USERS:
            user, created = User.objects.get_or_create(
                email=spec["email"],
                defaults={
                    "first_name": spec["first_name"],
                    "last_name": spec["last_name"],
                    "is_staff": spec["is_staff"],
                    "is_superuser": spec["is_superuser"],
                },
            )
            if created:
                user.set_password(spec["password"])
                user.save()
                if not quiet:
                    self.stdout.write(f"  Created user {spec['email']}")
            role, _ = Role.objects.get_or_create(name=spec["role"])
            UserRole.objects.get_or_create(user=user, role=role)

    def _seed_workflow(self, spec, quiet):
        if WorkflowDefinition.objects.filter(name=spec["name"]).exists():
            if not quiet:
                self.stdout.write(f"  Workflow '{spec['name']}' already exists — skipping")
            return

        admin = User.objects.get(email="admin@flowforge.dev")
        wf = WorkflowDefinition.objects.create(
            name=spec["name"],
            description=spec["description"],
            reference_prefix=spec["prefix"],
            is_active=True,
            created_by=admin,
        )

        state_map = {}
        for s in spec["states"]:
            state = State.objects.create(workflow_definition=wf, **{k: v for k, v in s.items() if k != "name"}, name=s["name"])
            state_map[s["name"]] = state

        transition_map = {}
        for t in spec["transitions"]:
            tr = Transition.objects.create(
                workflow_definition=wf,
                from_state=state_map[t["from"]],
                to_state=state_map[t["to"]],
                name=t["name"],
                display_name=t.get("display_name", ""),
                requires_approval=t.get("requires_approval", False),
            )
            transition_map[t["name"]] = tr

        for r in spec.get("rules", []):
            Rule.objects.create(
                workflow_definition=wf,
                transition=transition_map[r["transition"]],
                condition=r["condition"],
                action=r["action"],
                priority=r["priority"],
            )

        if not quiet:
            self.stdout.write(f"  Created workflow '{spec['name']}' ({spec['prefix']})")

        for inst_spec in spec.get("instances", []):
            creator = User.objects.get(email=inst_spec["creator"])
            instance = WorkflowInstance.objects.create(
                workflow_definition=wf,
                created_by=creator,
                metadata_json=inst_spec["meta"],
            )
            instance_created(instance, actor=creator)
            for tr_name in inst_spec.get("advance", []):
                tr = Transition.objects.get(workflow_definition=wf, from_state=instance.current_state, name=tr_name)
                from_name = instance.current_state.name
                perform_transition(instance, tr.id)
                instance.refresh_from_db()
                transition_applied(
                    instance, actor=creator,
                    from_state=from_name,
                    to_state=instance.current_state.name,
                    payload={"transition_name": tr_name, "seeded": True},
                )
            if not quiet:
                self.stdout.write(f"    {instance.reference_number} [{instance.current_state.name}]")
