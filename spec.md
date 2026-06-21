# FlowForge — Project Specification (v2)

> **Living document.** This spec reflects the full intended scope of FlowForge as a production-grade, portfolio-quality workflow automation platform. Each section maps directly to a development phase.

---

## Overview

**FlowForge** is a configurable business workflow automation platform that enables organisations to design, deploy, and manage multi-step approval and operational processes without writing code. The platform acts as a lightweight business operating system: the same engine powers an insurance claims process, an HR onboarding flow, a software bug lifecycle, or any other sequential approval chain.

### Positioning

| Comparable Product | What FlowForge borrows |
|--------------------|------------------------|
| Jira | Task/ticket lifecycle management |
| ServiceNow | Enterprise process orchestration |
| Zapier | Trigger-based automation |
| Monday.com | Visual workflow configuration |
| Power Automate | Rule-driven conditional routing |

FlowForge is not a clone of any of these. It is a focused, developer-owned platform that demonstrates the same engineering depth while remaining genuinely configurable.

---

## Goals

### Primary Goal
Demonstrate production-grade software engineering skills relevant to a backend/full-stack Python role, specifically targeting:

- State machine design
- REST API development
- Rule-driven automation
- Audit and compliance systems
- Cloud-native deployment

### Secondary Goal
Produce a real, reusable product that serves as a foundation for freelance work or a SaaS offering — and as a living portfolio piece that can be quickly re-skinned or extended for any employer or client demo.

---

## Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Backend framework | Django 5 + Django REST Framework | Batteries-included, industry standard for Python backends |
| Rule microservice | FastAPI | Demonstrates SOA; async-native; auto-generates OpenAPI docs |
| Database | PostgreSQL 16 | Production-grade relational DB; JSONB support for flexible schema storage |
| Frontend | React 18 + TypeScript | Modern SPA; type safety demonstrates engineering rigour |
| Containerisation | Docker + Docker Compose | Reproducible environments; production parity in development |
| Task queue | Celery + Redis | Async notification dispatch; scheduled SLA checks |
| Authentication | JWT (djangorestframework-simplejwt) | Stateless auth suitable for SPA + API consumption |
| CI/CD | GitHub Actions | Automated testing and deployment on every push |
| Cloud deployment | AWS (ECS, RDS, ALB, ECR, ElastiCache) | Industry-standard cloud; demonstrates production deployment |
| Testing | Pytest + Playwright | Unit/integration tests + end-to-end browser tests |
| Email (dev) | Mailhog | Local SMTP trap; no real emails sent during development |
| Email (prod) | SendGrid | Reliable transactional email; environment-switchable |

---

## Core Components

### 1. Workflow Engine

A **database-driven state machine**. Each workflow is defined as an ordered set of states and the valid transitions between them.

**Concepts:**

- **Workflow Definition** — a named, versioned template (e.g., "New Insurance Claim", "Employee Onboarding"). Multiple versions can exist; only one is `is_active` at a time.
- **State** — a named step within a workflow (e.g., Draft, Submitted, Under Review, Approved, Rejected, Completed). States have a `position_order` for display, and `is_initial` / `is_terminal` flags.
- **Transition** — a permitted move from one state to another. May require approval (`requires_approval=True`), may be gated by rules, and may carry a display label.
- **Workflow Instance** — a live execution of a workflow definition, tracking current state and full history. Each instance has an auto-generated `reference_number`.

**State Machine Rules:**
- An instance may only advance via a transition that explicitly connects the current state to a target state.
- An instance cannot leave a terminal state.
- An instance cannot be in multiple states simultaneously.
- Every state change is atomic and logged to the audit trail before the HTTP response is returned.

**Example — Insurance Claim:**
```
New Claim → Under Review → Approved → Paid Out
                        ↘ Rejected
```

**Example — Employee Onboarding:**
```
New Employee → Manager Approval → IT Setup → Payroll Setup → Completed
```

**Example — Bug Report:**
```
Bug Report → QA Review → Developer Review → Ready for Deploy → Deployed
                                          ↘ Won't Fix
```

The same engine handles all three. Configuration, not code, determines behaviour.

**Reference Number Format:**
`{PREFIX}-{YEAR}-{SEQUENCE:05d}` e.g. `CLM-2026-00042`. The prefix is configured per workflow definition. Sequence resets per workflow per year.

---

### 2. Rule Engine

A configurable condition evaluator that gates transitions and routes submissions automatically.

**Architecture:** The rule engine runs as a separate **FastAPI microservice** (`rules-service/`). The Django backend calls it via HTTP during transition evaluation. This decoupling demonstrates service-oriented architecture and allows the rule engine to be scaled or swapped independently.

**Supported Condition Operators:**

| Operator | Description | Example |
|----------|-------------|---------|
| `gt` | Greater than | `claim_value > 5000` |
| `gte` | Greater than or equal | `claim_value >= 1000` |
| `lt` | Less than | `priority < 3` |
| `lte` | Less than or equal | — |
| `eq` | Equal | `category == "Liability"` |
| `neq` | Not equal | `status != "draft"` |
| `contains` | String contains | `description contains "urgent"` |
| `starts_with` | String starts with | `reference starts_with "CLM"` |
| `is_true` | Boolean true | `is_verified is_true` |
| `is_false` | Boolean false | — |

**Compound Conditions:**
```json
{
  "operator": "and",
  "conditions": [
    {"field": "claim_value", "operator": "gt", "value": 1000},
    {"field": "category", "operator": "eq", "value": "Liability"}
  ]
}
```
Both `and` and `or` are supported. Conditions can be nested to arbitrary depth.

**Supported Actions:**

| Action Type | Description |
|-------------|-------------|
| `assign_role` | Route the resulting task to a named role |
| `assign_user` | Assign the task to a specific user by ID |
| `block_transition` | Prevent the transition and return a reason |
| `notify` | Trigger a notification on a named channel |
| `set_metadata` | Write a computed value into instance metadata |

**Rule Evaluation Order:** Rules fire in ascending `priority` order (1 = highest). First matching rule wins per action type, unless rules are explicitly marked `continue_on_match=True`.

**Example rules:**
```
IF claim_value > 10000 → assign to CFO role
IF claim_value > 5000  → assign to Director role
IF claim_value > 1000  → assign to Manager role
(default)              → assign to handler role
```

---

### 3. Form Builder

Users construct data-capture forms that are attached to workflow states. When a workflow enters a state, the assigned form is presented to the responsible party. Form data drives rule evaluation.

**Supported Field Types:**

| Type | Notes |
|------|-------|
| `text` | Single-line string input |
| `textarea` | Multi-line string input |
| `number` | Integer or decimal; supports `min`, `max` |
| `currency` | Decimal with currency symbol display |
| `date` | ISO 8601 date |
| `datetime` | ISO 8601 datetime |
| `dropdown` | Static list or dynamic lookup from an API endpoint |
| `checkbox` | Boolean toggle |
| `file` | File upload (stored on S3 in production, local volume in dev) |
| `hidden` | System-populated; not shown to the user |

**Form Schema (JSONB):**
```json
{
  "fields": [
    {
      "name": "claim_value",
      "label": "Claim Value (£)",
      "type": "currency",
      "required": true,
      "validation": {"min": 0, "max": 1000000}
    },
    {
      "name": "category",
      "label": "Claim Category",
      "type": "dropdown",
      "options": ["Property", "Liability", "Health", "Vehicle"],
      "required": true
    },
    {
      "name": "supporting_doc",
      "label": "Supporting Document",
      "type": "file",
      "required": false,
      "accepted_types": ["application/pdf", "image/jpeg", "image/png"]
    },
    {
      "name": "description",
      "label": "Description",
      "type": "textarea",
      "required": true,
      "conditional": {
        "show_if": {"field": "category", "operator": "eq", "value": "Liability"}
      }
    }
  ]
}
```

**Form Behaviour:**
- Required/optional per field.
- Conditional visibility: show field B only if field A matches a condition (evaluated client-side and re-validated server-side).
- Server-side validation: type coercion, required checks, range constraints.
- Submissions are versioned and **immutable** once stored. No `PATCH` or `DELETE` on submissions.
- A form submission is linked to a specific `WorkflowInstance` and `FormDefinition` version.

**Form Versioning:**
When a `FormDefinition` is updated after submissions exist, a new version is created rather than modifying in place. Existing submissions retain their original schema version.

---

### 4. REST API Layer

The primary interface for all platform operations, built with **Django REST Framework**.

A separate **FastAPI** microservice exposes the rule evaluation engine.

#### Django REST Framework Endpoints

**Authentication**

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/auth/register/` | Create a user account | Public |
| `POST` | `/api/auth/login/` | Obtain access + refresh tokens | Public |
| `POST` | `/api/auth/refresh/` | Refresh an access token | Public |
| `GET` | `/api/health/` | Health check | Public |

**Workflows**

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/workflows/` | Create a workflow definition | Admin/Designer |
| `GET` | `/api/workflows/` | List workflow definitions | Authenticated |
| `GET` | `/api/workflows/{id}/` | Retrieve a workflow definition (full graph) | Authenticated |
| `PATCH` | `/api/workflows/{id}/` | Update a workflow definition | Admin/Designer |
| `POST` | `/api/workflows/{id}/activate/` | Mark a version as active | Admin |
| `GET` | `/api/workflows/{id}/states/` | List states for a workflow | Authenticated |
| `POST` | `/api/workflows/{id}/states/` | Add a state | Admin/Designer |
| `GET` | `/api/workflows/{id}/transitions/` | List valid transitions | Authenticated |
| `POST` | `/api/workflows/{id}/transitions/` | Add a transition | Admin/Designer |

**Instances**

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/instances/` | Start a workflow instance | Authenticated |
| `GET` | `/api/instances/` | List instances (filtered to user's scope) | Authenticated |
| `GET` | `/api/instances/{id}/` | Get instance state, metadata, and history | Authenticated |
| `POST` | `/api/instances/{id}/transition/` | Request a state transition | Authenticated |
| `PATCH` | `/api/instances/{id}/metadata/` | Update instance metadata | Authenticated |

**Tasks**

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/api/tasks/` | List tasks assigned to the current user | Authenticated |
| `GET` | `/api/tasks/{id}/` | Retrieve a specific task | Authenticated |
| `POST` | `/api/tasks/{id}/complete/` | Mark a task complete | Assignee only |
| `POST` | `/api/tasks/{id}/reassign/` | Reassign a task | Admin/Manager |

**Forms & Submissions**

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/forms/` | Create a form definition | Admin/Designer |
| `GET` | `/api/forms/{id}/` | Retrieve a form definition and schema | Authenticated |
| `POST` | `/api/submissions/` | Submit a form response | Authenticated |
| `GET` | `/api/submissions/{id}/` | Retrieve a submission | Authenticated |

**Audit**

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/api/audit/` | Paginated list of all audit events | Admin only |
| `GET` | `/api/audit/{instance_id}/` | Full audit trail for an instance | Authenticated |

**Notifications**

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/api/notifications/logs/` | List notification log entries | Admin only |
| `POST` | `/api/notifications/templates/` | Create a notification template | Admin |
| `GET` | `/api/notifications/templates/` | List notification templates | Admin |

**Rules (Django proxy + management)**

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/api/rules/` | List rules for the current user's workflows | Admin/Designer |
| `POST` | `/api/rules/` | Create a rule | Admin/Designer |
| `PATCH` | `/api/rules/{id}/` | Update a rule | Admin/Designer |
| `DELETE` | `/api/rules/{id}/` | Delete a rule | Admin |

#### FastAPI Rule Engine Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/evaluate/` | Evaluate a rule set against a data payload |
| `GET` | `/rules/{workflow_id}/` | Retrieve rules for a workflow |
| `POST` | `/rules/` | Create a rule |
| `GET` | `/health/` | Health check |
| `GET` | `/docs` | Interactive OpenAPI documentation |

**Evaluate Request/Response:**
```json
// Request
POST /evaluate/
{
  "rules": [
    {"condition": {"field": "claim_value", "operator": "gt", "value": 5000}, "action": {"type": "assign_role", "role": "director"}, "priority": 1}
  ],
  "data": {"claim_value": 7500, "category": "Liability"}
}

// Response
{
  "matched_rules": [0],
  "actions": [{"type": "assign_role", "role": "director"}],
  "evaluation_log": [{"rule_index": 0, "matched": true}]
}
```

---

### 5. Audit System

Every state change, form submission, task assignment, and system event is logged to an **immutable** audit table. This makes FlowForge suitable for regulated industries (finance, insurance, healthcare) where a full change history is a compliance requirement.

**Audit record fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Immutable primary key |
| `workflow_instance` | FK | The instance this event relates to |
| `actor` | FK (nullable) | The user who performed the action; null for system actions |
| `action_type` | Enum | One of: `instance_created`, `transition`, `task_assigned`, `task_completed`, `form_submitted`, `rule_fired`, `notification_sent`, `comment` |
| `from_state` | String | State name before the event (null for creation) |
| `to_state` | String | State name after the event |
| `payload` | JSONB | Full contextual data (form data hash, rule result, transition name, etc.) |
| `ip_address` | String | IPv4/IPv6 of the requesting client (null for async/system events) |
| `user_agent` | String | Browser/client user-agent (null for system events) |
| `created_at` | DateTime (UTC) | Immutable timestamp set at creation |

**Immutability enforcement:**
- `AuditLog.save()` raises `PermissionError` if called on an existing record.
- No `update()` or `delete()` DRF endpoints exist for audit records.
- Django admin marks the model as read-only.
- Database-level: a `BEFORE UPDATE OR DELETE` PostgreSQL trigger raises an exception (defence-in-depth).

**Querying:**
- Filter by `instance_id`, `action_type`, `actor`, and date range.
- Results are always ordered `created_at ASC` within an instance.
- Admin view supports cross-instance search with pagination.

---

### 6. Task System

When a workflow enters a state, tasks are automatically created and assigned to the responsible parties. Completing all tasks for a state may automatically trigger the next transition (configurable per workflow).

**Task Properties:**

| Field | Description |
|-------|-------------|
| `title` | Auto-generated from workflow config; overridable |
| `description` | Instructions for the assignee |
| `assigned_to_user` | Specific user (nullable) |
| `assigned_to_role` | Role group (nullable) |
| `status` | `pending`, `in_progress`, `completed`, `overdue`, `cancelled` |
| `priority` | `low`, `normal`, `high`, `critical` |
| `due_at` | Calculated from state SLA config at creation time |
| `completed_at` | Set on completion |
| `completed_by` | FK to User |
| `linked_instance` | FK to WorkflowInstance |
| `linked_state` | FK to State |

**SLA Configuration (per State):**
```json
{
  "sla_hours": 48,
  "sla_business_hours_only": true,
  "escalate_after_hours": 36,
  "escalate_to_role": "manager"
}
```

**Assignment Strategies (evaluated in order):**
1. Rule-driven: if a matching rule produces an `assign_role` or `assign_user` action, use it.
2. State configuration: a default assignee role is set on the state definition.
3. Round-robin: within a role, tasks are distributed to the user with the fewest open tasks.

**Task Completion Flow:**
1. Assignee calls `POST /api/tasks/{id}/complete/`.
2. If required, the associated form submission must exist for this state (validated before completion).
3. Task marked complete. If all tasks for the current state are now complete, and the state is configured for auto-advance, the transition endpoint is called automatically.

**SLA Enforcement (Celery Beat):**
- Celery runs `check_overdue_tasks` every 30 minutes.
- Tasks past their `due_at` are marked `overdue`.
- Escalation notifications are dispatched.

---

### 7. Notification Engine

Outbound notifications triggered by workflow events, dispatched asynchronously via Celery.

**Supported Channels:**

| Channel | Mechanism |
|---------|-----------|
| `email` | SMTP (Mailhog in dev; SendGrid in production) |
| `slack` | Incoming Webhook POST |
| `webhook` | Generic HTTP POST to any URL |

**Trigger Events:**

| Event | When it fires |
|-------|---------------|
| `instance_created` | A new workflow instance starts |
| `transition` | An instance moves to a new state |
| `task_assigned` | A task is assigned to a user |
| `task_overdue` | A task passes its SLA deadline |
| `task_completed` | A task is marked complete |
| `workflow_completed` | An instance reaches a terminal state |
| `rule_blocked` | A rule's `block_transition` action fires |

**Notification Templates:**
Templates are stored in the database per workflow definition per event, with fallback to global templates. Body templates use Jinja2 syntax.

Available template variables:
```
{{ instance.reference_number }}
{{ instance.current_state }}
{{ actor.full_name }}
{{ actor.email }}
{{ task.title }}
{{ task.due_at }}
{{ workflow.name }}
{{ transition.name }}
```

**Retry Logic:**
Failed notifications are retried up to 3 times using Celery's `retry` with exponential backoff (30s, 120s, 480s). After 3 failures, status is set to `failed` and an alert is written to the notification log.

**NotificationLog Fields:**
`id`, `workflow_instance`, `channel`, `recipient`, `subject`, `body`, `status` (`queued`/`sent`/`failed`), `sent_at`, `failure_reason`.

---

### 8. Frontend (React + TypeScript)

A single-page application that provides the full user interface for FlowForge. Built incrementally alongside the backend. All state is managed via React Query (server state) and React Context (auth).

#### Design Identity

FlowForge's UI language is **process clarity** — the visual metaphor is a control room dashboard: dark neutral surfaces, sharp typographic hierarchy, muted colour with purposeful accent only where status or action demands attention. The signature element is the **live workflow state visualiser**: an animated directed-graph showing the current position in a workflow, with completed states greyed, the active state highlighted, and future states dimmed. This is present on every instance detail page.

**Design Tokens:**
- Background: `#0F1117` (near-black navy)
- Surface: `#1A1D27` (card background)
- Border: `#2A2D3A`
- Text primary: `#F0F2F8`
- Text secondary: `#8B90A4`
- Accent (CTA): `#4F6EF7` (electric indigo)
- Status green: `#22C55E`
- Status amber: `#F59E0B`
- Status red: `#EF4444`
- Font display: Inter (600–700 weight, tight tracking)
- Font body: Inter (400–500 weight)
- Font mono: JetBrains Mono (for reference numbers, code, timestamps)

#### Page Inventory

| Route | Page | Access |
|-------|------|--------|
| `/login` | JWT login form | Public |
| `/register` | User registration | Public |
| `/dashboard` | Task inbox with priority/overdue callouts | Authenticated |
| `/workflows` | Workflow definition library | Designer+ |
| `/workflows/new` | Workflow builder: states, transitions, rules, forms | Designer+ |
| `/workflows/:id` | View/edit a workflow definition | Designer+ |
| `/instances` | Instance list with status filters | Authenticated |
| `/instances/new` | Start a new instance (select workflow) | Authenticated |
| `/instances/:id` | Instance detail: state graph, form, actions, history | Authenticated |
| `/admin/audit` | Audit log browser with filters | Admin only |
| `/admin/users` | User management: roles, status | Admin only |
| `/admin/notifications` | Notification log and template management | Admin only |

#### Page Detail

**Dashboard (`/dashboard`)**
The primary landing page post-login. Shows the authenticated user's task inbox:
- Pinned section: overdue tasks (red accent border).
- Main list: pending tasks ordered by due date.
- Each task card shows: reference number, workflow name, task title, assigned date, due date (relative), priority badge.
- "Complete" CTA on each card triggers a modal with the associated form (if any), then posts completion.

**Workflow Builder (`/workflows/new` and `/workflows/:id`)**
A multi-step builder:
1. **Step 1 — Definition:** Name, description, reference prefix, active toggle.
2. **Step 2 — States:** Add/remove/reorder states. Mark initial and terminal states. Set SLA per state.
3. **Step 3 — Transitions:** Draw connections between states. Set `requires_approval` and display name.
4. **Step 4 — Forms:** Attach a form definition to each state. Drag-and-drop field builder.
5. **Step 5 — Rules:** Create conditional rules per transition. Visual condition builder (no raw JSON needed).
6. **Step 6 — Notifications:** Configure templates per event.
7. **Preview panel:** Live preview of the workflow state graph updates as the user builds.

**Instance Detail (`/instances/:id`)**
The most complex page. Divided into four panels:
- **Left — State Graph:** SVG directed graph of all states. Current state is highlighted with the accent colour. Completed states are ticked. Future states are dimmed. Animated transition when state advances.
- **Centre — Active Form:** The form attached to the current state, rendered dynamically from the schema. Submit triggers the transition endpoint.
- **Right — History:** Chronological list of audit events for this instance. Each entry shows actor, action, timestamp.
- **Top bar — Actions:** Transition buttons for permitted next states (filtered by the user's role and active rules).

**Admin Audit (`/admin/audit`)**
A filterable table with columns: timestamp, instance reference, actor, action type, from state, to state. Supports date range picker and action type filter. CSV export button.

#### Frontend Architecture

- `axios` with an interceptor that attaches the JWT `Authorization` header and handles 401 → token refresh → retry.
- React Query for all server state: queries, mutations, background refetch on window focus.
- React Hook Form for form rendering (schema-driven, driven by the form schema returned by `/api/forms/{id}/`).
- React Router v6 for routing with role-based route guards.
- Tailwind CSS with a custom theme configuration matching the design tokens above.
- TypeScript strict mode throughout; all API responses typed against generated OpenAPI types.

#### Frontend–Backend Contract

The frontend treats the API as the source of truth. It never assumes workflow shape — all state graph rendering, form fields, and transition options are fetched dynamically. This means a new workflow definition deployed via the API is immediately available in the UI with no frontend code changes.

---

## Data Model

### Core Tables

```sql
-- accounts
User
  id UUID PK
  email VARCHAR UNIQUE NOT NULL
  full_name VARCHAR NOT NULL
  is_active BOOL DEFAULT true
  is_staff BOOL DEFAULT false
  date_joined TIMESTAMPTZ
  last_login TIMESTAMPTZ

Role
  id SERIAL PK
  name VARCHAR UNIQUE  -- platform_admin | workflow_designer | participant | approver | viewer

UserRole
  id SERIAL PK
  user_id FK → User
  role_id FK → Role
  UNIQUE (user_id, role_id)

-- workflows
WorkflowDefinition
  id UUID PK
  name VARCHAR NOT NULL
  description TEXT
  reference_prefix VARCHAR(10) NOT NULL  -- e.g. "CLM", "HR", "BUG"
  version INT DEFAULT 1
  is_active BOOL DEFAULT false
  created_by FK → User
  created_at TIMESTAMPTZ
  updated_at TIMESTAMPTZ

State
  id UUID PK
  workflow_definition_id FK → WorkflowDefinition
  name VARCHAR NOT NULL
  display_name VARCHAR NOT NULL
  is_initial BOOL DEFAULT false
  is_terminal BOOL DEFAULT false
  position_order INT NOT NULL
  sla_config JSONB  -- {"sla_hours": 48, "sla_business_hours_only": true, ...}
  task_config JSONB -- {"title_template": "Review {{instance.reference_number}}", "default_role": "handler"}
  UNIQUE (workflow_definition_id, name)

Transition
  id UUID PK
  workflow_definition_id FK → WorkflowDefinition
  from_state_id FK → State
  to_state_id FK → State
  name VARCHAR NOT NULL
  display_name VARCHAR
  requires_approval BOOL DEFAULT false
  UNIQUE (from_state_id, to_state_id)

Rule
  id UUID PK
  workflow_definition_id FK → WorkflowDefinition
  transition_id FK → Transition (nullable — null = applies to all transitions)
  condition_json JSONB NOT NULL
  action_json JSONB NOT NULL
  priority INT NOT NULL DEFAULT 10
  continue_on_match BOOL DEFAULT false
  is_active BOOL DEFAULT true
  created_by FK → User
  created_at TIMESTAMPTZ

-- instances
WorkflowInstance
  id UUID PK
  workflow_definition_id FK → WorkflowDefinition
  current_state_id FK → State
  reference_number VARCHAR UNIQUE NOT NULL  -- CLM-2026-00042
  created_by FK → User
  created_at TIMESTAMPTZ
  updated_at TIMESTAMPTZ
  completed_at TIMESTAMPTZ (nullable)
  metadata_json JSONB  -- arbitrary key-value from form submissions + system

-- forms
FormDefinition
  id UUID PK
  workflow_definition_id FK → WorkflowDefinition
  state_id FK → State
  name VARCHAR NOT NULL
  schema_json JSONB NOT NULL
  version INT DEFAULT 1
  created_by FK → User
  created_at TIMESTAMPTZ

FormSubmission
  id UUID PK
  workflow_instance_id FK → WorkflowInstance
  form_definition_id FK → FormDefinition
  submitted_by FK → User
  submitted_at TIMESTAMPTZ
  data_json JSONB NOT NULL  -- validated field values

-- tasks
Task
  id UUID PK
  workflow_instance_id FK → WorkflowInstance
  state_id FK → State
  title VARCHAR NOT NULL
  description TEXT
  assigned_to_user_id FK → User (nullable)
  assigned_to_role VARCHAR (nullable)
  status VARCHAR  -- pending | in_progress | completed | overdue | cancelled
  priority VARCHAR  -- low | normal | high | critical
  due_at TIMESTAMPTZ
  completed_at TIMESTAMPTZ
  completed_by FK → User
  created_at TIMESTAMPTZ

-- audit
AuditLog
  id UUID PK
  workflow_instance_id FK → WorkflowInstance
  actor_id FK → User (nullable — null for system events)
  action_type VARCHAR  -- instance_created | transition | task_assigned | task_completed | form_submitted | rule_fired | notification_sent | comment
  from_state VARCHAR (nullable)
  to_state VARCHAR (nullable)
  payload_json JSONB
  ip_address INET
  user_agent TEXT
  created_at TIMESTAMPTZ  -- immutable; set once

-- notifications
NotificationTemplate
  id UUID PK
  workflow_definition_id FK → WorkflowDefinition (nullable — null = global)
  channel VARCHAR  -- email | slack | webhook
  event_trigger VARCHAR  -- instance_created | transition | task_assigned | ...
  subject_template TEXT  -- Jinja2
  body_template TEXT  -- Jinja2
  is_active BOOL DEFAULT true

NotificationLog
  id UUID PK
  workflow_instance_id FK → WorkflowInstance
  template_id FK → NotificationTemplate (nullable)
  channel VARCHAR
  recipient VARCHAR  -- email address, Slack channel, webhook URL
  subject TEXT
  body TEXT
  status VARCHAR  -- queued | sent | failed
  sent_at TIMESTAMPTZ
  failure_reason TEXT
  attempt_count INT DEFAULT 0
```

### Key Indexes

```sql
CREATE INDEX idx_workflow_instance_current_state ON instances_workflowinstance(current_state_id);
CREATE INDEX idx_task_assigned_user ON tasks_task(assigned_to_user_id, status);
CREATE INDEX idx_task_assigned_role ON tasks_task(assigned_to_role, status);
CREATE INDEX idx_task_due_at ON tasks_task(due_at) WHERE status != 'completed';
CREATE INDEX idx_auditlog_instance ON audit_auditlog(workflow_instance_id, created_at);
CREATE INDEX idx_auditlog_actor ON audit_auditlog(actor_id, created_at);
CREATE INDEX idx_notificationlog_status ON notifications_notificationlog(status, sent_at);
```

---

## User Roles & Permissions

| Role | Capabilities |
|------|-------------|
| **Platform Admin** | Create/edit/delete workflow definitions; manage users and roles; view all instances and audit logs; manage notification templates |
| **Workflow Designer** | Create/edit workflow definitions and forms within assigned domains; cannot manage users |
| **Process Participant** | Complete assigned tasks; submit forms; view own workflow instances |
| **Approver** | Complete approval tasks; view assigned instances and their audit trails |
| **Viewer / Auditor** | Read-only access to instances and audit logs within assigned scope |

**Row-level permissions:**
- A Participant can only see instances they created or are assigned to.
- An Approver can only see instances with tasks assigned to them or their role.
- Admins and Designers see all instances within their workflow domain.

**Permission enforcement:**
- DRF `permission_classes` on all ViewSets.
- Custom `BaseInstancePermission` checks object-level ownership.
- Middleware adds the requesting user's roles to `request.user.roles` on every authenticated request.

---

## Non-Functional Requirements

| Concern | Requirement |
|---------|-------------|
| **Security** | JWT authentication; HTTPS enforced in production; OWASP Top 10 mitigated; secrets via environment variables / AWS Secrets Manager; no secret in git history |
| **Scalability** | Stateless Django API; PostgreSQL indexes on all FK and status fields; Celery workers scaled independently; connection pooling via pgbouncer (production) |
| **Auditability** | AuditLog is append-only; enforced at model, API, and database trigger layers |
| **Testability** | ≥80% test coverage on `apps/` directory; integration tests for all API endpoints; Playwright e2e for happy paths |
| **Observability** | JSON structured logging throughout; `/api/health/` endpoint; Django admin for internal inspection; CloudWatch log groups in production |
| **Portability** | All services containerised; environment-based configuration; `docker compose up` is the only local setup command needed |
| **Reliability** | Notification dispatch is async with retry; task SLA checks survive service restarts via Redis-backed Celery beat state |

---

## Out of Scope (v1)

- Mobile application
- Real-time collaboration (WebSocket live updates are a v2 feature)
- Built-in payment processing
- AI-driven workflow suggestions
- Multi-tenancy (single-organisation deployment for v1)
- Gantt / calendar views for task scheduling
- SAML/SSO authentication
