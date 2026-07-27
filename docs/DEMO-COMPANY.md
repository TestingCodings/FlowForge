# Northwind Facilities — the demo company

**Status:** plan. Nothing here is built.

A prospective client shouldn't be shown "a workflow engine". They should be
shown **a company that already runs on it**, then told their own version is an
import away. This is the artefact that does that: a fictional SME with a
plausible, branded, exportable set of processes.

It doubles as the most demanding test the platform has — if every feature has
to earn its place in one coherent business, gaps show up fast.

---

## 1. The company

**Northwind Facilities** — a ~120-person commercial facilities-management firm
(cleaning, maintenance, compliance) operating across several client sites.

Chosen deliberately:

- **Unglamorous and legible.** Everyone understands a maintenance ticket. No
  domain explanation eats the first five minutes of a demo.
- **Genuinely multi-departmental** — operations, HR, finance, compliance, H&S
  — so the breadth is honest rather than five variations on a ticket.
- **Regulated enough to need audit trails and SLAs** without being so
  regulated the demo becomes a compliance lecture.
- **Not a software company.** Avoids the trap of demoing a dev-tool to people
  who don't build software.

Branding: its own name, logo, palette, and en-GB locale via the existing
`Workspace` config — so the first impression is "their system", not ours.

---

## 2. The workflow set

Grouped by department. **Shell** and **features** columns exist to keep this
honest: the point is comprehensive coverage, and anything with no feature
behind it is decoration.

### Operations
| Workflow | Shell | Exercises |
|---|---|---|
| Maintenance Request | kanban | SLAs, role gating, priority rules, photo evidence |
| Site Inspection | stepped_form | wizard, `file` fields, computed pass rate |
| Asset Register | table | computed rollups over child jobs |
| Incident Report | list | `before` hook to a mock alerting endpoint |

### People
| Workflow | Shell | Exercises |
|---|---|---|
| Leave Request | list | approvals, hierarchy rules |
| New Starter Onboarding | stepped_form | containers — one parent, many child tasks |
| Training & Certification | table | expiry via `age_days`, SLA breach |
| **Security Awareness Module** | **scene** | see §3 |
| **Manual Handling Module** | **scene** | see §3 |

### Finance
| Workflow | Shell | Exercises |
|---|---|---|
| Purchase Order | list | value-banded approval routing |
| Supplier Onboarding | stepped_form | secret store + outbound verification hook |
| Invoice Approval | table | `set_metadata` stamping, optimistic locking |

### Compliance & H&S
| Workflow | Shell | Exercises |
|---|---|---|
| Risk Assessment | matrix | risk × likelihood grid |
| Audit Finding | kanban | relationships to Incident Reports |
| Contract Renewal | calendar | date-driven view |

Fifteen workflows across four departments, covering **all seven shells** and
every major engine feature. Cross-department relationships are what make it
feel like one company rather than fifteen demos: an Audit Finding links to an
Incident Report, which links to a Maintenance Request, which hangs off an
Asset — and the topology view shows that as a single map.

---

## 3. Training delivered through the scene shell

This is the strongest idea in the brief and worth stating plainly: **the scene
shell turns mandatory training from a document into an interactive module**,
using machinery that already exists.

A security-awareness module is a branching story:

```
scene           = state           ("An email arrives from 'IT Support'")
choice          = transition      ("Click the link" / "Check the sender" / "Report it")
consequence     = rule            a wrong choice blocks progress with a reason
score / flags   = metadata        set_metadata records each decision
completion      = terminal state  passed vs. must-retake
attempt         = instance        each employee's run is their own record
```

Why this is more than a gimmick:

- **It's auditable by construction.** Completion is an instance with an
  immutable audit trail — who took it, when, what they chose. That is exactly
  what a compliance officer needs and what a slide deck cannot give them.
- **It links to the rest of the business.** A Training record can gate a
  transition elsewhere: no Manual Handling certificate, no assignment to a
  lifting job. That's a rule over a computed field, not new code.
- **Expiry is already modelled.** `age_days` plus an SLA turns "annual
  refresher" into the platform chasing people automatically.

Two modules, chosen to show range:

1. **Security Awareness — phishing.** Four scenes, two endings. One path is
   gated: you cannot reach "Report it correctly" without having checked the
   sender, and the block reason *is* the teaching moment.
2. **Manual Handling.** Assessment-style, feeding a computed score. Below
   threshold routes to "Retake", which demonstrates a loop rather than a
   straight line.

Both need illustrative artwork. That is the one genuine dependency, and it's
addressed in §6.

---

## 4. What the demo needs that doesn't exist yet

Being explicit, because "build a demo company" sounds like content work and
is partly platform work.

| Gap | Needed for | Size |
|---|---|---|
| **Multi-workflow export** — `export_workflow` handles one workflow; a bundle is `kind: "flowforge.workflow"` | Shipping the pack as one file | Medium — the App bundle in [APPS.md](APPS.md) Phase 3 |
| **Identity in the bundle** — branding lives in the `Workspace` singleton and isn't exported | "Branded and exportable" | Small once the bundle is versioned |
| **Custom role names** — Northwind needs "Site Manager", not "Approver" | Credibility | [ROLES.md](ROLES.md) Phases 1–3 |
| **Scene authoring UI** — `scene_config` is hand-written JSON today | Anyone but me building modules | Medium |
| **Seed content as data** — the seed is a Python literal | Fifteen workflows as code is unmaintainable | Small — load from bundles |

Nothing here is blocked; the demo can be built incrementally against what
exists, with the bundle work landing underneath it.

---

## 5. Phasing

Each phase is demonstrable on its own. That matters: a half-built demo company
must still be showable, or it can't be worked on between client conversations.

**Phase 1 — Vertical slice (highest value per hour).**
Three workflows that *relate to each other*: Maintenance Request → Asset
Register → Incident Report. Branded workspace. Real cross-links so the
topology view has something to show. This alone is a better demo than the
current seed, because it's one story instead of five samples.

**Phase 2 — One scene module.**
Security Awareness, end to end, with real artwork. The single most
differentiating thing in the whole pack.

**Phase 3 — Departmental breadth.**
Fill out People and Finance. Now the "we could run our whole company on this"
claim is visible rather than asserted.

**Phase 4 — Package it.**
Multi-workflow bundle + identity. `manage.py load_app northwind` becomes the
demo reset, and the same file is what a client receives.

**Phase 5 — Compliance & H&S + second module.**
Completes the set and the matrix/calendar shell coverage.

---

## 6. Risks and honest constraints

**Artwork is the real dependency.** Scene modules need backgrounds and
character art or they look like a prototype. Options, in order of preference:
commission a small consistent set; use a permissively-licensed asset pack
(check the licence permits commercial demo use); or design the modules around
typography and flat colour, which can look deliberate rather than unfinished.
Do not ship placeholder art in a client demo — it reads as "unfinished
product", which is precisely the opposite of the intended message.

**Fifteen workflows is a lot of content.** Half-finished workflows are worse
than fewer complete ones. The phasing exists so that stopping after Phase 2 or
3 still leaves something coherent.

**Fictional but not misleading.** Northwind must be obviously fictional — no
real company's name, logo, or data. The demo deployment already resets
nightly, and demo content must never include anything resembling real
personal data.

**Training content carries a duty of care.** A phishing module is fine. Manual
handling touches physical safety, and a module that teaches it *wrong* is a
liability, not a feature. Either keep the content generic enough to be
illustrative, have it reviewed by someone qualified, or label it explicitly as
a demonstration of the mechanism rather than actual training. My recommendation
is the last one, clearly stated in the module itself.

**This is a portfolio piece and a sales asset at once.** Those pull in
different directions — a portfolio rewards showing every feature, a sales
demo rewards showing one thing that lands. The phasing favours the sales cut,
with breadth arriving later.
