import { expect } from "@playwright/test";
import { Given, When, Then } from "./fixtures";

When("I open the workflows page", async ({ page }) => {
  await page.goto("/workflows");
});

Given("I am on the workflows page", async ({ page }) => {
  await page.goto("/workflows");
  await expect(page.getByText("Bug Report").first()).toBeVisible();
});

Then("I see a workflow named {string}", async ({ page }, name: string) => {
  await expect(page.getByText(name, { exact: true }).first()).toBeVisible();
});

When("I open the {string} workflow", async ({ page }, name: string) => {
  await page.getByText(name, { exact: true }).first().click();
  await expect(page).toHaveURL(/\/workflows\/[0-9a-f-]+$/);
});

Given("I am viewing the {string} workflow", async ({ page }, name: string) => {
  await page.goto("/workflows");
  await page.getByText(name, { exact: true }).first().click();
  await expect(page).toHaveURL(/\/workflows\/[0-9a-f-]+$/);
});

Then("I see the workflow's state diagram", async ({ page }) => {
  await expect(page.locator(".state-graph-wrap svg")).toBeVisible();
});

Then("I see the {string} action", async ({ page }, label: string) => {
  await expect(page.getByRole("link", { name: label }).or(page.getByRole("button", { name: label })).first()).toBeVisible();
});

When("I export the workflow", async ({ page }) => {
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export" }).click();
  const file = await download;
  (page as any)._lastDownload = file.suggestedFilename();
});

Then("a {string} bundle is downloaded", async ({ page }, ext: string) => {
  expect((page as any)._lastDownload).toContain(ext);
});

When("I choose {string}", async ({ page }, label: string) => {
  // Actions render as buttons or styled links depending on context. Use .or()
  // so Playwright auto-waits for whichever appears — an eager count() check
  // races the render and flakes under parallel load.
  const control = page
    .getByRole("button", { name: label })
    .or(page.getByRole("link", { name: label }));
  await control.first().click();
});

// The YAML opens in a read-only <textarea>; its content lives in .value, so
// text-matching locators and innerText() see nothing — use inputValue().
Then("I see the workflow rendered as YAML text", async ({ page }) => {
  const box = page.locator("textarea[readonly]");
  await expect(box).toBeVisible();
  expect(await box.inputValue()).toMatch(/workflow:/);
});

Then("the YAML contains the workflow's states and transitions", async ({ page }) => {
  const text = await page.locator("textarea[readonly]").inputValue();
  expect(text).toMatch(/states:/);
  expect(text).toMatch(/transitions:/);
});
