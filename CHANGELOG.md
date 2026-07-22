# Changelog

All notable changes to FlowForge are documented here. The format loosely
follows [Keep a Changelog](https://keepachangelog.com); versions are
retrospective milestones rather than published packages.

## [0.8.1] — 2026-07-22

### Added
- **i18n scaffolding** (VISION Layer 1 `locale`) — a dependency-free
  translation layer: workspace picks a language in Settings, `useTranslation().t()`
  resolves messages with en-GB fallback and `{placeholder}` interpolation, and
  `<html lang>` tracks the locale for native date/number formatting. Ships
  English (UK) and Spanish catalogues; nav, section headers, and common actions
  are wired as the proof. Adding a language is one catalogue file plus a registry
  line.
- **Workspace Language and Density pickers** in Settings (density was added in
  0.8.0 but had no UI control).

### Fixed
- Builder transitions could appear to leave a node's **left** edge: the visible
  right-hand source handle had no id, so an edge with an undefined source handle
  attached ambiguously; every handle now has an explicit id and forward/backward
  edges reference them directly. A companion effect-dependency fix normalises a
  newly-created backward edge immediately instead of on the next node move.

## [0.8.0] — 2026-07-21 · Layer 1 & 2 completion, relicensing

### Changed
- **Relicensed to Business Source License 1.1** (source-available). Free for
  evaluation, personal, educational, research, and internal business use
  including production; a commercial licence is required only to offer
  FlowForge as a competing hosted service or product. Converts to Apache 2.0
  on 2030-07-21. Versions through `633def5` remain MIT.

### Added
- **Matrix shell** (VISION Layer 2) — the TestRail-style cross-product view.
  Instances are laid out as rows × columns via `ui_schema.matrix`
  (`{rows, columns}`, each `current_state` / `parent` / `metadata.<key>`),
  cells coloured by state, transitions fired from a cell detail dialog.
  State-grouped columns follow the workflow's own state order.
- **Kanban swimlanes** — `ui_schema.swimlanes` adds a second grouping level
  (e.g. `metadata.epic`); drag-to-transition works across lanes.
- **`instance_view` config** — a workflow can now choose its detail-page
  title field and which panels appear in what order
  (`{title_field, panels[], layout}`).
- **`state_display.icon`** — the icon vocabulary from the spec
  (`circle`/`play`/`check`/`x`/…) renders in kanban columns and matrix cells,
  mapped to unicode so no icon font is needed and glyphs survive PNG export.
- **Workspace `default_view`** — a workspace-level fallback shell for
  workflows that never chose one.
- **Workspace `density`** — "comfortable" (default) or "compact", driving
  shared spacing tokens so every page condenses together.

### Fixed
- SLA webhook test asserted against `NotificationLog`, which stopped
  receiving webhook rows when delivery moved to `WebhookDeliveryLog` in
  0.6.0 — the assertion now targets the correct model. Full backend suite
  green at 178 tests.

## [0.7.1] — 2026-07-20

### Fixed
- Back-edge routing in both graph renderers: return transitions (e.g.
  *Reopen*) now arc cleanly below the graph instead of sweeping around the
  canvas; arrowheads are fixed-size and sit centred on their lines
- Builder toolbar: buttons no longer collapse into unstyled fragments on
  narrow widths (a tooltip class was shrinking them); bar wraps as coherent
  groups with single-line labels

### Added
- **Export workflow as PNG** from both the builder canvas (auto-fitted, 2×)
  and the detail-page state diagram — combined with the YAML editor this
  makes FlowForge usable as a text-to-diagram tool

## [0.7.0] — 2026-07-19 → 2026-07-20 · Builder overhaul & YAML authoring

### Added
- **Visual builder phases B1–B4** ([docs/BUILDER.md](docs/BUILDER.md)):
  - B1: atomic saves (transaction-wrapped nested create), localStorage
    draft autosave with resume banner, 50-step undo/redo (Ctrl+Z/Y)
  - B2: **edit existing workflows** on the canvas — diff-based
    `PUT /workflows/{id}/compose/` preserves attached forms and rules on
    untouched entities; workflows with instances get a one-click
    "publish new version with these changes" flow; canvas positions persist
    (`State.canvas_position`)
  - B3: dagre auto-layout, Ctrl+D duplicate, arrow-key nudge, snap-to-grid
  - B4: live lint panel (unreachable states, dead ends, terminal-state
    issues), rule editing on transitions, form editing on states — the
    builder now authors the entire workflow
- **YAML DSL** for text-first authoring (`apps/workflows/dsl.py`):
  `A -> B: Name` shorthand, inline rules and forms, line-numbered errors
  with did-you-mean hints; split-pane editor at `/workflows/new/text` with
  live server-validated preview; **View as YAML** round-trip export on every
  workflow — definitions are now git-diffable and scriptable
- Deployment plan for a public demo at flowforge.cortexa.solutions
  ([docs/DEPLOYMENT.md](docs/DEPLOYMENT.md))

## [0.6.0] — 2026-07-18 → 2026-07-19 · Production hardening (Tier 1)

### Added
- **Async webhook delivery** via Celery with exponential-backoff retries,
  delivery logs, dead-letter status, and admin replay
- **Optimistic locking** on instance metadata (`If-Match` / 409 with current
  server state) so concurrent edits can't silently overwrite each other
- **Form schema versioning**: forms with submissions become immutable —
  edits create v+1; submissions record the schema version they answered
- **SLA checking moved to Celery Beat** (every minute) with retry on
  transient DB errors, replacing the cron management command
- **Rules-service circuit breaker** (CLOSED→OPEN→HALF_OPEN) plus request
  timeouts; rule evaluation degrades to local execution, never blocks
  transitions
- Enhancement roadmap of 22 items across 4 tiers
  ([docs/ENHANCEMENT.md](docs/ENHANCEMENT.md))

## [0.5.0] — 2026-07-14 · Instance containers

### Added
- Sub-instances: single-parent hierarchy with cycle protection, ordered
  children API, breadcrumbs, roll-up progress, `children_complete` rule
  operator for gating parent transitions, per-workflow child-type allow-lists
- API reference documentation

## [0.4.0] — 2026-07-05 → 2026-07-08 · White-labelling & shells (VISION Layers 1–2)

### Added
- **Layer 1 — theming**: 15 design tokens, four presets (Midnight, Daylight,
  Ocean, Forest), font and date-format configuration, server-validated
  `ui_config`
- **Layer 2 — shells**: fixed `ShellProps` contract + registry rendering any
  workflow as **kanban, table, or calendar**; visual presentation
  configurator (columns, card fields, per-state colours); shells documented
  as the extension point ([docs/SHELLS.md](docs/SHELLS.md))
- **Layer 3 foundation**: portable workflow bundles
  (`.flowforge.json`, name-based references) with export/import

## [0.3.0] — 2026-07-02 → 2026-07-04 · Forms, webhooks, bulk operations

### Added
- Per-state form schemas: required forms gate transitions in the engine;
  submissions merge into instance metadata for rule evaluation; visual
  form editor
- Webhooks with HMAC-SHA256 signatures and event filters; `comment_added`
  and `rule_blocked` events; scheduled SLA-breach detection
- Bulk operations: multi-select transitions and CSV export
- MIT licence, CI fixes, README overhaul

## [0.2.0] — 2026-06-21 → 2026-06-22 · Visual tooling & governance

### Added
- Visual workflow builder (React Flow drag-and-drop canvas)
- Embedded rule builder; BFS-laid-out state graph with audit-accurate
  progress colouring; comments
- Dark-theme UI overhaul; dashboard analytics (recharts); seed workflows
  incl. a TestRail-style set; demo user switcher
- API-layer role enforcement; SLA breach indicators; workflow versioning
  (publish-new-version deep clone); typed instance relationships

## [0.1.0] — 2026-06-16 · Core platform

### Added
- Workflow engine: definitions, states, transitions, guarded by a rules
  engine; JWT auth; immutable audit log
- Forms, tasks, notifications apps; FastAPI rules microservice
- React + TypeScript frontend; Django REST Framework backend; Celery/Redis
  infrastructure; Docker Compose stack
