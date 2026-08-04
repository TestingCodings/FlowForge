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
  "nav.topology": "Topology",
  "nav.tasks": "My Tasks",
  "nav.workflows": "Workflows",
  "nav.newWorkflow": "New Workflow",
  "nav.templates": "Templates",
  "nav.auditLog": "Audit Log",
  "nav.users": "Users",
  "nav.roles": "Roles",
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

  // Pages
  "page.dashboard.title": "Dashboard",
  "page.dashboard.subtitle": "Platform overview — instances, tasks, and workflow performance",
  "page.workflows.title": "Workflows",
  "page.workflows.subtitle": "{count} definitions · {active} active",
  "page.instances.title": "Instances",
  "page.instances.subtitle": "{total} total · {active} active · {done} completed",
  "page.login.subtitle": "Sign in to your workspace",

  // Dashboard stats
  "stat.openTasks": "Open Tasks",
  "stat.openTasks.sub": "Awaiting action",
  "stat.activeInstances": "Active Instances",
  "stat.activeInstances.sub": "In progress",
  "stat.completed": "Completed",
  "stat.completed.sub": "{rate}% completion rate",
  "stat.workflows": "Workflows",
  "stat.workflows.sub": "Active definitions",

  // {n} is interpolated by the t() function.
  "instances.count": "{n} instances",
} as const;

export type MessageKey = keyof typeof enGB;
export type Catalogue = Partial<Record<MessageKey, string>>;
