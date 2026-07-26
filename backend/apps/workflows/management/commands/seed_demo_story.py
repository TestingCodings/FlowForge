"""
python manage.py seed_demo_story        — create/replace "The Locked Door" demo

A short branching story with two endings, used as the reference workflow for
the `scene` shell (docs/MEDIA.md Part 2). It exists to demonstrate that a
process and a story are the same shape — every game mechanic below is an
ordinary engine feature, with nothing story-specific in the backend:

    scene            = state
    choice           = transition
    inventory flag   = instance metadata
    "you find a key" = a set_metadata rule action
    locked door      = a block_transition rule, whose `reason` is the prose
                       the player reads
    ending           = terminal state
    save file        = instance
"""
from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.workflows.models import Rule, State, Transition, WorkflowDefinition

NAME = "The Locked Door (demo story)"

SCENES = [
    # (name, is_initial, is_terminal)
    ("Awakening", True, False),
    ("The Hallway", False, False),
    ("Dusty Study", False, False),
    ("Freedom", False, True),
    ("Still Trapped", False, True),
]

SCENE_CONFIG = {
    "Awakening": {
        "speaker": "Narrator",
        "dialogue": "You wake on a cold floor with no memory of arriving. A door waits in the dark.",
    },
    "The Hallway": {
        "speaker": "Narrator",
        "dialogue": "The hallway is silent. The front door is ahead; a study sits to your left.",
    },
    "Dusty Study": {
        "speaker": "Narrator",
        "dialogue": "Papers everywhere. Beneath them, a small brass key — you pocket it.",
    },
    "Freedom": {
        "speaker": "Narrator",
        "dialogue": "The key turns. Morning air. You step out and never look back.",
    },
    "Still Trapped": {
        "speaker": "Narrator",
        "dialogue": "You sit down against the wall. Eventually, the dark stops feeling strange.",
    },
}


class Command(BaseCommand):
    help = "Seed the 'The Locked Door' demo story for the scene shell."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true",
            help="Delete the existing demo story and its playthroughs first.",
        )

    def handle(self, *args, **options):
        existing = WorkflowDefinition.objects.filter(name=NAME).first()
        if existing is not None:
            if not options["reset"]:
                self.stdout.write(self.style.WARNING(
                    f"'{NAME}' already exists ({existing.id}). "
                    "Re-run with --reset to replace it and delete its playthroughs."
                ))
                return
            # Definitions are PROTECTed by their states and instances, so the
            # dependants have to go first — and that discards saved games.
            from apps.instances.models import WorkflowInstance

            instances = WorkflowInstance.objects.filter(workflow_definition=existing)
            self.stdout.write(f"Deleting {instances.count()} existing playthrough(s)...")
            instances.delete()
            Transition.objects.filter(workflow_definition=existing).delete()
            State.objects.filter(workflow_definition=existing).delete()
            existing.delete()

        wf = WorkflowDefinition.objects.create(
            name=NAME,
            reference_prefix="STORY",
            is_active=True,
            created_by=User.objects.filter(email="admin@flowforge.dev").first(),
            description="A tiny branching story: the scene shell playing a workflow.",
        )

        states = {
            name: State.objects.create(
                workflow_definition=wf, name=name, is_initial=initial,
                is_terminal=terminal, position_order=i,
            )
            for i, (name, initial, terminal) in enumerate(SCENES, start=1)
        }

        def tr(frm, to, name):
            return Transition.objects.create(
                workflow_definition=wf, from_state=states[frm],
                to_state=states[to], name=name,
            )

        tr("Awakening", "The Hallway", "Open your eyes")
        search = tr("The Hallway", "Dusty Study", "Search the study")
        unlock = tr("The Hallway", "Freedom", "Unlock the front door")
        tr("Dusty Study", "The Hallway", "Return to the hallway")
        tr("The Hallway", "Still Trapped", "Give up and wait")

        # Picking the key up is a plain metadata write — no hook, no network.
        Rule.objects.create(
            workflow_definition=wf, transition=search,
            condition={"field": "has_key", "operator": "is_false"},
            action={"type": "set_metadata", "values": {"has_key": True}},
            priority=10,
        )

        # The gate. The reason string is what the player reads when they try
        # the door too early, so the rule author is writing narration.
        Rule.objects.create(
            workflow_definition=wf, transition=unlock,
            condition={"field": "has_key", "operator": "is_false"},
            action={
                "type": "block_transition",
                "reason": "The door is locked. Something must open it.",
            },
            priority=10,
        )

        wf.ui_schema = {"shell": "scene", "scene_config": SCENE_CONFIG}
        wf.save(update_fields=["ui_schema"])

        self.stdout.write(self.style.SUCCESS(f"Seeded '{NAME}' ({wf.id})"))
        self.stdout.write("Open it under Workflows > view to play.")
