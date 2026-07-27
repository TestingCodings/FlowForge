# Northwind Phase 1 — Groundwork and Vertical Slice

**Status:** plan. Companion to [DEMO-COMPANY.md](DEMO-COMPANY.md).

Phase 1 has two jobs, and the order matters:

1. **Groundwork** — make demo content *data* instead of Python. Without this,
   fifteen workflows means fifteen hand-written seed functions, and Phases 2–5
   get progressively more expensive.
2. **The slice** — three cross-linked workflows and Northwind's branding, so
   the result is a demo you can actually put in front of someone.

Groundwork first is deliberate. The slice built the old way would have to be
rewritten once bundles exist.

---

## 1. Groundwork: content as data

### 1.1 The problem

`seed.py` is ~330 lines of Python literals defining five workflows. Adding
Northwind's fifteen the same way produces a thousand-line module that only I
can edit, can't be diffed meaningfully, and can't be handed to a client.

Meanwhile `portability.py` already exports a workflow as JSON and imports it
back — the format exists, it just isn't used for seeding.

### 1.2 The change

Store demo content as bundle files and load them:

```
backend/apps/workflows/content/
├── northwind/
│   ├── app.json                    # identity: name, logo, theme, locale
│   ├── maintenance-request.json    # a flowforge.workflow bundle
│   ├── asset-register.json
│   ├── incident-report.json
│   └── instances.json              # demo instances + relationships
└── README.md
```

```bash
python manage.py load_app northwind          # refuses if it already exists
python manage.py load_app northwind --reset  # replaces
```

`load_app` reuses `import_workflow`, so seeding and client delivery go through
**the same code path**. That's the real win: the demo can't drift from the
export format, because it *is* the export format. A bug in import shows up in
our own demo before a client ever sees it.

### 1.3 What has to be built

| Piece | Detail | Notes |
|---|---|---|
| `load_app` command | Read a directory, import each workflow, apply identity, create instances | Reuses `import_workflow` |
| Instance seeding from data | `instances.json`: metadata, target state (reached by firing real transitions), relationships | Must go through the engine, not direct writes, or the audit trail is a lie |
| Identity application | Apply `app.json` to the `Workspace` singleton | Small; the fields already exist |
| `export_app` (optional here) | The inverse — dump a whole app to a directory | Can wait for [APPS.md](APPS.md) Phase 3 |

**Instances must be created by firing transitions**, not by setting
`current_state` directly. The current seed already does this
(`perform_transition` + `instance_created`/`transition_applied` audit calls),
and it's why the demo has believable timelines. Losing that would gut the
audit-trail story, which is one of the strongest things to show.

### 1.4 Definition of done

- `manage.py load_app northwind` produces a working workspace from files only.
- No Northwind content in any `.py` file.
- Round-trip test: export an imported workflow, re-import, assert equivalence.
- `reset_demo` calls `load_app` so the nightly reset stays one command.

---

## 2. The vertical slice

Three workflows, chosen because they **relate to each other**. One story beats
five disconnected samples.

```
Asset Register  ──parent of──▶  Maintenance Request  ──relates to──▶  Incident Report
   (table)                          (kanban)                            (list)
```

### 2.1 Maintenance Request — the hero

The one a prospect sees first, so it carries the most.

- **Shell:** kanban. Drag-to-transition demos in two seconds with no explanation.
- **States:** Reported → Triaged → Scheduled → In Progress → Complete, plus
  Cancelled.
- **Rules:** priority `P1` blocks Scheduled without a named engineer; a rule
  reason that reads like an instruction, not an error.
- **Form:** on In Progress — completion notes plus a **photo of the finished
  work** (`image` field, which the file-field work now supports).
- **SLA:** 4h on P1, 48h on P3 — so the demo shows amber and red badges
  without waiting.
- **Computed:** `days_open` via `age_days`.
- **`panels_by_role`:** an engineer sees forms and attachments; a manager sees
  the state graph, timeline, and relationships. This is the creator/user split
  doing visible work.

### 2.2 Asset Register — the container

- **Shell:** table.
- **Container:** Maintenance Requests nest under an Asset.
- **Computed:** `open_jobs` (count over children), `total_cost` (sum over
  children of `metadata.cost`), `last_serviced`.
- Demonstrates rollups, which is what makes containers quantitative rather
  than decorative.

### 2.3 Incident Report — the integration story

- **Shell:** list.
- **Relationship:** `arose_from` → Maintenance Request.
- **Action hook:** a `before` hook posting to a mock endpoint on escalation —
  shows the platform reaching outward, with the SSRF guard and secret store
  behind it.
- Keep this one small. Its job is to make the topology view show something
  real and to prove hooks exist.

### 2.4 Branding

`app.json` sets name (Northwind Facilities), logo, palette, en-GB locale,
comfortable density. First impression should be "their system".

---

## 3. Sequence

| Step | Output |
|---|---|
| 1 | `load_app` + content directory format; port the *existing* seed to it as proof |
| 2 | `instances.json` support, transitions fired through the engine |
| 3 | Northwind identity + Maintenance Request |
| 4 | Asset Register + containment + computed rollups |
| 5 | Incident Report + relationship + hook |
| 6 | `panels_by_role` across all three; screenshots for the README |

Step 1 porting the existing seed first is the safety net: if `load_app` can
reproduce today's demo exactly, it's trustworthy for new content.

---

## 4. On artwork — the flat/typographic option

You asked what "design around typography and flat colour" means, since we're
going with a licensed pack. It's worth knowing because the two combine well.

The idea: a scene doesn't need illustration to feel designed. A full-bleed
flat colour field, one large piece of well-set text, and a consistent layout
grid reads as **a deliberate visual style** rather than as missing art —
think the interstitial title cards in a documentary, or Kurzgesagt's flat
vector language.

Concretely, per scene: a solid or two-tone background drawn from the brand
palette, the speaker's name in a heavy weight, dialogue at generous size and
line-height, choices as full-width blocks. No character sprites at all.

Why it works: the failure mode of stock art is *inconsistency* — five
illustrations in four styles looks worse than none. Typography is inherently
consistent, so it degrades gracefully.

**How they combine:** use the licensed pack for backgrounds where a location
genuinely helps (an office, a loading bay), and the flat/typographic treatment
for abstract beats (a decision point, a consequence, a summary). Mixing on
purpose looks intentional; mixing by accident looks unfinished. The rule to
hold: **one visual language per module**, decided up front.

This also removes a blocker — module structure can be built and demoed before
any artwork arrives, then upgraded scene by scene.

---

## 5. Risks

**Porting the existing seed could regress the current demo.** Mitigation: the
round-trip test, plus keeping `seed.py` until `load_app` reproduces it.

**Bundles carry no identity or roles yet** ([APPS.md](APPS.md) Phase 3). For
now `app.json` is a Phase-1-specific file that `load_app` understands; when
the App bundle lands it should absorb it rather than sit alongside it. Worth
being deliberate, or we end up with two formats.

**Custom role names aren't available** ([ROLES.md](ROLES.md)). Northwind's
"Site Manager" is an `approver` with a relabelled UI at best. Phase 1 should
avoid leaning on role names in the script; the creator/user split works with
the existing five.

**Scope creep into Phase 3.** `load_app` is not `import_app`. Resist building
the full App bundle here — Phase 1's job is to stop writing content in Python,
nothing more.
