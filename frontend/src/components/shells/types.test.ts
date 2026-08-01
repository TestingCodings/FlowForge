import { describe, expect, it } from "vitest";

import { Workflow, WorkflowInstance } from "../../types/api";
import {
  computedValue,
  groupLabel,
  groupValue,
  instanceTitle,
  stateColour,
  stateIcon,
} from "./types";

/**
 * The shell contract's field resolvers.
 *
 * Every shell reads instance data through these, so a mistake here shows up
 * as a whole board rendering blank rather than as an error. They were only
 * ever exercised through a browser before, which is slow and tells you a
 * column is empty without telling you why.
 */

function instance(over: Partial<WorkflowInstance> = {}): WorkflowInstance {
  return {
    id: "i1",
    reference_number: "REF-2026-00001",
    current_state_name: "Open",
    metadata_json: {},
    computed: {},
    ...over,
  } as WorkflowInstance;
}

function workflow(uiSchema: Record<string, unknown> = {}): Workflow {
  return { id: "w1", name: "Test", ui_schema: uiSchema } as unknown as Workflow;
}

describe("groupValue", () => {
  it("reads the current state", () => {
    expect(groupValue(instance({ current_state_name: "Triaged" }), "current_state")).toBe("Triaged");
  });

  it("reads the parent reference", () => {
    expect(groupValue(instance({ parent_reference: "AST-1" } as never), "parent")).toBe("AST-1");
  });

  it("reads a metadata key", () => {
    expect(groupValue(instance({ metadata_json: { suite: "Auth" } }), "metadata.suite")).toBe("Auth");
  });

  it("reads a computed key", () => {
    expect(groupValue(instance({ computed: { open_jobs: 4 } }), "computed.open_jobs")).toBe("4");
  });

  it("coerces numbers and booleans to strings", () => {
    expect(groupValue(instance({ metadata_json: { n: 0 } }), "metadata.n")).toBe("0");
    expect(groupValue(instance({ metadata_json: { b: false } }), "metadata.b")).toBe("false");
  });

  it("returns empty for a missing key rather than 'undefined'", () => {
    // Grouping on a key some instances lack is normal; the literal string
    // "undefined" would show up as a column heading.
    expect(groupValue(instance(), "metadata.nope")).toBe("");
    expect(groupValue(instance(), "computed.nope")).toBe("");
  });

  it("returns empty for an unrecognised field", () => {
    expect(groupValue(instance(), "assignee")).toBe("");
  });

  it("survives absent metadata and computed objects", () => {
    const bare = { id: "x" } as WorkflowInstance;
    expect(groupValue(bare, "metadata.a")).toBe("");
    expect(groupValue(bare, "computed.a")).toBe("");
  });
});

describe("groupLabel", () => {
  it("names the built-ins", () => {
    expect(groupLabel("current_state")).toBe("State");
    expect(groupLabel("parent")).toBe("Parent");
  });

  it("strips the prefix from metadata and computed fields", () => {
    expect(groupLabel("metadata.priority")).toBe("priority");
    expect(groupLabel("computed.days_open")).toBe("days_open");
  });

  it("passes an unknown field through unchanged", () => {
    expect(groupLabel("assignee")).toBe("assignee");
  });
});

describe("computedValue", () => {
  it("returns the raw value, not a string", () => {
    expect(computedValue(instance({ computed: { total: 1250 } }), "total")).toBe(1250);
  });

  it("returns null when absent", () => {
    expect(computedValue(instance(), "total")).toBeNull();
  });

  it("returns null rather than undefined for a missing computed block", () => {
    expect(computedValue({ id: "x" } as WorkflowInstance, "total")).toBeNull();
  });
});

describe("instanceTitle", () => {
  it("resolves the configured title field", () => {
    const wf = workflow({ title_field: "summary" });
    const inst = instance({ metadata_json: { summary: "Chiller fault" } });
    expect(instanceTitle(wf, inst)).toBe("Chiller fault");
  });

  it("returns null when no title field is configured", () => {
    expect(instanceTitle(workflow(), instance())).toBeNull();
  });

  it("returns null for an empty value so the caller can fall back", () => {
    // Falling back to the reference number is the caller's job; returning ""
    // here would render a blank card heading.
    const wf = workflow({ title_field: "summary" });
    expect(instanceTitle(wf, instance({ metadata_json: { summary: "" } }))).toBeNull();
    expect(instanceTitle(wf, instance({ metadata_json: {} }))).toBeNull();
  });

  it("stringifies a non-string title", () => {
    const wf = workflow({ title_field: "n" });
    expect(instanceTitle(wf, instance({ metadata_json: { n: 42 } }))).toBe("42");
  });
});

describe("stateColour and stateIcon", () => {
  const wf = workflow({
    state_display: { Open: { colour: "#f59e0b", icon: "alert" }, Done: { colour: "#22c55e" } },
  });

  it("resolves a configured colour", () => {
    expect(stateColour(wf, "Open")).toBe("#f59e0b");
  });

  it("returns undefined for an unconfigured state", () => {
    expect(stateColour(wf, "Missing")).toBeUndefined();
    expect(stateIcon(wf, "Done")).toBeUndefined();
  });

  it("maps a named icon to its glyph", () => {
    expect(stateIcon(wf, "Open")).toBe("!");
  });

  it("passes an unknown icon name through so it is visible rather than dropped", () => {
    const odd = workflow({ state_display: { Open: { icon: "rocket" } } });
    expect(stateIcon(odd, "Open")).toBe("rocket");
  });

  it("survives a workflow with no ui_schema at all", () => {
    const bare = { id: "w" } as Workflow;
    expect(stateColour(bare, "Open")).toBeUndefined();
    expect(stateIcon(bare, "Open")).toBeUndefined();
  });
});
