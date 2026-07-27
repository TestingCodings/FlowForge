# Parallel Development Plan (for concurrent agents / Copilot)

A set of **independent, low-conflict workstreams** that can be picked up
concurrently to speed development. Each names the files it owns, the contracts
it must not break, and its acceptance criteria. Hand one workstream to one
agent; they should not overlap in the files they edit.

## Workstream board (claim before starting!)

**Check this table AND open PRs before picking up a workstream.** Claim by
PR-ing a one-line status change here (or commenting on an issue). Two agents
building the same workstream wastes both runs — this happened with WS-F
(Copilot PR #2 duplicated work already merged on main; its
permissions-hardening idea was adopted, the rest closed as duplicate).

| WS | Status | Owner |
|----|--------|-------|
| WS-A media backend | ✅ done (TDD from PR #3's spec) | Copilot (tests) + Claude (impl) |
| WS-B media frontend | ✅ done (PR #5, issue #4) | Copilot |
| WS-C computed-in-shells | **done** (PR #7) | Copilot |
| WS-D parallel states | hold (engine-exclusive) | — |
| WS-E E2E @core | ✅ done (161a0d9) | Claude |
| WS-F CI hardening | ✅ done (3a98ede + perms hardening) | Claude |
| WS-G i18n breadth | ✅ done (ae2ad5e) | Claude |
| WS-H demo deployment | **code done** (VPS steps pending) | Claude |
| WS-I scene shell | **done** | Claude |
| WS-J scene authoring UI | in progress (issue #8) | Copilot |
| WS-K app content as data | in progress | Claude |

## How to use this
- **One agent per workstream.** Branch per workstream (`feat/<id>-<slug>`),
  PR into `main`.
- **Respect the shared contracts** listed below — those are the files many
  features touch, so changing them causes conflicts.
- **Always run `cd frontend && npm run build`** (this is `tsc -b`, what CI
  runs) and `cd backend && pytest` before pushing. Bare `tsc --noEmit` does
  NOT catch the strict errors CI does.
- Every workstream: add tests, update `CHANGELOG.md` under `[Unreleased]`, and
  the relevant design doc's status line.

## Shared contracts (change carefully; coordinate)
These are the hot files. If a workstream must touch one, flag it so others
rebase:
- `backend/apps/workflows/engine.py` — the transition pipeline. **WS-D
  (parallel states) owns this exclusively; no other workstream may edit it.**
- `backend/apps/workflows/ui_schema.py` — the `ui_schema` validator. Several
  workstreams add a block here; keep additions append-only (own validator
  function per block) to minimise conflicts.
- `backend/apps/instances/serializers.py` — the instance serializer. Add
  fields append-only.
- `frontend/src/types/api.ts` — shared types. Append interfaces; don't reorder.
- `frontend/src/components/shells/index.ts` — the shell registry.

---

## WS-A · File & image uploads (backend)
**Design:** [MEDIA.md](MEDIA.md) Part 1. **Depends on:** nothing.
**Owns:** new `backend/apps/media/` (app label to avoid stdlib clash),
`config/settings/base.py` (storage config, append-only), `config/urls.py`
(one router line).
**Do:** `MediaAsset` model; `multipart` upload endpoint with server-side
type/size allow-list (magic-byte sniff), generated storage keys, auth'd
download; Pillow re-encode to strip EXIF; `django-storages` swap documented
for R2. **Acceptance:** upload/list/download/delete with role checks; oversize
and wrong-type rejected; tests green; secret/private by default.

## WS-B · File uploads (frontend) + attachments panel
**Depends on:** WS-A's API shape (coordinate on the response contract first).
**Owns:** `frontend/src/components/AttachmentsPanel.tsx`, an `image`/`file`
form-field type in the form renderer, `types/api.ts` (append `MediaAsset`).
**Acceptance:** drag-drop upload on an instance, thumbnails inline, delete;
`npm run build` clean.

## WS-C · Computed fields in shells + relationship rollups
**Design:** [METAMODEL.md](METAMODEL.md) §2 (extends shipped work).
**Owns:** `backend/apps/workflows/compute.py` (add `over: "relationships"`),
`frontend/src/components/shells/*` (render `computed.<key>` in table columns,
kanban card fields, matrix cells). **Contract:** shells already read
`metadata.<key>`; add a parallel `computed.<key>` resolver in the shared shell
helpers (`shells/types.ts`) — don't fork each shell. **Acceptance:** a table
column `computed.total_cost` renders; relationship rollup tested.

## WS-D · Parallel states (engine) — ISOLATED, serialize this one
**Design:** [METAMODEL.md](METAMODEL.md) §3. **Owns exclusively:**
`engine.py`, a new `InstanceBranchState` model + migration, and the shells'
multi-state fallback. **Warning:** this is the only workstream allowed to
touch `engine.py`; run it when no other engine-adjacent work is in flight.
Start with the **computed-field approximation** (a rule on an
`approvals_received` count) to validate demand before the full fork/join.
**Acceptance:** a workflow with an all-join gateway advances only when all
branches complete; concurrency tests.

## WS-E · E2E `@core` coverage (test-only, zero prod conflict)
**Owns:** `frontend/e2e/steps/*.steps.ts`, `frontend/playwright.config.ts`
(widen `E2E_TAGS`). The `.feature` files already exist. **Do:** implement the
`@core` step definitions for auth, workflows, builder, instances, forms,
shells, workspace, yaml-authoring, topology; flip CI's `E2E_TAGS` to
`@smoke or @core`. **Acceptance:** `@core` green locally against the running
stack; CI job updated.

## WS-F · CI hardening (infra-only)
**Owns:** `.github/workflows/ci.yml` only. **Do:** add a **standalone
frontend job** running `npm ci && npm run build` (catches the `tsc -b` errors
fast, without the e2e servers); add `pip-audit` (backend) and `npm audit
--audit-level=high` (frontend) steps; cache tuning. **Acceptance:** new jobs
pass on `main`; a deliberately-broken TS type fails the frontend job.

## WS-G · i18n breadth
**Design:** [LAYERS.md](LAYERS.md) L1.2 (extends shipped scaffolding).
**Owns:** `frontend/src/i18n/locales/*` (new catalogues, e.g. `fr-FR`,
`de-DE`), and threading `t()` through more components (instance page, builder
toolbar). **Contract:** add keys to `en-GB.ts` first (the source of truth),
then translations. Backend: add locales to the `ui_config.locale` allow-list
(`accounts/views.py`, append-only). **Acceptance:** switching to a new locale
translates the newly-wired surfaces; fallback intact.

## WS-H · Demo deployment code
**Design:** [DEPLOYMENT.md](DEPLOYMENT.md). **Owns:** new
`config/settings/demo.py`, a `reset_demo` management command + Beat schedule,
`docker-compose.prod.yml` + Caddyfile, `OUTBOUND_ALLOWED_HOSTS` demo config.
**Acceptance:** `reset_demo` reseeds idempotently; demo settings disable
registration and set throttles; compose file documented (not run in CI).

**Repo code done.** demo.py, reset_demo (+ Beat entry, DEMO_MODE-guarded),
docker-compose.prod.yml, Caddyfile. Building it uncovered three latent bugs
that had nothing to do with the demo: there was no Celery app at all, so
Beat had never run and hooks were executing inline; production's S3 config
used settings Django 5.1 removed, so uploads would have gone to local disk;
and `seed --reset` crashed on nested instances. All fixed. Remaining work is
on the VPS (provision, DNS, first `docker compose up`) — see DEPLOYMENT.md §7
for the explicit unverified list.

## WS-I · Scene shell / visual-novel (after WS-A/B)
**Design:** [MEDIA.md](MEDIA.md) Part 2. **Depends on:** WS-A/B (media).
**Owns:** `frontend/src/components/shells/SceneShell.tsx` + registry line,
`scene_config` validation in `ui_schema.py` (own validator fn), a per-state
scene editor in the builder. **Acceptance:** a workflow with backgrounds +
dialogue + choice-gated transitions plays as a visual novel; a two-ending
demo workflow seeds.

**Done.** Shipped the shell, `scene_config` validation, and
`manage.py seed_demo_story`. Building it surfaced a gap: a transition could
only write metadata via an outbound HTTP hook, so an inventory flag needed a
network call. Added a `set_metadata` rule action (`apps/workflows/engine.py`)
— useful well beyond games. The per-state scene *editor* in the builder is
still outstanding.

---

## Suggested first wave (max parallelism, min conflict)
Run these four together — they touch disjoint areas:
- **WS-E** (E2E, test-only) · **WS-F** (CI, infra-only) · **WS-A** (media
  backend, new app) · **WS-G** (i18n, mostly new files).

Then **WS-B** (needs A), **WS-C** (shells), **WS-H** (deploy). Hold **WS-D**
(engine) to run alone. **WS-I** last (needs media).

## MCP note
The MCP server (`mcp-server/`) is a thin adapter over the REST API — as new
endpoints land (media, etc.), add matching tools there. It doesn't conflict
with any workstream above.
