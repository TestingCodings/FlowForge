# Workflow Builder: Improvement Plan & Alternative Authoring Modes

Status: planning document (July 2026). Covers the visual builder at
`/workflows/new` ([WorkflowBuilderPage.tsx](../frontend/src/pages/WorkflowBuilderPage.tsx))
and proposes a second, non-visual authoring path.

---

## Part 1 — Current State Assessment

The builder is a single 580-line page: React Flow canvas, custom `StateNode`,
inline top bar for workflow metadata, a connection-confirm dialog, and client-side
validation before a single POST-per-entity save sequence.

What works well:
- Drag-to-connect with a named-transition confirmation step
- Initial/terminal/SLA flags editable per node
- Client-side validation catches the basics (no name, no initial state)

Known gaps (ordered by user pain):

| # | Gap | Impact |
|---|-----|--------|
| G1 | No editing of existing workflows — builder is create-only; edits happen in WorkflowDetailPage forms | Two disjoint mental models for the same object |
| G2 | No auto-layout — nodes land where you drop them; big graphs become spaghetti | Demos look bad, real use is worse |
| G3 | No undo/redo | One mis-delete loses work |
| G4 | Save is N sequential POSTs (workflow, then each state, then each transition) — a mid-sequence failure leaves a half-created workflow | Data integrity |
| G5 | No draft persistence — refresh loses everything | Work loss |
| G6 | Rules, forms, and task config are not authorable in the builder; they require visiting the detail page after creation | Fragmented authoring |
| G7 | No validation preview — unreachable states / dead ends only surface at runtime | Silent logic bugs |
| G8 | No keyboard support (delete key, copy/paste nodes, arrow nudging) | Power-user friction |

---

## Part 2 — Visual Builder Improvement Plan

### Phase B1: Integrity & safety (1 week) — do first

1. **Atomic save.** New endpoint `POST /api/workflows/compose/` accepting the
   full graph `{workflow, states[], transitions[]}` in one transaction.
   The builder already assembles this shape client-side; the backend wraps it
   in `transaction.atomic()`. Kills G4, and is a prerequisite for edit mode
   (diffing against an existing graph needs a single round trip).
2. **Draft persistence.** Serialize `{nodes, edges, meta}` to localStorage on
   every change (debounced 1s), keyed by route. Offer "Resume draft?" on
   return. Kills G5 with ~30 lines.
3. **Undo/redo.** Keep a bounded history stack (50 snapshots) of
   `{nodes, edges}`; Ctrl+Z / Ctrl+Shift+Z. React Flow state is already
   serializable, so snapshots are cheap. Kills G3.

### Phase B2: Edit mode (1–2 weeks) — highest value

4. **Load an existing workflow into the canvas.** Route
   `/workflows/:id/edit`; hydrate nodes/edges from the API (positions stored
   in a new `State.canvas_position` JSON field, falling back to auto-layout).
   Save computes a diff (created / updated / deleted states and transitions)
   and sends it to the compose endpoint. Respect the versioning rule: if the
   workflow has instances, offer "Save as new version" (existing deep-clone
   publish flow) instead of in-place edit. Kills G1 and unifies authoring.

### Phase B3: Layout & ergonomics (1 week)

5. **Auto-layout button** using `dagre` (tiny, battle-tested with React Flow):
   left-to-right rank layout from initial state. Also run it automatically
   when hydrating a workflow that has no stored positions. Kills G2.
6. **Keyboard support:** Delete removes selection (with confirm for nodes that
   have transitions), Ctrl+D duplicates a node, arrows nudge 8px. Kills G8.
7. **Minimap toggle + snap-to-grid** (React Flow built-ins, config only).

### Phase B4: Deep authoring (2–3 weeks)

8. **Inline rule editor on transitions.** Selecting an edge opens the side
   panel with the existing rule-builder component (already built for
   WorkflowDetailPage — reuse, not rebuild). Rules ride along in the compose
   payload. Kills half of G6.
9. **Form attachment on states.** Same pattern: state side panel gets a
   "Forms" tab reusing the per-state form editor.
10. **Live linting panel** (see also ENHANCEMENT.md 4.3). Client-side graph
    checks, re-run on every change, rendered as dismissible warnings:
    - states unreachable from the initial state
    - non-terminal states with no outgoing transitions (dead ends)
    - terminal states with outgoing transitions
    - transition names duplicated between the same state pair
    - SLA on terminal states (meaningless)
    Kills G7 and doubles as the backend lint rule spec.

### Explicitly out of scope for the builder
Swimlanes, sub-workflow composition, and collaborative cursors — revisit after
Layer 3 ships.

---

## Part 3 — Alternative Authoring Mode: Text-First (YAML)

A second way to build workflows, aimed at (a) power users who think faster in
text, (b) reviewable/diffable workflow definitions in git, and (c) LLM- or
script-generated workflows.

### Why YAML and not a wizard?
A step-by-step wizard was considered and rejected: it duplicates the builder's
job with less power. Text-first is *complementary* — it serves users the canvas
doesn't (automation, review, bulk edits) and it reuses the portability layer
that already exists (`apps/workflows/portability.py` bundles are already JSON
with name-based references — the hard problem is solved).

### Format (maps 1:1 onto the existing bundle schema)

```yaml
workflow: Expense Approval
prefix: EXP
description: Simple expense approval with escalation

states:
  - name: Submitted        # first state is initial by default
    sla_hours: 24
  - name: Manager Review
    sla_hours: 48
    form:                  # optional per-state form
      fields:
        - {key: amount, type: number, label: Amount, required: true}
  - name: Approved
    terminal: true
  - name: Rejected
    terminal: true

transitions:
  - Submitted -> Manager Review: Submit
  - Manager Review -> Approved:
      name: Approve
      requires_approval: true
      rules:
        - if: {field: amount, op: gt, value: 5000}
          then: {block_transition: true, message: Needs director approval}
  - Manager Review -> Rejected: Reject
```

The `A -> B: Name` shorthand covers the common case; the expanded mapping form
carries approval flags, rules, and metadata.

### Implementation (2–3 weeks total)

1. **Parser + validator** (backend, ~1 week). `apps/workflows/dsl.py`:
   YAML → bundle dict → existing bundle import validation. Errors must carry
   line numbers ("line 14: transition references unknown state 'Aproved' —
   did you mean 'Approved'?"). No new import machinery — it feeds the
   portability importer.
2. **Endpoint** `POST /api/workflows/compose-yaml/` returning either the
   created workflow or a structured error list. Also a `?dry_run=true` mode
   returning the parsed graph + lint results without saving.
3. **Frontend split-pane page** (~1 week). `/workflows/new/text`: CodeMirror
   YAML editor on the left, read-only React Flow preview on the right,
   re-rendered from dry-run responses (debounced 500ms). Lint/parse errors
   inline in the gutter. "Create" button posts for real.
4. **Round-tripping.** "View as YAML" action on any workflow (export bundle →
   YAML) so users can eyeball, copy, or bulk-edit an existing definition and
   re-import as a new version. This also becomes the canonical seed-data
   format and makes workflow definitions PR-reviewable.

### Sequencing note
The YAML mode and builder Phase B1 share the compose endpoint work — build
B1 first, then the DSL parser targets the same code path.

---

## Part 4 — Recommended Order

| Order | Item | Effort | Rationale |
|-------|------|--------|-----------|
| 1 | B1 atomic save + drafts + undo | 1 wk | Integrity first; unblocks everything |
| 2 | B2 edit mode | 1–2 wk | Biggest gap; unifies authoring |
| 3 | B3 layout & keyboard | 1 wk | Cheap polish, big demo value |
| 4 | YAML mode (parser → endpoint → split-pane) | 2–3 wk | Differentiator; reuses B1 |
| 5 | B4 deep authoring + linting | 2–3 wk | Completes "one place to author" |

Total: ~7–10 weeks. Interleaves cleanly with ENHANCEMENT.md Tier 2 (backend
pagination/indexing work doesn't touch these files).
