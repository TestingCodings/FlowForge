import { expect } from "@playwright/test";
import { Given, When, Then, ACCOUNTS, apiFetch, login } from "./fixtures";

/**
 * Capability-gated navigation (docs/ROLES.md step 4).
 *
 * Each scenario builds a throwaway role holding exactly the capabilities it
 * names, a throwaway user to hold it, and signs in as them. Nothing here
 * touches a seeded account: reconfiguring shared users is what used to make
 * parallel runs race, and demoting a seeded admin mid-run would break every
 * other worker at once.
 *
 * Assertions are about what is *absent*, which is the awkward direction to
 * test — a typo'd selector also finds nothing. So each scenario checks
 * something present alongside, and the sidebar is read as a whole rather than
 * probed link by link.
 */

const SUFFIX = Symbol.for("ff.nav.suffix");

async function asAdmin(page: any) {
  const admin = ACCOUNTS["admin@flowforge.dev"];
  await login(page, admin.email, admin.password);
}

/** Everything the sidebar currently offers, flattened to link labels. */
async function sidebarLinks(page: any): Promise<string[]> {
  const nav = page.locator("nav").first();
  await expect(nav.getByRole("link").first()).toBeVisible();
  return (await nav.getByRole("link").allInnerTexts()).map((t: string) => t.trim());
}

Given(
  "I am signed in as a user holding only {string} and {string}",
  async ({ page }, capA: string, capB: string) => {
    const unique = `${Date.now()}${Math.floor(Math.random() * 1e4)}`;
    (page as any)[SUFFIX] = unique;

    // Registration first, while nobody is signed in, then the admin grants
    // the role. A fresh account holds nothing until told otherwise, which is
    // the baseline these scenarios want.
    const email = `navtest_${unique}@example.com`;
    const password = "NavTest1234!";
    const registered = await page.request.post("/api/auth/register/", {
      data: {
        email,
        password,
        password_confirm: password,
        first_name: "Nav",
        last_name: "Test",
      },
    });
    expect(registered.status(), `register failed: ${await registered.text()}`).toBe(201);

    await asAdmin(page);

    const roleKey = `nav_probe_${unique}`;
    const created = await apiFetch(page, "POST", "/roles/", {
      key: roleKey,
      label: `Nav Probe ${unique}`,
      capabilities: [capA, capB],
      rank: 10,
    });
    expect(created.status, `role create failed: ${JSON.stringify(created.json)}`).toBe(201);

    const users = await apiFetch(page, "GET", "/users/?page_size=200");
    const rows = ((users.json as any).results ?? users.json) as any[];
    const target = rows.find((u) => u.email === email);
    expect(target, `registered user ${email} not in the user list`).toBeTruthy();

    const assigned = await apiFetch(page, "POST", `/users/${target.id}/roles/`, {
      roles: [roleKey],
    });
    expect(assigned.status, `assign failed: ${JSON.stringify(assigned.json)}`).toBe(200);

    await login(page, email, password);

    // Confirm the premise before asserting on the UI. If the role did not
    // take, the sidebar would be correctly narrow for the wrong reason and
    // the scenario would pass while proving nothing.
    const me = await apiFetch(page, "GET", "/auth/me/");
    expect(new Set((me.json as any).capabilities)).toEqual(new Set([capA, capB]));
  },
);

When("I look at the sidebar", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.locator("nav").first()).toBeVisible();
});

Then("it offers workspace administration", async ({ page }) => {
  const links = await sidebarLinks(page);
  expect(links).toContain("Workspace");
  expect(links).toContain("Roles");
});

Then("it does not offer workspace administration", async ({ page }) => {
  const links = await sidebarLinks(page);
  expect(links).not.toContain("Workspace");
  expect(links).not.toContain("Roles");
  expect(links).not.toContain("Audit Log");
});

Then("it does not offer workflow authoring", async ({ page }) => {
  const links = await sidebarLinks(page);
  expect(links).not.toContain("New Workflow");
  expect(links).not.toContain("Templates");
});

Then("it offers workflow authoring", async ({ page }) => {
  const links = await sidebarLinks(page);
  expect(links).toContain("New Workflow");
  expect(links).toContain("Templates");
});

Then("it still offers the pages I can use", async ({ page }) => {
  // The other half of gating: hiding too much is as wrong as hiding too
  // little, and an all-absent assertion would pass on an empty sidebar.
  const links = await sidebarLinks(page);
  expect(links).toContain("Dashboard");
  expect(links).toContain("Instances");
  expect(links).toContain("Workflows");
});

Then("no section heading stands alone with nothing under it", async ({ page }) => {
  const sections = await page.locator("nav > div").evaluateAll((divs: Element[]) =>
    divs.map((d) => ({
      heading: d.querySelector(".sidebar-section-label")?.textContent?.trim() ?? "",
      links: d.querySelectorAll("a").length,
    })),
  );
  expect(sections.length, "no nav sections rendered at all").toBeGreaterThan(0);
  const empty = sections.filter((s: any) => s.links === 0).map((s: any) => s.heading);
  expect(empty, "section headings with no links beneath them").toEqual([]);
});
