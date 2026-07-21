import { Transition, Workflow, WorkflowInstance } from "../../types/api";

/**
 * The shell contract (VISION Layer 2).
 *
 * A shell is a pure presentation component: it receives the workflow
 * definition, its instances, and a callback to fire transitions. It never
 * mutates state itself — every action goes through fireTransition so the
 * engine (rules, approvals, required forms) always has the final word.
 *
 * Layer 3 consumes this same contract: an exported app bakes in the registry
 * and renders whichever shell the bundled ui_schema names. To add a shell,
 * implement ShellProps and register it in SHELL_REGISTRY (see index.ts) —
 * docs/SHELLS.md has the full guide.
 */
export interface ShellProps {
  workflow: Workflow;
  instances: WorkflowInstance[];
  /** Fire a transition through the engine; errors surface via the host page. */
  fireTransition: (instance: WorkflowInstance, transition: Transition) => void;
  transitionPending: boolean;
}

/** Resolve the configured colour for a state, if any. */
export function stateColour(workflow: Workflow, stateName: string): string | undefined {
  return workflow.ui_schema?.state_display?.[stateName]?.colour;
}

/**
 * Named icons from ui_schema.state_display rendered as glyphs.
 *
 * The VISION spec names icons like "circle" / "play" / "check" / "x"; we map
 * that vocabulary to unicode so no icon-font dependency is needed and the
 * glyphs survive PNG export.
 */
const ICON_GLYPHS: Record<string, string> = {
  circle: "○", "dot-filled": "●", play: "▶", pause: "❚❚", check: "✓",
  x: "✕", alert: "!", clock: "◷", star: "★", flag: "⚑",
  lock: "🔒", search: "🔍", edit: "✎", inbox: "▤", archive: "▣",
};

/** Resolve the configured icon glyph for a state, if any. */
export function stateIcon(workflow: Workflow, stateName: string): string | undefined {
  const icon = workflow.ui_schema?.state_display?.[stateName]?.icon;
  if (!icon) return undefined;
  return ICON_GLYPHS[icon] ?? icon;
}

export const ICON_OPTIONS = Object.keys(ICON_GLYPHS);
export { ICON_GLYPHS };

/**
 * Resolve a grouping key for an instance.
 *
 * Accepts "current_state", "parent", or "metadata.<key>" — the vocabulary
 * shared by matrix rows/columns and kanban swimlanes.
 */
export function groupValue(instance: WorkflowInstance, field: string): string {
  if (field === "current_state") return instance.current_state_name ?? "";
  if (field === "parent") return instance.parent_reference ?? "";
  if (field.startsWith("metadata.")) {
    const v = (instance.metadata_json ?? {})[field.slice(9)];
    return v === undefined || v === null ? "" : String(v);
  }
  return "";
}

/** Human label for a grouping field, for headers and legends. */
export function groupLabel(field: string): string {
  if (field === "current_state") return "State";
  if (field === "parent") return "Parent";
  if (field.startsWith("metadata.")) return field.slice(9);
  return field;
}

/** Resolve a card/row title from ui_schema.title_field, falling back to the reference. */
export function instanceTitle(workflow: Workflow, instance: WorkflowInstance): string | null {
  const field = workflow.ui_schema?.title_field;
  if (!field) return null;
  const value = (instance.metadata_json ?? {})[field];
  return value === undefined || value === null || value === "" ? null : String(value);
}
