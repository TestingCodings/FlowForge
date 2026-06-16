import { useMemo } from "react";

import { apiClient } from "../api/client";

export type WorkflowCategory = "insurance" | "hr" | "engineering" | "finance";

type WorkflowStatePayload = {
  name: string;
  display_name: string;
  is_initial: boolean;
  is_terminal: boolean;
  position_order: number;
};

type WorkflowTransitionPayload = {
  name: string;
  from_state: string;
  to_state: string;
  requires_approval: boolean;
};

type WorkflowPayload = {
  name: string;
  description: string;
  version: number;
  is_active: boolean;
  states: WorkflowStatePayload[];
  transitions: WorkflowTransitionPayload[];
};

type TemplateMap = Record<WorkflowCategory, WorkflowPayload>;

const baseTemplates: TemplateMap = {
  insurance: {
    name: "Insurance Claim Flow",
    description: "Claim intake, validation, and settlement approval",
    version: 1,
    is_active: true,
    states: [
      { name: "Intake", display_name: "Intake", is_initial: true, is_terminal: false, position_order: 1 },
      { name: "Review", display_name: "Review", is_initial: false, is_terminal: false, position_order: 2 },
      { name: "Settled", display_name: "Settled", is_initial: false, is_terminal: true, position_order: 3 },
    ],
    transitions: [
      { name: "Submit", from_state: "Intake", to_state: "Review", requires_approval: false },
      { name: "Approve Settlement", from_state: "Review", to_state: "Settled", requires_approval: true },
    ],
  },
  hr: {
    name: "Employee Onboarding Flow",
    description: "New hire approvals, setup, and completion",
    version: 1,
    is_active: true,
    states: [
      { name: "Offer Accepted", display_name: "Offer Accepted", is_initial: true, is_terminal: false, position_order: 1 },
      { name: "Provisioning", display_name: "Provisioning", is_initial: false, is_terminal: false, position_order: 2 },
      { name: "Onboarded", display_name: "Onboarded", is_initial: false, is_terminal: true, position_order: 3 },
    ],
    transitions: [
      { name: "Start Setup", from_state: "Offer Accepted", to_state: "Provisioning", requires_approval: false },
      { name: "Complete Onboarding", from_state: "Provisioning", to_state: "Onboarded", requires_approval: false },
    ],
  },
  engineering: {
    name: "Bug Resolution Flow",
    description: "Bug triage, implementation, and verification",
    version: 1,
    is_active: true,
    states: [
      { name: "Reported", display_name: "Reported", is_initial: true, is_terminal: false, position_order: 1 },
      { name: "In Progress", display_name: "In Progress", is_initial: false, is_terminal: false, position_order: 2 },
      { name: "Verified", display_name: "Verified", is_initial: false, is_terminal: true, position_order: 3 },
    ],
    transitions: [
      { name: "Assign", from_state: "Reported", to_state: "In Progress", requires_approval: false },
      { name: "QA Verify", from_state: "In Progress", to_state: "Verified", requires_approval: true },
    ],
  },
  finance: {
    name: "Purchase Approval Flow",
    description: "Purchase request, budget review, and approval",
    version: 1,
    is_active: true,
    states: [
      { name: "Requested", display_name: "Requested", is_initial: true, is_terminal: false, position_order: 1 },
      { name: "Budget Review", display_name: "Budget Review", is_initial: false, is_terminal: false, position_order: 2 },
      { name: "Approved", display_name: "Approved", is_initial: false, is_terminal: true, position_order: 3 },
    ],
    transitions: [
      { name: "Send To Review", from_state: "Requested", to_state: "Budget Review", requires_approval: false },
      { name: "Approve Purchase", from_state: "Budget Review", to_state: "Approved", requires_approval: true },
    ],
  },
};

function withUniqueName(template: WorkflowPayload): WorkflowPayload {
  const suffix = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
  return {
    ...template,
    name: `${template.name} ${suffix}`,
  };
}

export function useWorkflowTemplates() {
  const categories = useMemo(
    () => [
      { value: "insurance", label: "Insurance" },
      { value: "hr", label: "HR" },
      { value: "engineering", label: "Engineering" },
      { value: "finance", label: "Finance" },
    ] satisfies Array<{ value: WorkflowCategory; label: string }>,
    []
  );

  const createByCategory = async (category: WorkflowCategory) => {
    const payload = withUniqueName(baseTemplates[category]);
    await apiClient.post("/workflows/", payload);
  };

  const createFullSet = async () => {
    const created: string[] = [];
    const failures: string[] = [];

    for (const category of Object.keys(baseTemplates) as WorkflowCategory[]) {
      try {
        await createByCategory(category);
        created.push(category);
      } catch {
        failures.push(category);
      }
    }

    return { created, failures };
  };

  return {
    categories,
    createByCategory,
    createFullSet,
  };
}
