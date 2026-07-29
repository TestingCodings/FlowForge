import { expect } from "@playwright/test";
import { Given, When, Then, apiFetch, createWorkflowFixture, sweepFixtures } from "./fixtures";

/**
 * @core shell steps.
 *
 * Each scenario builds its **own** workflow. These used to reconfigure seeded
 * workflows' ui_schema, which is shared mutable state: two Playwright workers
 * could rewrite each other's setup mid-run, so a different scenario failed
 * each time and the suite was only trustworthy at --workers=1. It also
 * coupled these tests to unrelated features — workflows.feature opens Bug
 * Report expecting a kanban action, which broke when a shell scenario
 * repointed it.
 *
 * Owning the data also means the assertions can be exact rather than
 * defensive, because the fixture decides how many states and instances exist.
 */

/** Three states, two transitions — enough for every shell under test. */
function baseSpec(label: string, prefix: string) {
  return {
    label,
    prefix,
    states: [
      { name: "Open" },
      { name: "Doing" },
      { name: "Done", terminal: true },
    ],
    transitions: [
      { name: "Start", from: "Open", to: "Doing" },
      { name: "Finish", from: "Doing", to: "Done" },
    ],
  };
}

async function build(page: any, spec: any) {
  await sweepFixtures(page);
  const wf = await createWorkflowFixture(page, spec);
  page._shellWorkflowId = wf.id;   // consumed by the shared "I open its view"
  page._shellWorkflow = wf;
  return wf;
}

Given(
  "a workflow configured with the {string} shell and columns {string}",
  async ({ page }, shell: string, columns: string) => {
    await build(page, {
      ...baseSpec("Table", "TBL"),
      uiSchema: { shell, list_columns: columns.split(",").map((c) => c.trim()) },
      instances: [
        { metadata: { title: "First" } },
        { metadata: { title: "Second" }, advance: ["Start"] },
      ],
    });
  },
);

Given("a workflow configured with the {string} shell", async ({ page }, shell: string) => {
  await build(page, {
    ...baseSpec("List", "LST"),
    uiSchema: { shell },
    instances: [{ metadata: { title: "One" } }, { metadata: { title: "Two" } }],
  });
});

Given(
  "the {string} workflow uses the {string} shell grouped by suite and state",
  async ({ page }, _name: string, shell: string) => {
    // Two suites × two occupied states, so "a row per suite" and "a column
    // per state" are both satisfied by construction rather than by luck.
    await build(page, {
      ...baseSpec("Matrix", "MTX"),
      uiSchema: { shell, matrix: { rows: "metadata.suite", columns: "current_state" } },
      instances: [
        { metadata: { suite: "Authentication" } },
        { metadata: { suite: "Authentication" }, advance: ["Start"] },
        { metadata: { suite: "Checkout" } },
        { metadata: { suite: "Checkout" }, advance: ["Start"] },
      ],
    });
  },
);

Then("the table header shows {string}, {string} and {string}", async ({ page }, a: string, b: string, c: string) => {
  for (const label of [a, b, c]) {
    await expect(page.getByRole("columnheader", { name: new RegExp(label, "i") })).toBeVisible();
  }
});

Then("I see a row per suite", async ({ page }) => {
  const rows = page.locator("table tbody tr");
  await expect(rows).toHaveCount(2);   // exactly the two suites the fixture made
});

Then("I see a column per state", async ({ page }) => {
  // The matrix renders a column only for states instances actually occupy.
  // The fixture puts instances in exactly two ("Open" and "Doing"), plus the
  // row-label column.
  await expect(page.locator("table thead th")).toHaveCount(3);
});

Then("cells show state-coloured instance chips", async ({ page }) => {
  await expect(page.locator("table tbody button").first()).toBeVisible();
});

When("I filter the list by a reference substring", async ({ page }) => {
  await page.getByPlaceholder(/filter by reference/i).fill("LST");
});

Then("only matching instances remain", async ({ page }) => {
  const rows = page.locator(".card > div[style*='cursor']");
  await expect(rows.first()).toBeVisible();
  for (const text of await rows.allTextContents()) {
    expect(text).toMatch(/LST/);
  }
  await page.getByPlaceholder(/filter by reference/i).fill("zzz-no-match");
  await expect(page.getByText(/no instances match/i)).toBeVisible();
});
