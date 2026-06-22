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


TESTRAIL_WORKFLOWS = [
    {
        "name": "Test Run",
        "prefix": "TRN",
        "description": "A test execution run against a specific build. Tracks overall pass/fail status and blocks release if failures exist.",
        "states": [
            {"name": "Planning",    "display_name": "Planning",    "is_initial": True,  "is_terminal": False, "position_order": 1,
             "task_config": {"requires_task": True,  "title_template": "Define scope and assign test cases", "default_role": "workflow_designer"}, "sla_config": {"sla_hours": 24}},
            {"name": "In Progress", "display_name": "In Progress", "is_initial": False, "is_terminal": False, "position_order": 2,
             "task_config": {"requires_task": True,  "title_template": "Execute test cases and record results", "default_role": "participant"},   "sla_config": {"sla_hours": 72}},
            {"name": "Passed",      "display_name": "Passed",      "is_initial": False, "is_terminal": True,  "position_order": 3,
             "task_config": {"requires_task": False}, "sla_config": {}},
            {"name": "Failed",      "display_name": "Failed",      "is_initial": False, "is_terminal": True,  "position_order": 4,
             "task_config": {"requires_task": False}, "sla_config": {}},
            {"name": "Blocked",     "display_name": "Blocked",     "is_initial": False, "is_terminal": True,  "position_order": 5,
             "task_config": {"requires_task": False}, "sla_config": {}},
        ],
        "transitions": [
            {"name": "Start Run",       "from": "Planning",    "to": "In Progress"},
            {"name": "Mark Passed",     "from": "In Progress", "to": "Passed",      "requires_approval": True},
            {"name": "Mark Failed",     "from": "In Progress", "to": "Failed"},
            {"name": "Mark Blocked",    "from": "In Progress", "to": "Blocked"},
            {"name": "Reopen",          "from": "Failed",      "to": "In Progress"},
            {"name": "Reopen Blocked",  "from": "Blocked",     "to": "In Progress"},
        ],
        "rules": [
            {
                "transition": "Mark Passed",
                "condition": {"field": "fail_count", "operator": "gt", "value": 0},
                "action": {"type": "block_transition", "reason": "This run has recorded failures. Resolve all failed test cases before marking the run as Passed."},
                "priority": 1,
            },
            {
                "transition": "Mark Passed",
                "condition": {"field": "block_count", "operator": "gt", "value": 0},
                "action": {"type": "block_transition", "reason": "This run has blocked test cases. Unblock or remove them before closing as Passed."},
                "priority": 2,
            },
        ],
        "instances": [
            {"creator": "alice@flowforge.dev", "meta": {"suite": "Authentication",  "build": "v2.4.1", "environment": "Staging",    "total_cases": 24, "fail_count": 0, "block_count": 0}, "advance": ["Start Run", "Mark Passed"]},
            {"creator": "bob@flowforge.dev",   "meta": {"suite": "Checkout Flow",   "build": "v2.4.1", "environment": "Staging",    "total_cases": 18, "fail_count": 3, "block_count": 0}, "advance": ["Start Run"]},
            {"creator": "alice@flowforge.dev", "meta": {"suite": "API Regression",  "build": "v2.4.0", "environment": "Production", "total_cases": 56, "fail_count": 0, "block_count": 2}, "advance": ["Start Run", "Mark Blocked"]},
            {"creator": "bob@flowforge.dev",   "meta": {"suite": "Smoke Tests",     "build": "v2.4.1", "environment": "UAT",        "total_cases": 8,  "fail_count": 0, "block_count": 0}, "advance": ["Start Run"]},
        ],
    },
    {
        "name": "Bug Report",
        "prefix": "BUG",
        "description": "Defect lifecycle from discovery through to verified fix. Raised from failed test runs.",
        "states": [
            {"name": "New",         "display_name": "New",         "is_initial": True,  "is_terminal": False, "position_order": 1,
             "task_config": {"requires_task": True,  "title_template": "Triage and assign bug", "default_role": "approver"},      "sla_config": {"sla_hours": 4}},
            {"name": "In Progress", "display_name": "In Progress", "is_initial": False, "is_terminal": False, "position_order": 2,
             "task_config": {"requires_task": True,  "title_template": "Investigate and fix",   "default_role": "participant"},   "sla_config": {"sla_hours": 48}},
            {"name": "In Review",   "display_name": "In Review",   "is_initial": False, "is_terminal": False, "position_order": 3,
             "task_config": {"requires_task": True,  "title_template": "Code review and QA sign-off", "default_role": "approver"}, "sla_config": {"sla_hours": 24}},
            {"name": "Fixed",       "display_name": "Fixed",       "is_initial": False, "is_terminal": True,  "position_order": 4,
             "task_config": {"requires_task": False}, "sla_config": {}},
            {"name": "Won't Fix",   "display_name": "Won't Fix",   "is_initial": False, "is_terminal": True,  "position_order": 5,
             "task_config": {"requires_task": False}, "sla_config": {}},
            {"name": "Duplicate",   "display_name": "Duplicate",   "is_initial": False, "is_terminal": True,  "position_order": 6,
             "task_config": {"requires_task": False}, "sla_config": {}},
        ],
        "transitions": [
            {"name": "Assign",        "from": "New",         "to": "In Progress"},
            {"name": "Mark Duplicate","from": "New",         "to": "Duplicate"},
            {"name": "Won't Fix",     "from": "New",         "to": "Won't Fix",   "requires_approval": True},
            {"name": "Submit Review", "from": "In Progress", "to": "In Review"},
            {"name": "Reopen",        "from": "In Progress", "to": "New"},
            {"name": "Approve Fix",   "from": "In Review",   "to": "Fixed",       "requires_approval": True},
            {"name": "Reject Fix",    "from": "In Review",   "to": "In Progress"},
        ],
        "rules": [
            {
                "transition": "Approve Fix",
                "condition": {"field": "severity", "operator": "eq", "value": "critical"},
                "action": {"type": "assign_role", "role": "approver"},
                "priority": 1,
            },
        ],
        "instances": [
            {"creator": "bob@flowforge.dev",   "meta": {"title": "Login fails with SSO on Safari", "severity": "critical", "reported_in": "TRN-2026-00002", "component": "Auth"}, "advance": ["Assign"]},
            {"creator": "bob@flowforge.dev",   "meta": {"title": "Cart total rounds incorrectly",  "severity": "high",     "reported_in": "TRN-2026-00002", "component": "Checkout"}, "advance": ["Assign", "Submit Review"]},
            {"creator": "alice@flowforge.dev", "meta": {"title": "Tooltip misaligned on mobile",   "severity": "low",      "reported_in": "TRN-2026-00001", "component": "UI"}, "advance": ["Won't Fix"]},
            {"creator": "bob@flowforge.dev",   "meta": {"title": "API 500 on concurrent checkout", "severity": "critical", "reported_in": "TRN-2026-00002", "component": "API"}, "advance": ["Assign", "Submit Review", "Approve Fix"]},
        ],
    },
    {
        "name": "Release",
        "prefix": "REL",
        "description": "Software release gate. Blocks deployment if open critical bugs or failing test runs exist.",
        "states": [
            {"name": "Draft",      "display_name": "Draft",      "is_initial": True,  "is_terminal": False, "position_order": 1,
             "task_config": {"requires_task": True,  "title_template": "Prepare release notes and changelog", "default_role": "workflow_designer"}, "sla_config": {"sla_hours": 8}},
            {"name": "QA Sign-off","display_name": "QA Sign-off","is_initial": False, "is_terminal": False, "position_order": 2,
             "task_config": {"requires_task": True,  "title_template": "QA lead: confirm all runs passed",    "default_role": "approver"},          "sla_config": {"sla_hours": 4}},
            {"name": "Approved",   "display_name": "Approved",   "is_initial": False, "is_terminal": False, "position_order": 3,
             "task_config": {"requires_task": True,  "title_template": "Engineering lead: approve deployment", "default_role": "approver"},         "sla_config": {"sla_hours": 2}},
            {"name": "Deployed",   "display_name": "Deployed",   "is_initial": False, "is_terminal": True,  "position_order": 4,
             "task_config": {"requires_task": False}, "sla_config": {}},
            {"name": "Rolled Back","display_name": "Rolled Back","is_initial": False, "is_terminal": True,  "position_order": 5,
             "task_config": {"requires_task": False}, "sla_config": {}},
        ],
        "transitions": [
            {"name": "Submit for QA",   "from": "Draft",       "to": "QA Sign-off"},
            {"name": "QA Approve",      "from": "QA Sign-off", "to": "Approved",    "requires_approval": True},
            {"name": "QA Reject",       "from": "QA Sign-off", "to": "Draft"},
            {"name": "Approve Deploy",  "from": "Approved",    "to": "Deployed",    "requires_approval": True},
            {"name": "Reject Deploy",   "from": "Approved",    "to": "Draft"},
            {"name": "Roll Back",       "from": "Deployed",    "to": "Rolled Back"},
        ],
        "rules": [
            {
                "transition": "QA Approve",
                "condition": {"field": "open_critical_bugs", "operator": "gt", "value": 0},
                "action": {"type": "block_transition", "reason": "Open critical bugs must be resolved before QA sign-off."},
                "priority": 1,
            },
            {
                "transition": "QA Approve",
                "condition": {"field": "failing_runs", "operator": "gt", "value": 0},
                "action": {"type": "block_transition", "reason": "All test runs must be in Passed state before QA sign-off."},
                "priority": 2,
            },
        ],
        "instances": [
            {"creator": "alice@flowforge.dev", "meta": {"version": "v2.4.0", "environment": "Production", "open_critical_bugs": 0, "failing_runs": 0, "release_notes": "Performance improvements and bug fixes"}, "advance": ["Submit for QA", "QA Approve", "Approve Deploy"]},
            {"creator": "alice@flowforge.dev", "meta": {"version": "v2.4.1", "environment": "Production", "open_critical_bugs": 2, "failing_runs": 1, "release_notes": "SSO fix, cart rounding fix"}, "advance": ["Submit for QA"]},
        ],
    },
]

ALL_TESTRAIL_NAMES = [w["name"] for w in TESTRAIL_WORKFLOWS]


class Command(BaseCommand):
    help = "Seed FlowForge with demo workflows and instances."

    def add_arguments(self, parser):
        parser.add_argument("--reset",    action="store_true", help="Delete existing demo data before seeding")
        parser.add_argument("--quiet",    action="store_true", help="Suppress per-row output")
        parser.add_argument("--testrail", action="store_true", help="Also seed TestRail-replacement example workflows")

    def handle(self, *args, **options):
        quiet    = options["quiet"]
        testrail = options["testrail"]

        if options["reset"]:
            self.stdout.write(self.style.WARNING("Resetting demo data..."))
            names = [LEAVE_WORKFLOW["name"], CLAIM_WORKFLOW["name"]]
            if testrail:
                names += ALL_TESTRAIL_NAMES
            WorkflowInstance.objects.filter(workflow_definition__name__in=names).delete()
            WorkflowDefinition.objects.filter(name__in=names).delete()
            for spec in DEMO_USERS:
                User.objects.filter(email=spec["email"]).delete()

        self._seed_users(quiet)
        self._seed_workflow(LEAVE_WORKFLOW, quiet)
        self._seed_workflow(CLAIM_WORKFLOW, quiet)

        if testrail:
            self.stdout.write(self.style.HTTP_INFO("\nSeeding TestRail-replacement workflows..."))
            for wf_spec in TESTRAIL_WORKFLOWS:
                self._seed_workflow(wf_spec, quiet)

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
