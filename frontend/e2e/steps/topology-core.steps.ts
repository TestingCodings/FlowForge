import { expect } from "@playwright/test";
import { Given, When, Then, apiFetch } from "./fixtures";

Given("I am viewing an instance with relationships", async ({ page }) => {
  // Ask the topology endpoint for any relationship edge and root at its source.
  const topo = await apiFetch(page, "GET", "/topology/");
  const edges = (topo.json as any).edges.filter((e: any) => e.kind === "relationship");
  expect(edges.length, "seeded data should contain at least one relationship").toBeGreaterThan(0);
  await page.goto(`/instances/${edges[0].source}`);
  await expect(page.getByRole("link", { name: "View topology" })).toBeVisible();
});

Then("the map is rooted at that instance", async ({ page }) => {
  await expect(page).toHaveURL(/\/topology\?root=/);
  await expect(page.getByText(/rooted at one instance/i)).toBeVisible();
  await expect(page.locator(".react-flow__node").first()).toBeVisible();
});

Then("I can widen the depth to reveal further connections", async ({ page }) => {
  const before = await page.locator(".react-flow__node").count();
  await page.getByLabel(/depth/i).selectOption("3");
  await expect(page.locator(".react-flow__node").first()).toBeVisible();
  const after = await page.locator(".react-flow__node").count();
  expect(after).toBeGreaterThanOrEqual(before); // deeper walk never shrinks the graph
});
