/**
 * Base translation catalogue (en-GB) — the source of truth for message keys.
 *
 * Every other locale is a Partial of this shape; missing keys fall back to
 * en-GB at lookup time, so a half-translated locale never shows a blank
 * string. Keys are dot-namespaced by area ("nav.dashboard").
 */
export const enGB = {
  "nav.overview": "Overview",
  "nav.configuration": "Configuration",
  "nav.administration": "Administration",
  "nav.dashboard": "Dashboard",
  "nav.instances": "Instances",
  "nav.tasks": "My Tasks",
  "nav.workflows": "Workflows",
  "nav.newWorkflow": "New Workflow",
  "nav.templates": "Templates",
  "nav.auditLog": "Audit Log",
  "nav.users": "Users",
  "nav.workspace": "Workspace",
  "nav.userGuide": "User Guide",

  "action.save": "Save",
  "action.cancel": "Cancel",
  "action.delete": "Delete",
  "action.edit": "Edit",
  "action.close": "Close",
  "action.signOut": "Sign out",

  "common.loading": "Loading…",
  "common.search": "Search",
  "common.status": "Status",
  "common.completed": "Completed",
  "common.inProgress": "In Progress",

  // {n} is interpolated by the t() function.
  "instances.count": "{n} instances",
} as const;

export type MessageKey = keyof typeof enGB;
export type Catalogue = Partial<Record<MessageKey, string>>;
