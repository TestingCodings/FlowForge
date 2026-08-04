"""Re-sync built-in roles with SYSTEM_ROLES.

0003 backfilled capabilities from the spec as it stood then. Capabilities
added to the vocabulary afterwards never reached existing rows, because
`Role.save()` only filled them when blank. `instance.relate` was added during
the capability flip, so on any database migrated before that change every
built-in role lacked it and *nobody*, including a platform admin, could
re-parent or link an instance.

`save()` now treats SYSTEM_ROLES as authoritative for built-in roles, which
prevents recurrence. This repairs rows that already drifted.
"""
from django.db import migrations


def resync(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")

    from apps.accounts.models import SYSTEM_ROLES

    for key, spec in SYSTEM_ROLES.items():
        # Historical models have no custom save(), so the fields are set here.
        Role.objects.filter(key=key).update(
            label=spec["label"],
            capabilities=spec["capabilities"],
            rank=spec["rank"],
            is_system=True,
        )


def noop(apps, schema_editor):
    """Nothing to reverse: this only ever brings rows up to date."""


class Migration(migrations.Migration):

    dependencies = [("accounts", "0003_roles_as_data")]

    operations = [migrations.RunPython(resync, noop)]
