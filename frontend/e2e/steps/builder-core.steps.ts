import { expect } from "@playwright/test";
import { Given, When, Then } from "./fixtures";

Given("I am in the workflow builder on a fresh canvas", async ({ page }) => {
  // Clear any persisted draft first so the resume banner can't interfere.
  await page.goto("/dashboard");
  await page.evaluate(() => localStorage.removeItem("flowforge:builder-draft"));
  await page.goto("/workflows/new");
  await expect(page.locator(".react-flow__node")).toHaveCount(1);
});

When("I add a new state", async ({ page }) => {
  await page.getByRole("button", { name: "+ Add State" }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(2);
});

When("I press undo", async ({ page }) => {
  await page.getByRole("button", { name: "↩" }).click();
});

Then("the canvas shows only the start state", async ({ page }) => {
  await expect(page.locator(".react-flow__node")).toHaveCount(1);
});

When("I save the workflow without a name", async ({ page }) => {
  await page.getByRole("button", { name: /save workflow/i }).click();
});

Then("I see a validation error requiring a workflow name", async ({ page }) => {
  await expect(page.locator(".alert-error").getByText(/name is required/i)).toBeVisible();
});

When("I name the workflow {string}", async ({ page }, name: string) => {
  await page.getByPlaceholder("Workflow name *").fill(name);
});

When("I leave and reopen the builder", async ({ page }) => {
  // The draft autosave is debounced (1s); let it flush before navigating away.
  await page.waitForTimeout(1400);
  await page.goto("/dashboard");
  await page.goto("/workflows/new");
});

Then("I am offered to resume the draft", async ({ page }) => {
  await expect(page.getByRole("button", { name: "Resume draft" })).toBeVisible();
});

Then("resuming restores the workflow name {string}", async ({ page }, name: string) => {
  await page.getByRole("button", { name: "Resume draft" }).click();
  await expect(page.getByPlaceholder("Workflow name *")).toHaveValue(name);
});
