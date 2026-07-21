import { ComponentType } from "react";

import { ShellName } from "../../types/api";
import { ShellProps } from "./types";
import KanbanShell from "./KanbanShell";
import TableShell from "./TableShell";
import CalendarShell from "./CalendarShell";
import MatrixShell from "./MatrixShell";

/**
 * The shell registry — the Layer 2/3 extension point.
 *
 * "list" maps to the platform's default instances table, so it has no entry
 * here; WorkflowViewPage redirects list-shell workflows to /instances.
 * Adding a shell = one component implementing ShellProps + one line here.
 */
export const SHELL_REGISTRY: Partial<Record<ShellName, ComponentType<ShellProps>>> = {
  kanban: KanbanShell,
  table: TableShell,
  calendar: CalendarShell,
  matrix: MatrixShell,
};

export const SHELL_OPTIONS: { value: ShellName; label: string }[] = [
  { value: "list",     label: "List (default)" },
  { value: "kanban",   label: "Kanban board" },
  { value: "table",    label: "Table" },
  { value: "calendar", label: "Calendar" },
  { value: "matrix",   label: "Matrix (TestRail-style)" },
];

export type { ShellProps } from "./types";
