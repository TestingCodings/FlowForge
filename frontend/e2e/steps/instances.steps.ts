import { expect } from "@playwright/test";
import { Given, When, Then } from "./fixtures";

When("I open the instances page", async ({ page }) => {
  await page.goto("/instances");
});

Given("I am on the instances page", async ({ page }) => {
  await page.goto("/instances");
});

Then("I see at least one instance reference number", async ({ page }) => {
  // Reference numbers are monospaced links like BUG-2026-00004.
  await expect(page.getByText(/[A-Z]{2,4}-\d{4}-\d{5}/).first()).toBeVisible();
});

When("I open the first instance", async ({ page }) => {
  await page.getByRole("link", { name: /[A-Z]{2,4}-\d{4}-\d{5}/ }).first().click();
  await expect(page).toHaveURL(/\/instances\/[0-9a-f-]+$/);
});

Then("I see its state diagram", async ({ page }) => {
  await expect(page.locator(".state-graph-wrap svg")).toBeVisible();
});

Then("I see the {string} panel", async ({ page }, name: string) => {
  await expect(page.getByRole("heading", { name: new RegExp(name, "i") }).first()).toBeVisible();
});

Then("I see the available transition actions", async ({ page }) => {
  // The Actions panel heading is always present on an open instance.
  await expect(page.getByRole("heading", { name: /actions/i })).toBeVisible();
});
