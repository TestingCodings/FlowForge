export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface UserProfile {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
}

export interface TaskItem {
  id: string;
  title: string;
  status: string;
  state_name: string;
  workflow_reference: string;
}

export interface Workflow {
  id: string;
  name: string;
  description: string;
  version: number;
  is_active: boolean;
}

export interface WorkflowInstance {
  id: string;
  reference_number: string;
  workflow_definition_name: string;
  current_state_name: string;
  metadata: Record<string, unknown>;
}
