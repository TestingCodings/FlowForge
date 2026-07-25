# Meta-model Expansion: Hooks, Computed Fields, Parallel States, Topology

A design doc for the four capabilities that most widen the class of
applications FlowForge can express, drawn from the strategy discussion in
[VISION.md](VISION.md). Each is independent and ships on its own; they are
ordered here by dependency, not priority.

FlowForge can generate any application expressible in its meta-model —
`{states, transitions, rules, forms, shells, relationships, containers}`.
Everything below **widens that meta-model**: after these land, the platform
can express integrations, derived data, concurrent work, and cross-system
maps that it cannot today.

Status: planning. Nothing here is built.

---

## 0. First, what "topology" means (vs. the state diagram)

These render the same-looking boxes-and-arrows but answer completely
different questions, on different axes:

| | State diagram (built today) | Topology view (proposed) |
|---|---|---|
| **Shows** | One workflow *definition* | Many workflow *instances* |
| **Nodes are** | States (Draft, Review, Done) | Real assets (this VM, that device) |
| **Edges are** | Transitions (Submit, Approve) | Relationships between instances |
| **Answers** | "What shape can one thing's life take?" | "How are all these actual things wired together right now?" |
| **Scope** | A single workflow | Across every workflow |
| **Data source** | `State` + `Transition` rows | `InstanceRelationship` + `parent` rows |

The state diagram is the **blueprint** — every Bug Report follows
`New → In Progress → Fixed`. It's a template; all instances share it.

The topology view is the **live map** — "Azure-VM-07 *hosts* Test-Host-3,
which *is used by* Test-Run-2026-00042 and *contains* Device-A, Device-B."
The nodes are specific instances from different workflows; the edges are the
typed relationships and containment links that already exist in the data but
are currently only shown as a flat list on each instance's detail page.

So topology is not a new kind of diagram engine — it's a new *view over data
we already store*. That's why it's the cheapest of the four and the one that
directly serves the "VM → test host → labs → devices" picture.

---

## 1. Action Hooks (transition side-effects)

**What it unlocks:** integrations. Today a transition can *block* (rules) and
*notify* (webhooks fire-and-forget on events). It cannot *do* anything with a
result — call an external API, run a check, and let the outcome influence the
transition. Hooks turn FlowForge from a system that records that work
happened into one that can make work happen.

**Model.** A new `TransitionHook` attached to a transition:

```json
{
  "trigger": "before | after",
  "action": "http_request | script | probe",
  "config": { "url": "...", "method": "POST", "body_template": "...", "timeout": 5 },
  "on_failure": "block | warn | ignore",
  "output_to": "metadata.<key>"
}
```

- **`before` hooks** run inside the transition, before the state changes. A
  `block` failure aborts the transition (like a rule) — this is how a health
  check gates a promotion.
- **`after` hooks** run once the state has changed — provisioning calls,
  downstream notifications with delivery tracking.
- **`output_to`** writes the response back into `metadata_json`, so a hook's
  result feeds rules and computed fields on the next step.

**Where it plugs in.** `apps/workflows/engine.py::perform_transition` already
evaluates rules and collects `actions`; hooks run in the same pipeline, reusing
the async-webhook infrastructure (Celery task, retries, delivery log,
circuit breaker) built in 0.6.0. `before` hooks run synchronously with a hard
timeout; `after` hooks queue.

**The hard parts (and why this is a deliberate build, not a quick add):**
- **Secrets.** Hooks need credentials; `metadata_json` is plaintext. Requires
  a `Secret` store (encrypted at rest, referenced by name, never returned by
  the API) before any real integration is safe. This is the gating dependency.
- **SSRF.** User-defined URLs fired server-side — reuse the allow-list guard
  already specified for the demo ([DEPLOYMENT.md](DEPLOYMENT.md) §2.2).
- **Sandboxing** `script` actions — defer; ship `http_request` and `probe`
  first, which cover most needs.

**Effort:** 3–4 weeks incl. the secret store. Ship `http_request` + `probe`
first; `script` later behind a sandbox. **Full design:** [HOOKS.md](HOOKS.md).

---

## 2. Computed Fields (derived metadata)

**What it unlocks:** data that stays correct without manual entry — rollups,
formulas, and derived status. Today every metadata value is typed by a human
or written by a form; nothing is *derived*.

**Model.** A `computed` block on `ui_schema` (or a first-class list), each
entry a named expression over the instance's own metadata, its children, and
its relationships:

```json
{
  "computed": {
    "total_cost": { "expr": "sum", "over": "children", "field": "metadata.cost" },
    "days_open":  { "expr": "age_days", "from": "created_at" },
    "risk":       { "expr": "if", "cond": {"field": "value", "op": "gt", "value": 10000},
                    "then": "high", "else": "normal" }
  }
}
```

Reuse the existing rules vocabulary (`field`/`op`/`value`, the `children_*`
facts) so the expression language is one users already know from the rule
builder — no second DSL.

**Where it plugs in.** Computed values are resolved at read time in the
instance serializer and merged into the metadata the rules engine sees
(`_hierarchy_facts` in `rules.py` already injects `children_*` facts the same
way — this generalises that mechanism). Because they're derived, they're
read-only and never stored, so they can't drift.

**Design decisions:**
- **Read-time vs. materialised.** Start read-time (simple, always correct).
  Materialise later only if a hot path needs it.
- **No cycles.** A computed field may not reference another computed field in
  v1 — keeps evaluation a single pass; revisit with a dependency sort if
  needed.
- **Children/relationship rollups** are the highest-value case (they make the
  container feature quantitative: "total cost of all sub-tasks"), so prioritise
  `sum`/`count`/`min`/`max` over `children`.

**Effort:** 2 weeks for self + children rollups; +1 week for relationship
rollups and conditionals.

---

## 3. Parallel States (concurrent work)

**What it unlocks:** processes where several things happen at once — the
single biggest expressiveness gap versus real BPM engines. Today an instance
has exactly one `current_state` (`engine.py` sets `instance.current_state`);
it cannot be "in Legal Review AND Security Review simultaneously."

**Model.** A state may be a **parallel gateway** that forks into named
branches, each an independent sub-track, rejoined at a **synchronising join**:

```yaml
states:
  - name: Reviews            # parallel gateway
    parallel:
      branches: [legal, security, finance]
      join: all              # all | any | n_of_m
  - name: Approved
transitions:
  - Reviews -> Approved: Complete    # fires only when the join condition is met
```

Each branch tracks its own progress; the join gates the outgoing transition
(this is the `children_complete` gating pattern generalised from containers to
in-instance branches).

**Where it plugs in — and why it's the heaviest:**
- `WorkflowInstance.current_state` (a single FK) becomes insufficient. Either
  a new `InstanceBranchState` table (one row per active branch) with
  `current_state` demoted to a computed "primary" pointer, or model branches
  as auto-managed child instances (reuses containment + `children_complete`,
  but muddies the hierarchy). **Recommendation: `InstanceBranchState`** — it
  keeps parallelism a first-class engine concept rather than overloading
  containers.
- The engine's "one transition from current_state" assumption
  (`perform_transition`, `evaluate_for_transition`) must become per-branch.
- Every shell renders `current_state`; they need a fallback for
  multi-state instances (show the set, or the gateway name).
- Audit, SLA, and the state diagram all assume linearity.

Because it touches the engine's core invariant, this is the one to design
most carefully and ship last. An **80/20 option**: model the common case
("wait for N approvals in parallel") purely with computed fields + a rule
(`approvals_received >= 3`) and skip true forking. That covers many real
needs without the engine surgery — worth validating demand before the full
build.

**Effort:** 4–6 weeks for true parallelism; ~1 week for the computed-field
approximation.

---

## 4. Topology View (cross-instance system map)

**What it unlocks:** the "house the connection between systems" use case —
render the graph of real assets and their links as a diagram, not a per-
instance list. A CMDB / asset-map on top of data FlowForge already stores.

**Model.** No new storage — it's a view over existing `InstanceRelationship`
(directional, typed: `from_instance --rel_type--> to_instance`) and `parent`
containment rows.

- **New endpoint** `GET /api/topology/?root=<instance>&depth=<n>&rel_types=[...]`
  returns the sub-graph reachable from a root instance: nodes (instances,
  with workflow, state, title) + edges (relationship type or "contains").
- **New page** `/topology` (and a "View topology" action on an instance):
  render with React Flow (already a dependency), nodes coloured by workflow /
  `state_display`, edges labelled by `rel_type`. Reuse `dagre` auto-layout and
  the `html-to-image` PNG export already built for the builder.
- **Filters:** by workflow, by relationship type, by depth, so a 500-asset
  estate stays legible.

**Worked example (the one from the discussion):**
```
Azure-VM-07  ──hosts──▶  Test-Host-3  ──contains──▶  Device-A
   (Infrastructure)         (Hosts)         │            (Devices)
                                            └──contains──▶  Device-B
Test-Run-42  ──runs-on──▶  Test-Host-3
   (Test Run)
```
Each node is a real instance from a different workflow; each edge already
exists as a relationship/containment row. The topology view just draws it.

**Design decisions:**
- **Read-only first.** v1 visualises; editing links stays on the instance
  page. Drawing edges *on the topology canvas* is a fast follow.
- **Cross-workflow by nature** — this is the first view that ignores workflow
  boundaries, so it belongs at the top nav level, not under a workflow.
- **Performance:** bound by `depth` and node cap; paginate/cluster beyond ~200
  nodes.

**Effort:** 1–1.5 weeks. Cheapest of the four, no new storage, no engine
change, reuses React Flow + dagre + PNG export.

---

## 5. Inbound Triggers (the world → FlowForge)

**What it unlocks:** letting external systems *drive* FlowForge, not just be
notified by it. Every integration primitive is one cell of a
direction × timing matrix, and today only one is filled:

| | Synchronous (gates the transition) | Asynchronous (fire and continue) |
|---|---|---|
| **Outbound** (FlowForge → world) | Action hooks `before` (§1) | **Webhooks** ✅ built |
| **Inbound** (world → FlowForge) | Callbacks (deferred) | **Inbound triggers** ← this |

Webhooks made FlowForge *tell* other systems what happened. Inbound triggers
let other systems tell FlowForge what happened: a CI pipeline finishing marks
a Test Run passed; a monitoring alert opens an Incident; a git push creates a
Release. It turns FlowForge from a place people *record* status into a system
that *reflects reality automatically* — and it pairs directly with the
topology view, where a triggered state change lights up on the live map.

**Model.** A `Trigger` bound to a workflow, addressed by a secret token in its
own URL (the token is the credential, like a webhook-receiver URL):

```json
{
  "name": "CI marks run passed",
  "workflow_definition": "<id>",
  "action": "create_instance | fire_transition",
  "transition": "<id>",            // for fire_transition
  "lookup_field": "reference_number | metadata.<key>",   // how to find the instance
  "metadata_mapping": { "build": "build_number", "suite": "suite" },
  "is_active": true
}
```

- **`create_instance`** — the POST payload creates a new instance of the bound
  workflow; `metadata_mapping` maps payload fields into `metadata_json`.
- **`fire_transition`** — finds an existing instance via `lookup_field` +
  payload and fires the named transition **through the engine**, so rules,
  approvals, and required-form gating apply exactly as for a human. A blocked
  transition returns the reason.

**Endpoint.** `POST /api/trigger/<token>/` — unauthenticated (the token is the
credential), throttled, with a distinct path from the authenticated
management CRUD at `/api/triggers/`. Every fire is audited (actor = the
trigger) and bumps `last_triggered_at` / `trigger_count` for observability.

**Why this is the cheapest high-reach primitive.** It's the transition/create
API you already have, wrapped in a scoped token and a payload mapping. No
secret store needed (unlike outbound hooks — the token is inbound), no engine
change (unlike parallel states). It is the single largest increase in what
*real processes* FlowForge can automate, per unit of work.

**Security.** Long random token in the URL, regeneratable; per-trigger scope
(one workflow, one action); DRF throttling; inactive triggers 404. No
credentials stored (the caller holds the token).

## Recommended sequence

| Order | Capability | Why | Effort |
|-------|-----------|-----|--------|
| 1 | **Topology view** | Cheapest; no schema/engine change; serves the system-map use case immediately | 1–1.5 wk |
| 2 | **Computed fields** | Makes containers quantitative; reuses the rule vocabulary; unblocks parallel-state approximation | 2–3 wk |
| 3 | **Action hooks** | Highest capability gain (integrations), but gated on a secret store; the "housed connection" becomes live here | 3–4 wk |
| 4 | **Parallel states** | Biggest expressiveness gain but touches the engine's core invariant — design last; validate demand for true forking vs. the computed-field approximation | 1 wk (approx) / 4–6 wk (full) |

Topology + computed fields (≈4 weeks) deliver the asset-map-with-rollups that
directly answers the systems-connection question, without touching the engine.
Hooks and true parallelism are larger, security- and architecture-weighted
builds to schedule deliberately.
