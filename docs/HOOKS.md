# Secret Store & Action Hooks — Design

The design for the two remaining **synchronous outbound** capabilities from
[METAMODEL.md](METAMODEL.md): action hooks (transitions that call out to other
systems and act on the result) and the encrypted secret store they depend on.

This is the security-heaviest feature in FlowForge to date — it makes the
server hold credentials and make outbound calls to user-defined URLs — so the
design leads with the threat model, not the feature.

Status: design. Nothing here is built. Sequencing at the end.

---

## Why the secret store comes first

Action hooks are useless without credentials (an Azure token, a PagerDuty
key), and `metadata_json` is plaintext returned by the API — storing secrets
there would leak them to every viewer. So the secret store is a hard
prerequisite, built and shipped on its own first.

---

## Part 1 — Secret Store

### Threat model

| Threat | Mitigation |
|--------|-----------|
| Secret read via the API | Secrets are **write-only** — the API never returns a value, only names + metadata |
| Secret read from the DB | Values encrypted at rest (Fernet/AES-128-CBC+HMAC); DB dump alone is useless |
| Secret in logs / errors / audit | Central redaction: values scrubbed from hook logs, exception messages, and audit payloads before persistence |
| Secret in the frontend | Never sent to the client; resolved only in the worker at fire time |
| Encryption key in the repo | Key from a dedicated env var (`SECRETS_ENCRYPTION_KEY`), distinct from `DJANGO_SECRET_KEY`, absent from settings and VCS |
| Compromised key | Key rotation procedure (re-encrypt all secrets under a new key); keys versioned so old ciphertext is decryptable during rotation |

### Model

```python
class Secret(models.Model):
    id            = UUIDField(pk)
    name          = SlugField                 # referenced as {{secret.NAME}}
    scope         = FK(WorkflowDefinition, null=True)  # null = workspace-global
    ciphertext    = BinaryField               # Fernet token; never a plain column
    key_version   = PositiveSmallInteger      # which encryption key encrypted it
    created_by    = FK(User, SET_NULL)
    created_at    = DateTimeField
    last_used_at  = DateTimeField(null=True)  # observability, not the value

    class Meta:
        constraints = [UniqueConstraint(fields=["scope", "name"])]
```

- No `value` field is ever exposed. A property `set_value(plaintext)` encrypts;
  a `_decrypt()` is called **only** by the hook runner in the worker.
- `scope` lets a secret be workflow-specific or workspace-global; workflow
  hooks resolve workflow-scoped first, then fall back to global.

### Encryption

- `cryptography` (new dependency) `Fernet`. `SECRETS_ENCRYPTION_KEY` is a
  base64 32-byte key from the environment.
- **Key versioning:** settings hold `SECRETS_ENCRYPTION_KEYS = {1: key1, 2: key2}`
  and `SECRETS_ENCRYPTION_KEY_CURRENT = 2`. New secrets encrypt under the
  current key; `_decrypt()` picks the key by `key_version`. Rotation =
  add a new key, re-encrypt each row, retire the old key.
- If no key is configured, secret creation is refused with a clear error
  (fail closed) rather than storing plaintext.

### API

- `POST /api/secrets/` `{name, scope?, value}` → 201 with **name + metadata,
  no value**. platform_admin or workflow_designer.
- `GET /api/secrets/` → list of `{id, name, scope, last_used_at, created_at}` —
  never values.
- `DELETE /api/secrets/<id>/`.
- `POST /api/secrets/<id>/rotate/` `{value}` → replaces the ciphertext.
- No retrieve-value endpoint exists, by design.

### Redaction

A single `redact(text, secret_values)` helper runs over every hook execution
log, error message, and audit payload before persistence, replacing any known
secret value with `«redacted»`. The resolved secret set for a hook run is held
only in memory for the duration of the call.

---

## Part 2 — Action Hooks

### Model

```python
class TransitionHook(models.Model):
    id            = UUIDField(pk)
    transition    = FK(Transition, related_name="hooks")
    trigger       = CharField(choices=["before", "after"])
    action        = CharField(choices=["http_request", "probe"])   # script: later
    config        = JSONField   # {url, method, headers, body_template, timeout, expect_status}
    on_failure    = CharField(choices=["block", "warn", "ignore"], default="warn")
    output_to     = CharField(blank=True)     # "metadata.<key>" ← response (or json_path)
    order         = PositiveSmallInteger      # multiple hooks per transition run in order
    is_active     = BooleanField(default=True)
```

- **`before`** hooks run *before* the state changes. `on_failure=block` aborts
  the transition (like a rule) — this is how a health check gates a promotion.
- **`after`** hooks run once the state has changed — provisioning, downstream
  sync — and are async.
- **`http_request`**: full request with secret-templated headers/body.
- **`probe`**: a lighter GET that just asserts reachability / status — the
  "is this system up?" gate, no body.
- **`output_to`**: writes the response (optionally a JSON path of it) into
  `metadata_json`, so a hook result feeds rules and computed fields downstream.

### The transaction problem (the crux)

`perform_transition` is `@transaction.atomic` and validation runs inside it.
A synchronous `before` hook makes a network call — running that inside the
transaction would hold a DB transaction open across the wire (lock contention,
pool exhaustion). So the pipeline is **restructured**, not extended:

```
1. pre-flight (no transaction):
     - validate rules + required forms (read-only checks)
     - run `before` hooks with per-hook timeout + circuit breaker
     - on a `block` failure → abort here, nothing has changed
     - collect `output_to` metadata deltas
2. atomic transaction (fast, no network):
     - re-check the guard invariants (state unchanged since pre-flight)
     - apply metadata deltas, change state, save
3. post-commit (no transaction):
     - queue `after` hooks (Celery, reuses webhook delivery infra)
     - audit, event notifications
```

Step 2's re-check makes this safe under concurrency: if the instance moved
between pre-flight and commit, abort with a 409 (the optimistic-locking
pattern already used for metadata edits). `before` hooks must be treated as
**potentially side-effecting but idempotent-friendly** — documented, since a
retried transition may call them twice.

### Reuse, don't rebuild

- **`after` hooks** reuse the webhook delivery machinery wholesale: Celery
  task, exponential-backoff retries, dead-letter, delivery log, and the
  existing SSRF guard. A `HookExecutionLog` mirrors `WebhookDeliveryLog`
  (status, attempts, http_status, error, replay).
- **`before` hooks** reuse the rules-service **circuit breaker**
  (`apps/workflows/rules.py::CircuitBreaker`) so a flapping downstream doesn't
  make every transition hang on a timeout — after N failures the breaker
  opens and `before` hooks fast-fail per their `on_failure` policy.
- **SSRF guard** (private/loopback/link-local IP block) is shared across
  webhooks, triggers, and hooks — lift it into one `outbound.py` helper now
  that three features need it.

### Config templating

`config.url`, `headers`, and `body_template` support:
- `{{secret.NAME}}` → resolved from the secret store (worker only).
- `{{metadata.key}}` / `{{instance.reference_number}}` → from the instance.

Templating is a strict allow-list resolver (no arbitrary expression eval), and
the resolved values are redacted from all logs.

### Failure semantics

| `on_failure` | `before` hook fails | `after` hook fails |
|---|---|---|
| `block` | transition aborts, 409 + reason | n/a (after can't block) |
| `warn` | transition proceeds; a warning is recorded on the instance timeline | logged + retried, then dead-lettered |
| `ignore` | transition proceeds silently | logged only |

### What "houses the connection" means, concretely

The recurring example from the strategy chats — an Azure VM linked to test
hosts and devices — becomes live here:
- a **`probe` before-hook** on a "Bring Online" transition pings the VM and
  blocks the transition if it's unreachable;
- an **`http_request` after-hook** registers the host with a lab controller,
  writing the returned device id back via `output_to`;
- the **topology view** then shows the connection, and its freshness is real
  because a scheduled re-probe (a trigger on a timer) updates state.

That is the difference between *documenting* a connection and *maintaining*
one.

---

## Deliberately deferred

- **`script` actions** (arbitrary code) — needs a real sandbox
  (subprocess isolation / WASM); the `http_request` + `probe` actions cover
  most integrations without it.
- **Long-running / callback hooks** (fire, then wait for the external system
  to call back before completing) — needs a suspended-transition state in the
  engine; this is the fourth cell of the integration matrix and a separate
  design.

---

## Sequencing

| Step | Scope | Effort |
|------|-------|--------|
| 1 | **Secret store** — model, Fernet encryption + key versioning, write-only API, redaction helper, tests | 1–1.5 wk |
| 2 | **Shared `outbound.py`** — extract the SSRF guard from webhooks; add config templating + secret resolution | 3–4 days |
| 3 | **`after` hooks** — model + HookExecutionLog, reuse webhook delivery, `output_to`, admin/replay | 1 wk |
| 4 | **`before` hooks** — the pre-flight/commit/post-commit restructure of `perform_transition`, circuit breaker, `block`/`warn`/`ignore` | 1.5–2 wk |

Total ≈ 4–5 weeks. Steps 1–3 are additive and low-risk (nothing touches the
engine's core). Step 4 restructures the transition pipeline and is the one to
design-review carefully and cover with concurrency tests before shipping — the
`before`-hook transaction boundary is where correctness bugs would hide.
