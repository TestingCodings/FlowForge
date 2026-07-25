import { expect } from "@playwright/test";
import { When, Then } from "./fixtures";

When("I open the topology view", async ({ page }) => {
  await page.goto("/topology");
});

Then("I see connected instance nodes on the map", async ({ page }) => {
  // React Flow renders one .react-flow__node per instance; the seeded estate
  // has linked instances, so at least a couple appear.
  await expect(page.locator(".react-flow__node").first()).toBeVisible({ timeout: 15_000 });
  const count = await page.locator(".react-flow__node").count();
  expect(count).toBeGreaterThan(1);
});

Then("the legend explains relationship and containment edges", async ({ page }) => {
  await expect(page.getByText("relationship", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("containment", { exact: false }).first()).toBeVisible();
});
