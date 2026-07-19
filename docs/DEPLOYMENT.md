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

`production.py` is already correct: `DATABASE_URL` + SSL, HSTS, secure
redirects, env-driven `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS`.

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
   `DJANGO_SETTINGS_MODULE=config.settings.demo`. Never committed.
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
