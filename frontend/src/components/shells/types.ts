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
  return (workflow.ui_schema?.state_display as Record<string, { colour?: string }> | undefined)?.[
    stateName
  ]?.colour;
}

/** Resolve a card/row title from ui_schema.title_field, falling back to the reference. */
export function instanceTitle(workflow: Workflow, instance: WorkflowInstance): string | null {
  const field = workflow.ui_schema?.title_field;
  if (!field) return null;
  const value = (instance.metadata_json ?? {})[field];
  return value === undefined || value === null || value === "" ? null : String(value);
}
