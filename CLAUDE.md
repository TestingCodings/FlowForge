# Working in this repo

## Check the backend isn't stale before believing a result

The dev server runs with `--noreload` (Django's StatReloader hangs on the
maintainer's Windows machine), so **it keeps serving whatever code it loaded
at boot**. Editing a backend file changes nothing until the process is
restarted.

This has repeatedly presented as a code bug: a fix that "doesn't work", a
feature that "broke", once nearly reported against someone else's pull
request. Every time, the code was correct and the process was old.

**After changing any backend file, check before drawing a conclusion:**

```bash
curl -s http://localhost:8000/api/health/
```

`"stale": true` means the process predates your edit — restart it. The
response also carries `revision` (the commit it's running) and `started_at`.
Staleness is only computed when `DEBUG` is on.

Restarting on Windows (`pkill` does not work here):

```bash
powershell -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -like '*runserver*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"
```

Then start it again via `.claude/launch.json`, or directly — it needs both
`--noreload` and `--settings=config.settings.local_sqlite`. Without the
settings flag it defaults to `config.settings.local`, which targets Postgres
and hangs silently, because Docker does not work on this machine.

## Tests

```bash
cd backend && DJANGO_SETTINGS_MODULE=config.settings.local_sqlite python -m pytest -q
cd frontend && npm run build          # tsc -b, strict — an implicit any fails CI
```

E2E needs both servers up, and the tags set at generation time as well as run
time:

```bash
cd frontend
export E2E_TAGS="@smoke or (@core and not @wip)" E2E_BASE_URL=http://localhost:5173
npx bddgen && npx playwright test --project=chromium
```

**Run E2E with `--workers=1`.** The shell scenarios mutate shared seeded
workflows' `ui_schema`, so parallel workers race and a different scenario
fails each run. Serially it is reliable. The real fix is per-scenario
fixtures; until then, a failure under parallel workers is not evidence of a
regression.

**E2E depends on seeded data.** Run `manage.py seed --reset --testrail`
first. Do not generate demo content by exporting a working database — the
suite rewrites `ui_schema` on several seeded workflows, and those mutations
get captured as if they were the seed's own output.

## Demo content

Content lives as YAML in `backend/apps/workflows/content/` and loads through
the same importer a client's app would use:

```bash
python manage.py load_app demo --reset      # Northwind slice
python manage.py load_app classic           # the original seeded set
```

`tests/integration/test_seed_port_equivalence.py` asserts `load_app classic`
reproduces `seed --testrail`. Keep it passing — it is the evidence that the
YAML path is faithful.
