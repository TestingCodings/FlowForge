# FlowForge API Reference

Base URL: `http://localhost:8000/api/` (local dev). All endpoints return JSON. List endpoints are paginated (`{count, next, previous, results}`).

## Authentication

Every endpoint except register, login, refresh, and health requires a JWT access token:

```
Authorization: Bearer <access_token>
```

| Method | Path | Description |
|---|---|---|
| POST | `/auth/register/` | Create an account. Body: `email, first_name, last_name, password, password_confirm` |
| POST | `/auth/login/` | Returns `{access, refresh, user}` |
| POST | `/auth/refresh/` | Body `{refresh}` → new access token |
| GET | `/auth/me/` | Current user profile including `roles` |
| GET | `/health/` | Unauthenticated liveness check |

Tokens are short-lived; the frontend stores them as `ff_access_token` / `ff_refresh_token` and refreshes automatically.

## Roles

Five roles form a hierarchy; each level includes everything below it:

`viewer < participant < approver < workflow_designer < platform_admin`

Role requirements are listed per endpoint below. A denied request returns `403` with a message naming the required role and your current roles. Enforcement lives in `apps/accounts/permissions.py`.

## Users (platform_admin unless noted)

| Method | Path | Description |
|---|---|---|
| GET | `/users/` | List users (any authenticated) |
| POST | `/users/demo-switch/` | Body `{user_id}` → JWT pair for that user (demo feature) |
| POST | `/users/{id}/roles/` | Body `{roles: [...]}` — replace a user's roles |

## Workspace (Layer 1 theming)

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/workspace/` | viewer | Singleton branding config: `name, tagline, logo_url, ui_config` |
| PUT | `/workspace/` | platform_admin | Update any of those fields. `ui_config` supports `theme` (colour token map), `font`, `date_format` — validated server-side |

## Workflows

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/workflows/` | viewer | List definitions with nested `states`, `transitions`, `rules` |
| POST | `/workflows/` | workflow_designer | Create with inline `states` and `transitions` (name-referenced). Exactly one state must have `is_initial: true` |
| GET | `/workflows/{id}/` | viewer | Full definition |
| PUT/PATCH | `/workflows/{id}/` | workflow_designer | Update definition fields |
| DELETE | `/workflows/{id}/` | workflow_designer | Delete (blocked if instances exist) |
| POST | `/workflows/{id}/publish-new-version/` | workflow_designer | Stamps `published_at`, deep-clones states/transitions/rules as a v+1 draft linked via `parent` |
| GET | `/workflows/{id}/version-history/` | viewer | Whole version chain |
| PATCH | `/workflows/{id}/ui-schema/` | workflow_designer | Set presentation config (see below) |
| GET | `/workflows/{id}/export/` | viewer | Download a portable `.flowforge.json` bundle |
| POST | `/workflows/import/` | workflow_designer | Recreate a workflow from a bundle. Body: the bundle, or `{bundle, name}` to import under a new name |

### ui_schema

Validated by `apps/workflows/ui_schema.py`. Keys:

```jsonc
{
  "shell": "kanban",              // list | kanban | table | calendar
  "title_field": "title",         // metadata key used as card/row title
  "card_fields": ["priority"],    // kanban card lines
  "list_columns": ["reference", "state", "metadata.priority"],  // table shell
  "date_field": "due_date",       // calendar source: created_at or metadata key
  "state_display": {"Done": {"colour": "#22c55e"}},
  "children": {                    // containment (sub-instances)
    "workflows": ["Test Run"],    // definitions allowed to nest inside this one
    "shell": "table",
    "columns": ["reference", "state"],
    "roll_up": true                // show completion bar on the parent
  }
}
```

## States / Transitions / Rules

Standard CRUD at `/states/`, `/transitions/`, `/rules/`. Reads need viewer; writes need workflow_designer. Rules attach to a workflow and optionally a specific transition:

```json
{
  "workflow_definition": "<id>",
  "transition": "<id or null = all transitions>",
  "condition": {"field": "claim_value", "operator": "gt", "value": 10000},
  "action": {"type": "block_transition", "reason": "Needs director approval"},
  "priority": 1
}
```

Operators: `gt gte lt lte eq ne contains starts_with is_true is_false`. Actions: `block_transition`, `assign_role`. Rules evaluate against instance `metadata_json` **plus injected hierarchy facts**: `children_total`, `children_open`, `children_complete` — so a rule can hold a parent in place until every child completes.

## Instances

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/instances/` | viewer | Filters: `?workflow_definition=`, `?current_state=`, `?parent=`, `?parent__isnull=true` |
| POST | `/instances/` | participant | Body `{workflow_definition, parent?, metadata_json?}`. With `parent`, the parent workflow's `ui_schema.children.workflows` allow-list is enforced |
| GET | `/instances/{id}/` | viewer | Detail — embeds `sla`, `relationships`, `current_form`, `children_stats` |
| POST | `/instances/{id}/transition/` | participant / approver* | Body `{transition_id}`. *approver when the transition has `requires_approval` |
| POST | `/instances/bulk-transition/` | participant / approver* | Body `{instance_ids: [...max 100], transition_id}` → per-instance results (`ok / blocked / error`) |
| GET | `/instances/export/` | viewer | CSV download. Filters: `?ids=a,b,c` or `?workflow_definition=`. Metadata keys become columns |
| POST | `/instances/{id}/comment/` | viewer | Body `{body}` — appended to the audit timeline |
| PATCH | `/instances/{id}/metadata/` | participant | Body `{metadata_json: {...}}` — full replace, audited with before/after |
| GET | `/instances/{id}/children/` | viewer | Ordered sub-instances |
| PATCH | `/instances/{id}/move/` | participant | Body `{parent: <id or null>}` — re-parent or detach; allow-list and cycle checks apply |
| GET | `/instances/search/?q=` | viewer | Quick search by reference or workflow name (min 2 chars, max 20 results) |
| POST | `/instances/{id}/link/` | participant | Body `{to_instance: <id or reference>, rel_type, notes?}` — typed relationship |
| DELETE | `/instances/{id}/link/{rel_id}/` | participant | Remove a relationship |

Transitions are refused with `400` and a human-readable `detail` when: a rule blocks them, the current state has an unsubmitted required form, or the transition doesn't start from the instance's current state.

## Forms

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/forms/?workflow_definition=&state=` | viewer | Form definitions |
| POST/PUT/DELETE | `/forms/…` | workflow_designer | Manage definitions. Delete returns `400` if submissions exist — publish a new workflow version instead |
| POST | `/submissions/` | participant | Body `{form_definition, workflow_instance, data}` — validated against the schema; values merge into instance `metadata_json` |

Form schema: `{"fields": [{"key", "label", "type": "text|textarea|number|checkbox|dropdown|date", "required", "options?"}], "required_to_transition": bool}`.

## Tasks

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/tasks/` | viewer | Tasks for states the instance has entered |
| POST | `/tasks/{id}/complete/` | participant | Mark complete |

## Audit

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/audit/{instance_id}/` | viewer | Timeline for one instance (create, transitions, rules fired, comments, metadata edits, relationships, SLA breaches, child added/moved) |
| GET | `/audit/` | platform_admin | Global audit log |

Audit rows are immutable — saving an existing row raises.

## Notifications and Webhooks

| Method | Path | Role | Description |
|---|---|---|---|
| GET/POST/PUT/DELETE | `/notification-templates/` | platform_admin | Per-event templates (email / slack / webhook channels), Django template syntax |
| GET | `/notification-logs/` | platform_admin | Delivery log. Filters: `workflow_instance, event_trigger, status, channel` |
| GET/POST/PATCH/DELETE | `/webhooks/` | workflow_designer | HTTP subscriptions: `{workflow_definition (null = all), url, events: [] (empty = all), secret?, is_active}` |

Webhook deliveries POST the payload with headers `X-FlowForge-Event` and, when a secret is set, `X-FlowForge-Signature: sha256=<HMAC-SHA256 of raw body>`.

Events: `instance_created, state_transition, comment_added, rule_blocked, form_submitted, sla_breached, task_created, task_completed`.

Payload shape:

```json
{
  "event": "state_transition",
  "timestamp": "2026-07-13T10:00:00Z",
  "instance": {"id", "reference_number", "workflow", "current_state", "completed"},
  "data": {"from_state": "Draft", "to_state": "Review", "...": "event-specific"}
}
```

## Scheduled commands (not HTTP)

| Command | Purpose |
|---|---|
| `python manage.py check_slas` | Finds open instances past their state's `sla_hours`, writes one immutable `sla_breached` audit entry per state entry, and notifies subscribers. Idempotent — safe on any cron cadence |
| `python manage.py seed [--reset] [--testrail]` | Demo data; prints credentials to the terminal only |
