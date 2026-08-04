"""Step 1 of roles-as-data (docs/ROLES.md §2): the model gains fields.

Deliberately invisible. This step must change nothing about behaviour — it
only makes the shape available so `require_capability` can be built on top
next. A permissions change is the one class where "mostly working" is
dangerous, so the migration lands and is proven inert before anything starts
reading it.

The migration deliberately does not seed the built-in roles: doing so would
put them in every freshly-migrated database, including every test database,
and the suite's existing `Role.objects.create(name=...)` calls would then
collide on the unique name. `Role.save()` fills the new fields instead, so
those calls keep working *and* keep producing correct rows.
"""
import pytest

from apps.accounts.models import CAPABILITIES, SYSTEM_ROLES, Role, RoleName


@pytest.mark.django_db
class TestCreatingRolesTheOldWay:
    """Every existing caller does `Role.objects.create(name=RoleName.X)` and
    knows nothing about the new fields. Those calls must keep working *and*
    keep producing correct rows — a role that silently ended up permitted
    nothing would be worse than a hard failure."""

    @pytest.mark.parametrize("key", [r.value for r in RoleName])
    def test_legacy_create_fills_the_new_fields(self, key):
        role = Role.objects.create(name=key)
        assert role.key == key
        assert role.label
        assert role.capabilities
        assert role.rank > 0
        assert role.is_system

    def test_key_matches_the_legacy_name(self):
        """`name` is what every permission check reads today. Until those are
        migrated the two must agree exactly, or a check silently stops
        matching."""
        role = Role.objects.create(name=RoleName.APPROVER)
        assert role.key == role.name


@pytest.mark.django_db
class TestCapabilities:
    def test_admin_has_every_capability(self):
        admin = Role.objects.create(name=RoleName.PLATFORM_ADMIN)
        assert set(admin.capabilities) == set(CAPABILITIES)

    def test_viewer_cannot_transition(self):
        assert not Role.objects.create(name=RoleName.VIEWER).has("instance.transition")

    def test_participant_can_transition_but_not_design(self):
        participant = Role.objects.create(name=RoleName.PARTICIPANT)
        assert participant.has("instance.transition")
        assert not participant.has("workflow.design")

    def test_approver_outranks_participant(self):
        approver = Role.objects.create(name=RoleName.APPROVER)
        participant = Role.objects.create(name=RoleName.PARTICIPANT)
        assert approver.rank > participant.rank


class TestCapabilityDefinitions:
    """Pure checks on the declarations themselves — no database needed."""

    def test_every_declared_capability_is_known(self):
        """A typo'd capability would grant nothing and fail silently."""
        for key, spec in SYSTEM_ROLES.items():
            unknown = set(spec["capabilities"]) - set(CAPABILITIES)
            assert not unknown, f"{key} declares unknown: {unknown}"

    def test_ranks_are_distinct(self):
        ranks = [s["rank"] for s in SYSTEM_ROLES.values()]
        assert len(set(ranks)) == len(ranks)

    def test_capabilities_grow_with_rank(self):
        """A more senior role must never be permitted less than a junior one.
        Otherwise `rank` and `capabilities` disagree about who can do what,
        which docs/ROLES.md §5 flags as the trap of running two models of
        authority side by side."""
        by_rank = sorted(SYSTEM_ROLES.values(), key=lambda s: s["rank"])
        for lower, higher in zip(by_rank, by_rank[1:]):
            missing = set(lower["capabilities"]) - set(higher["capabilities"])
            assert not missing, (
                f"{higher['label']} outranks {lower['label']} but lacks {missing}"
            )

    def test_every_role_key_is_covered(self):
        assert set(SYSTEM_ROLES) == {r.value for r in RoleName}


@pytest.mark.django_db
class TestCustomRoles:
    def test_a_custom_role_can_be_created(self):
        """The whole point: a client can have a 'Site Manager'."""
        role = Role.objects.create(
            key="site_manager", name="site_manager", label="Site Manager",
            capabilities=["instance.view", "instance.transition"], rank=25,
        )
        assert not role.is_system
        assert role.has("instance.transition")

    def test_a_custom_role_gets_a_readable_label_by_default(self):
        assert Role.objects.create(name="site_manager").label == "Site Manager"

    def test_a_custom_role_is_granted_nothing_by_default(self):
        """Inventing permissions for an unrecognised role would be privilege
        escalation by convenience."""
        assert Role.objects.create(name="site_manager").capabilities == []

    def test_keys_are_unique(self):
        from django.db import IntegrityError

        Role.objects.create(name=RoleName.VIEWER)
        with pytest.raises(IntegrityError):
            Role.objects.create(key="viewer", name="viewer_two", label="Dupe")


@pytest.mark.django_db
class TestNothingElseChanged:
    def test_existing_role_lookups_by_name_still_work(self):
        """Every permission check does Role.objects.get(name=...) today."""
        Role.objects.create(name=RoleName.PLATFORM_ADMIN)
        assert Role.objects.get(name=RoleName.PLATFORM_ADMIN).label == "Platform Admin"

    def test_str_is_still_human_readable(self):
        assert str(Role.objects.create(name=RoleName.APPROVER)) == "Approver"


@pytest.mark.django_db
class TestSystemRolesNeverDrift:
    """Built-in roles must match SYSTEM_ROLES exactly.

    Regression: `instance.relate` was added to CAPABILITIES during the
    capability flip, but Role.save() only filled capabilities when they were
    blank, so existing rows kept the older list. Every built-in role, platform
    admin included, was left unable to re-parent or link an instance on any
    database migrated before that change. The failure was invisible from the
    tests because they create roles fresh.
    """

    @pytest.mark.parametrize("key", list(SYSTEM_ROLES))
    def test_saved_role_matches_the_spec(self, key):
        role = Role.objects.create(name=key)
        assert set(role.capabilities) == set(SYSTEM_ROLES[key]["capabilities"])
        assert role.rank == SYSTEM_ROLES[key]["rank"]

    def test_a_stale_role_is_repaired_on_save(self):
        """The mechanism that stops this recurring."""
        role = Role.objects.create(name=RoleName.PLATFORM_ADMIN)
        Role.objects.filter(pk=role.pk).update(capabilities=["workflow.view"])

        stale = Role.objects.get(pk=role.pk)
        assert stale.capabilities == ["workflow.view"]
        stale.save()

        assert set(Role.objects.get(pk=role.pk).capabilities) == set(CAPABILITIES)

    def test_every_capability_reaches_the_platform_admin(self):
        """A capability nobody holds denies everyone, which is how the
        original bug behaved."""
        admin = Role.objects.create(name=RoleName.PLATFORM_ADMIN)
        missing = set(CAPABILITIES) - set(admin.capabilities)
        assert not missing, f"platform admin cannot {missing}"

    def test_a_custom_role_is_not_overwritten(self):
        """Only built-ins are code-authoritative; a client's own role must
        keep exactly what was configured."""
        role = Role.objects.create(
            key="site_manager", name="site_manager", label="Site Manager",
            capabilities=["workflow.view"], rank=25,
        )
        role.save()
        assert Role.objects.get(pk=role.pk).capabilities == ["workflow.view"]
        assert Role.objects.get(pk=role.pk).is_system is False
