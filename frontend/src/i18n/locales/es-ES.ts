import type { Catalogue } from "./en-GB";

/**
 * Spanish (es-ES). A partial catalogue: any key omitted here falls back to
 * en-GB, which is how a translation can ship incrementally.
 */
export const esES: Catalogue = {
  "nav.overview": "Resumen",
  "nav.configuration": "Configuración",
  "nav.administration": "Administración",
  "nav.dashboard": "Panel",
  "nav.instances": "Instancias",
  "nav.tasks": "Mis tareas",
  "nav.workflows": "Flujos de trabajo",
  "nav.newWorkflow": "Nuevo flujo",
  "nav.templates": "Plantillas",
  "nav.auditLog": "Registro de auditoría",
  "nav.users": "Usuarios",
  "nav.workspace": "Espacio de trabajo",
  "nav.userGuide": "Guía del usuario",

  "action.save": "Guardar",
  "action.cancel": "Cancelar",
  "action.delete": "Eliminar",
  "action.edit": "Editar",
  "action.close": "Cerrar",
  "action.signOut": "Cerrar sesión",

  "common.loading": "Cargando…",
  "common.search": "Buscar",
  "common.status": "Estado",
  "common.completed": "Completado",
  "common.inProgress": "En curso",

  "instances.count": "{n} instancias",
};
