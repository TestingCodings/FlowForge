import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { apiClient } from "../api/client";
import { WorkflowInstance } from "../types/api";

export default function InstancesPage() {
  const { data } = useQuery({
    queryKey: ["instances"],
    queryFn: async () => {
      const response = await apiClient.get("/instances/");
      return response.data.results as WorkflowInstance[];
    },
  });

  return (
    <div className="card">
      <h2>Instances</h2>
      <table className="table">
        <thead>
          <tr>
            <th>Reference</th>
            <th>Workflow</th>
            <th>State</th>
          </tr>
        </thead>
        <tbody>
          {(data ?? []).map((instance) => (
            <tr key={instance.id}>
              <td>
                <Link to={`/instances/${instance.id}`}>{instance.reference_number}</Link>
              </td>
              <td>{instance.workflow_definition_name}</td>
              <td>{instance.current_state_name}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
