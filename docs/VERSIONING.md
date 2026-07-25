# Versioning & Release Policy

From v0.9.0 onward, FlowForge follows [Semantic Versioning](https://semver.org)
and ties releases to git tags and the [CHANGELOG](../CHANGELOG.md).

## The scheme

`MAJOR.MINOR.PATCH`, where a "public surface" is the REST API, the
`.flowforge.json` bundle format, the `ui_schema`/`ui_config` shapes, and the
YAML DSL.

- **MAJOR** — backwards-incompatible change to any public surface (a removed
  endpoint, a renamed `ui_schema` key, a bundle format break). Pre-1.0 these
  are allowed in MINOR bumps but must be called out in the changelog.
- **MINOR** — new backwards-compatible capability (a new shell, a new
  endpoint, a new `ui_config` key).
- **PATCH** — backwards-compatible bug fixes and internal changes only.

While the project is pre-1.0, MINOR is the effective "feature release" and
PATCH is "fixes only" — the history in CHANGELOG.md already follows this.

**1.0.0** is reserved for when the public API and bundle format are declared
stable (tentatively after Layer 3 / multi-tenancy lands).

## Where the version lives

The single source of truth is a `VERSION` file at the repo root. It is read by:
- `backend` — surfaced at `GET /api/health/` and in the API metadata.
- `frontend` — injected at build time (Vite `define`) and shown in the UI footer.

A release bumps `VERSION`, updates the top of `CHANGELOG.md` from the
`[Unreleased]` section to the new version + date, and tags the commit.

## Release checklist

1. Ensure `main` is green (backend + e2e CI jobs).
2. Move `CHANGELOG.md` `[Unreleased]` entries under a new
   `## [X.Y.Z] — YYYY-MM-DD` heading.
3. Bump the `VERSION` file.
4. Run the `@full` E2E tag locally or via the manual CI dispatch.
5. Commit `chore(release): X.Y.Z`, then `git tag vX.Y.Z && git push --tags`.
6. (Later, once deployed) the tag triggers the deploy workflow.

## Conventional commits (recommended, not enforced)

Commit prefixes already used loosely in history — `feat:`, `fix:`, `docs:`,
`chore:`, `test:` — map cleanly onto the scheme: `feat:` → MINOR, `fix:` →
PATCH, a `!` suffix or `BREAKING CHANGE:` footer → MAJOR. Adopting them
consistently would let the changelog and version bump be generated
automatically later.
