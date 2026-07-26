import type { Catalogue } from "./en-GB";

/**
 * German (de-DE). A partial catalogue: any key omitted here falls back to
 * en-GB, which is how a translation can ship incrementally.
 */
export const deDE: Catalogue = {
  "nav.overview": "Übersicht",
  "nav.configuration": "Konfiguration",
  "nav.administration": "Verwaltung",
  "nav.dashboard": "Dashboard",
  "nav.instances": "Instanzen",
  "nav.topology": "Topologie",
  "nav.tasks": "Meine Aufgaben",
  "nav.workflows": "Workflows",
  "nav.newWorkflow": "Neuer Workflow",
  "nav.templates": "Vorlagen",
  "nav.auditLog": "Auditprotokoll",
  "nav.users": "Benutzer",
  "nav.workspace": "Arbeitsbereich",
  "nav.userGuide": "Benutzerhandbuch",

  "action.save": "Speichern",
  "action.cancel": "Abbrechen",
  "action.delete": "Löschen",
  "action.edit": "Bearbeiten",
  "action.close": "Schließen",
  "action.signOut": "Abmelden",

  "common.loading": "Wird geladen…",
  "common.search": "Suchen",
  "common.status": "Status",
  "common.completed": "Abgeschlossen",
  "common.inProgress": "In Bearbeitung",

  "page.dashboard.title": "Dashboard",
  "page.dashboard.subtitle": "Plattformübersicht — Instanzen, Aufgaben und Workflow-Leistung",
  "page.workflows.title": "Workflows",
  "page.workflows.subtitle": "{count} Definitionen · {active} aktiv",
  "page.instances.title": "Instanzen",
  "page.instances.subtitle": "{total} gesamt · {active} aktiv · {done} abgeschlossen",
  "page.login.subtitle": "Melden Sie sich bei Ihrem Arbeitsbereich an",

  "stat.openTasks": "Offene Aufgaben",
  "stat.openTasks.sub": "Warten auf Bearbeitung",
  "stat.activeInstances": "Aktive Instanzen",
  "stat.activeInstances.sub": "In Bearbeitung",
  "stat.completed": "Abgeschlossen",
  "stat.completed.sub": "{rate} % Abschlussquote",
  "stat.workflows": "Workflows",
  "stat.workflows.sub": "Aktive Definitionen",

  "instances.count": "{n} Instanzen",
};
