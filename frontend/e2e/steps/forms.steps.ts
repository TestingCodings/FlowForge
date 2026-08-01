import { expect } from "@playwright/test";
import { Given, When, Then, apiFetch, createWorkflowFixture, sweepFixtures } from "./fixtures";

/**
 * State-form scenarios.
 *
 * A required form is the clearest example of the engine having the final say:
 * the transition is refused server-side until the form is submitted, and the
 * UI reflects that rather than deciding it. These scenarios check the refusal
 * is real, not just a disabled button.
 *
 * Each builds its own workflow, form and instance, so nothing here depends on
 * or disturbs the seeded demo data.
 */

async function buildFormFixture(page: any, opts: { required: boolean }) {
  await sweepFixtures(page);

  const wf = await createWorkflowFixture(page, {
    label: opts.required ? "FormGate" : "FormOpen",
    prefix: "FRM",
    states: [{ name: "Open" }, { name: "Done", terminal: true }],
    transitions: [{ name: "Finish", from: "Open", to: "Done" }],
    instances: [{ metadata: { origin: "fixture" } }],
  });

  const state = (wf.states ?? []).find((s: any) => s.name === "Open");
  const created = await apiFetch(page, "POST", "/forms/", {
    workflow_definition: wf.id,
    state: state.id,
    name: "Completion Report",
    schema: {
      required_to_transition: opts.required,
      fields: [
        { name: "outcome", type: "text", label: "Outcome", required: true },
        { name: "notes", type: "textarea", label: "Notes", required: false },
      ],
    },
  });
  expect(created.status, `form create failed: ${JSON.stringify(created.json)}`).toBe(201);

  const list = await apiFetch(page, "GET", `/instances/?workflow_definition=${wf.id}`);
  const instance = ((list.json as any).results ?? [])[0];
  expect(instance, "fixture produced no instance").toBeTruthy();

  (page as any)._formWorkflow = wf;
  (page as any)._formInstance = instance;
  await page.goto(`/instances/${instance.id}`);
  await expect(page.getByRole("heading", { name: "Completion Report" })).toBeVisible();
  return instance;
}

Given("I am viewing an instance whose current state has a required form", async ({ page }) => {
  await buildFormFixture(page, { required: true });
  await expect(page.getByText(/required before transition/i)).toBeVisible();
});

Given("I am viewing an instance with a required form", async ({ page }) => {
  await buildFormFixture(page, { required: true });
});

Given("I am viewing an instance with a form", async ({ page }) => {
  await buildFormFixture(page, { required: false });
});

Then("the transition gated by the form is unavailable", async ({ page }) => {
  // Asserted against the engine, not the button: the API is what enforces
  // this, and a UI that merely hides the control would still let a direct
  // call through. The button is checked too, since that is what a user sees.
  const instance = (page as any)._formInstance;
  const wf = (page as any)._formWorkflow;
  const transition = (wf.transitions ?? []).find((t: any) => t.name === "Finish");

  const resp = await apiFetch(page, "POST", `/instances/${instance.id}/transition/`, {
    transition_id: transition.id,
  });
  expect(resp.status, "engine allowed a transition its form should gate").toBe(400);
  expect(JSON.stringify(resp.json)).toMatch(/form/i);
});

When("I complete and submit the form", async ({ page }) => {
  await page.getByLabel(/outcome/i).fill("Repaired and tested");
  await page.getByRole("button", { name: /submit completion report/i }).click();
  await expect(page.getByText(/submitted/i).first()).toBeVisible({ timeout: 10_000 });
});

Then("the gated transition becomes available", async ({ page }) => {
  const instance = (page as any)._formInstance;
  const wf = (page as any)._formWorkflow;
  const transition = (wf.transitions ?? []).find((t: any) => t.name === "Finish");

  const resp = await apiFetch(page, "POST", `/instances/${instance.id}/transition/`, {
    transition_id: transition.id,
  });
  expect(resp.status, `transition still refused: ${JSON.stringify(resp.json)}`).toBe(200);
});

When("I submit the form with a required field empty", async ({ page }) => {
  // Leave "outcome" untouched; it is the required field.
  await page.getByRole("button", { name: /submit completion report/i }).click();
});

Then("I see a validation error on that field", async ({ page }) => {
  await expect(page.getByText(/required/i).first()).toBeVisible();

  // And nothing was stored: a client-side complaint that still submitted
  // would be worse than no validation at all.
  //
  // Checked through the instance rather than /submissions/, because that
  // endpoint declares no filterset and silently ignores
  // ?workflow_instance=, returning every submission in the database. Under
  // parallel workers this test then saw another scenario's valid submission
  // and failed. The instance's own view of its form cannot be confused with
  // anyone else's.
  const instance = (page as any)._formInstance;
  const fresh = await apiFetch(page, "GET", `/instances/${instance.id}/`);
  expect((fresh.json as any).current_form?.submitted,
    "an invalid form was submitted anyway").toBe(false);
});

When("I submit the form with values", async ({ page }) => {
  await page.getByLabel(/outcome/i).fill("Filter replaced");
  await page.getByLabel(/notes/i).fill("Next service due in six months");
  await page.getByRole("button", { name: /submit completion report/i }).click();
  await expect(page.getByText(/submitted/i).first()).toBeVisible({ timeout: 10_000 });
});

Then("those values appear in the instance metadata", async ({ page }) => {
  // Merging submissions into metadata is what lets rules and computed fields
  // read form answers, so this is the join that matters, not the storage.
  const instance = (page as any)._formInstance;
  const fresh = await apiFetch(page, "GET", `/instances/${instance.id}/`);
  const metadata = (fresh.json as any).metadata_json ?? {};
  expect(metadata.outcome).toBe("Filter replaced");
  expect(metadata.notes).toBe("Next service due in six months");
});
