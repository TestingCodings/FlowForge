import type { Catalogue } from "./en-GB";

/**
 * French (fr-FR). A partial catalogue: any key omitted here falls back to
 * en-GB, which is how a translation can ship incrementally.
 */
export const frFR: Catalogue = {
  "nav.overview": "Vue d'ensemble",
  "nav.configuration": "Configuration",
  "nav.administration": "Administration",
  "nav.dashboard": "Tableau de bord",
  "nav.instances": "Instances",
  "nav.topology": "Topologie",
  "nav.tasks": "Mes tâches",
  "nav.workflows": "Flux de travail",
  "nav.newWorkflow": "Nouveau flux",
  "nav.templates": "Modèles",
  "nav.auditLog": "Journal d'audit",
  "nav.users": "Utilisateurs",
  "nav.roles": "Rôles",
  "nav.workspace": "Espace de travail",
  "nav.userGuide": "Guide de l'utilisateur",

  "action.save": "Enregistrer",
  "action.cancel": "Annuler",
  "action.delete": "Supprimer",
  "action.edit": "Modifier",
  "action.close": "Fermer",
  "action.signOut": "Se déconnecter",

  "common.loading": "Chargement…",
  "common.search": "Rechercher",
  "common.status": "Statut",
  "common.completed": "Terminé",
  "common.inProgress": "En cours",

  "page.dashboard.title": "Tableau de bord",
  "page.dashboard.subtitle": "Vue d'ensemble — instances, tâches et performance des flux",
  "page.workflows.title": "Flux de travail",
  "page.workflows.subtitle": "{count} définitions · {active} actives",
  "page.instances.title": "Instances",
  "page.instances.subtitle": "{total} au total · {active} actives · {done} terminées",
  "page.login.subtitle": "Connectez-vous à votre espace de travail",

  "stat.openTasks": "Tâches ouvertes",
  "stat.openTasks.sub": "En attente d'action",
  "stat.activeInstances": "Instances actives",
  "stat.activeInstances.sub": "En cours",
  "stat.completed": "Terminées",
  "stat.completed.sub": "{rate} % de taux d'achèvement",
  "stat.workflows": "Flux de travail",
  "stat.workflows.sub": "Définitions actives",

  "instances.count": "{n} instances",
};
