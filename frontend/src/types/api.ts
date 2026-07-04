export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface UserProfile {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  roles: string[];
  date_joined: string;
}

export interface TaskItem {
  id: string;
  title: string;
  status: string;
  state_name: string;
  workflow_reference: string;
  assigned_to_role: string;
  due_at: string | null;
}

export interface State {
  id: string;
  name: string;
  display_name: string;
  is_initial: boolean;
  is_terminal: boolean;
  position_order: number;
  sla_config: Record<string, unknown>;
  task_config: Record<string, unknown>;
  workflow_definition: string;
}

export interface Transition {
  id: string;
  name: string;
  display_name: string;
  from_state: string;
  to_state: string;
  requires_approval: boolean;
  workflow_definition: string;
}

export interface Rule {
  id: string;
  transition: string;
  condition: Record<string, unknown>;
  action: Record<string, unknown>;
  priority: number;
}

export interface Workflow {
  id: string;
  name: string;
  description: string;
  reference_prefix: string;
  version: number;
  published_at: string | null;
  parent: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  states: State[];
  transitions: Transition[];
  rules: Rule[];
}

export interface InstanceRelationship {
  id: string;
  from_instance: string;
  from_reference: string;
  from_workflow: string;
  from_state: string;
  from_completed: boolean;
  to_instance: string;
  to_reference: string;
  to_workflow: string;
  to_state: string;
  to_completed: boolean;
  rel_type: string;
  notes: string;
  created_by_name: string;
  created_at: string;
}

export interface InstanceSearchResult {
  id: string;
  reference_number: string;
  workflow_name: string;
  current_state: string;
  completed: boolean;
}

export interface SlaInfo {
  status: "ok" | "warning" | "breached";
  sla_hours: number;
  elapsed_hours: number;
  entered_at: string;
}

export interface WebhookSubscription {
  id: string;
  workflow_definition: string | null;
  workflow_name: string | null;
  url: string;
  events: string[];
  is_active: boolean;
  created_at: string;
}

export interface FormField {
  name: string;
  type: "text" | "textarea" | "number" | "currency" | "checkbox" | "toggle" | "dropdown" | "date" | "datetime";
  required?: boolean;
  label?: string;
  min?: number;
  max?: number;
  options?: string[];
}

export interface FormSchema {
  required_to_transition?: boolean;
  fields: FormField[];
}

export interface CurrentForm {
  id: string;
  name: string;
  schema: FormSchema;
  version: number;
  required_to_transition: boolean;
  submitted: boolean;
  submission_data: Record<string, unknown> | null;
  submitted_at: string | null;
}

export interface FormDefinitionApi {
  id: string;
  workflow_definition: string;
  state: string;
  name: string;
  schema: FormSchema;
  version: number;
  created_at: string;
}

export interface WorkflowInstance {
  id: string;
  reference_number: string;
  workflow_definition: string;
  workflow_definition_name: string;
  current_state: string;
  current_state_name: string;
  metadata_json: Record<string, unknown>;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  created_by: string;
  sla: SlaInfo | null;
  relationships: InstanceRelationship[];
  current_form: CurrentForm | null;
}

export interface AuditEntry {
  id: string;
  action_type: string;
  from_state: string | null;
  to_state: string | null;
  actor_email: string;
  created_at: string;
  payload: Record<string, unknown>;
}

export type RoleName =
  | "platform_admin"
  | "workflow_designer"
  | "approver"
  | "participant"
  | "viewer";

export const ALL_ROLES: { value: RoleName; label: string }[] = [
  { value: "platform_admin",    label: "Platform Admin" },
  { value: "workflow_designer", label: "Workflow Designer" },
  { value: "approver",          label: "Approver" },
  { value: "participant",       label: "Participant" },
  { value: "viewer",            label: "Viewer" },
];
