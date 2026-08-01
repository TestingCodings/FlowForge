import { defineConfig } from "vitest/config";

/**
 * Unit tests for the frontend's pure logic.
 *
 * Deliberately narrow. Component rendering is covered by the Playwright
 * suite against a real browser and a real API, which is a better test of a
 * component than jsdom is. What Playwright covers badly is the small pure
 * functions everything else depends on: field resolution, capability checks,
 * message interpolation. Those get unit tests, because a bug there shows up
 * as a blank board rather than an error.
 *
 * e2e/ is excluded: those are Playwright specs and would be collected here
 * otherwise, then fail on a missing browser fixture.
 */
export default defineConfig({
  test: {
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    exclude: ["e2e/**", "node_modules/**", ".features-gen/**"],
    environment: "node",
    coverage: {
      provider: "v8",
      include: ["src/**/*.ts", "src/**/*.tsx"],
      exclude: ["src/**/*.test.ts", "src/**/*.test.tsx", "src/types/**", "src/main.tsx"],
      reporter: ["text-summary", "html"],
    },
  },
});
