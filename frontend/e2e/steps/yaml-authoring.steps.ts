import { expect } from "@playwright/test";
import { Given, When, Then, apiFetch, listAllWorkflows } from "./fixtures";

/**
 * Text-first authoring.
 *
 * The YAML editor compiles to the same bundle the export produces and imports
 * through the same validated path, so these scenarios are really checking
 * that the compile step is honest: a valid document previews as the graph it
 * describes, and an invalid one is refused with a message that says where.
 *
 * Workflows created here are swept by name on the way in, because a created
 * workflow with no instances is deletable and leaving them behind would grow
 * the catalogue.
 */

const YAML_NAME = "E2E YAML Flow";

const VALID_YAML = `workflow: ${YAML_NAME}
prefix: EYF
description: Authored from YAML by the E2E suite

states:
  - name: Drafted
  - name: Reviewed
  - name: Approved
    terminal: true

transitions:
  - Drafted -> Reviewed: Submit
  - Reviewed -> Approved: Approve
`;

const BROKEN_YAML = `workflow: ${YAML_NAME} Broken
prefix: EYB

states:
  - name: Drafted
  - name: Approved
    terminal: true

transitions:
  - Drafted -> Aproved: Submit
`;

async function sweepYamlWorkflows(page: any) {
  for (const wf of await listAllWorkflows(page)) {
    if (typeof wf.name === "string" && wf.name.startsWith(YAML_NAME)) {
      await apiFetch(page, "DELETE", `/workflows/${wf.id}/`);
    }
  }
}

Given("I open the YAML workflow editor", async ({ page }) => {
  await sweepYamlWorkflows(page);
  await page.goto("/workflows/new/text");
  await expect(page.getByLabel("Workflow YAML")).toBeVisible();
});

When("I enter a valid workflow definition in YAML", async ({ page }) => {
  await page.getByLabel("Workflow YAML").fill(VALID_YAML);
  await expect(page.getByText(/✓ Valid/)).toBeVisible({ timeout: 10_000 });
});

When("I enter a valid workflow named {string}", async ({ page }, name: string) => {
  await page.getByLabel("Workflow YAML").fill(VALID_YAML.replace(YAML_NAME, name));
  await expect(page.getByText(/✓ Valid/)).toBeVisible({ timeout: 10_000 });
});

When("I enter a transition referencing an unknown state", async ({ page }) => {
  await page.getByLabel("Workflow YAML").fill(BROKEN_YAML);
  await expect(page.getByText(/Has errors/)).toBeVisible({ timeout: 10_000 });
});

Then("the preview shows the corresponding state nodes", async ({ page }) => {
  // The preview is a React Flow graph, so the nodes are real elements rather
  // than a rendered image.
  for (const state of ["Drafted", "Reviewed", "Approved"]) {
    await expect(page.locator(".react-flow__node").filter({ hasText: state }).first())
      .toBeVisible({ timeout: 10_000 });
  }
});

Then("the preview shows the transitions between them", async ({ page }) => {
  await expect(page.locator(".react-flow__edge").first()).toBeVisible();
  expect(await page.locator(".react-flow__edge").count()).toBe(2);
});

Then("I see an error naming the unknown state", async ({ page }) => {
  // The parser reports the typo and suggests the near match, which is the
  // part that makes text authoring usable rather than a guessing game.
  await expect(page.getByText(/unknown state 'Aproved'/)).toBeVisible();
  await expect(page.getByText(/did you mean 'Approved'/)).toBeVisible();
});

Then("the create action is disabled while the definition is invalid", async ({ page }) => {
  await expect(page.getByRole("button", { name: /create workflow/i })).toBeDisabled();
});

When("I create the workflow", async ({ page }) => {
  await page.getByRole("button", { name: /create workflow/i }).click();
});

Then("the workflow {string} is created", async ({ page }, name: string) => {
  // Landing on the detail page is the visible outcome; the API check is what
  // proves it was actually persisted rather than optimistically routed.
  await expect(page).toHaveURL(/\/workflows\/[0-9a-f-]{36}/, { timeout: 15_000 });

  const wfs = await listAllWorkflows(page);
  const created = wfs.find((w: any) => w.name === name);
  expect(created, `${name} was not created`).toBeTruthy();

  const full = await apiFetch(page, "GET", `/workflows/${created.id}/`);
  const body = full.json as any;
  expect((body.states ?? []).map((s: any) => s.name).sort())
    .toEqual(["Approved", "Drafted", "Reviewed"]);
  expect((body.transitions ?? []).length).toBe(2);
});
