# FlowForge — Project Specification

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
Produce a real, reusable product that can serve as a foundation for freelance work or a SaaS offering.

---

## Core Components

### 1. Workflow Engine

A **database-driven state machine**. Each workflow is defined as an ordered set of states and the valid transitions between them.

**Concepts:**
- **Workflow Definition** — a named template (e.g., "New Insurance Claim", "Employee Onboarding")
- **State** — a named step within a workflow (e.g., Draft, Submitted, Under Review, Approved, Rejected, Completed)
- **Transition** — a permitted move from one state to another, optionally guarded by rules
- **Workflow Instance** — a live execution of a workflow definition, tracking current state and history

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

**Key requirement:** The same engine handles all three. Configuration, not code, determines behaviour.

---

### 2. Rule Engine

A configurable condition evaluator that gates transitions and routes submissions automatically.

**Example rules:**
```
IF claim_value > 1000  → assign to Manager
IF claim_value > 5000  → assign to Director
IF claim_value > 10000 → assign to CFO
```

Rules are stored in the database and evaluated at runtime. The rule engine supports:

- **Numeric comparisons** (`>`, `<`, `>=`, `<=`, `==`, `!=`)
- **String matching** (`equals`, `contains`, `starts_with`)
- **Boolean flags** (`is_true`, `is_false`)
- **Compound conditions** (`AND`, `OR`)
- **Actions** — route to role, assign to user, send notification, block transition

---

### 3. Form Builder

Users construct data-capture forms through a UI. Forms are attached to workflow states; when a workflow enters a state, the assigned form is presented to the responsible party.

**Supported field types:**
- Text (single-line, multi-line)
- Number (integer, decimal, currency)
- Date / DateTime
- Dropdown (static options or dynamic lookup)
- Checkbox / Toggle
- File upload
- Hidden (system-populated)

**Form behaviour:**
- Required/optional per field
- Conditional visibility (show field B only if field A equals X)
- Validation rules per field
- Form submissions are versioned and immutable once submitted

---

### 4. REST API Layer

The primary interface for all platform operations, built with **Django REST Framework**.

A separate **FastAPI** microservice exposes the rule evaluation engine, demonstrating service-oriented architecture.

#### Django REST Framework Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/workflows/` | Create a workflow definition |
| `GET` | `/api/workflows/` | List workflow definitions |
| `GET` | `/api/workflows/{id}/` | Retrieve a workflow definition |
| `POST` | `/api/instances/` | Start a workflow instance |
| `GET` | `/api/instances/{id}/` | Get instance state and history |
| `POST` | `/api/instances/{id}/transition/` | Advance to next state |
| `GET` | `/api/tasks/` | List tasks assigned to the current user |
| `POST` | `/api/tasks/{id}/complete/` | Complete a task |
| `GET` | `/api/audit/{instance_id}/` | Full audit trail for an instance |
| `POST` | `/api/forms/` | Create a form definition |
| `POST` | `/api/submissions/` | Submit a form response |

#### FastAPI Rule Engine Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/evaluate/` | Evaluate a rule set against a data payload |
| `GET` | `/rules/{workflow_id}/` | Retrieve rules for a workflow |
| `POST` | `/rules/` | Create a rule |

---

### 5. Audit System

Every state change, form submission, task assignment, and system event is logged to an immutable audit table.

**Each audit record captures:**
- Timestamp (UTC)
- Actor (user or system)
- Action type (transition, assignment, comment, rule_fired, notification_sent)
- Before state / after state
- Associated data payload (JSON)
- IP address / user agent (for user actions)

This makes FlowForge suitable for regulated industries (finance, insurance, healthcare) where a full change history is a compliance requirement.

---

### 6. Task System

When a workflow enters a state, tasks are created and assigned to users or roles.

**Task properties:**
- Title and description (auto-generated from workflow config)
- Assignee (specific user or role-based)
- Due date (configurable SLA per state)
- Priority
- Status (Pending, In Progress, Complete, Overdue)
- Linked workflow instance and state

**Assignment strategies:**
- Explicit user assignment
- Role-based round-robin
- Rule-driven assignment (based on form data)

---

### 7. Notification Engine

Outbound notifications triggered by workflow events.

**Supported channels:**
- Email (SMTP / SendGrid)
- Slack (Incoming Webhooks)
- Generic Webhook (POST to any URL)

**Trigger events:**
- Workflow instance created
- State transition occurred
- Task assigned
- Task overdue
- Workflow completed

**Notification templates** are configurable per workflow and per event, with variable substitution from the workflow instance data.

---

## Data Model

### Core Tables

```
WorkflowDefinition
  id, name, description, version, created_by, created_at, is_active

State
  id, workflow_definition_id, name, display_name, is_initial, is_terminal, position_order

Transition
  id, workflow_definition_id, from_state_id, to_state_id, name, requires_approval

Rule
  id, workflow_definition_id, transition_id (nullable), condition_json, action_json, priority

FormDefinition
  id, workflow_definition_id, state_id, name, schema_json, version

WorkflowInstance
  id, workflow_definition_id, current_state_id, reference_number, created_by, created_at, updated_at, metadata_json

FormSubmission
  id, workflow_instance_id, form_definition_id, submitted_by, submitted_at, data_json

Task
  id, workflow_instance_id, state_id, assigned_to_user_id, assigned_to_role, status, due_at, completed_at, completed_by

AuditLog
  id, workflow_instance_id, actor_id, action_type, from_state, to_state, payload_json, ip_address, created_at

NotificationLog
  id, workflow_instance_id, channel, recipient, subject, body, status, sent_at
```

---

## User Roles & Permissions

| Role | Capabilities |
|------|-------------|
| **Platform Admin** | Create/edit workflow definitions, manage users and roles, view all instances |
| **Workflow Designer** | Create/edit workflow definitions and forms within assigned domains |
| **Process Participant** | Complete tasks, submit forms, view own instances |
| **Approver** | Complete approval tasks, view assigned instances |
| **Viewer / Auditor** | Read-only access to instances and audit logs |

Permissions are enforced at the API layer using DRF permission classes. Row-level permissions ensure users can only access instances relevant to them.

---

## Non-Functional Requirements

| Concern | Requirement |
|---------|-------------|
| **Security** | JWT authentication, HTTPS enforced, OWASP Top 10 mitigated, secrets in environment variables |
| **Scalability** | Stateless API; database queries optimised with indexes on foreign keys and status fields |
| **Auditability** | Audit log is append-only; no UPDATE or DELETE on `AuditLog` |
| **Testability** | Minimum 80% test coverage on business logic; integration tests for all API endpoints |
| **Observability** | Structured logging (JSON); health check endpoint; Django admin for internal inspection |
| **Portability** | All services containerised with Docker; environment-based configuration |

---

## Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Backend framework | Django + Django REST Framework | Batteries-included, industry standard for Python backends |
| Rule microservice | FastAPI | Demonstrates service architecture; async-native; auto-generated OpenAPI docs |
| Database | PostgreSQL | Production-grade relational DB; JSONB support for flexible schema storage |
| Frontend | React + TypeScript | Modern SPA; type safety demonstrates engineering rigour |
| Containerisation | Docker + Docker Compose | Reproducible environments; production parity in development |
| Task queue | Celery + Redis | Async notification dispatch; scheduled SLA checks |
| Authentication | JWT (djangorestframework-simplejwt) | Stateless auth suitable for SPA + API consumption |
| CI/CD | GitHub Actions | Automated testing and deployment on every push |
| Cloud deployment | AWS (ECS or EC2 + RDS) | Industry-standard cloud; demonstrates production deployment |
| Testing | Pytest + Playwright | Unit/integration tests + end-to-end browser tests |

---

## Out of Scope (v1)

- Mobile application
- Real-time collaboration (WebSocket live updates are a v2 feature)
- Built-in payment processing
- AI-driven workflow suggestions
- Multi-tenancy (single-organisation deployment for v1)
