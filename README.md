# FlowForge

A configurable business workflow automation platform. Define states, transitions, forms, rules, and approvals through configuration — not code. The same engine powers an insurance claims process, an HR onboarding flow, a software bug lifecycle, or any other multi-step approval chain.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 5 + Django REST Framework |
| Rule Engine | FastAPI microservice |
| Database | PostgreSQL 16 |
| Task Queue | Celery + Redis |
| Frontend | React + TypeScript (Phase 8) |
| Infrastructure | Docker, GitHub Actions, AWS |

## Quick Start (Development)

**Prerequisites:** Docker Desktop, Python 3.12+

```bash
# 1. Clone the repo
git clone https://github.com/<your-username>/flowforge.git
cd flowforge

# 2. Copy the example env file
cp backend/.env.example backend/.env

# 3. Start all services
docker compose up --build

# 4. The API is now available at http://localhost:8000
#    Mailhog UI at http://localhost:8025
#    Django Admin at http://localhost:8000/admin/
```

## API Endpoints (Phase 1)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/auth/register/` | Create a new user account | Public |
| `POST` | `/api/auth/login/` | Obtain access + refresh tokens | Public |
| `POST` | `/api/auth/refresh/` | Refresh an access token | Public |
| `GET` | `/api/health/` | Health check | Public |

## Running Tests

```bash
cd backend
pip install -r requirements.txt
pytest
```

## Project Structure

```
flowforge/
├── backend/          # Django project
├── rules-service/    # FastAPI rule evaluation microservice (Phase 5)
├── frontend/         # React + TypeScript SPA (Phase 8)
├── .github/          # GitHub Actions CI/CD
└── docker-compose.yml
```

## Development Phases

See [implementation.md](implementation.md) for the full breakdown.

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | Foundation — Auth, Docker, CI | ✅ Complete |
| 2 | Workflow Engine — State Machine | 🔜 Next |
| 3 | Form Builder | — |
| 4 | Task System | — |
| 5 | Rule Engine + FastAPI | — |
| 6 | Audit System | — |
| 7 | Notification Engine | — |
| 8 | React Frontend | — |
| 9 | Testing | — |
| 10 | AWS Deployment | — |
