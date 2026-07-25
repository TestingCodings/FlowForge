import { defineConfig, devices } from "@playwright/test";
import { defineBddConfig } from "playwright-bdd";

/**
 * playwright-bdd compiles the Gherkin .feature files in e2e/features into
 * runnable Playwright specs using the step definitions in e2e/steps.
 */
// All .feature files are compiled, but a tag expression selects which
// scenarios run — only those need step definitions. We start gated to @smoke
// (implemented + proven here); @core and @full steps are filled in
// incrementally, widening E2E_TAGS as they land. The full Gherkin set stays
// committed as living documentation regardless.
const testDir = defineBddConfig({
  features: "e2e/features/**/*.feature",
  steps: "e2e/steps/**/*.ts",
  tags: process.env.E2E_TAGS ?? "@smoke",
});

const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:5173";

export default defineConfig({
  testDir,
  timeout: 30_000,
  expect: { timeout: 7_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI
    ? [["html", { open: "never" }], ["list"]]
    : [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  // Start the Vite dev server for local runs; in CI a preview build is served
  // by the workflow instead (E2E_BASE_URL points at it).
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: "npm run dev",
        url: BASE_URL,
        reuseExistingServer: true,
        timeout: 60_000,
      },
});
