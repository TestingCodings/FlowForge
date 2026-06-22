# FlowForge — Platform Vision

> "Make the initial building blocks so customisable and configurable that it becomes impossible to know what someone could one day create with it."

---

## What FlowForge is today

A **process engine with a fixed UI**. You configure the *logic* (states, transitions, rules, roles) and the platform renders a consistent interface for everyone who uses it. The engine is generic; the shell is not.

This is the right place to start — you need a solid, proven engine before you abstract the presentation layer. The engine is now solid.

---

## The Three Layers of Ambition

Think of these as concentric shells. Each one adds expressive power and ships independently.

```
┌─────────────────────────────────────────────────────────┐
│  Layer 3 — Standalone Deployable App                    │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Layer 2 — Custom UI Shell per Workflow           │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │  Layer 1 — Theme + Layout per Workspace     │  │  │
│  │  │  ┌─────────────────────────────────────────┐│  │  │
│  │  │  │  Current — Shared Platform UI           ││  │  │
│  │  │  └─────────────────────────────────────────┘│  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## Layer 1 — Theme + Layout per Workspace

**What it is:** Each team or client gets a "workspace" with its own branding, colour scheme, logo, and global layout preferences. The underlying components are the same; the skin is swapped.

**What this enables:**
- A legal firm's approval workflow looks like *their* tool, not FlowForge
- White-labelling without rebuilding anything
- Different default views per workspace (Kanban vs list, condensed vs spacious)

**Technical approach:**

Add a `Workspace` model with a `ui_config` JSON field:

```json
{
  "name": "Acme Corp",
  "logo_url": "...",
  "theme": {
    "primary":    "#0052cc",
    "accent":     "#00b8d9",
    "background": "#fafbfc",
    "sidebar_bg": "#0747a6",
    "font":       "Inter"
  },
  "default_view": "kanban",
  "date_format": "DD/MM/YYYY",
  "locale": "en-GB"
}
```

The frontend reads this at login and injects CSS custom properties. Every component already uses `var(--accent)` etc — theming is ~2 weeks of backend model + frontend CSS variable injection.

**Effort:** Low-Medium (3–4 weeks). This is table stakes for any SaaS product.

---

## Layer 2 — Custom UI Shell per Workflow

**What it is:** Each workflow definition carries a `ui_schema` that tells the renderer *how* to present it — not just what colour to use, but what views to show, which layout to use, which fields are prominent, what the list view looks like.

**What this enables:**

| If you configure... | It looks like... |
|---|---|
| Kanban shell + state columns | Trello / Jira board |
| List shell + priority + assignee columns | Linear / GitHub Issues |
| Calendar shell + date fields | Google Calendar / Teamup |
| Table shell + custom columns | Airtable / Notion database |
| Stepped-form shell | Typeform / multi-step wizard |
| TestRail shell | TestRail — matrix view of test cases |

**Technical approach:**

A `ui_schema` JSON field on `WorkflowDefinition`:

```json
{
  "shell": "kanban",
  "list_columns": ["reference", "metadata.assignee", "current_state", "metadata.priority", "created_at"],
  "kanban": {
    "group_by": "current_state",
    "card_fields": ["metadata.title", "metadata.assignee", "metadata.priority"],
    "swimlanes": "metadata.epic"
  },
  "instance_view": {
    "title_field": "metadata.title",
    "panels": ["description", "metadata", "comments", "state_graph", "timeline"],
    "layout": "sidebar"
  },
  "state_display": {
    "Backlog":     { "colour": "#6b7280", "icon": "circle" },
    "In Progress": { "colour": "#3b82f6", "icon": "play" },
    "Done":        { "colour": "#22c55e", "icon": "check" },
    "Blocked":     { "colour": "#ef4444", "icon": "x" }
  }
}
```

The frontend router checks the workflow's `ui_schema.shell` and renders a different view component:

```
WorkflowShellRouter
  ├── shell="list"    → ListView (current)
  ├── shell="kanban"  → KanbanView
  ├── shell="table"   → TableView (Airtable-style)
  ├── shell="calendar"→ CalendarView
  └── shell="matrix"  → MatrixView (TestRail-style)
```

Each shell component receives the same data (instances, workflow definition, rules) and presents it differently. The engine doesn't change — only the renderer.

**Effort:** Medium-High (8–14 weeks). The hard work is building 4-5 high-quality shell components, not the routing. A Kanban board with drag-to-transition is a month on its own. Worth prioritising the one that matches your first real use case.

**UI Schema Builder:** Rather than hand-writing JSON, a visual UI configurator (a "Workflow Builder" but for the presentation layer) is the natural next step. Select your shell, drag columns in/out, pick card fields. This is another 4–6 weeks but dramatically lowers the barrier.

---

## Layer 3 — Standalone Deployable App

**What it is:** A configured workspace + UI schema can be *exported* as a first-class application — either hosted on FlowForge's infrastructure at a custom domain, or exported as a self-contained deployable that the user runs themselves.

This is where "application creation factory" becomes real.

**Three deployment models:**

### 3a — Subdomain Hosting (Fastest to ship)
Each workspace gets `acme.flowforge.app`. The platform handles auth, storage, and compute. The custom domain resolves to a whitelabelled view filtered to that workspace. No code changes required — just DNS + workspace config. This is how Notion, Linear, and Retool work.

### 3b — Embedded Widget
A `<script>` tag embeds a FlowForge workflow into *any* existing web page. The instance list, forms, and state transitions render in an iframe or web component. Companies can drop a bug report form or approval chain into their existing intranet without migrating to a new tool.

### 3c — Exported Standalone App (Most ambitious)
A "Build → Export" button generates a self-contained deployable package:

```
my-qa-tool/
├── backend/          ← Django app, pre-configured with your workflow definitions
├── frontend/         ← React app, built with your UI schema baked in
├── docker-compose.yml
└── README.md
```

The exported app has no FlowForge branding. It *is* the tool — it just happens to have been built with FlowForge. This is the "impossible to know what someone could one day create" endgame.

**Effort:** 3a (subdomain) ~4 weeks. 3b (widget) ~6 weeks. 3c (export) is 3–6 months — it requires a code generation layer or a runtime that fully decouples the schema from the application shell.

---

## The Missing Primitives

To get from "configurable process engine" to "application factory" you need a handful of additional primitives. Everything else can be composed from these:

### 1. Relationship Fields (Cross-workflow linking)
Instances that reference other instances as first-class foreign keys, not just metadata strings.

```
Bug Report ──[reported_in]──► Test Run
Test Run   ──[part_of]──────► Release
Release    ──[blocks]────────► Deployment
```

With this, you can model parent/child, blocking, and dependency graphs. This is the primitive that turns isolated workflows into a connected system. **Without it you can't build a real Jira or TestRail.**

### 2. Form Schemas per State
Each state can define a structured form — typed fields with validation, required/optional, conditionally shown. The engine enforces the form is completed before a transition fires.

```json
{
  "state": "In Review",
  "form": [
    { "key": "test_evidence_url", "type": "url",    "required": true,  "label": "Evidence link" },
    { "key": "reviewer_notes",    "type": "text",   "required": false, "label": "Notes" },
    { "key": "regression_passed", "type": "boolean","required": true,  "label": "Regression passed?" }
  ]
}
```

This replaces the current free-form metadata editor with structured data collection. Rules can then operate on form values with full type safety. **Without it you can't build a real ServiceNow or HRMS.**

### 3. Notifications + Webhooks
Trigger emails, Slack messages, or HTTP POSTs on any event (transition fired, SLA breached, rule blocked, comment added). The notifications app is already stubbed in the backend — it needs a delivery layer.

**Without it, people have to manually check for updates.** Every real process tool has this.

### 4. SLA Breach Indicators + Scheduler
The SLA config is already stored on states. A background task (Celery beat) needs to run periodically, find instances that have exceeded their SLA, update a status flag, and trigger a notification. This turns SLAs from decoration into enforcement.

### 5. Bulk Operations
Select 20 instances → transition them all, assign them all, export them all. Critical for test management (mark 50 test cases as "Passed" at once) and any high-volume process.

### 6. Role Enforcement at the API Layer
Currently roles are frontend-only — a participant could call the API directly and fire an approver-only transition. This needs to move to the backend for any real production use.

### 7. Workflow Versioning
Publish a new version of a workflow definition without breaking open instances. Open instances stay on v1; new instances start on v2. Critical for anything with a long lifecycle (insurance claims that span months, support tickets).

---

## What Could Be Built With the Full Platform

Once Layers 1–3 and the missing primitives exist, these are all *configurations*, not new code:

| Product Category | Example | Key primitives needed |
|---|---|---|
| **Test Management** | TestRail replacement | Form schemas, matrix shell, bulk ops, cross-workflow links |
| **Project Tracker** | Jira / Linear | Kanban shell, relationships, custom fields, notifications |
| **HR Processes** | Leave, onboarding, performance review | Form schemas, SLA enforcement, email notifications |
| **IT Service Desk** | ServiceNow-lite | SLA breach, escalation rules, email intake |
| **CRM / Sales Pipeline** | Salesforce-lite | Kanban shell, calendar view, relationship fields |
| **Compliance & Audit** | SOC2 evidence collection | Form schemas, immutable audit log (already exists), role gating |
| **Document Approval** | Contract lifecycle | Multi-step forms, versioning, approval chains |
| **Incident Management** | PagerDuty workflow | SLA enforcement, webhooks, escalation rules |
| **Customer Onboarding** | Checklists + tasks | Form schemas, task system (already exists), email notifications |

---

## The Philosophical Parallel

The analogy to numbers or a coding language is the right frame. The primitives of arithmetic are five operations: add, subtract, multiply, divide, exponentiate. From those five, all of mathematics follows.

FlowForge's primitives are:

| Primitive | What it expresses |
|---|---|
| State | Where something is |
| Transition | How it moves |
| Rule | What governs movement |
| Role | Who can act |
| Form | What data is collected |
| Relationship | How things connect |
| Event | What happens as a result |
| View | How it's presented |

**With those eight primitives fully composable and configurable, it genuinely becomes impossible to predict what someone could build.** The constraint shifts from "what does the platform support" to "what can the user imagine."

The precedent exists: Notion started as a note-taking app and people use it to run entire companies. Airtable started as a spreadsheet and people build CRMs on it. The difference is that Notion and Airtable optimised for *data storage*. FlowForge optimises for *process* — and process is what every organisation actually runs on.

---

## Suggested Build Order

Given existing foundation, the highest-leverage sequence:

1. **Relationship fields** (4 weeks) — unlocks cross-workflow linking immediately; TestRail use case becomes real
2. **Form schemas per state** (6 weeks) — structured data collection; rules become far more powerful
3. **Layer 1: Workspace theming** (3 weeks) — sellable to clients immediately
4. **Notifications + webhooks** (4 weeks) — makes the platform "live" rather than something you have to check manually
5. **Kanban shell** (5 weeks) — first custom UI shell; Jira/Trello analogue
6. **SLA enforcement** (2 weeks) — short but high-value; makes SLA config meaningful
7. **Role enforcement at API** (2 weeks) — required before any real production use
8. **Bulk operations** (2 weeks) — unlocks test management and high-volume workflows
9. **Layer 2: UI Schema Builder** (8 weeks) — visual configurator for shells
10. **Layer 3a: Subdomain hosting** (4 weeks) — first deployable product

**Total to "application factory" MVP: approximately 12–18 months** of focused development. Not a small project — but each phase ships something genuinely useful independently.

---

## The North Star

> A user with no coding ability should be able to open FlowForge, describe their business process, configure how they want it to look, and ship it as a product their team uses daily — without writing a line of code and without the result looking like a generic SaaS tool.

That is the north star. Everything in this document is a step toward it.
