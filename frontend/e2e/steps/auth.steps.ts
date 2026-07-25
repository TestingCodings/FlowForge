import { expect } from "@playwright/test";
import { Given, When, Then, ACCOUNTS, login } from "./fixtures";

Given("the FlowForge app is running with seeded demo accounts", async () => {
  // No-op: asserted implicitly by the seeded-login steps. Documents the
  // precondition that the API is up and `seed --testrail` has been run.
});

Given("I am on the login page", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
});

Given("I am not signed in", async ({ page }) => {
  await page.context().clearCookies();
  await page.addInitScript(() => localStorage.clear());
});

Given("I am signed in as {string}", async ({ page }, email: string) => {
  const acct = ACCOUNTS[email];
  if (!acct) throw new Error(`Unknown seeded account: ${email}`);
  await login(page, acct.email, acct.password);
});

When("I sign in as {string} with password {string}", async ({ page }, email: string, password: string) => {
  await page.goto("/login");
  await page.getByPlaceholder("you@example.com").fill(email);
  await page.getByPlaceholder("••••••••").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
});

When("I navigate to {string}", async ({ page }, path: string) => {
  await page.goto(path);
});

When("I sign out", async ({ page }) => {
  await page.getByRole("button", { name: /sign out|cerrar sesión/i }).click();
});

Then("I land on the dashboard", async ({ page }) => {
  await expect(page).toHaveURL(/\/dashboard$/);
});

Then("the sidebar shows my workspace navigation", async ({ page }) => {
  await expect(page.getByRole("link", { name: /dashboard|panel/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /workflows|flujos/i })).toBeVisible();
});

Then("I see an authentication error", async ({ page }) => {
  await expect(page.locator(".alert-error, [role='alert']").first()).toBeVisible();
});

Then("I remain on the login page", async ({ page }) => {
  await expect(page).toHaveURL(/\/login/);
});

Then("I am redirected to the login page", async ({ page }) => {
  await expect(page).toHaveURL(/\/login/);
});

Then("I return to the login page", async ({ page }) => {
  await expect(page).toHaveURL(/\/login/);
});

Then("navigating to {string} redirects me back to login", async ({ page }, path: string) => {
  await page.goto(path);
  await expect(page).toHaveURL(/\/login/);
});
