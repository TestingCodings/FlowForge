# FlowForge — Implementation Plan

## Repository Structure

```
flowforge/
├── .github/
│   └── workflows/
│       ├── ci.yml            # Run tests on every push/PR
│       └── deploy.yml        # Deploy to AWS on main branch merge
├── backend/                  # Django project
│   ├── config/               # Django settings, urls, wsgi
│   ├── apps/
│   │   ├── accounts/         # User auth, roles, permissions
│   │   ├── workflows/        # Workflow definitions, states, transitions
│   │   ├── instances/        # Live workflow instances
│   │   ├── forms/            # Form builder and submissions
│   │   ├── tasks/            # Task assignment and completion
│   │   ├── audit/            # Audit logging
│   │   └── notifications/    # Email/Slack/webhook dispatch
│   ├── Dockerfile
│   └── requirements.txt
├── rules-service/            # FastAPI microservice
│   ├── main.py
│   ├── evaluator.py
│   ├── models.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                 # React + TypeScript
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── api/              # API client
│   │   └── types/
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml
├── docker-compose.prod.yml
├── spec.md
└── implementation.md
```

---

## Development Phases

Each phase has a clear target state. Phases are designed so that the application is functional and demonstrable at the end of every phase — never broken mid-feature.

---

### Phase 1 — Foundation (Week 1)

**Goal:** Users can register, log in, and the project runs end-to-end in Docker.

#### Tasks

- [ ] Initialise Django project with `config/` layout (settings split into `base.py`, `local.py`, `production.py`)
- [ ] Configure PostgreSQL connection via environment variables
- [ ] Implement `accounts` app
  - Custom `User` model extending `AbstractBaseUser`
  - `Role` model (platform_admin, workflow_designer, participant, approver, viewer)
  - `UserRole` many-to-many assignment
- [ ] JWT authentication endpoints (`/api/auth/register/`, `/api/auth/login/`, `/api/auth/refresh/`)
- [ ] Django admin registered for all models
- [ ] Write `docker-compose.yml` with services: `db` (Postgres), `backend`, `redis`
- [ ] Health check endpoint: `GET /api/health/` returns `{"status": "ok"}`
- [ ] GitHub repo created with branch protection on `main` (PRs required)
- [ ] GitHub Actions CI: run `pytest` on every push

#### Acceptance Criteria
- `docker compose up` starts all services without errors
- `POST /api/auth/register/` creates a user and returns a JWT
- `POST /api/auth/login/` returns access + refresh tokens
- Protected endpoint returns 401 without a valid token

---

### Phase 2 — Workflow Engine (Week 2)

**Goal:** A workflow definition can be created and a live instance can move through states.

#### Tasks

- [ ] `workflows` app models:
  - `WorkflowDefinition` — name, description, version, is_active
  - `State` — FK to WorkflowDefinition, name, is_initial, is_terminal, position_order
  - `Transition` — from_state, to_state, name, requires_approval
- [ ] `instances` app models:
  - `WorkflowInstance` — FK to WorkflowDefinition, current_state, reference_number (auto-generated), metadata JSONB
- [ ] DRF serializers and viewsets for all models
- [ ] `POST /api/instances/{id}/transition/` — validates that the requested transition is permitted from the current state, then advances
- [ ] Transition validation raises a descriptive error if the transition is not valid
- [ ] Unit tests for the state machine transition logic (the engine should be a pure Python function, testable without HTTP)

#### Data Notes
- `reference_number` is auto-generated as `{WORKFLOW_PREFIX}-{YEAR}-{SEQUENCE}` (e.g., `CLM-2026-00042`)
- `metadata` JSONB stores arbitrary key-value data about the instance (claim value, employee name, etc.)

#### Acceptance Criteria
- Create a workflow definition via API with 3 states and 2 transitions
- Start an instance; it begins in the initial state
- Call transition endpoint; instance advances to the next state
- Invalid transitions return a 400 with a clear error message

---

### Phase 3 — Form Builder (Week 3)

**Goal:** Users can define forms, attach them to states, and submit responses.

#### Tasks

- [ ] `forms` app models:
  - `FormDefinition` — FK to WorkflowDefinition, FK to State, name, `schema` JSONB, version
  - `FormSubmission` — FK to WorkflowInstance, FK to FormDefinition, `data` JSONB, submitted_by, submitted_at
- [ ] Form schema structure (stored as JSONB):
  ```json
  {
    "fields": [
      {"name": "claim_value", "label": "Claim Value", "type": "number", "required": true},
      {"name": "description", "label": "Description", "type": "textarea", "required": true},
      {"name": "category", "label": "Category", "type": "dropdown",
       "options": ["Property", "Liability", "Health"], "required": true}
    ]
  }
  ```
- [ ] `POST /api/submissions/` — validates submitted data against the form schema before saving
- [ ] Form validation service: check required fields, type coercion, range constraints
- [ ] Submissions are immutable once stored (no update endpoint)

#### Acceptance Criteria
- Create a form definition with 3 fields via API
- Submit valid data; it is saved and retrievable
- Submit with a missing required field; receive a 400 with field-level error detail
- Attempt to modify a submission; receive a 405

---

### Phase 4 — Task System (Week 4)

**Goal:** When a workflow transitions into a state, tasks are created and assigned to the right people.

#### Tasks

- [ ] `tasks` app models:
  - `Task` — FK to WorkflowInstance, FK to State, assigned_to_user (nullable FK), assigned_to_role (nullable), status, due_at, completed_at, completed_by
- [ ] Task creation signal: when a `WorkflowInstance` transitions to a new state, auto-create tasks based on the state's task configuration
- [ ] `GET /api/tasks/` — returns tasks assigned to the authenticated user (or their role)
- [ ] `POST /api/tasks/{id}/complete/` — marks a task complete; triggers the associated workflow transition if all tasks for that state are complete
- [ ] SLA due date calculation: configurable per state (e.g., "complete within 2 business days")
- [ ] Celery beat task: check for overdue tasks every hour and update status

#### Acceptance Criteria
- Start a workflow instance; tasks are automatically created for the initial state
- Complete a task as an assigned user; task status updates
- Retrieve task list as an assigned user; only relevant tasks are returned
- Attempt to complete another user's task; receive a 403

---

### Phase 5 — Rule Engine (Week 5)

**Goal:** Conditional routing works. The system automatically assigns tasks and routes transitions based on form data.

#### Tasks

- [ ] `Rule` model in `workflows` app:
  - FK to WorkflowDefinition
  - FK to Transition (nullable — some rules apply globally)
  - `condition` JSONB
  - `action` JSONB
  - `priority` integer (lower number = higher priority)
- [ ] Rule condition schema:
  ```json
  {
    "field": "claim_value",
    "operator": "gt",
    "value": 5000
  }
  ```
  Compound example:
  ```json
  {
    "operator": "and",
    "conditions": [
      {"field": "claim_value", "operator": "gt", "value": 1000},
      {"field": "category", "operator": "eq", "value": "Liability"}
    ]
  }
  ```
- [ ] Rule action schema:
  ```json
  {"type": "assign_role", "role": "director"}
  {"type": "block_transition", "reason": "Requires director sign-off"}
  {"type": "notify", "channel": "email", "template": "high_value_claim"}
  ```
- [ ] **FastAPI rules microservice** (`rules-service/`):
  - `POST /evaluate/` accepts `{rules: [...], data: {...}}` and returns matching actions
  - Pure evaluation logic — no database access; stateless
  - Auto-generated OpenAPI docs at `/docs`
- [ ] Django backend calls the FastAPI service during transition evaluation
- [ ] `GET /api/rules/` and `POST /api/rules/` endpoints in Django

#### Acceptance Criteria
- Create a rule: "if claim_value > 5000, assign to director role"
- Submit a form with claim_value = 7500; resulting task is assigned to a director
- Submit with claim_value = 500; task follows the default assignment
- FastAPI `/evaluate/` endpoint returns correct actions for a given rule set and data payload
- FastAPI `/docs` renders the interactive documentation

---

### Phase 6 — Audit System (Week 6 — merged with audit focus from original Week 7)

**Goal:** Every action in the system is logged immutably and queryable.

#### Tasks

- [ ] `audit` app models:
  - `AuditLog` — workflow_instance (FK), actor (FK to User, nullable for system), action_type (choices), from_state, to_state, payload JSONB, ip_address, user_agent, created_at
  - No `update` or `delete` operations permitted on this model (enforce at model level with `save()` override and no `delete()` method)
- [ ] Django signal or mixin that writes to AuditLog on:
  - Workflow instance created
  - State transition
  - Task assigned / completed
  - Form submitted
  - Rule fired
  - Notification sent
- [ ] `GET /api/audit/{instance_id}/` — returns chronological audit trail for an instance
- [ ] `GET /api/audit/` — admin-only paginated list of all audit events with filters (date range, action type, actor)

#### Acceptance Criteria
- Complete a full workflow cycle; every step appears in the audit trail
- Audit records have correct timestamps and actor information
- Attempt to delete an audit record via the API; receive a 405
- Admin can filter audit logs by date range

---

### Phase 7 — Notification Engine (Week 7 — merged from original Week 8)

**Goal:** Participants receive notifications when relevant events occur.

#### Tasks

- [ ] `notifications` app models:
  - `NotificationTemplate` — channel (email/slack/webhook), event_trigger, subject_template, body_template (Jinja2 syntax), workflow_definition (FK, nullable for global templates)
  - `NotificationLog` — FK to WorkflowInstance, channel, recipient, subject, body, status (queued/sent/failed), sent_at
- [ ] Celery task for async dispatch:
  - Email via SMTP (configurable; use SendGrid in production)
  - Slack via Incoming Webhook URL
  - Generic webhook via HTTP POST
- [ ] Template variable substitution: `{{ instance.reference_number }}`, `{{ actor.full_name }}`, `{{ task.due_at }}`
- [ ] Retry logic: failed notifications retry up to 3 times with exponential backoff
- [ ] `GET /api/notifications/logs/` — admin view of sent notifications and their status

#### Acceptance Criteria
- Configure an email notification for "task assigned" event
- Assign a task; a notification email is dispatched (verify in dev with Mailhog in Docker)
- Failed notifications appear in the log with status "failed"
- Successful notifications appear with status "sent" and a timestamp

---

### Phase 8 — Frontend (React) (Weeks 3–8, built incrementally)

The frontend is built incrementally alongside the backend. By the end of Phase 7 all backend APIs exist; the frontend should reach feature-complete at the same time.

#### Pages

| Page | Description |
|------|-------------|
| `/login` | JWT login form |
| `/register` | User registration |
| `/dashboard` | Task inbox — tasks assigned to the current user |
| `/workflows` | List of workflow definitions |
| `/workflows/new` | Workflow builder (states, transitions, rules) |
| `/workflows/:id` | View/edit a workflow definition |
| `/instances` | List of workflow instances the user has access to |
| `/instances/:id` | Instance detail: current state, history, form, actions |
| `/admin/audit` | Audit log browser (admin role only) |
| `/admin/users` | User management (admin role only) |

#### Frontend Stack Details
- `axios` for API calls with an interceptor that attaches the JWT and handles 401 refresh
- `React Query` for server state management (caching, background refetch)
- `React Hook Form` for form rendering (driven by the form schema from the API)
- `Tailwind CSS` for styling
- TypeScript strict mode throughout

---

### Phase 9 — Testing (Week 9)

**Goal:** Professional test coverage gives confidence and demonstrates engineering rigour.

#### Backend (Pytest)

- [ ] Unit tests for state machine transition logic
- [ ] Unit tests for rule evaluator (all operators and compound conditions)
- [ ] Unit tests for form schema validation
- [ ] Integration tests for all API endpoints (use `pytest-django` and DRF's `APITestCase`)
- [ ] Fixture factories with `factory_boy`
- [ ] Test database isolation (transactions rolled back after each test)
- [ ] Coverage report: target ≥ 80% on `apps/` directory
- [ ] CI runs `pytest --cov` and fails if coverage drops below threshold

#### End-to-End (Playwright)

- [ ] Full happy-path test: log in → create workflow → start instance → complete task → verify audit trail
- [ ] Negative test: attempt unauthorised action and verify rejection
- [ ] Run in GitHub Actions against a Docker Compose test environment

#### FastAPI Service Tests
- [ ] `pytest` tests using `httpx.AsyncClient` against the FastAPI app directly (no running server needed)
- [ ] Parameterised tests covering all condition operators

---

### Phase 10 — AWS Deployment (Week 10)

**Goal:** The application is publicly accessible and deployed from `main` via CI/CD.

#### Infrastructure

```
Internet
   │
   ▼
Application Load Balancer (HTTPS)
   │          │
   ▼          ▼
Django      FastAPI
(ECS)       (ECS)
   │
   ▼
RDS PostgreSQL    ElastiCache Redis
```

#### Tasks

- [ ] `docker-compose.prod.yml` with production-grade settings (no volume mounts, proper env vars)
- [ ] Django production settings: `DEBUG=False`, `ALLOWED_HOSTS`, `SECURE_SSL_REDIRECT`, `STATIC_ROOT` with S3 backend
- [ ] `deploy.yml` GitHub Actions workflow:
  1. Run full test suite
  2. Build and push Docker images to ECR
  3. Update ECS service task definitions
  4. Run Django migrations (ECS one-off task)
- [ ] Environment variables managed in AWS Secrets Manager (never committed to git)
- [ ] RDS PostgreSQL in a private subnet
- [ ] ECS tasks in private subnets; ALB in public subnet
- [ ] HTTPS via ACM certificate on the ALB
- [ ] CloudWatch log groups for structured log output from both services

#### Acceptance Criteria
- `git push origin main` triggers a full CI/CD pipeline
- The application is accessible at a public URL via HTTPS
- A failed test blocks the deployment
- Secrets are not present in the git history

---

## Branching Strategy

```
main          ← production; protected; deploy on merge
  └─ develop  ← integration branch; PRs target here
       └─ feature/phase-1-auth
       └─ feature/phase-2-workflow-engine
       └─ bugfix/task-assignment-403
```

- Every feature/bugfix starts from a branch off `develop`
- PRs require CI to pass before merge
- `develop` is merged into `main` at the end of each phase
- Commit messages follow Conventional Commits: `feat:`, `fix:`, `test:`, `docs:`, `chore:`

---

## Environment Variables

All configuration is environment-driven. Never hardcode secrets.

```env
# Django
DJANGO_SECRET_KEY=
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=
DATABASE_URL=postgres://user:pass@host:5432/flowforge
REDIS_URL=redis://localhost:6379/0

# JWT
JWT_ACCESS_TOKEN_LIFETIME_MINUTES=60
JWT_REFRESH_TOKEN_LIFETIME_DAYS=7

# Rules service
RULES_SERVICE_URL=http://rules-service:8001

# Email
EMAIL_BACKEND=smtp
EMAIL_HOST=
EMAIL_PORT=587
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=

# Slack
SLACK_WEBHOOK_URL=

# AWS (production only)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_STORAGE_BUCKET_NAME=
AWS_S3_REGION_NAME=
```

---

## CV / Portfolio Description

Once complete, this project maps directly to the following CV entry:

> **FlowForge** — Configurable Workflow Automation Platform  
> Designed and developed a full-stack business process automation platform supporting state-driven workflows, dynamic form generation, rule-based conditional routing, audit logging, async notifications, and REST APIs. Built with Django, Django REST Framework, FastAPI, PostgreSQL, React (TypeScript), Celery, Docker, GitHub Actions, and AWS (ECS, RDS). Demonstrates state machine design, service-oriented architecture, compliance-grade audit systems, and production cloud deployment.

**Skills evidenced:**
- Python, Django, DRF, FastAPI
- PostgreSQL, JSONB schema design
- State machine and rule engine design
- REST API design and documentation
- React, TypeScript, React Query
- Celery async task processing
- Docker, Docker Compose
- CI/CD with GitHub Actions
- AWS deployment (ECS, RDS, ALB, ECR, S3, CloudWatch)
- Pytest, Playwright end-to-end testing
- Security: JWT auth, OWASP mitigations, secrets management
