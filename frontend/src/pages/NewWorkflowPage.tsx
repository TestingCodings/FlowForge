import { useState } from "react";

import { useWorkflowTemplates, WorkflowCategory } from "../hooks/useWorkflowTemplates";

export default function NewWorkflowPage() {
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState<WorkflowCategory>("insurance");
  const { categories, createByCategory, createFullSet } = useWorkflowTemplates();

  const createSingle = async () => {
    setStatus(`Creating ${category} workflow...`);
    try {
      await createByCategory(category);
      setStatus(`Workflow created for ${category}`);
    } catch {
      setStatus(`Failed to create ${category} workflow`);
    }
  };

  const createAll = async () => {
    setStatus("Creating full category set...");
    try {
      const result = await createFullSet();
      if (result.failures.length === 0) {
        setStatus(`Full set created (${result.created.length} workflows)`);
        return;
      }
      setStatus(
        `Created: ${result.created.join(", ") || "none"}. Failed: ${result.failures.join(", ")}`
      );
    } catch {
      setStatus("Failed to create full set");
    }
  };

  return (
    <div className="card">
      <h2>Create Workflow</h2>
      <p>Quick-create a workflow by category or create a full starter set of categories.</p>
      <div className="grid two">
        <div>
          <label>Category</label>
          <select value={category} onChange={(event) => setCategory(event.target.value as WorkflowCategory)}>
            {categories.map((entry) => (
              <option key={entry.value} value={entry.value}>
                {entry.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="header" style={{ marginTop: 12 }}>
        <button onClick={createSingle}>Create Category Workflow</button>
        <button className="secondary" onClick={createAll}>Create Full Set</button>
      </div>
      {status ? <p>{status}</p> : null}
    </div>
  );
}
