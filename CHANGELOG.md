# Changelog

All notable changes to FlowForge are documented here. The format loosely
follows [Keep a Changelog](https://keepachangelog.com). From v0.9.0 the
project follows Semantic Versioning — see [docs/VERSIONING.md](docs/VERSIONING.md).

## [Unreleased]

### Fixed
- **There was no Celery app.** `config/celery.py` did not exist, so
  `celery -A config worker` could not start and *nothing* in
  `CELERY_BEAT_SCHEDULE` — SLA checks, webhook retries — had ever run. This
  stayed invisible because every call site falls back to inline execution
  when `.delay()` raises, so webhook delivery and action hooks were running
  synchronously inside the request instead of on a worker. Added the app,
  wired it into `config/__init__.py` so `@shared_task` binds correctly, and
  added `autodiscover_tasks(related_name="hooks")` — without it the worker
  would have rejected `execute_hook_task` as unregistered, since it lives in
  `hooks.py` rather than `tasks.py`. A test now asserts every Beat entry
  points at a task that actually exists.
- **Production object storage was silently disabled.** `production.py` set
  `DEFAULT_FILE_STORAGE` / `STATICFILES_STORAGE`, both removed in Django 5.1,
  so `STORAGES["default"]` still resolved to `FileSystemStorage`: a real
  deployment would have written every uploaded `MediaAsset` to container-local
  disk, lost on redeploy and invisible to other workers. Now configured
  through `STORAGES`.
- **`seed --reset` crashed on nested instances.** `WorkflowInstance.parent`
  is `PROTECT`, so a flat delete raised `ProtectedError` as soon as any
  instance had a child. On the public demo one visitor creating a
  sub-instance would have wedged the nightly reset permanently. Instances are
  now deleted leaves-first.
- Workspace `default_view` now accepts `scene`, matching `VALID_SHELLS`.
- **The E2E suite could never pass on a clean database.** Three `@core`
  scenarios asserted against data `manage.py seed` has never produced: a
  workflow named "Test" that only ever existed by hand on one developer
  machine, a matrix column count that assumed every workflow state is
  occupied (the shell only renders states instances actually sit in), and at
  least one instance relationship — of which the seed created **none**.
  The suite now runs green against a freshly-seeded database (24 scenarios).
  The seed creates eight relationships (`reported_in`, `part_of`), which also
  fills a real demo gap: relationships have their own instance panel, a
  topology view and a README screenshot, but a fresh install showed both as
  empty.

### Fixed
- **`?page_size=` was silently ignored, and the dashboard's charts were
  wrong because of it.** DRF's `PageNumberPagination` only honours the
  parameter when `page_size_query_param` is configured, and it wasn't — so
  the dashboard asked for 200 instances, received the default 25, and
  charted those as though they were the whole set. Any caller asking for
  more was quietly truncated rather than visibly so. Now served by
  `config.pagination.DefaultPagination`, which honours `page_size` and caps
  it at 200 so making it work doesn't hand a caller the whole table.
- **Workflows past the first page were unreachable in the app.** The
  workflows catalogue rendered page 1 with no pagination controls, so with
  more than 25 definitions the rest simply weren't there — and the demo
  company alone plans fifteen on top of the seeded set. The catalogue,
  instances page and dashboard now request the full (capped) list.
- **"View as YAML" produced text that could not be re-imported.** Two
  independent faults in `export_dsl`, both silent: it never emitted the `ui:`
  key (which `parse_dsl` has always read), so a round-trip dropped the shell,
  per-role panels, computed fields and scene config and the workflow came back
  looking unconfigured; and it built its lines with f-strings, so any value
  containing a colon — "A story: told in scenes" — or starting with a YAML
  indicator produced a document that failed to parse. Scalars now go through
  `safe_dump`, so quoting is PyYAML's problem rather than ours, and the
  transition key is quoted as a whole since it embeds two state names. Every
  workflow in a populated database now round-trips exactly.

### Security
- **Demo credentials no longer live in source.** The login page hard-coded
  `admin@flowforge.dev / Admin1234!`, and the help page rendered a table of
  all four accounts including the platform admin — working logins in public
  files, shown to every visitor. Both now read a new public
  `/api/demo-info/` endpoint, which serves accounts only when the deployment
  sets `DEMO_MODE`; configuring accounts is deliberately not sufficient, so a
  stray setting on a real deployment publishes nothing. The accounts
  themselves come from a `DEMO_ACCOUNTS` env var read at deploy time.
  `reset_demo` now re-points the seeded users at those passwords, so a public
  demo never runs the ones `seed.py` publishes. Unconfigured means unchanged,
  so local dev keeps the seed's credentials. The MCP server's `.env.example`
  and README used a real working password as their example; both are now
  placeholders.

### Added
- **Creator/user UI split** (docs/ROLES.md §3) — the same workflow can now
  present a designer's page and an end user's page. `ui_schema.instance_view`
  gains `panels_by_role`, overriding `panels` for a given role; anything not
  listed falls back, so existing workflows are untouched and configuring a
  workflow doesn't become a chore. When a user holds several roles the most
  senior override wins rather than a union — the point is to show *less* to
  lesser roles, so a designer who is also a participant still gets the
  designer's view. A typo'd role key is rejected at validation rather than
  silently never matching, which would read as a broken feature.

  Alongside it, a `useCapabilities` hook puts UI permission checks in one
  place instead of role literals scattered across pages, and creator-only
  affordances are now hidden rather than shown-and-broken — starting with the
  "Workflow settings" link, which took end users to a page they cannot use.
  These checks decide what to *render*; the API still enforces every one
  server-side.
- **`file` / `image` form fields** — a form field can now hold a real
  uploaded file instead of a pasted link. The stored value is a **MediaAsset
  id**, so the reference is durable, access-controlled, and verifiably
  present; the backend checks the asset exists *and* is anchored to this
  instance (or its workflow), closing a hole where a submission could point
  at an attachment on an instance you can't see. Uploading happens inline and
  anchors the file immediately, so a validation error can't lose it. This
  turns "Evidence link" on a test result into an actual attachment.

  Found while wiring it: the two halves had drifted badly. `file`/`image`
  existed in the frontend types and rendered a "paste a file reference" box,
  but the backend didn't know those types at all, so **any string passed
  validation unchecked**. Meanwhile the form editor offered only 6 of the 11
  supported types — `currency`, `toggle`, `datetime`, `image` and `file`
  validated and rendered but could never be *authored*. All three surfaces
  now agree, and the shared upload widget is used by both the instance page
  and the stepped-form shell rather than being implemented twice.
- **Demo deployment code (WS-H)** — `config/settings/demo.py` for the public
  demo: registration disabled (with a message pointing visitors at the seeded
  accounts), DRF anon/user throttles, console email so a notification bug can
  never become outbound spam, an `OUTBOUND_ALLOWED_HOSTS` allow-list on top of
  the existing SSRF guard, tighter upload caps, and no DB SSL against a
  same-network Postgres container. A `reset_demo` management command rebuilds
  the demo nightly via Celery Beat; it reuses `seed --reset` so the demo can't
  drift from local dev, suppresses the seed's credential table (container logs
  are not a secret store), and is guarded by `DEMO_MODE` at both scheduling
  and run time so it can never fire against real data. Plus
  `docker-compose.prod.yml` (only Caddy binds host ports; worker and beat
  share the web image via YAML anchors so they cannot drift) and a Caddyfile.
  See DEPLOYMENT.md §7 for what is and isn't verified — the stack itself has
  not been brought up, since Docker doesn't run on this machine.
- **Computed fields in shells + relationship rollups (WS-C)** — shells now
  render `computed.<key>` columns/card-fields/axes alongside `metadata.<key>`.
  The `TableShell`, `KanbanShell`, and `MatrixShell` all read the shared
  `computedValue` helper in `shells/types.ts`; no per-shell logic is forked.
  The list endpoint gains an opt-in `?include=computed` query param that
  prefetches children and relationship links so rollups don't N+1; the default
  list response is unchanged. Backend: `compute.py` now supports
  `over: "relationships"` (aggregating across `InstanceRelationship` links,
  both directions, with an optional `rel_type` filter); the `ui_schema`
  validator accepts the new `over` value and the optional `rel_type` string;
  `WorkflowViewPage` automatically opts in when the workflow declares
  `ui_schema.computed`. Query-count and integration tests added. (PR #6.)
- **Scene shell / visual-novel player (WS-I)** — `shell: "scene"` turns a
  workflow into a playable branching story with no story-specific machinery in
  the engine: a scene is a state, a choice is a transition, an inventory flag
  is instance metadata, and a locked path is a rule whose `reason` becomes the
  narration the player reads. Instances are save files, so one workflow holds
  many playthroughs. Per-state presentation lives in `ui_schema.scene_config`
  (background, positioned sprites, speaker, dialogue, music), validated
  server-side; backgrounds and sprites accept a MediaAsset id or a URL, and ids
  are fetched as authenticated blobs since asset URLs are private. Dialogue
  supports `{{metadata.key}}` interpolation.
- **`set_metadata` rule action** — a transition can now write values onto the
  instance without an outbound call. Previously the only path to a metadata
  write was an HTTP action hook, so even a purely internal stamp ("record that
  approval happened", "the player now holds the key") needed a network round
  trip. Values merge rather than replace; a `before` hook writing the same key
  still wins, since it reflects external truth; a malformed `values` is skipped
  rather than raised so one bad rule can't make a transition impossible.
- **`manage.py seed_demo_story`** — seeds "The Locked Door", a two-ending
  reference story for the scene shell. Refuses to clobber an existing copy
  without `--reset`, since playthroughs are real instances.
- **Attachments panel (WS-B)** — drag-and-drop / click-to-browse uploads on an
  instance, image thumbnails, download and delete, wired as an `attachments`
  panel in `instance_view`. Thumbnails and downloads fetch through the
  authenticated API as blobs, since asset URLs are private, never public.
  (Contributed via PR #5.)
- **i18n breadth (WS-G)** — French and German catalogues alongside English and
  Spanish, and `t()` threaded through the dashboard, workflows, instances, and
  login pages (page titles, subtitles with interpolation, and the four stat
  cards). Untranslated strings still fall back to en-GB, so partial catalogues
  stay safe. Backend `ui_config.locale` allow-list widened to match.
- **File & image uploads (WS-A)** — `MediaAsset` plus `/api/media/`:
  multipart upload (participant+), list and authenticated download (viewer+),
  delete (uploader or designer+). Security is server-side throughout: the type
  is decided by **magic-byte sniffing** (so a renamed executable is rejected),
  size is capped by `MEDIA_UPLOAD_MAX_BYTES`, **images are re-encoded through
  Pillow** to strip EXIF and defuse polyglot/trailing payloads, storage keys are
  UUID-generated so a crafted filename can never shape the path, and the
  internal `file` path is never serialised — downloads route through the
  authenticated endpoint, never a bucket URL. Local dev writes to disk;
  production swaps `STORAGES["default"]` for R2 with no model change.
  Built TDD against the 38-test spec from PR #3, plus polyglot and
  instance-attachment coverage (40 tests).
- **E2E `@core` coverage (WS-E)** — step definitions for the primary happy
  paths across auth, dashboard, workflows, builder, instances, shells, and
  topology; scenarios needing still-unwritten steps are tagged `@wip`. CI now
  runs `@smoke or (@core and not @wip)` — 24 scenarios, green.
- **CI hardening (WS-F)** — a standalone frontend-build job (tsc -b + vite,
  ~2-minute type gate) and an enforced dependency-vulnerability job
  (pip-audit on backend requirements, npm audit at high+ on the frontend).

### Changed
- **Security dependency bumps** to make the audit gate enforceable: Django
  5.0.6 → 5.2.16 LTS (~20 advisories), DRF 3.16.1, simplejwt 5.5.1
  (PYSEC-2026-1305), cryptography 48.0.1 (secret-store relevant), pytest 9 +
  plugins; unused Pillow removed (MEDIA.md re-adds it when uploads land).
  Migrated the removed STATICFILES_STORAGE setting to STORAGES (silently
  ignored since Django 5.1). Full suite green on the new stack.
- **Computed fields** (docs/METAMODEL.md §2) — derived, read-only values
  defined per workflow in `ui_schema.computed`: rollups over children
  (`sum`/`min`/`max`/`avg`/`count`), `age_days`, and `if` conditionals, reusing
  the rules operator vocabulary. Resolved at read time (never stored, can't
  drift), shown on the instance detail page, and injected into the data the
  rules engine sees — so a rule can gate on a rollup (e.g. block while
  `total_cost > budget`). Makes containers quantitative. 9 tests.
- **Action hooks — `before` (gating) hooks** (docs/HOOKS.md step 4, completing
  the feature). `before` hooks run synchronously ahead of the state change and
  can **block** a transition (on_failure=block) — a health-check gate — while
  warn/ignore proceed. `perform_transition` was restructured: validation +
  before-hooks run pre-transaction (so their network calls don't hold a DB
  transaction open), then an atomic block re-checks the instance's state under
  `select_for_update` and aborts with a clear error if it moved concurrently.
  Successful before-hooks can still write `output_to` metadata. They reuse the
  rules-service circuit breaker so a flapping dependency fast-fails. Full
  suite 227 passed; verified live (a blocking probe kept an instance in place).
- **Action hooks — `after` + outbound safety** (docs/HOOKS.md steps 2–3). A
  `TransitionHook` fires when a transition commits: it calls an external system
  (`http_request` or `probe`), with `{{secret.NAME}}` / `{{metadata.key}}` /
  `{{instance.reference_number}}` templating resolved from the encrypted secret
  store, and can write the response back into instance metadata via `output_to`
  (feeding rules/computed fields). Delivery is async with retries + a
  `HookExecutionLog`, and secret values are redacted from every log. A shared
  `outbound.py` adds an **SSRF guard** (rejects private/loopback/link-local
  hosts, optional allow-list) now applied to webhooks too, plus the templating.
  Managed at `/api/hooks/` (workflow_designer+) with a HooksPanel on the
  workflow detail page. `before` (gating) hooks are the next step. New
  `cryptography` use; migration `notifications.0004`.
- **Secret store** (docs/HOOKS.md Part 1) — encrypted credential storage, the
  prerequisite for action hooks. Values are write-only (the API never returns
  one), encrypted at rest with Fernet under versioned keys (rotatable without
  downtime), and fail closed when no key is configured. `/api/secrets/`
  (workflow_designer+): create, list (names/metadata only), delete, and rotate;
  workflow-scoped secrets override workspace-global ones of the same name. New
  `cryptography` dependency; key via `SECRETS_ENCRYPTION_KEY_V1` env var.
- **Inbound triggers** (meta-model expansion) — the inbound counterpart to
  webhooks: external systems drive FlowForge instead of only being notified.
  A `Trigger` bound to a workflow is addressed by a secret token in its own
  URL (`POST /api/trigger/<token>/`, unauthenticated + throttled); firing it
  either **creates an instance** (payload mapped into metadata) or **fires a
  transition** on an instance found by reference or metadata key — always
  through the engine, so rules/approvals/required-form gating still apply and
  a blocked transition returns its reason. Managed via `/api/triggers/`
  (workflow_designer+) and a TriggersPanel on the workflow detail page that
  surfaces the fire URL. Pairs with the topology view: a triggered state
  change shows up live on the map. See [docs/METAMODEL.md](docs/METAMODEL.md).
- **Topology view** (meta-model expansion) — a cross-instance system map.
  `GET /api/topology/` assembles a graph from existing `InstanceRelationship`
  links and parent containment (rooted BFS with depth/rel-type filters, or the
  whole estate, node-capped). A new `/topology` page renders it with React
  Flow + dagre auto-layout: nodes coloured per workflow, relationship vs.
  containment edges distinguished, PNG export, and a "View topology" action on
  each instance to focus the map. First view that crosses workflow boundaries.
  See [docs/METAMODEL.md](docs/METAMODEL.md).
- **End-to-end test suite** (Playwright + playwright-bdd) — Gherkin
  `.feature` files under `frontend/e2e/features` document every feature's
  intended flow and are executed as tests, so documentation can't drift.
  Nine feature areas specified; the `@smoke` slice (auth, dashboard,
  workflows, instances, builder, shells) is implemented and passing, with
  `@core`/`@full` steps filled in incrementally. Strategy in
  [docs/TESTING.md](docs/TESTING.md).
- **CI e2e job** — boots Postgres/Redis, migrates + seeds, serves the API and
  a production frontend build, and runs the `@smoke` Playwright tag on every
  push; uploads the HTML report/traces on failure.
- **Versioning policy** — SemVer tied to a root `VERSION` file, git tags, and
  the changelog ([docs/VERSIONING.md](docs/VERSIONING.md)). Project set to
  `0.9.0`.

## [0.8.1] — 2026-07-22

### Added
- **i18n scaffolding** (VISION Layer 1 `locale`) — a dependency-free
  translation layer: workspace picks a language in Settings, `useTranslation().t()`
  resolves messages with en-GB fallback and `{placeholder}` interpolation, and
  `<html lang>` tracks the locale for native date/number formatting. Ships
  English (UK) and Spanish catalogues; nav, section headers, and common actions
  are wired as the proof. Adding a language is one catalogue file plus a registry
  line.
- **Stepped-form shell** (VISION Layer 2) — the Typeform/wizard view. Walks a
  single instance through its states as an ordered progress stepper, rendering
  each state's form as one focused card; submitting the form and picking a
  transition advances the instance, with required-form gating and rules still
  enforced by the engine. Completes the shell registry named in the spec.
- **List shell** is now a first-class registry entry (was a redirect), so every
  shell — list included — is configurable through the same ui_schema.
- **Workspace Language and Density pickers** in Settings (density was added in
  0.8.0 but had no UI control).

### Fixed
- **Saving instance metadata was broken in the browser** since optimistic
  locking shipped (0.6.0): `If-Match` is not a CORS-safelisted request header,
  so the PATCH triggered a preflight that django-cors-headers rejected — the
  request never reached Django and the UI showed "Failed to save metadata".
  Added `if-match` to `CORS_ALLOW_HEADERS`, with a regression test asserting
  the preflight advertises it. Found by the new @core E2E coverage.
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
