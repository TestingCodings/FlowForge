import { useState } from "react";

import { apiClient } from "../api/client";

const seedWorkflow = {
  name: "Example Approval",
  description: "Starter workflow",
  version: 1,
  is_active: true,
  states: [
    { name: "Draft", is_initial: true, is_terminal: false, position_order: 1 },
    { name: "Review", is_initial: false, is_terminal: false, position_order: 2 },
    { name: "Completed", is_initial: false, is_terminal: true, position_order: 3 }
  ],
  transitions: [
    { name: "Submit", from_state: "Draft", to_state: "Review" },
    { name: "Complete", from_state: "Review", to_state: "Completed" }
  ]
};

export default function NewWorkflowPage() {
  const [status, setStatus] = useState("");

  const create = async () => {
    setStatus("Creating...");
    try {
      await apiClient.post("/workflows/", seedWorkflow);
      setStatus("Workflow created");
    } catch {
      setStatus("Failed to create workflow");
    }
  };

  return (
    <div className="card">
      <h2>Create Workflow</h2>
      <p>This creates a starter workflow template you can edit in API/Django admin.</p>
      <button onClick={create}>Create Starter Workflow</button>
      {status ? <p>{status}</p> : null}
    </div>
  );
}
