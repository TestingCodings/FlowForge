import { describe, expect, it } from "vitest";

import { Capability, hasCapability } from "./useCapabilities";

/**
 * UI capability checks.
 *
 * These decide what renders, not what is allowed: the API enforces every one
 * of these server-side.
 *
 * This file used to assert a role-to-capability map kept in the frontend —
 * that a designer could design, that a viewer could not, and so on. That map
 * is gone. It was a second copy of the backend's, and being a copy was the
 * problem: it only knew the five built-in roles, so a custom role matched
 * nothing and its holder saw the interface of someone with no permissions.
 * `/auth/me/` now serves the resolved set and the frontend does no mapping.
 *
 * So the old assertions have nothing left to protect — who holds what is
 * decided in one place and covered by test_me_capabilities.py. What remains
 * worth testing here is the predicate itself.
 *
 * The other seam, that the hand-written `Capability` union still matches the
 * backend's vocabulary, is checked in
 * backend/tests/unit/test_capability_vocabulary.py. It lives there because it
 * has to read a file from each side, which Python does without needing Node
 * types in the app's build.
 */

describe("hasCapability", () => {
  it("grants a capability the user holds", () => {
    expect(hasCapability(["workflow.design"], "workflow.design")).toBe(true);
  });

  it("refuses one they do not", () => {
    expect(hasCapability(["workflow.view"], "workflow.design")).toBe(false);
  });

  it("refuses everything to a user holding nothing", () => {
    for (const cap of [
      "workflow.view",
      "workflow.design",
      "instance.create",
      "workspace.manage",
    ] as Capability[]) {
      expect(hasCapability([], cap)).toBe(false);
    }
  });

  it("fails closed while the profile is still loading", () => {
    // undefined means "not known yet", and a creator-only control must not
    // flash in front of an end user during that window.
    expect(hasCapability(undefined, "workspace.manage")).toBe(false);
  });

  it("does not care about ordering or extras", () => {
    const held = ["workspace.manage", "audit.view", "user.view"];
    expect(hasCapability(held, "audit.view")).toBe(true);
  });

  it("matches exactly, not by prefix", () => {
    // "instance.view" must not satisfy a check for "instance.view_all" or
    // vice versa; substring matching here would quietly over-grant.
    expect(hasCapability(["instance.view"], "instance.relate")).toBe(false);
    expect(hasCapability(["workflow.view"], "workflow.publish")).toBe(false);
  });
});
