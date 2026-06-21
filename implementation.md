# FlowForge — Implementation Plan (v2)

> **Living document.** Updated to include comprehensive task lists for all phases, with Phase 8 (Frontend) fully expanded. Each phase leaves the application in a demonstrable, working state.

---

## Repository Structure

```
flowforge/
├── .github/
│   └── workflows/
│       ├── ci.yml            # Run tests + lint on every push/PR
│       └── deploy.yml        # Build, push to ECR, update ECS on main merge
├── backend/
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py       # Shared settings
│   │   │   ├── local.py      # Development overrides
│   │   │   └── production.py # Production overrides
│   │   ├── urls.py
│   │   └── wsgi.py
│   ├── apps/
│   │   ├── accounts/         # User model, roles, JWT auth
│   │   ├── workflows/        # WorkflowDefinition, State, Transition, Rule
│   │   ├── instances/        # WorkflowInstance, state machine logic
│   │   ├── forms/            # FormDefinition, FormSubmission
│   │   ├── tasks/            # Task model, SLA logic, assignment
│   │   ├── audit/            # AuditLog (immutable)
│   │   └── notifications/    # Templates, dispatch, Celery tasks
│   ├── tests/
│   │   ├── unit/
│   │   └── integration/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── rules-service/
│   ├── main.py               # FastAPI app entrypoint
│   ├── evaluator.py          # Pure rule evaluation logic
│   ├── models.py             # Pydantic request/response schemas
│   ├── tests/
│   │   └── test_evaluator.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/              # Axios client + typed API functions
│   │   ├── components/       # Shared UI components
│   │   │   ├── ui/           # Primitives: Button, Badge, Card, Modal, Table
│   │   │   ├── workflow/     # StateGraph, TransitionButton, WorkflowCard
│   │   │   ├── forms/        # DynamicForm, FieldRenderer, FileUpload
│   │   │   └── layout/       # AppShell, Sidebar, TopBar, PageHeader
│   │   ├── pages/            # Route-level components
│   │   ├── hooks/            # useAuth, useWorkflow, useTasks, etc.
│   │   ├── types/            # TypeScript interfaces (API-generated)
│   │   ├── store/            # React Context: AuthContext
│   │   └── utils/            # Date formatting, reference parsing, etc.
│   ├── public/
│   ├── Dockerfile
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── vite.config.ts
├── docker-compose.yml        # Development (Mailhog, hot-reload volumes)
├── docker-compose.prod.yml   # Production (no volumes, env-driven)
├── spec.md
├── implementation.md
├── README.md
└── USER_GUIDE.md
```

---

## Branching Strategy

```
main          ← production; protected; deploy on merge
  └─ develop  ← integration branch; PRs target here
       └─ feature/phase-2-workflow-engine
       └─ feature/phase-3-form-builder
       └─ feature/phase-4-task-system
       └─ feature/phase-5-rule-engine
       └─ feature/phase-6-audit
       └─ feature/phase-7-notifications
       └─ feature/phase-8-frontend
       └─ bugfix/task-assignment-403
```

- Every feature starts from `develop`.
- PRs require CI to pass (tests + lint) before merge.
- `develop` is merged to `main` at the end of each phase.
- Commit messages follow Conventional Commits: `feat:`, `fix:`, `test:`, `docs:`, `chore:`.

---

## Environment Variables

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
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=mailhog          # Use 'smtp.sendgrid.net' in production
EMAIL_PORT=1025             # Use 587 in production
EMAIL_HOST_USER=            # Set for SendGrid
EMAIL_HOST_PASSWORD=        # Set for SendGrid
DEFAULT_FROM_EMAIL=flowforge@yourdomain.com

# Slack
SLACK_WEBHOOK_URL=

# AWS (production only)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_STORAGE_BUCKET_NAME=
AWS_S3_REGION_NAME=eu-west-2
```

---

## Development Phases

Each phase has a clear target state. The application is always functional and demonstrable at the end of every phase — never broken mid-feature.

---

### Phase 1 — Foundation ✅ Complete

**Goal:** Users can register, log in, and the project runs end-to-end in Docker.

**What was built:**
- Django project with split settings (`base`, `local`, `production`)
- PostgreSQL connection via environment variables
- Custom `User` model extending `AbstractBaseUser`
- `Role` model with five roles; `UserRole` many-to-many
- JWT authentication endpoints (register, login, refresh)
- Django admin registered for all models
- `docker-compose.yml` with `db` (Postgres), `backend`, `redis`, `mailhog`
- Health check endpoint: `GET /api/health/`
- GitHub Actions CI: `pytest` on every push

**Status:** All acceptance criteria met.

---

### Phase 2 — Workflow Engine

**Goal:** A workflow definition can be created and a live instance can move through states.

**Branch:** `feature/phase-2-workflow-engine`

#### 2.1 — `workflows` App Models

- [ ] Create `apps/workflows/models.py`:
  ```python
  class WorkflowDefinition(models.Model):
      id = models.UUIDField(primary_key=True, default=uuid.uuid4)
      name = models.CharField(max_length=200)
      description = models.TextField(blank=True)
      reference_prefix = models.CharField(max_length=10)  # CLM, HR, BUG
      version = models.PositiveIntegerField(default=1)
      is_active = models.BooleanField(default=False)
      created_by = models.ForeignKey(settings.AUTH_USER_MODEL, ...)
      created_at = models.DateTimeField(auto_now_add=True)
      updated_at = models.DateTimeField(auto_now=True)

  class State(models.Model):
      id = models.UUIDField(primary_key=True, default=uuid.uuid4)
      workflow_definition = models.ForeignKey(WorkflowDefinition, related_name='states', ...)
      name = models.CharField(max_length=100)
      display_name = models.CharField(max_length=200)
      is_initial = models.BooleanField(default=False)
      is_terminal = models.BooleanField(default=False)
      position_order = models.PositiveIntegerField(default=0)
      sla_config = models.JSONField(default=dict, blank=True)
      task_config = models.JSONField(default=dict, blank=True)
      class Meta:
          unique_together = [('workflow_definition', 'name')]
          ordering = ['position_order']

  class Transition(models.Model):
      id = models.UUIDField(primary_key=True, default=uuid.uuid4)
      workflow_definition = models.ForeignKey(WorkflowDefinition, related_name='transitions', ...)
      from_state = models.ForeignKey(State, related_name='outgoing_transitions', ...)
      to_state = models.ForeignKey(State, related_name='incoming_transitions', ...)
      name = models.CharField(max_length=100)
      display_name = models.CharField(max_length=200, blank=True)
      requires_approval = models.BooleanField(default=False)
      class Meta:
          unique_together = [('from_state', 'to_state')]
  ```

- [ ] Create and run migrations.
- [ ] Register all models in Django admin with list displays and filters.

#### 2.2 — `instances` App Models

- [ ] Create `apps/instances/models.py`:
  ```python
  class WorkflowInstance(models.Model):
      id = models.UUIDField(primary_key=True, default=uuid.uuid4)
      workflow_definition = models.ForeignKey(WorkflowDefinition, ...)
      current_state = models.ForeignKey(State, ...)
      reference_number = models.CharField(max_length=50, unique=True)
      created_by = models.ForeignKey(settings.AUTH_USER_MODEL, ...)
      created_at = models.DateTimeField(auto_now_add=True)
      updated_at = models.DateTimeField(auto_now=True)
      completed_at = models.DateTimeField(null=True, blank=True)
      metadata_json = models.JSONField(default=dict)
  ```

- [ ] Implement `generate_reference_number(workflow_definition)` utility:
  - Format: `{PREFIX}-{YEAR}-{SEQUENCE:05d}`
  - Sequence is `WorkflowInstance.objects.filter(workflow_definition=wf, created_at__year=year).count() + 1`
  - Use `select_for_update()` to prevent race conditions.

- [ ] Create and run migrations.

#### 2.3 — State Machine Service

- [ ] Create `apps/instances/state_machine.py` — a **pure Python module** with no Django model imports at the top level, so it is fully unit-testable:
  ```python
  def get_valid_transitions(current_state_id: str, all_transitions: list[dict]) -> list[dict]:
      """Return all transitions whose from_state_id matches current_state_id."""

  def validate_transition(
      instance_id: str,
      requested_transition_id: str,
      current_state_id: str,
      all_transitions: list[dict],
  ) -> tuple[bool, str]:
      """Return (is_valid, error_message). Error is empty string if valid."""

  def perform_transition(instance: WorkflowInstance, transition: Transition, actor) -> WorkflowInstance:
      """
      Atomically:
        1. Validate the transition is permitted.
        2. Update instance.current_state.
        3. Set instance.completed_at if new state is terminal.
        4. Save the instance.
        5. Write AuditLog entry.
      Wrapped in django.db.transaction.atomic().
      """
  ```

#### 2.4 — DRF Serializers and ViewSets

- [ ] `WorkflowDefinitionSerializer`: full representation including nested states and transitions.
- [ ] `StateSerializer`: id, name, display_name, is_initial, is_terminal, position_order, sla_config.
- [ ] `TransitionSerializer`: id, name, from_state, to_state, requires_approval.
- [ ] `WorkflowInstanceSerializer`: id, reference_number, workflow_definition name, current_state name, created_at, metadata_json.
- [ ] `TransitionRequestSerializer`: just `transition_id` — used for the transition endpoint body.

- [ ] ViewSets:
  - `WorkflowDefinitionViewSet` (ListCreateRetrieveUpdateAPI) — permission: Admin or Designer to write; authenticated to read.
  - `WorkflowInstanceViewSet` (ListCreateRetrieveAPI).
  - `TransitionView` (POST only) at `/api/instances/{id}/transition/`.

- [ ] Wire into `config/urls.py` via DRF router.

#### 2.5 — Tests

- [ ] `tests/unit/test_state_machine.py`:
  - Test valid transition advances state.
  - Test invalid transition returns `(False, error_message)`.
  - Test attempting to leave a terminal state returns error.
  - Test `generate_reference_number` produces correct format.

- [ ] `tests/integration/test_workflow_api.py`:
  - Create workflow definition; assert HTTP 201 and correct structure.
  - Start instance; assert it begins in the initial state.
  - Transition to next state; assert current_state updated.
  - Attempt invalid transition; assert HTTP 400 with error detail.
  - Unauthenticated request to instance endpoint; assert HTTP 401.

#### Acceptance Criteria
- Create a 3-state, 2-transition workflow via API.
- Start an instance; it begins in the initial state.
- Transition; instance advances correctly.
- Invalid transition returns HTTP 400 with a descriptive message.

---

### Phase 3 — Form Builder

**Goal:** Users can define forms, attach them to states, and submit responses.

**Branch:** `feature/phase-3-form-builder`

#### 3.1 — `forms` App Models

- [ ] Create `apps/forms/models.py`:
  ```python
  class FormDefinition(models.Model):
      id = models.UUIDField(primary_key=True, default=uuid.uuid4)
      workflow_definition = models.ForeignKey(WorkflowDefinition, ...)
      state = models.ForeignKey(State, ...)
      name = models.CharField(max_length=200)
      schema_json = models.JSONField()
      version = models.PositiveIntegerField(default=1)
      created_by = models.ForeignKey(settings.AUTH_USER_MODEL, ...)
      created_at = models.DateTimeField(auto_now_add=True)

  class FormSubmission(models.Model):
      id = models.UUIDField(primary_key=True, default=uuid.uuid4)
      workflow_instance = models.ForeignKey(WorkflowInstance, ...)
      form_definition = models.ForeignKey(FormDefinition, ...)
      submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, ...)
      submitted_at = models.DateTimeField(auto_now_add=True)
      data_json = models.JSONField()

      def save(self, *args, **kwargs):
          if self.pk:
              raise PermissionError("FormSubmissions are immutable once created.")
          super().save(*args, **kwargs)

      def delete(self, *args, **kwargs):
          raise PermissionError("FormSubmissions cannot be deleted.")
  ```

#### 3.2 — Form Validation Service

- [ ] Create `apps/forms/validators.py`:
  ```python
  def validate_submission(schema: dict, data: dict) -> dict:
      """
      Validates `data` against the form `schema`.
      Returns a dict of {field_name: [errors]} if invalid.
      Raises ValidationError if any required field is missing or any type check fails.
      """
  ```
  - Required field check: error if field is `required: true` and key absent or empty.
  - Type validation: `number` and `currency` → coerce to float; error if not numeric.
  - Range validation: `min` / `max` constraints from schema.
  - Enum validation: `dropdown` value must be in `options` list.
  - Date validation: `date` and `datetime` fields parse as ISO 8601.

- [ ] After validation passes, merge validated data into `instance.metadata_json` so rules can reference form values.

#### 3.3 — DRF Serializers and ViewSets

- [ ] `FormDefinitionSerializer`: full schema.
- [ ] `FormSubmissionSerializer`: `workflow_instance_id`, `form_definition_id`, `data`. Override `create()` to call `validate_submission` before saving.
- [ ] ViewSets:
  - `FormDefinitionViewSet` (ListCreateRetrieve) — write: Admin/Designer.
  - `FormSubmissionViewSet` (CreateRetrieve only — no update/delete endpoints).

#### 3.4 — Tests

- [ ] `tests/unit/test_form_validator.py`:
  - Valid submission passes.
  - Missing required field returns field-level error.
  - Non-numeric value in a number field returns error.
  - Out-of-range value returns error.
  - Dropdown value not in options returns error.

- [ ] `tests/integration/test_forms_api.py`:
  - Create form definition; assert 201.
  - Submit valid data; assert 201 and data is stored.
  - Submit missing required field; assert 400 with field detail.
  - Attempt PUT on submission; assert 405.

#### Acceptance Criteria
- Create a form with 3 fields.
- Submit valid data; retrievable.
- Missing required field → HTTP 400 with field-level errors.
- Attempt to modify submission → HTTP 405.

---

### Phase 4 — Task System

**Goal:** Tasks are auto-created on transition; assigned users can complete them.

**Branch:** `feature/phase-4-task-system`

#### 4.1 — `tasks` App Models

- [ ] Create `apps/tasks/models.py`:
  ```python
  class Task(models.Model):
      STATUS_CHOICES = [
          ('pending', 'Pending'),
          ('in_progress', 'In Progress'),
          ('completed', 'Completed'),
          ('overdue', 'Overdue'),
          ('cancelled', 'Cancelled'),
      ]
      PRIORITY_CHOICES = [('low', 'Low'), ('normal', 'Normal'), ('high', 'High'), ('critical', 'Critical')]

      id = models.UUIDField(primary_key=True, default=uuid.uuid4)
      workflow_instance = models.ForeignKey(WorkflowInstance, related_name='tasks', ...)
      state = models.ForeignKey(State, ...)
      title = models.CharField(max_length=500)
      description = models.TextField(blank=True)
      assigned_to_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, ...)
      assigned_to_role = models.CharField(max_length=100, blank=True)
      status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
      priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
      due_at = models.DateTimeField(null=True, blank=True)
      completed_at = models.DateTimeField(null=True, blank=True)
      completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name='completed_tasks', ...)
      created_at = models.DateTimeField(auto_now_add=True)
  ```

#### 4.2 — Task Creation on Transition

- [ ] Create `apps/tasks/services.py`:
  ```python
  def create_tasks_for_state(instance: WorkflowInstance, state: State) -> list[Task]:
      """
      Called after every transition. Reads state.task_config to determine
      what tasks to create and what default assignment to apply.
      Returns the list of created tasks.
      """

  def calculate_due_date(state: State) -> datetime | None:
      """
      Reads state.sla_config. Supports:
        - sla_hours: integer (calendar hours)
        - sla_business_hours_only: bool (skip weekends/bank holidays — UK calendar)
      Returns None if no SLA is configured.
      """
  ```

- [ ] Connect to `perform_transition()` in `state_machine.py`: after the instance is saved, call `create_tasks_for_state(instance, new_state)`.

- [ ] Alternatively, use a Django `post_save` signal on `WorkflowInstance` that fires when `current_state` changes.

#### 4.3 — Task Assignment

- [ ] Create `apps/tasks/assignment.py`:
  ```python
  def apply_rule_driven_assignment(task: Task, rule_actions: list[dict]) -> Task:
      """
      If rule engine returned assign_role or assign_user actions,
      apply them to the task and save.
      """

  def apply_round_robin(task: Task, role: str) -> Task:
      """
      Find all users with the given role.
      Assign to the user with the fewest open tasks.
      """
  ```

#### 4.4 — DRF Serializers and ViewSets

- [ ] `TaskSerializer`: full detail.
- [ ] `TaskListSerializer`: summary for the dashboard (id, title, status, priority, due_at, workflow reference, state name).
- [ ] ViewSets:
  - `TaskViewSet` (ListRetrieve) — `GET /api/tasks/` returns only tasks assigned to `request.user` or `request.user`'s role.
  - `TaskCompleteView` (POST) at `/api/tasks/{id}/complete/`:
    1. Assert `request.user` is the assignee (or admin). Return 403 otherwise.
    2. Assert task status is `pending` or `in_progress`. Return 400 if complete/cancelled.
    3. Mark complete. Set `completed_at` and `completed_by`.
    4. Check if all tasks for the current state are now complete; if so, and state config `auto_advance` is set, trigger the configured transition.
  - `TaskReassignView` (POST) at `/api/tasks/{id}/reassign/` — Admin/Manager only.

#### 4.5 — SLA Enforcement (Celery Beat)

- [ ] In `apps/tasks/tasks.py` (Celery task):
  ```python
  @shared_task
  def check_overdue_tasks():
      """
      Run every 30 minutes via Celery Beat.
      Finds Tasks where due_at < now() and status in ('pending', 'in_progress').
      Updates status to 'overdue'.
      Dispatches escalation notifications.
      """
  ```

- [ ] Register in `config/settings/base.py`:
  ```python
  CELERY_BEAT_SCHEDULE = {
      'check-overdue-tasks': {
          'task': 'apps.tasks.tasks.check_overdue_tasks',
          'schedule': crontab(minute='*/30'),
      },
  }
  ```

#### 4.6 — Tests

- [ ] `tests/unit/test_task_service.py`:
  - Test `create_tasks_for_state` creates the correct number of tasks.
  - Test `calculate_due_date` with and without business-hours-only flag.
  - Test round-robin assigns to the user with fewest open tasks.

- [ ] `tests/integration/test_tasks_api.py`:
  - Start instance; assert tasks created for initial state.
  - Complete task as assignee; assert status = completed.
  - Complete task as different user; assert 403.
  - Retrieve task list as assignee; assert only own tasks returned.

#### Acceptance Criteria
- Start an instance; tasks auto-created for the initial state.
- Complete a task as the assignee; status updates.
- Task list only returns tasks relevant to the authenticated user.
- Completing another user's task returns 403.

---

### Phase 5 — Rule Engine

**Goal:** Conditional routing works. The FastAPI microservice evaluates rules and the Django backend uses results to route tasks.

**Branch:** `feature/phase-5-rule-engine`

#### 5.1 — `Rule` Model in `workflows` App

- [ ] Add to `apps/workflows/models.py`:
  ```python
  class Rule(models.Model):
      id = models.UUIDField(primary_key=True, default=uuid.uuid4)
      workflow_definition = models.ForeignKey(WorkflowDefinition, related_name='rules', ...)
      transition = models.ForeignKey(Transition, null=True, blank=True, ...)  # null = applies globally
      condition_json = models.JSONField()
      action_json = models.JSONField()
      priority = models.IntegerField(default=10)
      continue_on_match = models.BooleanField(default=False)
      is_active = models.BooleanField(default=True)
      created_by = models.ForeignKey(settings.AUTH_USER_MODEL, ...)
      created_at = models.DateTimeField(auto_now_add=True)
      class Meta:
          ordering = ['priority']
  ```

- [ ] Create and run migration.

#### 5.2 — FastAPI Rules Microservice

- [ ] Create `rules-service/models.py` (Pydantic):
  ```python
  class SimpleCondition(BaseModel):
      field: str
      operator: Literal["gt", "gte", "lt", "lte", "eq", "neq", "contains", "starts_with", "is_true", "is_false"]
      value: Any = None

  class CompoundCondition(BaseModel):
      operator: Literal["and", "or"]
      conditions: list[Union["CompoundCondition", SimpleCondition]]

  class RuleAction(BaseModel):
      type: Literal["assign_role", "assign_user", "block_transition", "notify", "set_metadata"]
      # Optional fields depending on type:
      role: str | None = None
      user_id: str | None = None
      reason: str | None = None
      channel: str | None = None
      template: str | None = None
      key: str | None = None
      value: Any = None

  class Rule(BaseModel):
      condition: SimpleCondition | CompoundCondition
      action: RuleAction
      priority: int = 10
      continue_on_match: bool = False

  class EvaluateRequest(BaseModel):
      rules: list[Rule]
      data: dict[str, Any]

  class EvaluateResponse(BaseModel):
      matched_rules: list[int]
      actions: list[RuleAction]
      evaluation_log: list[dict]
  ```

- [ ] Create `rules-service/evaluator.py`:
  ```python
  def evaluate_condition(condition: SimpleCondition | CompoundCondition, data: dict) -> bool:
      """
      Pure function. No I/O. Recursively evaluates compound conditions.
      """

  def evaluate_rules(rules: list[Rule], data: dict) -> EvaluateResponse:
      """
      Evaluates all rules in priority order.
      Stops at first match per action type unless continue_on_match is True.
      """
  ```

  Operator implementations:
  - `gt`, `gte`, `lt`, `lte`: numeric comparison (coerce field value to float).
  - `eq`, `neq`: equality, works for strings, numbers, bools.
  - `contains`, `starts_with`: string operations; cast field value to str.
  - `is_true`, `is_false`: bool coercion.
  - `and`, `or`: short-circuit evaluation.

- [ ] Create `rules-service/main.py`:
  ```python
  app = FastAPI(title="FlowForge Rule Engine", version="1.0.0")

  @app.post("/evaluate/", response_model=EvaluateResponse)
  async def evaluate(request: EvaluateRequest): ...

  @app.get("/health/")
  async def health(): return {"status": "ok"}
  ```

- [ ] `rules-service/Dockerfile`:
  ```dockerfile
  FROM python:3.12-slim
  WORKDIR /app
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt
  COPY . .
  CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
  ```

- [ ] Add `rules-service` to `docker-compose.yml`:
  ```yaml
  rules-service:
    build: ./rules-service
    ports:
      - "8001:8001"
    restart: unless-stopped
  ```

#### 5.3 — Django → FastAPI Integration

- [ ] Create `apps/workflows/rule_client.py`:
  ```python
  import httpx
  from django.conf import settings

  def evaluate_rules(rules: list[dict], data: dict) -> dict:
      """
      POST to the FastAPI /evaluate/ endpoint.
      Returns the response dict.
      Raises RuleServiceUnavailable if the service is unreachable.
      """
      response = httpx.post(
          f"{settings.RULES_SERVICE_URL}/evaluate/",
          json={"rules": rules, "data": data},
          timeout=5.0,
      )
      response.raise_for_status()
      return response.json()
  ```

- [ ] Integrate into `perform_transition()`:
  1. Before advancing state, fetch all active rules for `workflow_definition` where `transition = requested_transition` or `transition = null`.
  2. Call `evaluate_rules(rules, instance.metadata_json)`.
  3. If any action is `block_transition`, raise `TransitionBlockedError` and return HTTP 400.
  4. If any action is `assign_role` or `assign_user`, pass to `create_tasks_for_state()`.
  5. Log `rule_fired` audit events for each matched rule.

#### 5.4 — DRF Endpoints for Rule Management

- [ ] `RuleSerializer` and `RuleViewSet` (ListCreateUpdateDestroy):
  - `GET /api/rules/` — list rules (filtered to workflows the user can manage).
  - `POST /api/rules/` — create rule.
  - `PATCH /api/rules/{id}/` — update rule.
  - `DELETE /api/rules/{id}/` — Admin only.

#### 5.5 — Tests

- [ ] `rules-service/tests/test_evaluator.py`:
  - Test each operator individually.
  - Test compound `and` — both true, one false, both false.
  - Test compound `or` — both true, one true, both false.
  - Test nested compound conditions.
  - Test priority ordering: rule at priority 1 fires before priority 10.
  - Test `continue_on_match=True` collects multiple actions.
  - Test `block_transition` action stops further processing.
  - Parameterise across all operators using `pytest.mark.parametrize`.

- [ ] `tests/integration/test_rule_engine.py`:
  - Create rule: `claim_value > 5000 → assign_role: director`.
  - Submit form with `claim_value = 7500`; assert resulting task has `assigned_to_role = director`.
  - Submit with `claim_value = 500`; assert default assignment applies.
  - Create `block_transition` rule; attempt transition; assert HTTP 400 with block reason.

#### Acceptance Criteria
- FastAPI `/evaluate/` returns correct actions.
- FastAPI `/docs` renders interactive documentation.
- Rule-based assignment routes correctly.
- Block rule prevents transition with a clear message.

---

### Phase 6 — Audit System

**Goal:** Every action is logged immutably and queryable.

**Branch:** `feature/phase-6-audit`

#### 6.1 — `audit` App Models

- [ ] Create `apps/audit/models.py`:
  ```python
  class AuditLog(models.Model):
      ACTION_TYPES = [
          ('instance_created', 'Instance Created'),
          ('transition', 'State Transition'),
          ('task_assigned', 'Task Assigned'),
          ('task_completed', 'Task Completed'),
          ('form_submitted', 'Form Submitted'),
          ('rule_fired', 'Rule Fired'),
          ('notification_sent', 'Notification Sent'),
          ('comment', 'Comment'),
      ]
      id = models.UUIDField(primary_key=True, default=uuid.uuid4)
      workflow_instance = models.ForeignKey(WorkflowInstance, related_name='audit_logs', ...)
      actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, ...)  # null = system
      action_type = models.CharField(max_length=30, choices=ACTION_TYPES)
      from_state = models.CharField(max_length=100, blank=True)
      to_state = models.CharField(max_length=100, blank=True)
      payload_json = models.JSONField(default=dict)
      ip_address = models.GenericIPAddressField(null=True, blank=True)
      user_agent = models.TextField(blank=True)
      created_at = models.DateTimeField(auto_now_add=True)

      def save(self, *args, **kwargs):
          if self.pk:
              raise PermissionError("AuditLog records are immutable.")
          super().save(*args, **kwargs)

      def delete(self, *args, **kwargs):
          raise PermissionError("AuditLog records cannot be deleted.")

      class Meta:
          ordering = ['created_at']
          indexes = [
              models.Index(fields=['workflow_instance', 'created_at']),
              models.Index(fields=['actor', 'created_at']),
          ]
  ```

#### 6.2 — Database-Level Immutability

- [ ] Create a migration with a `RunSQL` operation to add PostgreSQL triggers:
  ```sql
  CREATE OR REPLACE FUNCTION prevent_audit_modification()
  RETURNS TRIGGER AS $$
  BEGIN
      RAISE EXCEPTION 'AuditLog records are immutable and cannot be modified or deleted.';
  END;
  $$ LANGUAGE plpgsql;

  CREATE TRIGGER no_update_auditlog
      BEFORE UPDATE ON audit_auditlog
      FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();

  CREATE TRIGGER no_delete_auditlog
      BEFORE DELETE ON audit_auditlog
      FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();
  ```

#### 6.3 — Audit Writer Service

- [ ] Create `apps/audit/services.py`:
  ```python
  def write_audit(
      *,
      instance: WorkflowInstance,
      action_type: str,
      actor=None,
      from_state: str = '',
      to_state: str = '',
      payload: dict = None,
      request=None,  # Django request for IP/user-agent
  ) -> AuditLog:
      """
      Creates and saves an AuditLog record.
      Extracts IP and user-agent from request if provided.
      Must be called inside the same database transaction as the action it logs.
      """
  ```

- [ ] Integrate `write_audit()` calls at:
  - `perform_transition()` (transition event)
  - `WorkflowInstance` creation (instance_created)
  - `Task` creation (task_assigned)
  - `Task.complete()` (task_completed)
  - `FormSubmission.save()` (form_submitted)
  - Rule evaluation (rule_fired, one entry per matched rule)
  - Notification dispatch (notification_sent, called from Celery worker)

#### 6.4 — DRF ViewSets

- [ ] `AuditLogSerializer`: all fields, read-only.
- [ ] `AuditLogViewSet`:
  - `GET /api/audit/{instance_id}/` — chronological trail for one instance. Any user with access to the instance can read its audit trail.
  - `GET /api/audit/` — admin-only; paginated; filterable by `action_type`, `actor_id`, `date_from`, `date_to`.
  - No `POST`, `PUT`, `PATCH`, `DELETE` endpoints.

- [ ] Django admin: `AuditLogAdmin` with `has_add_permission`, `has_change_permission`, and `has_delete_permission` all returning `False`. List display with search and date filters.

#### 6.5 — Tests

- [ ] `tests/unit/test_audit_immutability.py`:
  - Call `.save()` on an existing AuditLog; assert `PermissionError`.
  - Call `.delete()` on an AuditLog; assert `PermissionError`.

- [ ] `tests/integration/test_audit_api.py`:
  - Run a full workflow cycle; assert all expected events appear in order.
  - Assert timestamps are UTC and monotonically increasing.
  - Attempt `DELETE /api/audit/{id}/`; assert HTTP 405.
  - As non-admin, attempt `GET /api/audit/`; assert HTTP 403.

#### Acceptance Criteria
- Full workflow cycle produces complete, ordered audit trail.
- Attempt to delete audit record via API → 405.
- Admin can filter audit logs by date range and action type.

---

### Phase 7 — Notification Engine

**Goal:** Participants receive notifications when relevant events occur; dispatch is async with retry.

**Branch:** `feature/phase-7-notifications`

#### 7.1 — `notifications` App Models

- [ ] Create `apps/notifications/models.py`:
  ```python
  class NotificationTemplate(models.Model):
      CHANNEL_CHOICES = [('email', 'Email'), ('slack', 'Slack'), ('webhook', 'Webhook')]
      EVENT_CHOICES = [
          ('instance_created', '...'),
          ('transition', '...'),
          ('task_assigned', '...'),
          ('task_overdue', '...'),
          ('task_completed', '...'),
          ('workflow_completed', '...'),
          ('rule_blocked', '...'),
      ]
      id = models.UUIDField(primary_key=True, default=uuid.uuid4)
      workflow_definition = models.ForeignKey(WorkflowDefinition, null=True, blank=True, ...)  # null = global
      channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
      event_trigger = models.CharField(max_length=30, choices=EVENT_CHOICES)
      subject_template = models.TextField()     # Jinja2; used for email
      body_template = models.TextField()        # Jinja2; used for all channels
      is_active = models.BooleanField(default=True)

  class NotificationLog(models.Model):
      STATUS_CHOICES = [('queued', 'Queued'), ('sent', 'Sent'), ('failed', 'Failed')]
      id = models.UUIDField(primary_key=True, default=uuid.uuid4)
      workflow_instance = models.ForeignKey(WorkflowInstance, ...)
      template = models.ForeignKey(NotificationTemplate, null=True, ...)
      channel = models.CharField(max_length=20)
      recipient = models.CharField(max_length=500)
      subject = models.TextField(blank=True)
      body = models.TextField()
      status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
      sent_at = models.DateTimeField(null=True, blank=True)
      failure_reason = models.TextField(blank=True)
      attempt_count = models.PositiveIntegerField(default=0)
  ```

#### 7.2 — Template Rendering

- [ ] Create `apps/notifications/renderer.py`:
  ```python
  from jinja2 import Environment, BaseLoader

  JINJA_ENV = Environment(loader=BaseLoader())

  def render_template(template_str: str, context: dict) -> str:
      """
      Renders a Jinja2 template string with the given context.
      Context always includes: instance, actor, task (if applicable), workflow, transition (if applicable).
      """
  ```

#### 7.3 — Celery Dispatch Tasks

- [ ] Create `apps/notifications/tasks.py`:
  ```python
  @shared_task(bind=True, max_retries=3)
  def dispatch_notification(self, notification_log_id: str):
      """
      Loads NotificationLog by ID.
      Dispatches based on channel:
        - email: Django email backend (SMTP → Mailhog in dev, SendGrid in prod)
        - slack: httpx.post to SLACK_WEBHOOK_URL
        - webhook: httpx.post to recipient URL with body as JSON payload
      On success: sets status='sent', sent_at=now().
      On failure: increments attempt_count, sets failure_reason.
                  Calls self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
                  After max_retries: sets status='failed'.
      """
  ```

#### 7.4 — Event Dispatcher

- [ ] Create `apps/notifications/dispatcher.py`:
  ```python
  def dispatch_for_event(event_type: str, instance: WorkflowInstance, context: dict = None):
      """
      1. Find all active NotificationTemplates for (workflow_definition, event_type)
         plus global templates (workflow_definition=None).
      2. For each template:
         a. Determine recipient (from context: task assignee email, or workflow creator, etc.)
         b. Render subject and body using renderer.render_template()
         c. Create NotificationLog(status='queued')
         d. Enqueue dispatch_notification.delay(log.id)
      """
  ```

- [ ] Call `dispatch_for_event()` from:
  - `write_audit()` for relevant action types, OR
  - Directly from `perform_transition()`, task completion, SLA check, etc.

#### 7.5 — DRF ViewSets

- [ ] `NotificationTemplateSerializer` and `NotificationTemplateViewSet` (CRUD — Admin only).
- [ ] `NotificationLogSerializer` and `NotificationLogViewSet` (List only — Admin only):
  - `GET /api/notifications/logs/` — filterable by `status`, `channel`, `workflow_instance`.

#### 7.6 — Tests

- [ ] `tests/unit/test_renderer.py`:
  - Test all template variables render correctly.
  - Test missing variable raises `UndefinedError`.

- [ ] `tests/integration/test_notifications.py`:
  - Configure email template for `task_assigned`.
  - Assign task; assert `NotificationLog` created with `status=queued`.
  - Mock `dispatch_notification`; verify it's called with the correct log ID.
  - Simulate dispatch failure; assert retry logic increments `attempt_count`.
  - After 3 failures; assert `status=failed` and `failure_reason` set.

- [ ] Mailhog Integration:
  - In dev Docker Compose, emails go to Mailhog.
  - Manual acceptance test: trigger event, open `http://localhost:8025`, assert email received.

#### Acceptance Criteria
- Configure email template for "task assigned".
- Assign a task; email dispatched (visible in Mailhog).
- Failed notifications appear with `status=failed` in the log.
- Successful notifications have `status=sent` and `sent_at`.

---

### Phase 8 — Frontend (React + TypeScript)

**Goal:** A complete, polished UI for all FlowForge functionality. Built incrementally in parallel with backend phases 3–7; should reach feature-complete at the same time.

**Branch:** `feature/phase-8-frontend`

> The frontend is the primary showcase layer. It must look and feel production-quality. Follow the design identity from `spec.md` section 8 exactly.

---

#### 8.1 — Project Bootstrap and Architecture

- [ ] **Scaffold:**
  ```bash
  cd frontend
  npm create vite@latest . -- --template react-ts
  npm install
  ```

- [ ] **Dependencies:**
  ```bash
  npm install axios @tanstack/react-query react-router-dom react-hook-form
  npm install @radix-ui/react-dialog @radix-ui/react-dropdown-menu @radix-ui/react-toast
  npm install date-fns clsx tailwind-merge lucide-react
  npm install -D tailwindcss autoprefixer postcss @types/node
  ```

- [ ] **Tailwind configuration** (`tailwind.config.ts`):
  ```ts
  export default {
    content: ['./index.html', './src/**/*.{ts,tsx}'],
    theme: {
      extend: {
        colors: {
          bg: '#0F1117',
          surface: '#1A1D27',
          border: '#2A2D3A',
          'text-primary': '#F0F2F8',
          'text-secondary': '#8B90A4',
          accent: '#4F6EF7',
          'status-green': '#22C55E',
          'status-amber': '#F59E0B',
          'status-red': '#EF4444',
        },
        fontFamily: {
          sans: ['Inter', 'system-ui', 'sans-serif'],
          mono: ['JetBrains Mono', 'monospace'],
        },
      },
    },
  }
  ```

- [ ] **TypeScript** (`tsconfig.json`): strict mode, `noUncheckedIndexedAccess: true`.

- [ ] **Vite config** (`vite.config.ts`): proxy `/api` and `/evaluate` to `http://localhost:8000` and `http://localhost:8001` respectively during development.
  ```ts
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  }
  ```

#### 8.2 — API Client

- [ ] Create `src/api/client.ts`:
  ```ts
  import axios from 'axios'

  const client = axios.create({ baseURL: '/api' })

  // Request interceptor: attach JWT
  client.interceptors.request.use((config) => {
    const token = localStorage.getItem('access_token')
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
  })

  // Response interceptor: handle 401 → refresh → retry
  client.interceptors.response.use(
    (res) => res,
    async (error) => {
      if (error.response?.status === 401) {
        const refresh = localStorage.getItem('refresh_token')
        if (refresh) {
          const { data } = await axios.post('/api/auth/refresh/', { refresh })
          localStorage.setItem('access_token', data.access)
          error.config.headers.Authorization = `Bearer ${data.access}`
          return client(error.config)
        }
      }
      return Promise.reject(error)
    }
  )

  export default client
  ```

- [ ] Create typed API functions per resource in `src/api/`:
  - `auth.ts` — register, login, refresh
  - `workflows.ts` — list, get, create, update, activate, listStates, listTransitions
  - `instances.ts` — list, get, create, transition
  - `tasks.ts` — list, get, complete, reassign
  - `forms.ts` — get (schema), submit
  - `audit.ts` — get by instance, list all
  - `notifications.ts` — logs, templates

- [ ] Create `src/types/api.ts` — TypeScript interfaces matching Django serializer output for all entities.

#### 8.3 — Auth Context and Route Guards

- [ ] Create `src/store/AuthContext.tsx`:
  ```tsx
  interface AuthContextValue {
    user: User | null
    isAuthenticated: boolean
    login: (email: string, password: string) => Promise<void>
    logout: () => void
    hasRole: (role: string) => boolean
  }
  ```
  - On mount, read `access_token` from localStorage; decode JWT to get user info and roles.
  - `login()` posts to `/api/auth/login/`, stores tokens, decodes payload.
  - `logout()` clears storage, redirects to `/login`.

- [ ] Create `src/components/layout/ProtectedRoute.tsx`:
  ```tsx
  // Redirects to /login if not authenticated
  // Redirects to /dashboard if authenticated but missing required role
  ```

- [ ] Create `src/components/layout/RoleGate.tsx`:
  ```tsx
  // Renders children only if user has the required role(s)
  // Shows a 403 message otherwise
  ```

#### 8.4 — App Shell and Navigation

- [ ] Create `src/components/layout/AppShell.tsx`:
  - Fixed left sidebar (240px) with navigation links grouped by section.
  - Top bar with page title, user menu (avatar, name, logout).
  - Main content area with `<Outlet />`.
  - Sidebar collapses to icon-only on small screens.

- [ ] **Sidebar navigation:**
  ```
  ─ Dashboard
  ─ My Tasks
  ─ Instances
  ─ Workflows        (Designer+ only)
  ─ ─────────────
  ─ Admin
    ─ Audit Log      (Admin only)
    ─ Users          (Admin only)
    ─ Notifications  (Admin only)
  ```

- [ ] `src/components/ui/` — primitive components:
  - `Button.tsx` — variants: `primary`, `secondary`, `ghost`, `destructive`; sizes: `sm`, `md`, `lg`; loading state.
  - `Badge.tsx` — status badges using design token colours.
  - `Card.tsx` — surface card with optional header and footer.
  - `Modal.tsx` — Radix Dialog wrapper.
  - `Table.tsx` — sortable, paginated data table with loading skeleton.
  - `Toast.tsx` — Radix Toast notifications for success/error feedback.
  - `Spinner.tsx` — loading indicator.
  - `EmptyState.tsx` — illustrated empty state with a CTA button.

#### 8.5 — Authentication Pages

- [ ] `src/pages/LoginPage.tsx`:
  - Form fields: Email, Password.
  - React Hook Form with `zodResolver` validation.
  - On submit: call `auth.login()`, redirect to `/dashboard`.
  - Error message displayed inline if login fails.
  - Link to `/register`.

- [ ] `src/pages/RegisterPage.tsx`:
  - Form fields: Full Name, Email, Password, Confirm Password.
  - Validation: password ≥ 8 chars, passwords match.
  - On success: auto-login, redirect to `/dashboard`.

#### 8.6 — Dashboard Page

- [ ] `src/pages/DashboardPage.tsx`:
  - Fetches tasks via `GET /api/tasks/` using React Query.
  - Splits into sections: **Overdue** (red accent border), **Due Today**, **Upcoming**.
  - Task card component (`src/components/workflow/TaskCard.tsx`):
    - Reference number (monospace font)
    - Workflow name
    - Task title
    - Priority badge (colour-coded)
    - Due date (relative: "2 hours ago", "in 3 days")
    - Status badge
    - "Complete" button — opens `CompleteTaskModal.tsx`
  - Background refetch every 60 seconds.
  - Empty state: "No tasks assigned — you're all caught up."

- [ ] `src/components/workflow/CompleteTaskModal.tsx`:
  - Fetches the form schema for the current state (`GET /api/forms/{id}/`).
  - Renders `DynamicForm` if a form is attached.
  - On confirm: submits form data then calls `POST /api/tasks/{id}/complete/`.
  - Shows success toast; removes task from list optimistically.

#### 8.7 — Workflow Management Pages

- [ ] `src/pages/WorkflowListPage.tsx`:
  - Fetches all workflow definitions.
  - Card grid: name, description, state count, active badge, "Edit" and "New Instance" buttons.
  - "Create Workflow" CTA button → `/workflows/new`.

- [ ] `src/pages/WorkflowBuilderPage.tsx` — 6-step wizard:

  **Step 1 — Definition:**
  - Fields: Name, Description, Reference Prefix, Active toggle.
  - Saves as draft on "Next".

  **Step 2 — States:**
  - Add/remove/reorder states with drag-and-drop (using `@dnd-kit/core`).
  - Each state card: name, display_name, is_initial toggle, is_terminal toggle, SLA config (hours).
  - Validation: exactly one initial state, at least one terminal state.

  **Step 3 — Transitions:**
  - Visual transition editor: left column = source states, right = target states, middle = drawn arrows.
  - "Add Transition" button opens a modal: select from_state, to_state, name, requires_approval.
  - Transition list below the graph.

  **Step 4 — Forms:**
  - For each state, attach or create a form.
  - Field builder: "Add Field" button with type selector, label input, required toggle, options (for dropdown).
  - Fields reorderable via drag-and-drop.

  **Step 5 — Rules:**
  - Per-transition rule builder.
  - Visual condition builder: field dropdown (populated from attached form fields), operator selector, value input.
  - Compound condition toggle (AND / OR).
  - Action selector: assign_role (role name input), assign_user (user picker), block_transition (reason input), notify (channel + template).
  - Rule priority number input.

  **Step 6 — Notifications:**
  - For each event type, configure template (channel, subject, body with variable hints shown).

  **Live preview panel** (right side, 300px):
  - SVG state graph updated in real-time as states and transitions are added.
  - Shows current state as highlighted node, arrows as directed edges.
  - Built with plain SVG + D3-style force layout.

  **Save logic:**
  - Each step auto-saves to the backend on "Next".
  - Final "Activate" button calls `POST /api/workflows/{id}/activate/`.

#### 8.8 — Instance Pages

- [ ] `src/pages/InstanceListPage.tsx`:
  - Table: reference number, workflow name, current state, created date, created by.
  - Status filter chips: All, Active, Completed.
  - "Start New Instance" button → `/instances/new`.

- [ ] `src/pages/NewInstancePage.tsx`:
  - Workflow selector (dropdown of active workflows).
  - Initial metadata fields (pre-filled from workflow config if any).
  - "Start" calls `POST /api/instances/`; redirects to `/instances/{id}`.

- [ ] `src/pages/InstanceDetailPage.tsx` — the flagship page:

  **Layout (three columns + top bar):**

  Top bar:
  - Reference number (large, monospace, accent colour)
  - Workflow name
  - Transition buttons (one per valid next state, derived from `/api/instances/{id}/`)
  - Each button triggers `TransitionModal.tsx`

  Left panel (30%) — **State Graph:**
  - SVG directed graph of all states.
  - Completed states: filled surface node with tick icon.
  - Active state: accent-colour border, pulsing glow animation.
  - Future states: dimmed (50% opacity).
  - Arrows between states, labelled with transition names.
  - Graph updates with smooth transition animation when state advances.

  Centre panel (40%) — **Active Form:**
  - `DynamicForm` component driven by the form schema from `/api/forms/{id}/`.
  - "Submit" button calls `POST /api/submissions/`.
  - If no form is attached to the current state, shows a placeholder: "No form required for this state."

  Right panel (30%) — **Audit Trail:**
  - Chronological list of events from `/api/audit/{instance_id}/`.
  - Each entry: icon (per action type), actor name, description, relative timestamp.
  - Polls for updates every 30 seconds.

- [ ] `src/components/workflow/StateGraph.tsx`:
  - Pure SVG component.
  - Props: `states`, `transitions`, `currentStateId`, `completedStateIds`.
  - Layout: top-to-bottom DAG layout computed on mount (simple topological sort → y positions; equal distribution → x positions).
  - Animated: SVG `stroke-dashoffset` transition for new arrows; node colour transition for state changes.
  - Accessibility: `role="img"`, `aria-label` describing current state.

#### 8.9 — Dynamic Form Renderer

- [ ] `src/components/forms/DynamicForm.tsx`:
  - Props: `schema: FormSchema`, `onSubmit: (data: Record<string, unknown>) => void`, `isLoading: boolean`.
  - Uses React Hook Form's `useForm` with a schema built from the form definition.
  - Renders `FieldRenderer` for each field in `schema.fields`.
  - Handles conditional visibility: hides a field if its `conditional.show_if` condition is not met (evaluated against watched form values).

- [ ] `src/components/forms/FieldRenderer.tsx`:
  - Switch on `field.type` to render the appropriate input:
    - `text` → `<input type="text" />`
    - `textarea` → `<textarea />`
    - `number` / `currency` → `<input type="number" />` (currency shows `£` prefix)
    - `date` → `<input type="date" />`
    - `datetime` → `<input type="datetime-local" />`
    - `dropdown` → `<select>` with options
    - `checkbox` → `<input type="checkbox" />`
    - `file` → `<input type="file" />` with accepted types validation
  - Renders label, required asterisk, field error message.
  - All inputs styled with Tailwind to match design tokens.

#### 8.10 — Admin Pages

- [ ] `src/pages/AdminAuditPage.tsx`:
  - Filterable, paginated table of all audit events.
  - Columns: timestamp, reference number (linked to instance), actor, action type badge, from state → to state.
  - Filter bar: date range picker, action type multi-select, search by reference number.
  - "Export CSV" button: downloads filtered results as CSV (client-side generation from fetched data).

- [ ] `src/pages/AdminUsersPage.tsx`:
  - Table: full name, email, roles badges, status (active/inactive), joined date.
  - "Edit Roles" button opens modal with role checkbox group.
  - "Deactivate" button toggles `is_active`.
  - "Invite User" button opens invite modal (creates account via `/api/auth/register/`).

- [ ] `src/pages/AdminNotificationsPage.tsx`:
  - Two tabs: **Logs** and **Templates**.
  - Logs tab: table of NotificationLog entries, filterable by status and channel.
  - Templates tab: list of templates with edit button; opens `NotificationTemplateModal`.

#### 8.11 — Error Handling and Loading States

- [ ] Global error boundary: `src/components/ErrorBoundary.tsx` — catches React render errors and displays a friendly message.
- [ ] All React Query queries show a `Spinner` while loading and an inline error message with a "Retry" button on failure.
- [ ] API errors from axios are parsed into user-friendly messages:
  - 400: display field-level errors from DRF's response.
  - 401: redirect to `/login`.
  - 403: display "You don't have permission to do this."
  - 404: display "Not found."
  - 500: display "Something went wrong — please try again."
- [ ] Toast notifications for all mutations (success and error).

#### 8.12 — Accessibility and Responsiveness

- [ ] All interactive elements are keyboard-navigable with visible focus rings.
- [ ] All form fields have associated `<label>` elements.
- [ ] Colour is not the only means of conveying status (badges include text).
- [ ] Responsive: sidebar collapses on screens narrower than 768px; tables become scrollable.
- [ ] `prefers-reduced-motion`: disable all animations when user prefers reduced motion.

#### 8.13 — Dockerfile and Dev Server

- [ ] `frontend/Dockerfile`:
  ```dockerfile
  FROM node:20-alpine AS build
  WORKDIR /app
  COPY package*.json ./
  RUN npm ci
  COPY . .
  RUN npm run build

  FROM nginx:alpine
  COPY --from=build /app/dist /usr/share/nginx/html
  COPY nginx.conf /etc/nginx/conf.d/default.conf
  EXPOSE 80
  ```

- [ ] Add `frontend` service to `docker-compose.yml` with a volume mount for hot-reload during development:
  ```yaml
  frontend:
    build:
      context: ./frontend
      target: build   # Override for dev to use vite dev server
    command: npm run dev -- --host
    volumes:
      - ./frontend/src:/app/src
    ports:
      - "5173:5173"
    environment:
      VITE_API_BASE_URL: http://localhost:8000
  ```

#### Acceptance Criteria (Phase 8)
- `docker compose up` serves the React app at `http://localhost:5173`.
- User can register, log in, and see their task dashboard.
- User can create a workflow definition (all 6 steps) and start an instance.
- Instance detail page shows the state graph, form, and audit trail.
- Completing a task via the UI advances the workflow and updates the graph.
- All pages are responsive at 375px (mobile) and 1440px (desktop).
- No TypeScript errors (`tsc --noEmit` passes).
- No console errors in production build.

---

### Phase 9 — Testing

**Goal:** Professional test coverage gives confidence and demonstrates engineering rigour.

**Branch:** `feature/phase-9-testing`

#### 9.1 — Backend (Pytest)

**Setup:**
- `pytest-django`, `factory_boy`, `pytest-cov` in `requirements.txt`.
- `conftest.py` at `backend/tests/conftest.py`:
  - `db` fixture for database access.
  - `api_client` fixture returning an authenticated DRF `APIClient`.
  - Factory fixtures using `factory_boy` for User, WorkflowDefinition, State, Transition, WorkflowInstance, Task.

**Unit tests (`tests/unit/`):**
- [ ] `test_state_machine.py` — all transition scenarios (valid, invalid, terminal).
- [ ] `test_rule_evaluator.py` — all operators, compound conditions, priority ordering (mock the HTTP call).
- [ ] `test_form_validator.py` — all field types, required, range, enum.
- [ ] `test_audit_immutability.py` — save and delete raise errors.
- [ ] `test_reference_number.py` — format, uniqueness, year boundary.
- [ ] `test_sla_calculation.py` — calendar hours and business hours.
- [ ] `test_notification_renderer.py` — template variable substitution.

**Integration tests (`tests/integration/`):**
- [ ] `test_auth_api.py` — register, login, refresh, protected endpoint.
- [ ] `test_workflow_api.py` — CRUD + activate.
- [ ] `test_instance_api.py` — create, transition, metadata update.
- [ ] `test_task_api.py` — creation on transition, complete, reassign, 403.
- [ ] `test_forms_api.py` — schema validation, immutability.
- [ ] `test_audit_api.py` — trail completeness, 405 on delete.
- [ ] `test_notification_api.py` — template CRUD, log listing.
- [ ] `test_rule_api.py` — CRUD, integration with transition endpoint.

**Coverage:**
- [ ] CI command: `pytest --cov=apps --cov-report=xml --cov-fail-under=80`
- [ ] Coverage report uploaded to GitHub Actions as an artifact.

#### 9.2 — FastAPI Service Tests

- [ ] `rules-service/tests/test_evaluator.py` using `pytest` and `httpx.AsyncClient`:
  - `pytest.mark.parametrize` across all operators.
  - Test all action types returned correctly.
  - Test invalid operator raises a validation error.
  - Test `POST /evaluate/` returns correct HTTP responses.
  - Test `GET /health/` returns 200.

#### 9.3 — End-to-End Tests (Playwright)

- [ ] Install: `npm install -D @playwright/test` in `frontend/`.
- [ ] `frontend/tests/e2e/`:

  `auth.spec.ts`:
  - Navigate to `/login`.
  - Fill credentials and submit.
  - Assert redirect to `/dashboard`.
  - Assert sidebar is visible with user's name.

  `workflow_happy_path.spec.ts`:
  - Log in as Admin.
  - Create a workflow definition with 2 states and 1 transition.
  - Start a workflow instance.
  - Complete the form and trigger the transition.
  - Assert instance is now in the terminal state.
  - Assert the audit trail shows the transition event.

  `task_completion.spec.ts`:
  - Log in as Participant.
  - Assert an assigned task is visible on the dashboard.
  - Click "Complete" — fill the form — confirm.
  - Assert task disappears from dashboard.

  `permissions.spec.ts`:
  - Log in as Participant.
  - Navigate to `/admin/audit`.
  - Assert HTTP 403 response and a "Permission denied" message.

- [ ] GitHub Actions Playwright job: runs against `docker compose up` in CI with a health-check wait.

#### 9.4 — CI Configuration (`.github/workflows/ci.yml`)

```yaml
name: CI
on: [push, pull_request]
jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      db:
        image: postgres:16-alpine
        env: { POSTGRES_DB: flowforge, POSTGRES_USER: flowforge, POSTGRES_PASSWORD: flowforge }
        options: --health-cmd pg_isready --health-interval 10s --health-timeout 5s --health-retries 5
      redis:
        image: redis:7-alpine
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r backend/requirements.txt
      - run: cd backend && pytest --cov=apps --cov-report=xml --cov-fail-under=80
        env:
          DJANGO_SETTINGS_MODULE: config.settings.local
          DATABASE_URL: postgres://flowforge:flowforge@localhost:5432/flowforge
          REDIS_URL: redis://localhost:6379/0

  rules-service:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r rules-service/requirements.txt
      - run: cd rules-service && pytest

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: cd frontend && npm ci
      - run: cd frontend && npm run type-check
      - run: cd frontend && npm run lint
      - run: cd frontend && npm run build
```

---

### Phase 10 — AWS Deployment

**Goal:** The application is publicly accessible and deployed from `main` via CI/CD.

**Branch:** `feature/phase-10-deployment`

#### 10.1 — Infrastructure Architecture

```
Internet
   │
   ▼
Route 53 (DNS)
   │
   ▼
Application Load Balancer (HTTPS via ACM)
   │             │              │
   ▼             ▼              ▼
Django        FastAPI        Frontend
(ECS Fargate) (ECS Fargate)  (S3 + CloudFront)
   │
   ▼
RDS PostgreSQL          ElastiCache Redis
(private subnet)        (private subnet)
   │
   ▼
S3 (static files + media uploads)
```

#### 10.2 — Production Docker Configuration

- [ ] `docker-compose.prod.yml`:
  - No bind mounts.
  - Images pulled from ECR (not built locally).
  - All secrets via environment variables (not `.env` files).

- [ ] `backend/config/settings/production.py`:
  ```python
  DEBUG = False
  ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS')
  SECURE_SSL_REDIRECT = True
  SECURE_HSTS_SECONDS = 31536000
  SESSION_COOKIE_SECURE = True
  CSRF_COOKIE_SECURE = True
  STATIC_URL = f"https://{env('AWS_STORAGE_BUCKET_NAME')}.s3.amazonaws.com/static/"
  DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
  STATICFILES_STORAGE = 'storages.backends.s3boto3.StaticRootS3Boto3Storage'
  EMAIL_HOST = 'smtp.sendgrid.net'
  EMAIL_PORT = 587
  EMAIL_HOST_USER = 'apikey'
  EMAIL_HOST_PASSWORD = env('SENDGRID_API_KEY')
  ```

#### 10.3 — GitHub Actions Deploy (`.github/workflows/deploy.yml`)

```yaml
name: Deploy
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    needs: [backend, rules-service, frontend]  # Reuse CI jobs defined in ci.yml
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: eu-west-2

      # Build and push to ECR
      - name: Build and push backend image
        run: |
          aws ecr get-login-password | docker login --username AWS --password-stdin $ECR_REGISTRY
          docker build -t $ECR_REGISTRY/flowforge-backend:$GITHUB_SHA ./backend
          docker push $ECR_REGISTRY/flowforge-backend:$GITHUB_SHA

      - name: Build and push rules-service image
        run: |
          docker build -t $ECR_REGISTRY/flowforge-rules:$GITHUB_SHA ./rules-service
          docker push $ECR_REGISTRY/flowforge-rules:$GITHUB_SHA

      # Run migrations (ECS one-off task)
      - name: Run Django migrations
        run: |
          aws ecs run-task \
            --cluster flowforge \
            --task-definition flowforge-migrate \
            --overrides '{"containerOverrides":[{"name":"backend","command":["python","manage.py","migrate"]}]}'

      # Update ECS services
      - name: Update backend ECS service
        run: |
          aws ecs update-service --cluster flowforge --service flowforge-backend \
            --task-definition flowforge-backend:latest

      - name: Update rules-service ECS service
        run: |
          aws ecs update-service --cluster flowforge --service flowforge-rules \
            --task-definition flowforge-rules:latest

      # Deploy frontend to S3 + CloudFront
      - name: Build and deploy frontend
        run: |
          cd frontend && npm ci && npm run build
          aws s3 sync dist/ s3://${{ secrets.FRONTEND_BUCKET }} --delete
          aws cloudfront create-invalidation --distribution-id ${{ secrets.CF_DISTRIBUTION_ID }} --paths "/*"
```

#### 10.4 — Secrets Management

- [ ] All production secrets stored in **AWS Secrets Manager**, not in git.
- [ ] ECS task definition references secrets via `valueFrom` (Secrets Manager ARN).
- [ ] Local development uses `.env` file (git-ignored, with `.env.example` committed).

#### 10.5 — Observability

- [ ] CloudWatch log groups: `/flowforge/backend`, `/flowforge/rules-service`.
- [ ] Django JSON structured logging via `python-json-logger`.
- [ ] CloudWatch alarm on `5xx` error rate > 1% over 5 minutes → SNS email alert.
- [ ] ECS task health checks configured; unhealthy tasks replaced automatically.

#### Acceptance Criteria
- `git push origin main` triggers the full CI + deploy pipeline.
- Application accessible at `https://flowforge.yourdomain.com`.
- Failed test blocks deployment.
- No secrets in git history (`git log --all -- '*.env'` returns nothing).

---

## CV / Portfolio Description

Once complete, this project maps directly to the following CV entry:

> **FlowForge** — Configurable Workflow Automation Platform  
> Designed and developed a full-stack business process automation platform supporting state-driven workflows, dynamic form generation, rule-based conditional routing, compliance-grade audit logging, async notifications, and REST APIs. Built with Django, Django REST Framework, FastAPI, PostgreSQL, React (TypeScript), Celery, Docker, GitHub Actions, and AWS (ECS, RDS, ALB, ECR, S3, CloudFront, CloudWatch).

**Skills evidenced:**
- Python, Django, DRF, FastAPI
- PostgreSQL, JSONB schema design, database-level integrity (triggers)
- State machine design, rule engine design (service-oriented, async-safe)
- REST API design and documentation (OpenAPI via FastAPI, browsable API via DRF)
- React 18, TypeScript strict mode, React Query, React Hook Form
- SVG data visualisation (state graph)
- Celery async task processing, scheduled jobs
- Docker, Docker Compose, multi-stage Dockerfile
- CI/CD with GitHub Actions (test → build → deploy)
- AWS deployment: ECS Fargate, RDS, ALB, ECR, S3, CloudFront, ElastiCache, CloudWatch, Secrets Manager
- Pytest, factory_boy, Playwright end-to-end testing, ≥80% coverage
- Security: JWT auth, OWASP mitigations, secrets management, immutable audit trail, DB-level constraints
