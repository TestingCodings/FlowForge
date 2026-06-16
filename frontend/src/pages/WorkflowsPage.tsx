import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { apiClient } from "../api/client";
import { Workflow } from "../types/api";

export default function WorkflowsPage() {
  const { data } = useQuery({
    queryKey: ["workflows"],
    queryFn: async () => {
      const response = await apiClient.get("/workflows/");
      return response.data.results as Workflow[];
    },
  });

  return (
    <div className="card">
      <div className="header">
        <h2>Workflows</h2>
        <Link to="/workflows/new">
          <button>Create</button>
        </Link>
      </div>
      <table className="table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Version</th>
            <th>Active</th>
          </tr>
        </thead>
        <tbody>
          {(data ?? []).map((workflow) => (
            <tr key={workflow.id}>
              <td>
                <Link to={`/workflows/${workflow.id}`}>{workflow.name}</Link>
              </td>
              <td>{workflow.version}</td>
              <td>{workflow.is_active ? "Yes" : "No"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
