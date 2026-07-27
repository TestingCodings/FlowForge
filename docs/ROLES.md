# Roles and User Management as Data — Design

**Status:** design. Nothing here is built.

Answers: *can a creator build an app that has its own user creation and role
allowances, the way FlowForge itself does?* Yes — and it's less ambitious than
it sounds, because the engine already treats almost everything else as data.
The blocker is narrow and specific.

---

## 1. The blocker

Roles are a compiled-in enum:

```python
# apps/accounts/models.py
class RoleName(models.TextChoices):
    PLATFORM_ADMIN    = "platform_admin", "Platform Admin"
    WORKFLOW_DESIGNER = "workflow_designer", "Workflow Designer"
    PARTICIPANT       = "participant", "Participant"
    APPROVER          = "approver", "Approver"
    VIEWER            = "viewer", "Viewer"
```

There is already a `Role` **model** — but its `name` is constrained to those
five choices, so the table is a lookup for the enum rather than a definition.
`require_role(user, "platform_admin")` compares against a literal, and the
frontend's `userCan` mirrors the same list.

So a client cannot have a "Claims Handler" or a "Ward Sister". They get an
"Approver" and are told to imagine. For a product sold as *their* system, that
is the single most visible place the mask slips.

Everything else needed is already data: users are rows, `UserRole` is a join
table, transitions already carry `requires_approval` and role requirements,
and the API enforces server-side rather than trusting the UI.

---

## 2. Design

### 2.1 Capabilities are the fixed vocabulary

Role *names* become free-form. What a role may *do* is drawn from a closed set
of capabilities, because those correspond to real code paths and cannot be
invented at runtime:

```
workflow.view      workflow.design     workflow.publish
instance.view      instance.create     instance.transition
instance.comment   instance.metadata   instance.delete
form.submit        media.upload        media.delete
user.view          user.create         user.assign_roles
secret.manage      hook.manage         audit.view
workspace.manage
```

Inverting it this way is what makes the feature safe. A creator composes roles
from capabilities; they never define a new *kind* of permission, so there is
no path from "custom role" to "unchecked code path".

### 2.2 Model changes

```python
class Role(models.Model):
    id            = UUIDField(primary_key=True)
    key           = SlugField()          # "claims_handler" — stable, referenced by bundles
    label         = CharField()          # "Claims Handler" — shown in the UI
    capabilities  = JSONField(default=list)
    is_system     = BooleanField(default=False)   # the built-in five; cannot be deleted
    rank          = IntegerField(default=0)       # for "approver+" style comparisons

    class Meta:
        constraints = [UniqueConstraint(fields=["key"], name="uniq_role_key")]
```

The existing five become seeded rows with `is_system=True`, so nothing breaks
and the migration is additive.

`rank` earns its place: several checks today mean "this role or above"
(`viewer+`, `designer+`). Without an ordering that becomes an explicit
capability list on every call site, which is more honest but much noisier.
Keep rank, and document it as a convenience over capabilities, not a parallel
system.

### 2.3 Permission checks

```python
def require_capability(user, capability, action="perform this action"):
    if capability not in capabilities_for(user):   # cached per request
        raise PermissionDenied(f"You need '{capability}' to {action}.")
```

`require_role` stays as a thin wrapper during migration, then goes. The cache
is per request and a miss denies — never fails open.

### 2.4 User creation by a creator

A role carrying `user.create` may invite users and assign roles, but **only
roles ranked at or below their own**. Without that rule, any role with
`user.assign_roles` is a privilege-escalation path to platform admin.

Registration flow reuses what exists: `RegisterView` already honours
`DEMO_REGISTRATION_ENABLED`. Add invite-based creation alongside it, so a
client's admin can onboard their own staff without a FlowForge operator.

---

## 3. Surfaces per role — the creator/user split

The complaint that the app "feels rigid and unimpressive to demo" is mostly
this: everyone sees the designer's interface. A participant is shown builder
links they can't use, rule explanations for rules they can't change, and
schema hints for fields they can't edit.

Two changes fix it, and neither needs the role work above to land first:

**1. Gate affordances by capability, not by presence.** Any control that leads
somewhere the user can't go should not render. Today several render and then
fail, or render and do nothing.

**2. Per-role panels.** Extend `ui_schema.instance_view`:

```json
{
  "instance_view": {
    "panels": ["description", "metadata", "state_graph", "timeline"],
    "panels_by_role": {
      "participant": ["description", "forms", "attachments"],
      "viewer":      ["description", "timeline"]
    }
  }
}
```

`panels` stays the default so every existing workflow is unaffected;
`panels_by_role` overrides per role when present. Falling back rather than
requiring exhaustive definition is what keeps this from becoming a chore.

The same idea extends to hint text: creator-facing explanations belong behind
`workflow.design`, not in every user's face.

---

## 4. Phasing

| Step | Work | Ships as |
|---|---|---|
| 1 | `Role` gains `key`/`label`/`capabilities`/`rank`; seed the five as system roles | Nothing visible — migration only |
| 2 | `require_capability` + per-request cache; migrate call sites | Nothing visible |
| 3 | Role management UI (create, edit capabilities, assign) | **Custom roles** |
| 4 | Capability-gated affordances + `panels_by_role` | **Creator/user split** |
| 5 | Invite-based user creation, rank-capped | **Client-managed users** |

Steps 1–2 are invisible and must be, since they touch every permission check.
Step 4 is the demo-facing win and is independent enough to pull forward — it
can use the existing five roles and gain custom ones for free later.

---

## 5. Risks

**Every permission check is a potential regression.** Migrating `require_role`
call sites is mechanical but exhaustive. Mitigation: keep both mechanisms
during migration with the old one authoritative, add a test asserting they
agree for the five system roles, then flip.

**Custom roles can lock people out.** A creator can build a role with no
capabilities and assign it to themselves. Mitigation: refuse to remove the
last `user.assign_roles` holder, the same way you can't delete the last admin.

**Rank plus capabilities is two models of authority.** They can disagree.
Mitigation: rank is *only* for "or above" comparisons and never grants a
capability by itself. Write that down in code, not just here.

**Bundles referencing roles that don't exist.** An App bundle naming
`claims_handler` imported where that role is absent must create it, not fail
or silently drop permissions. Import creates missing roles as non-system rows.
