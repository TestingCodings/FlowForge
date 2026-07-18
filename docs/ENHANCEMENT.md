# FlowForge Enhancement Roadmap

> Strengthening and hardening phases 1–11 for production reliability, scalability, and user experience before Layer 3 deployment.

This document outlines gap-closure and enhancement opportunities organized by impact and effort. Phases 1–11 are feature-complete; these enhancements address robustness, scale, operational safety, and user-facing polish.

---

## Priority Tiers

**Tier 1 — Production Critical**  
Must-haves before production deployment; blockers for data integrity or safety.

**Tier 2 — Scale & Reliability**  
Needed as user count and instance volume grow; prevents degradation under realistic load.

**Tier 3 — User Experience**  
Polishing, discoverability, and ease-of-use; shipping quality rather than MVP.

**Tier 4 — Operational & Extensibility**  
Observability, i18n, and integration hooks for third-party deployments.

---

## Tier 1: Production Critical

### 1.1 Async Webhook Delivery with Retry Logic
**Why:** Webhooks are currently synchronous—a slow subscriber blocks the user's transition.  
**What:** Move delivery to Celery with exponential backoff (1s, 2s, 4s, 8s, 16s, 32s, then dead-letter after 6 retries).  
**Scope:**
- Add `WebhookDeliveryLog` model with status (`pending`, `delivered`, `failed`, `dead_letter`)
- Celery task `deliver_webhook(subscription_id, payload)` with retries
- Beat scheduler for dead-letter expiry cleanup
- Per-subscription "recent deliveries" UI with replay button
- Metrics: delivery latency, failure rate, retry attempts

**Effort:** 2–3 weeks  
**Files:** `apps/notifications/tasks.py` (new), `models.py` (WebhookDeliveryLog), `admin.py` (dead-letter UI)

---

### 1.2 Optimistic Locking on Metadata Edits
**Why:** Two users editing metadata simultaneously—last-write-wins silently. No warning.  
**What:** Add `updated_at` timestamp to instances; PATCH `/instances/{id}/metadata/` validates precondition via `If-Match` header (409 Conflict on mismatch).  
**Scope:**
- Add `updated_at` to WorkflowInstance model (auto-update on every change)
- Frontend: capture `updated_at` on load, send in `If-Match: <timestamp>`
- API: check precondition, return 409 with current state if stale
- Frontend: on 409, show merge dialog (show both versions, let user pick)

**Effort:** 1–2 weeks  
**Files:** `models.py`, `serializers.py`, `views.py`, `InstanceDetailPage.tsx`

---

### 1.3 Form Schema Versioning
**Why:** Editing a form silently changes what past submissions were validated against.  
**What:** Forms follow workflow versioning pattern—immutable once submitted-against; new version on edit.  
**Scope:**
- Add `version` field to FormDefinition (increment on save if schema changed)
- Add `form_definition_version` to FormSubmission (capture version at submission time)
- API: prevent form edits if submissions exist; instead create v+1 draft linked via `parent`
- Docs: clarify that form versions follow workflow versions (publish new workflow → new form versions)

**Effort:** 1–2 weeks  
**Files:** `apps/forms/models.py`, `migrations/`, API endpoint enforcement

---

### 1.4 SLA Scheduler Robustness
**Why:** `check_slas` management command can fail silently or miss breaches if it doesn't run on schedule.  
**What:** Move from one-off command to Celery Beat periodic task; add idempotency guarantees.  
**Scope:**
- Celery Beat task `check_slas_scheduled()` (runs every 5 minutes)
- Idempotency: deduplicate via `(instance_id, state_entry_id)` + SLA hours (no duplicate breach entries)
- Alerting: log if task misses its window; emit metric for monitoring
- Docs: how to scale beat (single scheduler per deployment or HA leader)

**Effort:** 1–2 weeks  
**Files:** `apps/notifications/tasks.py`, `celery.py` (beat schedule config)

---

### 1.5 Rule Evaluation Timeout & Circuit Breaker
**Why:** Slow rules microservice can hang transitions indefinitely; no fallback if service crashes.  
**What:** Add timeout + circuit breaker; fall back to local evaluator on timeout/error.  
**Scope:**
- Timeout: 5s max for rules microservice call; log slow calls
- Circuit breaker: if >50% requests fail in 60s window, fall back to local evaluator for 30s
- Monitoring: expose as metrics (timeout count, fallback activations)
- Docs: clarify local evaluator is always available; microservice is optional optimization

**Effort:** 1–2 weeks  
**Files:** `apps/workflows/engine.py`, `services.py` (new CircuitBreaker class)

---

## Tier 2: Scale & Reliability

### 2.1 Server-Side Pagination & Indexed Search
**Why:** Instances list loads everything client-side; at 10k instances it crawls.  
**What:** Paginate all list endpoints (instances, workflows, audit logs); add indexed search by reference + state.  
**Scope:**
- API pagination: `limit=50&offset=0` (or cursor-based) on `/instances/`, `/audit/{id}/`
- Database indexes: `(workflow_definition, current_state, created_at)`, `reference` uniqueness
- Search: `/instances/search/?q=REF-123` → index lookup (not full table scan)
- Frontend: infinite scroll or page controls, load as user scrolls
- CSV export: still supports filters but exports paginated results (cap at 10k rows)

**Effort:** 2–3 weeks  
**Files:** `pagination.py` (new), `views.py` (apply to ListViewSets), `migrations/` (indexes), frontend infinite-scroll component

---

### 2.2 Audit Log Pagination & Export
**Why:** Instance detail page loads full timeline; 1000s of events kill performance.  
**What:** Paginate audit timeline in detail page; add audit export (JSON/CSV) for compliance.  
**Scope:**
- `/audit/{instance_id}/?limit=50&offset=0` — paginated, newest first
- UI: lazy-load older events as user scrolls
- Export: `/audit/{instance_id}/export/` → JSON or CSV with all fields
- Cleanup: optional `prune_old_audit_logs` command (archive to S3 after N days)

**Effort:** 1–2 weeks  
**Files:** `apps/audit/views.py`, frontend Timeline component (pagination)

---

### 2.3 Instance Bulk Fetch & Batch Operations Optimization
**Why:** Bulk transitions iterate N times; large batches are slow.  
**What:** Optimize bulk ops to use batch database operations; prefetch related data.  
**Scope:**
- Bulk transition: prefetch all workflows + rules once, then iterate (not per-instance fetch)
- Use `.select_related('workflow_definition')` + `.prefetch_related('current_form')`
- Batch rule evaluation: send all 100 instances' metadata to rules service in one call
- Monitoring: expose as metric (ms per instance in bulk)

**Effort:** 1–2 weeks  
**Files:** `apps/instances/views.py` (bulk_transition action), `engine.py`

---

### 2.4 Frontend Test Coverage (Vitest + React Testing Library)
**Why:** 95 backend tests but zero frontend tests; regressions go unnoticed.  
**What:** Unit + integration tests for critical components.  
**Scope:**
- Test the shells: ListShell, KanbanShell, TableShell, CalendarShell (rendering + drag-to-transition)
- Test ChildrenPanel (add/detach child, roll-up progress)
- Test form editor (add/remove fields, validation)
- Test rule editor (add/remove conditions, operator switching)
- Aim for 70%+ coverage on components/, at least 50% on pages/

**Effort:** 3–4 weeks  
**Files:** `src/**/*.test.tsx` (new), `vitest.config.ts`, `package.json` (vitest dep)

---

### 2.5 Database Query Performance Auditing
**Why:** No visibility into slow queries; N+1 problems hiding.  
**What:** Add query logging + slow-query detection; profile common flows.  
**Scope:**
- Django debug toolbar in local dev (already available)
- Production: django-silk or similar for query introspection
- Identify & fix N+1: instance detail page, bulk operations, audit timeline
- Indexes on foreign keys and common filters
- Docs: query optimization checklist for future work

**Effort:** 1–2 weeks  
**Files:** `settings/base.py` (middleware), migration docs

---

## Tier 3: User Experience

### 3.1 i18n Scaffolding (Translation Foundation)
**Why:** String count is still manageable; retrofitting later costs much more.  
**What:** Wrap all UI strings in translation layer; set up for volunteer translations.  
**Scope:**
- Use `react-i18next` + `i18next` for frontend
- Use Django's `gettext` for backend
- Extract strings: `npm run i18n:extract` → `.json` or `.po` files per language
- Add placeholder translations for 2–3 languages (e.g., Spanish, German)
- Docs: how to contribute translations

**Effort:** 2–3 weeks  
**Files:** `src/i18n/` (new), all `.tsx` files (wrap strings), `locales/en.json` + `locales/es.json`, etc.

---

### 3.2 Form Schema Conditionals (Show/Hide Fields)
**Why:** Forms currently show all fields always; no branching logic.  
**What:** Add conditional visibility based on other field values.  
**Scope:**
- Form schema extension: `fields[].visible_if: {field: "...", operator: "eq|contains", value: "..."}`
- Frontend: recompute visibility on input, hide/show with transition
- Example: "Show 'evidence_url' only if severity is 'high'"

**Effort:** 1–2 weeks  
**Files:** `apps/forms/models.py` (schema update), form renderer components

---

### 3.3 Bulk Transition with Per-Instance Preview
**Why:** Bulk select → transition is scary; users want to see what will happen first.  
**What:** Before firing, show per-instance results (which will succeed, which will be blocked, why).  
**Scope:**
- New endpoint: `POST /instances/bulk-transition/preview/` → returns per-instance outcome
- Frontend: modal showing green (✓ will succeed), red (✗ blocked by rule), yellow (⚠ requires form)
- Allow user to deselect instances before committing

**Effort:** 1–2 weeks  
**Files:** `views.py` (new endpoint), InstanceBulkModal.tsx (frontend modal)

---

### 3.4 Rich Text Support in Comments & Metadata
**Why:** Comments and descriptions are plain text; no formatting.  
**What:** Markdown or WYSIWYG editor for comments; render with syntax highlight.  
**Scope:**
- Store comments as markdown (backward-compatible)
- Frontend: simple markdown editor (toolbar for **bold**, *italic*, links)
- Render with markdown-it or similar
- Metadata: optional rich-text fields (textarea → markdown)

**Effort:** 1–2 weeks  
**Files:** CommentForm.tsx (editor), Markdown renderer component

---

### 3.5 Instance Cloning
**Why:** Users often need to copy an instance with the same metadata/forms.  
**What:** "Clone" button on instance detail → creates sibling in initial state with copied metadata.  
**Scope:**
- New action: `POST /instances/{id}/clone/` → returns new instance (copy metadata, new state machine)
- Frontend: "Clone" button, optional dialog to tweak metadata before cloning
- Audit: log clone relationship

**Effort:** 1 week  
**Files:** `views.py` (new action), InstanceDetailPage.tsx (button)

---

### 3.6 Keyboard Shortcuts & Command Palette
**Why:** Power users want to move fast; mouse-only is slow for frequent actions.  
**What:** Add global keyboard shortcuts (Cmd+K to open palette) + per-page shortcuts.  
**Scope:**
- Command palette: `Cmd+K` → search workflows, instances, actions
- Shortcuts: `Cmd+T` → new instance, `Cmd+L` → jump to list, `Shift+?` → help
- Toast notifications: show available shortcuts on first load
- Settings: customizable shortcuts

**Effort:** 1–2 weeks  
**Files:** `hooks/useKeyboardShortcuts.ts` (new), CommandPalette.tsx (new component)

---

## Tier 4: Operational & Extensibility

### 4.1 Application Observability (Logging, Metrics, Tracing)
**Why:** No visibility into what's happening in production; hard to debug issues.  
**What:** Structured logging + prometheus metrics + optional request tracing.  
**Scope:**
- Structured logs: JSON output with context (user_id, workflow_id, action)
- Metrics: transition count, rule evaluation time, webhook delivery latency, form submission rate
- Tracing: optional integration with OpenTelemetry (for distributed tracing)
- Dashboards: Grafana templates for common queries
- Docs: how to set up ELK or similar

**Effort:** 2–3 weeks  
**Files:** `logging_config.py` (new), middleware for tracing, `metrics.py` (new), `docker-compose.yml` (Prometheus)

---

### 4.2 Audit Log Retention & Compliance
**Why:** Audit logs grow indefinitely; no retention policy.  
**What:** Configurable retention + archive to immutable storage (S3).  
**Scope:**
- Settings: `AUDIT_LOG_RETENTION_DAYS` (default 365)
- Cleanup task: archive logs older than retention to S3, delete locally
- Verification: checksum archive to ensure no tampering
- Docs: compliance guidance (SOC2, GDPR, etc.)

**Effort:** 1–2 weeks  
**Files:** `management/commands/archive_audit_logs.py`, `settings/base.py`

---

### 4.3 Workflow Linting & Validation Rules
**Why:** Users can create invalid workflows (dead-end states, orphaned transitions).  
**What:** Linting layer that checks workflow structure before saving.  
**Scope:**
- Lint checks: all states reachable from initial, no cycles (unless intentional), no orphaned transitions, all rule operators valid
- API validation: return lint warnings on workflow save
- Frontend: show lint warnings in workflow builder (as hints, not errors)
- Docs: workflow best practices

**Effort:** 1–2 weeks  
**Files:** `apps/workflows/linting.py` (new), `views.py` (call on save)

---

### 4.4 Role Permission Audit & Reporting
**Why:** Hard to track who has what permissions; no audit of permission changes.  
**What:** Permission change log + reporting dashboard.  
**Scope:**
- Audit log entry type: `role_changed` (user, old roles, new roles, actor, timestamp)
- Dashboard: matrix of users × workflows showing access level
- Export: CSV of all permissions for compliance
- Docs: role management best practices

**Effort:** 1–2 weeks  
**Files:** `apps/accounts/signals.py` (on role change), permissions dashboard component

---

### 4.5 Custom Transition Actions (Hooks)
**Why:** Some workflows need custom side effects (call external API, generate PDF, update CRM).  
**What:** Before/after transition hooks (webhooks + custom code extension point).  
**Scope:**
- Webhooks already cover "notify external system"
- Add optional Lambda/serverless invocation for custom logic (fire-and-forget)
- Docs: example of calling external API on transition
- Security: rate-limit hook invocations, timeout at 10s

**Effort:** 2–3 weeks  
**Files:** `apps/workflows/hooks.py` (new), tasks for async hook execution

---

### 4.6 Configurable Email Templates
**Why:** Email notifications use hardcoded templates; no customization.  
**What:** Admin-editable email templates per event type.  
**Scope:**
- UI: template editor (WYSIWYG or liquid template syntax)
- Templates per event: transition_fired, rule_blocked, sla_breached, comment_added
- Preview: send test email
- Docs: template variable reference

**Effort:** 2 weeks  
**Files:** NotificationTemplate model (enhancement), admin UI, email rendering

---

## Implementation Sequence (Recommended)

### Quarter 1 (Months 1–3)
1. **Async webhooks + retries** (2–3w) — unblocks reliable webhook delivery
2. **Optimistic locking** (1–2w) — prevents silent data loss
3. **Form versioning** (1–2w) — ensures form history is accurate
4. **SLA scheduler robustness** (1–2w) — moves SLA to production-grade
5. **Rule timeout + circuit breaker** (1–2w) — stabilizes engine

**Result:** Core reliability solid. Safe for production.

### Quarter 2 (Months 4–6)
6. **Server-side pagination** (2–3w) — enables scale
7. **Audit log pagination** (1–2w) — performance on large instances
8. **Bulk op optimization** (1–2w) — fast bulk transitions
9. **Frontend test coverage** (3–4w) — regression safety

**Result:** Ready for thousands of instances and bulk workflows.

### Quarter 3 (Months 7–9)
10. **Query performance audit** (1–2w) — identify remaining N+1s
11. **i18n scaffolding** (2–3w) — prepare for international users
12. **Bulk preview** (1–2w) — safer bulk operations
13. **Observability** (2–3w) — production visibility

**Result:** Observable, translatable, high-performance platform.

### Quarter 4 (Months 10–12)
14. **Form conditionals** (1–2w) — richer forms
15. **Instance cloning** (1w) — user convenience
16. **Keyboard shortcuts** (1–2w) — power-user experience
17. **Remaining Tier 4 items** (2–3w each) — compliance, extensibility

**Result:** Feature-rich, extensible, compliant platform ready for Layer 3.

---

## Effort Summary

| Tier | Total Effort | Items |
|---|---|---|
| **Tier 1** | 7–11 weeks | 5 critical items |
| **Tier 2** | 8–13 weeks | 5 scale/reliability items |
| **Tier 3** | 7–12 weeks | 6 UX items |
| **Tier 4** | 11–17 weeks | 6 operational items |
| **Total** | ~35–50 weeks | 22 enhancements |

**If prioritized (Tier 1 + top Tier 2 items): ~4–5 months to production-ready.**

---

## Success Metrics

Once enhancements are in place, measure:

- **Reliability:** webhook delivery success rate >99%, rule eval timeout %  
- **Scale:** page load time on 10k instances, audit timeline render time  
- **Safety:** metadata edit conflicts resolved, form version mismatches  
- **Quality:** frontend test coverage ≥70%, slow query count  
- **Operations:** SLA breach detection latency <5min, backup/restore time  

---

## Future Work (Post-Enhancement)

Once these enhancements land, Layer 3 work becomes viable:
- Subdomain hosting (3a): production infrastructure, user workspace isolation
- Embedded widget (3b): iframe/web component, auth/CORS, standalone operation
- Exported standalone app (3c): code generation, self-contained deployable

See [VISION.md](VISION.md#layer-3--standalone-deployable-app) for Layer 3 detail.
