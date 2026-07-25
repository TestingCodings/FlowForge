# FlowForge Testing Strategy

How FlowForge is tested, why the tools were chosen, and how tests gate merges
and releases.

---

## The testing pyramid here

| Layer | Tool | Scope | Where |
|-------|------|-------|-------|
| **Unit** (backend) | pytest | pure logic — rules engine, ui_schema validation, DSL parser, circuit breaker, state machine | `backend/apps/**/tests*.py`, `backend/tests/unit/` |
| **Integration** (backend) | pytest + DRF `APIClient` | API endpoints against a real Postgres, role enforcement, engine transitions, compose/versioning | `backend/tests/integration/` |
| **End-to-end** (frontend) | **Playwright + playwright-bdd** | the app as a user drives it, through the real UI against the real API | `frontend/e2e/` |

The backend already has strong unit + integration coverage (178+ tests). This
document is mostly about the **new E2E layer**, which was the gap: nothing
exercised the React app itself.

---

## Why Playwright + playwright-bdd

The brief was "feature files documenting the intended flow of every feature,
then build an efficient suite from them." That is Behaviour-Driven
Development: Gherkin `.feature` files as living specification, executed as
tests so they can't drift from reality.

**Options considered:**

- **Robot Framework** — mature and keyword-driven, genuinely good where
  non-developers author tests. But it is Python-driven, so testing a
  TypeScript/React SPA means maintaining a second language's keyword layer,
  and its browser automation is Playwright/Selenium underneath anyway. The
  indirection buys nothing here and costs a language boundary.
- **Selenium** — the old default: no auto-waiting (so chronically flaky
  without hand-rolled waits), slower, more boilerplate, weaker debugging.
- **Playwright** — native TypeScript (one language across app and tests),
  auto-waiting (dramatically less flake), parallel execution, and the trace
  viewer, which makes a CI failure a replayable recording rather than a
  guessing game.

**`playwright-bdd`** runs Gherkin `.feature` files on the Playwright engine.
Features are the specification; step definitions bind Gherkin to Playwright
actions. A feature can't pass unless its steps are implemented, so the
documentation stays honest.

### Why not React Testing Library (component tests)?
RTL is valuable and may be added later for isolated component logic, but the
highest-value gap was *whole-flow confidence* — that login → build a workflow
→ create an instance → transition it actually works through the real stack.
E2E buys that first. Component tests are a Tier-2 follow-up.

---

## Layout

```
frontend/e2e/
  features/              Gherkin specs — the living documentation
    auth.feature
    dashboard.feature
    workflows.feature
    builder.feature
    yaml-authoring.feature
    shells.feature
    instances.feature
    forms.feature
    workspace.feature
  steps/                 step definitions (Given/When/Then → Playwright)
    fixtures.ts          shared BDD fixtures (auth, seeded data helpers)
    *.steps.ts
  playwright.config.ts
```

Feature files are grouped by product area and tagged:
- `@smoke` — the minimal path that proves the app boots and core flows work;
  runs on every push, must stay under ~2 minutes.
- `@core` — the primary happy paths for each feature; runs on PRs to main.
- `@full` — edge cases and secondary flows; runs nightly and pre-release.

---

## Running locally

```bash
cd frontend
npm install
npx playwright install --with-deps chromium
npm run test:e2e            # all tests, headless
npm run test:e2e:smoke      # @smoke only
npm run test:e2e:ui         # Playwright UI mode for debugging
```

E2E needs both servers up and a seeded database. The Playwright config starts
the Vite dev server automatically (`webServer`); the Django API + seed must be
running separately (or in CI, as a job step). Tests authenticate through the
seeded demo accounts (`admin@flowforge.dev` etc.) created by
`python manage.py seed --testrail`.

---

## CI integration

Two jobs in `.github/workflows/ci.yml`:

1. **backend** (existing) — pytest against Postgres + Redis, uploads coverage.
2. **e2e** (new) — boots Postgres/Redis, migrates + seeds, starts the Django
   API and the Vite preview build, then runs `@smoke` + `@core` Playwright
   tags. Uploads the HTML report and traces on failure.

Branch protection on `main` requires both jobs green. The `@full` set runs on
a nightly schedule and before tagging a release, to keep PR latency low.

---

## Conventions

- **Selectors:** prefer role/label/text queries (`getByRole`, `getByLabel`) —
  they double as accessibility checks. Add `data-testid` only where semantic
  queries are ambiguous.
- **Isolation:** each scenario is independent; never rely on ordering. Data a
  scenario mutates (transitions, submissions) is created by that scenario or
  targets a workflow it owns.
- **No hard waits:** rely on Playwright auto-waiting and web-first assertions
  (`expect(locator).toBeVisible()`), never `waitForTimeout`.
- **One assertion theme per scenario:** a scenario proves one behaviour.
