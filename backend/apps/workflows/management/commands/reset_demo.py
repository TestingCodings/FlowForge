"""
python manage.py reset_demo          — restore the public demo to a known state
python manage.py reset_demo --story  — also reseed the scene-shell demo story

Runs nightly on the public demo (docs/DEPLOYMENT.md §2.1). A public demo is a
database that strangers can write to, so the only workable model is that its
contents are disposable and get rebuilt on a schedule.

Two things this deliberately does NOT do:

* **It does not flush the database.** `manage.py flush` would take the
  migration history and any non-demo data with it. This removes demo-owned
  rows by name and re-seeds them, so the command is safe to run against a
  database that also holds something else.
* **It does not print credentials.** `seed` prints a login table, which is
  right at a developer's terminal and wrong in a container log that ships to
  a log aggregator. This suppresses that output.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Reset the public demo to a freshly-seeded state (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--story", action="store_true",
            help="Also reseed the scene-shell demo story ('The Locked Door').",
        )

    def handle(self, *args, **options):
        self.stdout.write("Resetting demo data...")

        with transaction.atomic():
            # `seed --reset` already deletes the demo workflows, their
            # instances and the demo users before recreating them, which is
            # exactly the semantics needed here. Reusing it means the demo can
            # never drift from what a developer sees locally.
            call_command("seed", "--reset", "--testrail", "--quiet", stdout=_Sink())

            if options["story"]:
                call_command("seed_demo_story", "--reset", stdout=_Sink())

        self.stdout.write(self.style.SUCCESS("Demo reset complete."))
        self.stdout.write(
            "Accounts and workflows restored. Credentials are intentionally "
            "not logged; they are shown on the demo login page."
        )


class _Sink:
    """Swallow the seed command's output.

    `seed` finishes by printing every demo account and its plaintext
    password. That is useful at a terminal and unacceptable in a nightly
    container log, so its stdout is discarded rather than forwarded.
    """

    def write(self, *args, **kwargs):
        pass

    def flush(self):
        pass
