# FlowForge Implementation Efficiency Playbook

## Objective

Optimise implementation speed and quality while minimising unnecessary token usage during AI-assisted development.

## Core Principles

1. Build only what the current phase requires.
2. Prefer small, testable increments over broad scaffolding.
3. Keep prompts short, explicit, and constraint-driven.
4. Reuse existing patterns instead of regenerating boilerplate.
5. Validate early with targeted tests before full-suite runs.

## Token-Efficient Working Rules

### 1. Scope Control Per Task

For every request, define:
- In scope: exact files/features to change now.
- Out of scope: what must not be touched.
- Done condition: concrete acceptance criteria.

Use this format before implementation:

- Goal:
- Files expected:
- API/behavior to add:
- Tests to pass:
- Non-goals:

### 2. Minimise Exploration Cost

- Read only files needed for the task.
- Prefer narrow searches over full-repo dumps.
- Avoid repeatedly reading the same file unless it changed.
- Batch read-only lookups in parallel.

### 3. Minimise Edit Cost

- Edit only changed regions.
- Keep each file patch focused on one concern.
- Avoid unrelated refactors while implementing a phase.
- Reuse existing serializers/viewsets/config style.

### 4. Test Efficiently

Test pyramid for fast feedback:

1. Run focused tests for changed module(s).
2. Run phase-level tests.
3. Run full backend suite only when focused tests pass.

Command pattern:

```powershell
# Fast check (module)
python -m pytest apps/workflows/tests.py -q

# Phase check (affected modules)
python -m pytest apps/workflows/tests.py apps/accounts/tests.py

# Full suite
python -m pytest
```

### 5. Error Handling Discipline

When a command fails:

1. Capture exact error.
2. Apply smallest fix.
3. Re-run only the failed command/test first.
4. Escalate to broader test runs after green status.

### 6. Prompt Hygiene (for AI requests)

Use concise prompts with structure:

- Task:
- Constraints:
- Acceptance criteria:
- Files to touch:
- Files not to touch:

Avoid open-ended prompts like "build everything" or "refactor all".

### 7. Prevent Redundant Tokens

- Do not ask for restatements of unchanged plans.
- Do not reprint full files after small edits.
- Summarise command output, keep only key lines.
- Report only deltas since previous update.

### 8. Branch and Commit Strategy

- One phase = one feature branch.
- One logical change = one commit.
- Commit message format:
  - feat: phase 2 workflow engine core
  - test: add transition validation tests
  - fix: enforce workflow-state consistency

This keeps context narrow and avoids repeated re-analysis.

## Phase-by-Phase Implementation Cadence

For each phase:

1. Define data model and contracts.
2. Implement pure domain logic.
3. Add API layer.
4. Add targeted tests.
5. Run focused tests, then full suite.
6. Commit.

## Definition of Efficient Done

A task is efficiently done when:

- Acceptance criteria are met.
- Only required files changed.
- Focused tests pass.
- Full-suite run is green (or explicitly deferred with reason).
- No speculative code for future phases was added.

## Anti-Patterns to Avoid

- Over-scaffolding future phases.
- Running full test suites after every tiny edit.
- Touching formatting/imports globally without need.
- Rewriting stable code for style preferences.
- Long narrative updates that do not change execution.

## Practical Checklist

Before coding:
- [ ] Scope and acceptance criteria are explicit.
- [ ] Target files identified.

During coding:
- [ ] Small patches only.
- [ ] Validate with module-level tests.

Before handoff:
- [ ] Acceptance criteria verified.
- [ ] Full relevant tests run.
- [ ] Summary includes only meaningful deltas.
