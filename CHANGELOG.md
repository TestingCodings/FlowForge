# Changelog

All notable changes to FlowForge are documented here. The format loosely
follows [Keep a Changelog](https://keepachangelog.com); versions are
retrospective milestones rather than published packages.

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
