# FlowForge Public Demo Deployment — flowforge.cortexa.solutions

Goal: a public, always-populated, safe-to-poke demo of FlowForge on a
subdomain of cortexa.solutions, linked from the landing page. This is the
VISION Layer 3 "subdomain hosting" milestone in its smallest viable form.

Status: plan (July 2026). Nothing here is deployed yet.

---

## 1. Architecture

One small VPS (Hetzner CX22 / DigitalOcean basic droplet, 2 vCPU / 4 GB,
~€5–10/mo) running the existing docker-compose stack plus a reverse proxy.
The laptop's Docker/DISM problem is irrelevant here — the server is Linux.

```
cortexa.solutions          → existing landing page hosting (unchanged)
flowforge.cortexa.solutions → VPS
    Caddy (TLS, reverse proxy, static frontend)
      ├── /            → frontend dist/ (static files)
      └── /api, /admin → gunicorn :8000
    docker compose services:
      db (postgres:16) · redis:7 · backend (gunicorn)
      worker (celery -A config worker)
      beat (celery -A config beat)
```

- **Caddy** over nginx: automatic TLS via Let's Encrypt, 10-line config.
- **Frontend** is a static Vite build (`npm run build`) served by Caddy —
  no Node process in production. Built with
  `VITE_API_BASE_URL=https://flowforge.cortexa.solutions/api`.
- **Celery worker + beat** are required, not optional: async webhooks,
  SLA scheduler, and webhook retries all live there now.
- Postgres data on a named volume; nightly `pg_dump` to the host (7-day
  rotation) is sufficient backup for a demo.

### docker-compose changes needed (new `docker-compose.prod.yml`)
- Add `worker` and `beat` services (same image as backend, different command)
- Add `caddy` service with mounted Caddyfile + frontend `dist/`
- Remove mailhog, remove backend port exposure (only Caddy binds 80/443)
- Backend env: `DJANGO_SETTINGS_MODULE=config.settings.production`

`production.py` covers `DATABASE_URL` + SSL, HSTS, secure redirects, and
env-driven `ALLOWED_HOSTS` / `CORS_ALLOWED_ORIGINS`. Two things it did *not*
cover, both found while building this and both now fixed:

- It configured object storage with `DEFAULT_FILE_STORAGE` /
  `STATICFILES_STORAGE`, which **Django 5.1 removed**. They were silently
  ignored, so `STORAGES["default"]` still resolved to `FileSystemStorage` —
  a real deployment would have written every uploaded `MediaAsset` to
  container-local disk, losing it on redeploy and hiding it from the other
  workers. Now set via `STORAGES`.
- There was **no Celery app at all** (`config/celery.py` did not exist), so
  `celery -A config worker` could not start and nothing in
  `CELERY_BEAT_SCHEDULE` had ever run. Call sites fall back to inline
  execution when `.delay()` raises, which is why this was invisible in dev:
  webhooks and action hooks were running synchronously inside the request.
  Added, with `autodiscover_tasks(related_name="hooks")` so
  `execute_hook_task` is registered too.

The demo overrides the rest in `config/settings/demo.py` (no DB SSL against
a same-network container, local disk instead of S3, console email).

---

## 2. Demo mode

A new settings module `config/settings/demo.py` extending `production.py`.
Demo mode is settings + a management command, not code forks.

### 2.1 Seeded accounts & nightly reset
- `python manage.py seed --testrail` already builds a populated workspace.
- New management command `reset_demo`: flush app tables (keep migrations),
  re-run seed, print nothing sensitive. Wired to Celery Beat
  (`reset-demo-nightly`, 03:00 UTC) — no host cron needed.
- Demo credentials rendered on the login screen (existing local pattern).
  The "no credentials in public files" rule applies to the README, not the
  demo login page — the whole point is that visitors can sign in.
- Each role gets an account (admin / designer / approver / participant /
  viewer) so reviewers can see the permission system, which is a
  differentiator.

### 2.2 Abuse hardening (blocking issues before going public)

| Risk | Mitigation |
|------|------------|
| **Webhook SSRF** — user-defined webhook URLs fired from the server can probe the VPS's network (cloud metadata, localhost, db) | Demo settings flag `WEBHOOK_ALLOWED_HOSTS`; delivery task refuses URLs whose resolved IP is private/loopback/link-local, and optionally only allows e.g. `webhook.site`. This check belongs in `deliver_webhook` so it also protects real deployments |
| Open registration → spam accounts | `DEMO_REGISTRATION_ENABLED=False`; register page shows "use a demo account" |
| API abuse / scraping | DRF throttling: `AnonRateThrottle` 20/min, `UserRateThrottle` 120/min (demo values) |
| Email spam via notifications | Console email backend in demo (no SMTP creds on the box at all) |
| Django admin exposure | `/admin` allowed but only the seeded superuser works; fails2ban-style rate limit via Caddy on `/admin/login` |
| Large uploads / payloads | `DATA_UPLOAD_MAX_MEMORY_SIZE` 2 MB; Caddy `request_body max_size 5MB` |

### 2.3 Demo UX niceties (non-blocking, post-launch)
- Banner: "Public demo — data resets nightly at 03:00 UTC"
- `/health` endpoint for uptime monitoring (UptimeRobot free tier)

---

## 3. Landing page integration (cortexa repos)

Smallest change to `cortexa-frontend`: a product section/card —
headline, 2–3 screenshots from `docs/screenshots/`, one-paragraph pitch,
two buttons: **Launch live demo** → `https://flowforge.cortexa.solutions`
and **Source** → the GitHub repo. No iframe embedding — different origin,
auth, and viewport assumptions make iframes strictly worse than a link.

Pitch draft: "FlowForge — a configurable workflow platform. Model any
process as states, transitions, and rules; get forms, SLAs, audit trails,
webhooks, and role-based boards without writing code. Built with Django,
React, and Celery."

Also worth adding: `README.md` gets a "Live demo" badge/link at the top,
and the CV links the demo rather than the repo.

---

## 4. Runbook (first deploy)

1. **DNS**: A record `flowforge.cortexa.solutions` → VPS IP (wherever
   cortexa.solutions DNS is managed). TLS is automatic once Caddy sees it.
2. **VPS**: install Docker + compose plugin; create `/opt/flowforge`;
   clone repo.
3. **Secrets**: write `backend/.env` on the server —
   `DJANGO_SECRET_KEY` (fresh), `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL`,
   `REDIS_URL`, `CORS_ALLOWED_ORIGINS=https://flowforge.cortexa.solutions`,
   `DJANGO_SETTINGS_MODULE=config.settings.demo`, and
   `SECRETS_ENCRYPTION_KEY_V1` (the secret-store Fernet key — generate with
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`;
   without it the secret store fails closed and action hooks can't run).
   Never committed.
4. **Frontend build**: `npm ci && npm run build` (in CI or on the VPS),
   output mounted into Caddy.
5. `docker compose -f docker-compose.prod.yml up -d` → migrate runs on
   backend start; run `seed --testrail` once manually.
6. **Verify**: login as each role, fire a transition, check
   `/api/webhooks/` blocked-URL behavior, confirm beat tasks in logs.
7. **Monitor**: UptimeRobot on `/health`; `docker compose logs` is enough
   observability until ENHANCEMENT 4.1 lands.

Ongoing: `git pull && docker compose build backend && docker compose up -d`
per release. GitHub Actions deploy-over-SSH can come later.

---

## 5. Effort estimate & order

| Step | Effort |
|------|--------|
| `demo.py` settings + throttles + registration flag | 0.5 day |
| Webhook SSRF guard + tests | 0.5–1 day |
| `reset_demo` command + beat schedule + tests | 0.5 day |
| `docker-compose.prod.yml` + Caddyfile + frontend build wiring | 0.5–1 day |
| VPS provision, DNS, first deploy, per-role verification | 0.5–1 day |
| Landing page card in cortexa-frontend | 0.5 day |

**Total: roughly one focused week.** The SSRF guard and reset command are
real repo code (with tests, committable now, useful beyond the demo); the
rest is server-side configuration. Recommended order: repo code first
(deployable any time), then the VPS steps in one sitting.

---

## 6. Dependency audit policy

CI gates on vulnerabilities, but the two halves of the dependency tree carry
different risk, so they are treated differently:

| Scope | Command | Gates CI? |
|---|---|---|
| Backend (all) | `pip-audit -r backend/requirements.txt --no-deps` | **Yes** |
| Frontend **production** | `npm audit --omit=dev --audit-level=high` | **Yes** |
| Frontend **dev tooling** | `npm audit --audit-level=high` | No — informational |

**Why the frontend gate is scoped to production dependencies.** Only
production dependencies are bundled by Vite and served to a browser. Dev
tooling (`vite`, `esbuild`) runs on a developer's laptop and in CI; it is
never part of a deployed artefact. Gating on it means an advisory in the
local dev server can block a release that the advisory cannot possibly
affect — which trains people to ignore the gate, the opposite of what it's
for. The dev audit still runs and still prints, so the advisories stay
visible and get upgraded deliberately.

**Currently accepted (dev-only, not shipped), as of 2026-07-26:**

- `vite <=6.4.2` — path traversal in optimised-deps `.map` handling,
  `server.fs.deny` bypass on Windows alternate paths, and `launch-editor`
  NTLMv2 hash disclosure via UNC paths. All three describe the **dev
  server**. Fix requires Vite 8 (major); schedule it as a deliberate upgrade
  with a full build + E2E pass, not as an emergency patch.
- `esbuild <=0.24.2` (transitive via Vite) — dev server request forgery.
  Clears with the same Vite upgrade.

**This exemption is for dev tooling only.** If a *production* dependency
ever needs an exception, do not widen this scope — pin the fix, or record
the exception explicitly with an expiry date and an owner.

---

## 7. What is and isn't verified

Being explicit about this, because "the config exists" and "the config works"
are different claims and only one of them has been demonstrated.

**Verified by test or by running it:**

- `config/settings/demo.py` imports, and its deltas from production are
  asserted (`tests/integration/test_demo_settings.py`, 14 tests) — including
  that it does not drop base's throttle scopes or Beat entries.
- Registration is refused when `DEMO_REGISTRATION_ENABLED=False`, with a
  message pointing at the demo accounts, and no user row is created
  (`test_demo_mode.py`, 5 tests).
- `reset_demo` seeds from empty, is idempotent, restores a deleted demo user,
  survives **nested instances**, and prints no credentials
  (`test_reset_demo.py`, 8 tests). Also run for real, twice in a row.
- The Celery app loads and every task the code enqueues is registered,
  including `execute_hook_task`; every Beat entry points at a task that
  actually exists (`test_celery_app.py`, 10 tests).
- `docker-compose.prod.yml` parses and interpolates: verified with
  `docker compose config`. The `:?` guards do fail the run when
  `POSTGRES_PASSWORD` / `DJANGO_SECRET_KEY` / `SECRETS_ENCRYPTION_KEYS` are
  unset, which was checked by omitting them.

**Not verified — must be checked on first deploy:**

- **The stack has never been brought up.** Docker cannot run on the
  development laptop (DISM), so `docker compose up` is untested end to end.
  Expect the first deploy to be a debugging session, not a formality.
- **The Caddyfile has never been parsed.** No `caddy` binary was available to
  run `caddy validate`. Run it on the VPS *before* pointing DNS:
  `docker run --rm -v $PWD/Caddyfile:/etc/caddy/Caddyfile caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile`
- **Admin-login rate limiting is not enabled** — the `rate_limit` directive
  needs a third-party module the official image lacks. See the note in the
  Caddyfile for the xcaddy build that turns it on.
- **The frontend does not yet render `DEMO_RESET_NOTICE`**; the setting
  exists but nothing consumes it, so visitors get no banner warning that data
  resets nightly.
- Backups (`pg_dump` rotation) and uptime monitoring are not set up.

---

## 8. Public shopfront on cortexa.solutions

**Status:** planned. Blocked on the VPS, same as the rest of §1-§7.

A page on the existing cortexa.solutions site, linked from the header, that
explains FlowForge and lets a visitor try it. The audience is colleagues and
prospective employers who will arrive from LinkedIn, so the page has to work
without any prior context.

### What goes on it
- A short explanation of what FlowForge is and the problem it solves.
- The quality report: test counts, coverage, CI gates, and the gaps. Real
  numbers are the strongest signal for this audience, and naming the gaps is
  what makes the good numbers believable.
- A feature summary with screenshots.
- Buttons into the live demo.

### How a visitor gets in
**Pre-made accounts, one click per role.** Not a signup form.

Self-registration is disabled on the demo on purpose (§2.2: open registration
on a public box is a spam-account vector). Re-enabling it would mean rate
limits, expiry, and cleanup, all to produce a worse demo. A row of buttons
reading "Try as Site Manager", "Try as Approver", "Try as Viewer" gets someone
into the product in one click and shows off the role system before they have
clicked anything else.

Implementation: `/api/demo-info/` already serves the demo accounts when
`DEMO_MODE` is on, and already returns nothing anywhere else. The page reads
it and posts to `/api/auth/login/`. No new endpoint needed.

### Stats are a snapshot, not a live feed
Numbers are baked in with an "as of" date and regenerated when the suite
changes materially. A live CI badge would eventually show a prospective
employer a red build, or a run in progress, with no context. A snapshot is
always a number somebody has looked at.

### Order of work
1. VPS, DNS, first deploy (§7 lists what is still unverified).
2. Demo account buttons wired to `/api/demo-info/`.
3. The page itself in the cortexa-frontend repo, plus the header link.
4. Screenshots refreshed from the deployed demo rather than local.

Step 1 gates everything else. Nothing here is worth building against a demo
that has never run.
