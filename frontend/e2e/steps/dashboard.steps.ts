import { expect } from "@playwright/test";
import { When, Then } from "./fixtures";

When("I open the dashboard", async ({ page }) => {
  await page.goto("/dashboard");
});

Then("I see the {string} stat", async ({ page }, label: string) => {
  // Stat cards render their label uppercased via CSS; match case-insensitively.
  await expect(page.getByText(label, { exact: false }).first()).toBeVisible();
});

Then("I see the {string} chart", async ({ page }, label: string) => {
  await expect(page.getByText(label, { exact: false }).first()).toBeVisible();
});

Then("I see the {string} breakdown", async ({ page }, label: string) => {
  await expect(page.getByText(label, { exact: false }).first()).toBeVisible();
});
