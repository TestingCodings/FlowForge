import { describe, expect, it } from "vitest";

import { Capability, roleHas } from "./useCapabilities";

/**
 * UI capability checks.
 *
 * These decide what renders, not what is allowed: the API enforces every one
 * of these server-side. But getting them wrong still matters in both
 * directions. Too generous and an end user is shown a control that fails when
 * they click it; too strict and a designer loses access to their own tools.
 *
 * The mapping mirrors SYSTEM_ROLES in backend/apps/accounts/models.py. If the
 * two drift, the UI and the API disagree about who can do what, so the
 * seniority assertions below are really a check on that agreement.
 */

const ALL_ROLES = [
  "platform_admin",
  "workflow_designer",
  "approver",
  "participant",
  "viewer",
] as const;

describe("roleHas", () => {
  it("grants a designer the design capability", () => {
    expect(roleHas(["workflow_designer"], "workflow.design")).toBe(true);
  });

  it("refuses a viewer the design capability", () => {
    expect(roleHas(["viewer"], "workflow.design")).toBe(false);
  });

  it("refuses a user with no roles everything", () => {
    for (const cap of [
      "workflow.view",
      "workflow.design",
      "instance.create",
      "workspace.manage",
    ] as Capability[]) {
      expect(roleHas([], cap)).toBe(false);
    }
  });

  it("unions across several roles", () => {
    // A user can hold more than one role; holding either is enough.
    expect(roleHas(["viewer", "workflow_designer"], "workflow.design")).toBe(true);
  });

  it("ignores a role it does not recognise", () => {
    // Custom roles exist server-side. The UI must not crash on one, and must
    // not silently grant on one either.
    expect(roleHas(["site_manager"], "workflow.design")).toBe(false);
  });
});

describe("role seniority", () => {
  it("gives every role the ability to view workflows", () => {
    for (const role of ALL_ROLES) {
      expect(roleHas([role], "workflow.view")).toBe(true);
    }
  });

  it("restricts workspace administration to the platform admin", () => {
    expect(roleHas(["platform_admin"], "workspace.manage")).toBe(true);
    for (const role of ALL_ROLES.filter((r) => r !== "platform_admin")) {
      expect(roleHas([role], "workspace.manage")).toBe(false);
    }
  });

  it("lets a viewer comment but not transition", () => {
    expect(roleHas(["viewer"], "instance.comment")).toBe(true);
    expect(roleHas(["viewer"], "instance.transition")).toBe(false);
  });

  it("lets a participant transition but not approve", () => {
    expect(roleHas(["participant"], "instance.transition")).toBe(true);
    expect(roleHas(["participant"], "instance.approve")).toBe(false);
  });

  it("lets an approver approve", () => {
    expect(roleHas(["approver"], "instance.approve")).toBe(true);
  });

  it("gives the platform admin every capability", () => {
    const every: Capability[] = [
      "workflow.view", "workflow.design", "instance.create", "instance.transition",
      "instance.approve", "instance.comment", "instance.metadata", "media.upload",
      "user.manage", "workspace.manage",
    ];
    for (const cap of every) {
      expect(roleHas(["platform_admin"], cap)).toBe(true);
    }
  });

  it("never grants a junior role something a senior one lacks", () => {
    // Seniority has to be monotonic or the UI contradicts itself: a designer
    // would see fewer controls than the participant they are supervising.
    const every: Capability[] = [
      "workflow.view", "workflow.design", "workflow.publish", "instance.create",
      "instance.transition", "instance.approve", "instance.comment",
      "instance.metadata", "media.upload", "user.manage", "workspace.manage",
    ];
    const order = [...ALL_ROLES].reverse(); // viewer first, admin last
    for (const cap of every) {
      let seen = false;
      for (const role of order) {
        const held = roleHas([role], cap);
        if (seen && !held) {
          throw new Error(`${role} lacks '${cap}' held by a more junior role`);
        }
        seen = seen || held;
      }
    }
  });
});
