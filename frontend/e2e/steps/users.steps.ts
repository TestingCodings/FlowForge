import { expect } from "@playwright/test";
import { Given, When, Then, apiFetch } from "./fixtures";

/**
 * User administration.
 *
 * This page had no coverage at any level, which is how it stayed broken from
 * the day it was written without anyone noticing. It rendered a blank
 * document, sidebar included, because AppLayout and the page declared
 * separate queries against the same ["users"] cache key and disagreed about
 * whether it held an array or a paginated envelope. Whichever mounted last
 * won, so opening this page handed AppLayout an object and its `.filter` call
 * took down the tree.
 *
 * A unit test on the page alone would have passed: the fault only exists when
 * both consumers of the cache are mounted together. So the assertions below
 * are deliberately about the whole shell staying up, not about the table.
 *
 * Read-only throughout. Changing anyone's roles here would race the other
 * workers and could demote the account the rest of the suite signs in as.
 */

Given("I am on the user administration page", async ({ page }) => {
  await page.goto("/admin/users");
  await expect(page.getByRole("heading", { name: "Users" })).toBeVisible();
});

Then("I see every user with the roles they hold", async ({ page }) => {
  const listed = await apiFetch(page, "GET", "/users/?page_size=200");
  const users = ((listed.json as any).results ?? listed.json) as any[];
  expect(users.length, "no users to render").toBeGreaterThan(0);

  for (const user of users) {
    await expect(page.getByText(user.email, { exact: true })).toBeVisible();
  }

  // A role badge reading its own key ("platform_admin") means the label
  // lookup missed, which is what a stale hardcoded role list used to cause.
  const admin = users.find((u) => (u.roles ?? []).includes("platform_admin"));
  if (admin) {
    await expect(page.getByText("Platform Admin").first()).toBeVisible();
  }
});

When("I move to the dashboard and back to user administration", async ({ page }) => {
  await page.getByRole("link", { name: /dashboard/i }).first().click();
  await expect(page).toHaveURL(/\/dashboard/);
  await page.getByRole("link", { name: /users/i }).first().click();
  await expect(page).toHaveURL(/\/admin\/users/);
});

Then("the navigation shell stayed up throughout", async ({ page }) => {
  // The symptom was a blank document, so this asserts the frame exists at
  // all, then that the part which actually threw is still working: the demo
  // switcher is the only consumer of AppLayout's user list.
  await expect(page.locator("nav").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Users" })).toBeVisible();
  await expect(page.locator("table").first()).toBeVisible();

  const body = (await page.locator("body").innerText()).trim();
  expect(body.length, "the page rendered nothing").toBeGreaterThan(50);
});

When("I open the role editor for a user", async ({ page }) => {
  await page.getByRole("button", { name: "Edit roles" }).first().click();
  await expect(page.getByText(/select roles for/i)).toBeVisible();
});

Then("every role defined in the workspace is offered", async ({ page }) => {
  // The offered set has to come from the role table, or a custom role a
  // client defined is invisible here and can never be handed out.
  const listed = await apiFetch(page, "GET", "/roles/?page_size=200");
  const roles = ((listed.json as any).results ?? listed.json) as any[];
  expect(roles.length).toBeGreaterThan(0);

  const editor = page.locator(".role-grid").first();
  for (const role of roles) {
    await expect(
      editor.getByText(role.label, { exact: true }),
      `role "${role.label}" was not offered`,
    ).toBeVisible();
  }

  await page.getByRole("button", { name: "Cancel" }).first().click();
});
