import { test as base, createBdd } from "playwright-bdd";
import type { Page } from "@playwright/test";

/** The seeded demo accounts (see backend seed command). */
export const ACCOUNTS: Record<string, { email: string; password: string }> = {
  "admin@flowforge.dev": { email: "admin@flowforge.dev", password: "Admin1234!" },
  "alice@flowforge.dev": { email: "alice@flowforge.dev", password: "Alice1234!" },
  "bob@flowforge.dev": { email: "bob@flowforge.dev", password: "Bob12345!" },
  "carol@flowforge.dev": { email: "carol@flowforge.dev", password: "Carol123!" },
};

/** Programmatic login: fills the login form and waits for the app shell. */
export async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByPlaceholder("you@example.com").fill(email);
  await page.getByPlaceholder("••••••••").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  // The app shell renders the sidebar nav once authenticated.
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 10_000 });
}

/**
 * Shared BDD test with a `signedInAs` helper. Scenarios that begin
 * "signed in as X" reuse this so auth isn't re-hand-rolled per step file.
 */
export const test = base.extend<{ signedInAs: (email: string) => Promise<void> }>({
  signedInAs: async ({ page }, use) => {
    await use(async (email: string) => {
      const acct = ACCOUNTS[email];
      if (!acct) throw new Error(`Unknown seeded account: ${email}`);
      await login(page, acct.email, acct.password);
    });
  },
});

export const { Given, When, Then } = createBdd(test);

/** Call the FlowForge API from inside the page, reusing the UI session's JWT. */
export async function apiFetch(page: Page, method: string, path: string, body?: unknown) {
  return page.evaluate(
    async ({ method, path, body, apiBase }) => {
      const token = localStorage.getItem("ff_access_token");
      const resp = await fetch(`${apiBase}${path}`, {
        method,
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const text = await resp.text();
      let json: unknown = null;
      try { json = text ? JSON.parse(text) : null; } catch { json = text; }
      return { status: resp.status, json };
    },
    { method, path, body, apiBase: process.env.E2E_API_BASE ?? "http://localhost:8000/api" },
  );
}

/**
 * Find a workflow by exact name, following pagination.
 *
 * Steps used to do `GET /workflows/` and search `results`, which is page 1
 * only — the API paginates at 25. On any database with more workflows than
 * that, seeded workflows became invisible and scenarios failed with
 * "workflow not found" for something that plainly existed. It surfaced when
 * a development database accumulated 29 definitions and pushed "Test Run"
 * to index 27, but it is not a test-only problem: the demo company alone
 * plans fifteen workflows on top of the seeded set.
 *
 * Paging is used rather than a `?search=` filter because the workflows
 * endpoint declares no `search_fields`, so DRF's SearchFilter is inert
 * there. If that changes, this can become one request.
 */
export async function findWorkflowByName(page: Page, name: string) {
  let path: string | null = "/workflows/";
  const seen: string[] = [];

  while (path) {
    const resp = await apiFetch(page, "GET", path);
    const body = resp.json as any;
    const results = (body?.results ?? body ?? []) as any[];
    const match = results.find((w) => w.name === name);
    if (match) return match;
    seen.push(...results.map((w) => w.name));

    // `next` is an absolute URL; apiFetch takes a path relative to the API base.
    const next: string | null = body?.next ?? null;
    path = next ? new URL(next).pathname.replace(/^\/api/, "") + new URL(next).search : null;
  }

  throw new Error(
    `workflow not found: ${name} (searched ${seen.length} workflows across all pages)`,
  );
}

/**
 * Every workflow, across all pages.
 *
 * The stale-fixture sweeps used to read page 1 only, so once leftovers from
 * crashed runs pushed past 25 they became permanently unsweepable and the
 * database grew without bound — which is how the pagination bug above came
 * to bite in the first place. A partial sweep is worse than none: it looks
 * like it worked.
 */
export async function listAllWorkflows(page: Page): Promise<any[]> {
  const all: any[] = [];
  let path: string | null = "/workflows/";
  while (path) {
    const resp = await apiFetch(page, "GET", path);
    const body = resp.json as any;
    all.push(...((body?.results ?? body ?? []) as any[]));
    const next: string | null = body?.next ?? null;
    path = next ? new URL(next).pathname.replace(/^\/api/, "") + new URL(next).search : null;
  }
  return all;
}

/**
 * Build a throwaway workflow, with instances, owned entirely by one scenario.
 *
 * The shell scenarios used to reconfigure *seeded* workflows' ui_schema —
 * Employee Leave Request became a table, Test Run a matrix, and so on. That
 * is shared mutable state: with two Playwright workers, two scenarios could
 * rewrite each other's setup mid-run, so a different one failed each time and
 * the suite was only trustworthy at --workers=1. It also coupled the shell
 * tests to unrelated features — workflows.feature opens Bug Report expecting
 * a kanban action, which broke when a shell scenario repointed it.
 *
 * Each scenario now creates its own workflow with a unique name, so nothing
 * it does can be observed by anything else.
 */
export interface FixtureInstance {
  metadata?: Record<string, unknown>;
  /** Transition names to fire in order, so the instance lands in a real state. */
  advance?: string[];
}

export interface WorkflowFixtureSpec {
  /** Short label; a timestamp is appended to keep runs from colliding. */
  label: string;
  prefix: string;
  states: { name: string; initial?: boolean; terminal?: boolean }[];
  transitions: { name: string; from: string; to: string }[];
  uiSchema?: Record<string, unknown>;
  instances?: FixtureInstance[];
}

export const FIXTURE_PREFIX = "E2E Fixture";

/** Remove workflows left behind by crashed runs, across all pages. */
export async function sweepFixtures(page: Page) {
  for (const wf of await listAllWorkflows(page)) {
    if (typeof wf.name === "string" && wf.name.startsWith(FIXTURE_PREFIX)) {
      // Best-effort: may 400 while instances exist, and that's acceptable —
      // the next run's unique name means a leftover can't affect it.
      await apiFetch(page, "DELETE", `/workflows/${wf.id}/`);
    }
  }
}

export async function createWorkflowFixture(page: Page, spec: WorkflowFixtureSpec) {
  const name = `${FIXTURE_PREFIX} ${spec.label} ${Date.now()}`;

  const created = await apiFetch(page, "POST", "/workflows/", {
    name,
    reference_prefix: spec.prefix,
    version: 1,
    is_active: true,
    states: spec.states.map((s, i) => ({
      name: s.name,
      is_initial: s.initial ?? i === 0,
      is_terminal: s.terminal ?? false,
      position_order: i + 1,
      sla_config: {},
      task_config: {},
    })),
    transitions: spec.transitions.map((t) => ({
      name: t.name, from_state: t.from, to_state: t.to, requires_approval: false,
    })),
  });
  if (created.status !== 201) {
    throw new Error(`fixture workflow create failed: ${JSON.stringify(created.json)}`);
  }
  // The create response carries `transitions: null` — nested states and
  // transitions are only serialised on a subsequent read. Fetch the detail so
  // advancing instances can resolve transition ids by name.
  const detail = await apiFetch(page, "GET", `/workflows/${(created.json as any).id}/`);
  const workflow = detail.json as any;

  if (spec.uiSchema) {
    const patched = await apiFetch(page, "PATCH", `/workflows/${workflow.id}/ui-schema/`, {
      ui_schema: spec.uiSchema,
    });
    if (patched.status !== 200) {
      throw new Error(`fixture ui-schema failed: ${JSON.stringify(patched.json)}`);
    }
  }

  for (const inst of spec.instances ?? []) {
    const made = await apiFetch(page, "POST", "/instances/", {
      workflow_definition: workflow.id,
      metadata_json: inst.metadata ?? {},
    });
    if (made.status !== 201) {
      throw new Error(`fixture instance create failed: ${JSON.stringify(made.json)}`);
    }
    // Advance through real transitions so instances sit in genuine states
    // rather than all piling into the initial one.
    for (const transitionName of inst.advance ?? []) {
      const tr = (workflow.transitions ?? []).find((t: any) => t.name === transitionName);
      if (!tr) throw new Error(`fixture: no transition named ${transitionName}`);
      await apiFetch(page, "POST", `/instances/${(made.json as any).id}/transition/`, {
        transition_id: tr.id,
      });
    }
  }

  return workflow;
}
