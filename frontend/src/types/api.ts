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
  is_active: boolean;
  created_at: string;
  updated_at: string;
  states: State[];
  transitions: Transition[];
  rules: Rule[];
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
