import { ComponentType } from "react";

import { ShellName } from "../../types/api";
import { ShellProps } from "./types";
import KanbanShell from "./KanbanShell";
import TableShell from "./TableShell";
import CalendarShell from "./CalendarShell";
import MatrixShell from "./MatrixShell";
import ListShell from "./ListShell";

/**
 * The shell registry — the Layer 2/3 extension point.
 *
 * Every shell, including "list", is a first-class registry entry, so all of
 * them are configurable through the same ui_schema and rendered by the same
 * WorkflowViewPage. Adding a shell = one component implementing ShellProps +
 * one line here.
 */
export const SHELL_REGISTRY: Record<ShellName, ComponentType<ShellProps>> = {
  list: ListShell,
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
