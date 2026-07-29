# Custom Exportable Apps — Design

**Status:** design. Nothing here is built. It supersedes the older framing in
which "workflow packages" and "multi-tenancy" were alternatives.

---

## 1. Why they're one strategy, not two

The earlier framing treated these as competing paths:

- **Packages** — export a workflow bundle, import it per client. Content is
  portable; each client still needs their own deployment.
- **Multi-tenancy** — one deployment serving many clients.

They aren't alternatives, because they answer different halves of the same
question. Packages make the *content* portable. Multi-tenancy makes the
*container* shareable. What a client actually buys is neither: it's a branded,
role-aware application covering their processes.

Call that unit an **App**. An App is a bundle that carries everything needed
to stand a client's system up:

```
App
├── identity      name, logo, theme, locale, density        (today: Workspace singleton)
├── workflows[]   states, transitions, rules, forms, ui_schema  (today: export bundle)
├── roles[]       role definitions and what each may do     (today: hard-coded enum)
├── surfaces      which screens exist, per role             (today: implicit, one UI)
└── seed          optional starting data / demo content     (today: seed command)
```

Two of those five exist. The strategy is to make the other three portable, at
which point one mechanism serves both models:

- **Consultancy delivery** — export the App, deploy it for one client.
- **SaaS** — import many Apps into one deployment, scoped by tenant.

Multi-tenancy stops being a rewrite and becomes *"the App boundary is enforced
at query time"*. That's the point of doing them together: build the App
boundary once, and which model you sell is a deployment decision.

---

## 2. What exists today

| Piece | State | Gap |
|---|---|---|
| Workflow export/import | `portability.py`, `bundle_version: 1` | Carries one workflow. No identity, roles, or surfaces |
| Branding | `Workspace` model | **Singleton** — `Workspace.current()`, one row |
| Roles | `RoleName` TextChoices | **Fixed five-value enum**, compiled in |
| Permissions | `require_role`, `userCan` | Checks against that enum |
| Surfaces | `ui_schema.instance_view.panels` | Per workflow, not per role |

The singleton and the enum are the two load-bearing assumptions. Everything
else is already data.

---

## 3. Phases

Deliberately ordered so each phase ships value alone, and none requires the
next to be worthwhile.

### Phase 1 — Role definitions become data
Turn `RoleName` from an enum into rows. See [ROLES.md](ROLES.md) for the full
design. Unlocks: a client can have a "Claims Handler" instead of an
"Approver", which is most of what "branded" means in practice.

**Ships alone as:** custom role names and permission sets.

### Phase 2 — Surfaces become per-role
Extend `ui_schema.instance_view` from one panel list to a panel list *per
role*, and gate creator-only affordances (builder links, rule explanations,
schema hints) behind capability checks rather than showing them to everyone.

**Ships alone as:** the creator/user UI split — the thing that currently makes
demos feel rigid.

### Phase 3 — The App bundle — **partially done**
`export_app` / `import_app` and `POST /api/workflows/export-app|import-app`
carry **identity + many workflows** as `kind: "flowforge.app"`, versioned
separately from the workflow bundle so the two formats evolve independently.
Workflow bundles nest inside unchanged, so there is one importer rather than
two that can drift, and existing v1 workflow bundles still import.

Import is atomic — a half-imported app (some workflows present, branding
changed) is worse than a failed one — and `apply_identity=False` lets an
install take a client's processes without adopting their branding.

**Still to carry:** roles and surfaces, which depend on [ROLES.md](ROLES.md).
Until roles are data there is nothing portable to put in the bundle.

**Ships alone as:** "here is your system as a file" — the consultancy
deliverable. Verified: the Northwind slice exports to a single 11.5 KB file
carrying three workflows, their rules, forms and presentation, plus the
workspace's name, tagline and theme.

### Phase 4 — Tenancy
Add a `Tenant` FK to `Workspace`, `WorkflowDefinition`, `User`, and
`WorkflowInstance`. Scope every queryset through a request-derived tenant.

**Ships alone as:** many clients on one deployment.

Phase 4 is the only genuinely risky one, and putting it last is deliberate:
by then the App boundary already exists conceptually, so tenancy is enforcement
rather than redesign.

---

## 4. The hard parts, named honestly

**Query scoping is all-or-nothing.** Multi-tenancy fails when *one* queryset
forgets its tenant filter. The mitigation is structural, not disciplinary: a
base manager that requires an explicit tenant, plus a test that enumerates
every model and asserts it's reachable only through it. Don't rely on review.

**Roles as data means permissions as data.** Once roles are rows, `require_role`
can't check a constant. It needs a capability lookup, which is a hot path on
every request — cache per request, and treat a cache miss as deny.

**Bundle versioning is a compatibility promise.** `bundle_version: 2` must
import v1 bundles, and a v2 bundle must fail cleanly on an older install
rather than half-importing. The current code already checks the version and
raises — keep that discipline.

**Seed data is client data.** An App's seed content is a starting point, not a
fixture; re-importing must not clobber live instances. Import should refuse by
default and require an explicit `--replace`, exactly as `seed_demo_story` does.

---

## 5. What this does *not* solve

- **Per-tenant custom code.** Apps are configuration. A client needing bespoke
  logic still needs a hook, an inbound trigger, or a code change.
- **Billing, provisioning, tenant self-signup.** Out of scope; Phase 4 gives
  the isolation those would build on, nothing more.
- **Data residency.** One deployment means one database and one region.
  Regulated clients still want their own deployment — which the package model
  serves, and which is a reason to keep both paths alive rather than replacing
  one with the other.
