# UI Shells — the Layer 2/3 extension point

A **shell** is how a workflow's instances are presented: list, kanban board,
table, or calendar. Shells are pure presentation components behind a fixed
contract, which is what makes Layer 3 (exported standalone apps) possible —
an exported app bakes in this registry and renders whichever shell the
bundled `ui_schema` names, with zero code generation.

## The contract

Every shell implements `ShellProps`
([frontend/src/components/shells/types.ts](../frontend/src/components/shells/types.ts)):

```ts
interface ShellProps {
  workflow: Workflow;              // definition incl. states, transitions, ui_schema
  instances: WorkflowInstance[];   // instances of this workflow
  fireTransition: (instance, transition) => void;  // the ONLY write path
  transitionPending: boolean;
}
```

Rules of the contract:

1. **Shells never mutate state directly.** All writes go through
   `fireTransition`, so the engine's rules, approval gating, and required
   forms apply identically in every shell. A drag on the kanban board and a
   button on the instance page hit the same endpoint.
2. **Shells read presentation config from `workflow.ui_schema`** — never from
   their own storage. This keeps the config portable (it travels in export
   bundles) and editable from one place (the Presentation panel).
3. **Data fetching lives in the host page** (`WorkflowViewPage`), not the
   shell. Shells are renderable anywhere the contract is satisfied — the
   platform today, an embedded widget or exported app tomorrow.

## Adding a shell

1. Create `frontend/src/components/shells/YourShell.tsx` implementing `ShellProps`.
2. Register it in [`shells/index.ts`](../frontend/src/components/shells/index.ts):
   add to `SHELL_REGISTRY` and `SHELL_OPTIONS`.
3. Add the shell name to `VALID_SHELLS` in
   [`backend/apps/workflows/ui_schema.py`](../backend/apps/workflows/ui_schema.py)
   (single source of truth — the API endpoint and bundle import both validate
   through it).
4. If the shell needs config, document the `ui_schema` key here and add a
   field to `PresentationPanel.tsx`.

## ui_schema reference

| Key | Type | Used by | Meaning |
|---|---|---|---|
| `shell` | `"list" \| "kanban" \| "table" \| "calendar"` | router | Which shell renders this workflow |
| `title_field` | string | all | Metadata key used as card/row/chip title |
| `card_fields` | string[] | kanban | Metadata keys shown on cards |
| `list_columns` | string[] | table | Columns: `reference`, `state`, `sla`, `status`, `created`, or `metadata.<key>` |
| `date_field` | string | calendar | `created_at` or a metadata key holding a date |
| `state_display` | `{[stateName]: {colour}}` | all | Per-state colour (kanban column tops, state badges, calendar chips) |

`ui_schema` is validated server-side (`validate_ui_schema`) on both the
`PATCH /api/workflows/{id}/ui-schema/` endpoint and workflow bundle import,
and is included in every exported `.flowforge.json` bundle.

## Layer 3 path

The deliberate boundaries above are what the remaining Layer 3 work builds on:

- **Embedded widget**: mount `WorkflowViewPage` (or a shell directly) in an
  iframe/web component; the contract already isolates it from the app chrome.
- **Exported standalone app**: bundle = engine config, ui_schema = presentation,
  workspace = branding. An export runtime ships the same shell registry and
  reads all three — no per-app code generation required.
