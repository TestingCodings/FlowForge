# Strengthening VISION Layers 1 & 2

> **Status (2026-07-22):** every Layer 1 & 2 gap except L1.4 is
> implemented (L2.1–L2.6, L1.1–L1.3). L1.4 (multi-tenancy) is
> deliberately deferred to Layer 3.

Gap analysis of what [VISION.md](VISION.md) specifies for Layers 1–2 against
what is actually built (July 2026), with a prioritised plan to close it.

Both layers were marked "complete" in July, but that was measured against a
narrower reading of the spec. Re-reading VISION.md line by line, several
explicitly-specified capabilities are missing — most of them in Layer 2,
which is where the product's differentiation lives.

---

## Layer 1 — Theme + Layout per Workspace

### Built
Workspace singleton with `ui_config`; 15 theme tokens; four presets
(Midnight / Daylight / Ocean / Forest) incl. working light mode; font
selection; `date_format` with shared `formatDate` helpers; `logo_url`;
name/tagline; server-side `ui_config` validation.

### Gaps

| # | Gap | Spec reference | Effort |
|---|-----|----------------|--------|
| L1.1 ✅ | **`default_view` unused** — spec makes it a workspace-level default ("Kanban vs list, condensed vs spacious"); today the shell is only per-workflow, so a workspace has no fallback presentation | `"default_view": "kanban"` | 2–3 days |
| L1.2 ✅ | **`locale` absent** — no i18n scaffolding at all; dates honour a format string but nothing else localises | `"locale": "en-GB"` | 1–2 weeks (see ENHANCEMENT 3.1) |
| L1.3 ✅ | **Density preference absent** — "condensed vs spacious" has no implementation; a `density` token driving spacing vars would satisfy it | Layer 1 prose | 2–3 days |
| L1.4 | **Workspace is a singleton** — spec says "*each* team or client gets a workspace". True per-tenant workspaces need an FK from users/workflows and request-scoped resolution | Layer 1 opening | 2–3 weeks |

**Assessment:** L1.1 and L1.3 are quick and close the letter of the spec.
L1.2 (i18n) is genuinely valuable and already scoped in ENHANCEMENT 3.1.
L1.4 is real multi-tenancy — arguably Layer 3 work; deliberately deferred
because it touches every query in the codebase and the demo doesn't need it.

---

## Layer 2 — Custom UI Shell per Workflow

### Built
`ShellProps` contract + `SHELL_REGISTRY`; kanban (drag-to-transition),
table (configurable columns), calendar (configurable date field); visual
PresentationPanel configurator; per-state colours; `ui_schema` validation
shared by the API and bundle import; documented in [SHELLS.md](SHELLS.md).

### Gaps

| # | Gap | Spec reference | Effort |
|---|-----|----------------|--------|
| L2.1 ✅ | **Matrix shell missing** — the TestRail-style shell appears in both the capability table and the router listing, and the repo already ships TestRail seed workflows that have nothing to render them | `shell="matrix" → MatrixView` | 1–2 weeks |
| L2.2 ✅ | **Swimlanes missing** — kanban config specifies `swimlanes: "metadata.epic"`; today kanban groups by state only | `"swimlanes": "metadata.epic"` | 4–5 days |
| L2.3 ✅ | **`instance_view` config ignored** — spec lets a workflow choose its detail-page title field, which panels appear, and the layout; today every instance page is identical and hard-coded | `"instance_view": {...}` | 1 week |
| L2.4 ✅ | **`state_display.icon` ignored** — colours are honoured, icons in the same object are silently dropped | `{"colour": "...", "icon": "play"}` | 2–3 days |
| L2.5 ✅ | **Stepped-form shell missing** — the Typeform-style shell is in the capability table | "Stepped-form shell" | 1 week |
| L2.6 ✅ | **`list` shell isn't a real shell** — it's the default page rather than a registry entry, so it can't be configured like the others and the registry has a hole | Router listing | 2–3 days |

**Assessment:** L2.1–L2.4 are the ones that matter. The matrix shell is the
single most valuable missing piece: it's the only shell that renders a
*cross-product* (test cases × runs) rather than a list, it's named twice in
the spec, and the seed data for it already exists. `instance_view` is the
difference between "configurable board" and "configurable application" —
right now every workflow's detail page looks the same no matter how
distinctive its board is.

---

## Recommended order

| Order | Item | Why first |
|-------|------|-----------|
| 1 | **L2.1 Matrix shell** | Highest-value gap; seed data exists; completes the shell router as specified |
| 2 | **L2.3 `instance_view`** | Extends configurability from the board to the record — biggest perceived-depth gain |
| 3 | **L2.2 Swimlanes + L2.4 icons** | Small, visible polish on the shell users see most |
| 4 | **L1.1 `default_view` + L1.3 density** | Cheap, closes Layer 1's letter |
| 5 | **L2.6 list-as-shell** | Tidies the registry once the others are in |
| 6 | **L1.2 i18n** | Valuable but self-contained; can run in parallel with anything |
| — | L1.4 multi-tenancy | Deferred: real per-tenant isolation is Layer 3 in disguise |

Items 1–4 total roughly 4–5 weeks and leave Layers 1 and 2 genuinely
matching the spec rather than approximately matching it.
