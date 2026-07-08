# UX & Usability Roadmap

The engine and presentation layers are built (see [VISION.md](VISION.md), [SHELLS.md](SHELLS.md)).
This document designs the next frontier: making FlowForge understandable to
non-technical users and expressive enough to model nested products like
TestRail or Jira. Three major workstreams, plus a backlog of smaller
improvements, with a suggested build order at the end.

---

## 1. Plain-language configuration

**Problem.** The configurable surfaces speak engine jargon. A workflow
designer who is not a developer meets: operators (`gt`, `is_true`),
"transitions", "terminal states", "SLA hours", "metadata keys",
"required_to_transition", HMAC signing secrets. Every one of these is
learnable, but nothing in the UI teaches them at the moment of need.

**Existing assets.** The rule builder already renders a live condition
preview (`IF claim_value gt 10000 ...`); the Help page has an operator
reference and FAQ. Both are foundations to build on: the preview needs to
become fully natural-language, and the help needs to come to the user
instead of living on a separate page.

### 1a. Natural-language previews everywhere

Every configuration form gets a live sentence that restates the config in
plain English, updated as the user types:

| Surface | Preview sentence |
|---|---|
| Rule builder | "**If** claim value **is greater than** 10,000, **block** 'Approve Standard' and show: 'Claims over £10,000 require Director approval.'" |
| Transition editor | "Anyone with the **Approver** role can move an instance from **Under Review** to **Approved**." |
| SLA config | "Instances should leave **Under Review** within **48 hours**. After 36 hours they show a warning; after 48 they are flagged overdue, logged, and subscribers are notified." |
| Form editor | "Before an instance can leave **In Progress**, someone must complete the **Test Results** form (3 fields, 2 required)." |
| Webhook form | "Every time a **comment is added** on any **Test Run**, POST a signed message to hooks.example.com." |

Implementation: a `describe*()` helper per config type in
`frontend/src/lib/describe.ts`, rendered in an accented callout under each
form. Pure functions over existing state — no backend changes. These same
helpers later feed i18n (section 2) since sentences are assembled from
translatable fragments.

### 1b. Term hints (glossary-on-hover)

A tiny `<Term k="terminal_state">terminal</Term>` component wraps jargon
wherever it appears and shows a two-sentence explanation on hover/tap, with
a "learn more" link into the relevant Help page section. One glossary file
(`frontend/src/lib/glossary.ts`) keyed by term id — which is also the
translation catalogue key. Candidate first batch: state, transition,
terminal state, initial state, rule, operator, metadata, SLA, approval,
shell, bundle, webhook, signing secret.

### 1c. Contextual help drawer

A `?` button in the page header opens a right-hand drawer with help for
*that page* (not a separate route): what this page does, the three most
common tasks, and links to the walkthrough. Content is markdown files per
page so contributions do not require touching components. The existing
HelpPage remains as the full manual; the drawer excerpts it.

### 1d. Example-first empty states

Every empty state should offer a working example, not a blank form: "No
rules yet — **add the classic escalation rule** (block approvals over a
threshold)" pre-fills the builder. Empty workflow list offers the seed
workflows as one-click imports (they already exist as bundles via Layer 3
export). This converts the seed command from a CLI step into product.

**Effort:** 1a+1b ~1 week combined; 1c ~3 days; 1d ~2 days. No migrations.

---

## 2. Translations (internationalisation)

**Scope decision that matters most:** translate the *product chrome*, not
*user content*. Workflow names, state names, comments, and metadata are the
customer's data — they stay as authored. (Per-locale `display_name` maps on
states/transitions are a possible later step for multi-lingual teams, noted
below, but not the first release.)

### Frontend (the bulk of the work)

- **Library:** `react-i18next` with JSON catalogues per locale
  (`frontend/src/locales/{en-GB,...}/common.json`).
- **Extraction is the long pole.** Every hardcoded string in ~20 pages and
  ~15 components moves to `t("...")` keys. Mechanical but wide: budget it
  honestly (2–3 weeks) and do it page-by-page behind no flag — English
  catalogue first, so each page keeps working as it converts.
- **Locale selection:** workspace-level default in `ui_config.locale`
  (Layer 1 already owns formatting config — date_format lives there), with
  an optional per-user override later. `formatDate`/`formatDateTime` in
  `useWorkspace.ts` already centralise date rendering and simply gain
  locale awareness.
- **Glossary + describe helpers (section 1) are catalogue-first** — build
  them with keys from day one so plain-language and i18n are one system,
  not two.

### Backend

- API error messages and permission denials (`require_min_role` messages,
  validation errors) wrapped in Django's `gettext_lazy`, activated per
  request from `Accept-Language`. Small surface (~40 strings), low risk.
- Notification templates are user content (customers author them) — no
  translation, but the *default* seeded templates ship per-locale.

### Pilot

Ship with `en-GB` (source) plus one pilot language to prove the pipeline
end-to-end. Suggest `es` or `fr` for coverage of grammar/pluralisation
differences. Pseudo-locale (`en-XA` accented text) in dev catches
unextracted strings.

**Effort:** ~3–4 weeks total, dominated by string extraction.

---

## 3. Instance containers — instances within instances

**Problem.** Real products are hierarchies. Building TestRail or Jira from
scratch needs a *container* concept:

| Product | Hierarchy |
|---|---|
| TestRail | Project → Test Plan → **Test Run → results** |
| Jira | Project → Epic → **Story → Sub-task** |
| Service desk | Major incident → linked tickets |
| Onboarding | New-starter case → per-department checklists |

FlowForge today has typed relationships (`part_of`, `blocks`, ...) which
*express* hierarchy but do not *enforce or present* it: nothing prevents
cycles or double-parenting, there is no tree query, no roll-up, and the UI
shows a flat link table rather than "this instance houses these".

### 3a. Data model: promote parenthood to first class

Add to `WorkflowInstance`:

```python
parent = models.ForeignKey("self", null=True, blank=True,
                           on_delete=models.PROTECT, related_name="children")
child_order = models.PositiveIntegerField(default=0)
```

Why a first-class FK instead of reusing `InstanceRelationship`:

- **Invariants**: exactly one parent, no cycles (validated on save/move),
  protected deletes. Relationship rows can't guarantee any of this.
- **Cheap tree queries**: `children.count()`, roll-up aggregates, breadcrumbs.
- **Keeps relationships for what they're good at**: cross-cutting links
  (`blocks`, `duplicate_of`, `reported_in`) between instances in *different*
  trees. Both primitives coexist; they answer different questions
  ("what does this contain?" vs "what does this touch?").

Migration is additive; existing `part_of` relationship data can be
back-filled into `parent` by a management command where unambiguous.

### 3b. Configuration: which workflows nest where

`ui_schema` gains a `children` block (validated centrally in
`ui_schema.py`, edited in the Presentation panel, travels in bundles):

```json
{
  "shell": "list",
  "children": {
    "workflows": ["Test Run"],
    "shell": "table",
    "columns": ["reference", "state", "metadata.suite", "sla"],
    "roll_up": true
  }
}
```

- `workflows`: which definitions may be created *inside* this one (empty =
  no children allowed; the panel offers the active definitions).
- `shell` + config: **how children render on the parent — this reuses
  SHELL_REGISTRY wholesale.** A Test Plan houses its Test Runs as a sortable
  table; an Epic houses Stories as a kanban. The "clean sleek UI for each
  variation" is the shell system pointed at a child list instead of a
  workflow list — no new rendering machinery.
- `roll_up`: show aggregate progress on the parent.

### 3c. Engine integration

- **Creation**: `POST /api/instances/ {workflow_definition, parent}` —
  validated against the parent's `children.workflows` allow-list.
- **Roll-up rule condition**: new operator `children_complete` usable in
  rules — "block 'Close Plan' unless all children are in a terminal state".
  This is what makes hierarchy *behave* (can't ship a Release while Test
  Runs are open) rather than just display.
- **API**: `GET /instances/{id}/children/` (ordered), `PATCH .../move/`
  (re-parent with cycle check), children counts embedded on detail.
- **Audit**: `child_added` / `child_moved` events through the existing
  pipeline (timeline, webhooks, notifications all inherit them for free).

### 3d. Presentation

- **Instance detail** gains a Children panel: the configured child shell,
  a "+ New <child workflow>" button per allowed type, and a roll-up header
  ("7 of 9 complete", progress bar, worst-SLA indicator).
- **Breadcrumbs** climb the tree: `REL-2026-00002 / TRN-2026-00004`.
- **Instances table** gets an optional expand-chevron for parents and an
  "only top-level" filter default, so trees don't flatten into noise.
- **Kanban cards** for parents show a compact `▣ 7/9` children chip.

### Worked example: TestRail from scratch

1. Import the Test Run bundle; create a "Test Plan" workflow
   (Draft → Active → Completed).
2. On Test Plan's Presentation panel: children = Test Run, shell = table,
   columns = reference, state, suite, fail_count; roll-up on.
3. Add rule: block "Complete Plan" unless `children_complete`.
4. A QA lead opens the plan, sees runs as a table with pass/fail colours,
   adds runs in place, and cannot close the plan with runs still open.

No code was written by the user — which is the platform's whole thesis.

**Effort:** ~3 weeks (model + engine ~1, UI ~1.5, polish/tests ~0.5).
Ships before i18n if hierarchy is the more urgent demo.

---

## 4. Smaller high-leverage UX backlog

| Improvement | Why | Effort |
|---|---|---|
| Global search / command palette (Ctrl+K) | The `/instances/search/` endpoint exists; jump to any instance/workflow/page from anywhere | 3–4 days |
| In-app notification centre | NotificationLog already records everything; a bell + unread list makes it visible without email | 4–5 days |
| First-run onboarding checklist | "Create a workflow → add a rule → run an instance" with live progress; replaces reading the README | 3 days |
| Optimistic updates + undo toast | Transitions/comments feel instant; undo where the engine allows | 4 days |
| Keyboard accessibility for kanban | Drag-and-drop needs a keyboard path (select card → move menu); plus ARIA on the board | 3 days |
| Saved views per user | Persist filters/sort/shell choices; "My overdue approvals" as a landing view | 1 week |
| Responsive pass | Tables and boards on tablet width; sidebar collapse exists but pages overflow | 1 week |
| Theme contrast checks | Validate custom themes meet WCAG AA contrast, warn in the editor | 2 days |

---

## 5. Suggested build order

1. **Instance containers (3)** — biggest capability unlock; makes the
   TestRail/Jira story real and demos brilliantly.
2. **Plain-language configuration (1)** — cheap, wide impact, and
   prerequisite thinking (keyed glossary/describe helpers) feeds i18n.
3. **Command palette + notification centre (4)** — daily-use quality of
   life, both mostly frontend over existing APIs.
4. **Translations (2)** — largest mechanical effort; schedule when the
   string surface has stabilised after 1–3 land.
5. Remaining backlog items opportunistically alongside.

Each stage is independently shippable and none blocks Layer 3.
