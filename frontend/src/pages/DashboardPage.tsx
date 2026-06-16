import { useQuery } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { TaskItem } from "../types/api";

export default function DashboardPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["tasks"],
    queryFn: async () => {
      const response = await apiClient.get("/tasks/");
      return response.data.results as TaskItem[];
    },
  });

  return (
    <div className="card">
      <h2>Task Inbox</h2>
      {isLoading ? <p>Loading...</p> : null}
      <table className="table">
        <thead>
          <tr>
            <th>Title</th>
            <th>Workflow</th>
            <th>State</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {(data ?? []).map((task) => (
            <tr key={task.id}>
              <td>{task.title}</td>
              <td>{task.workflow_reference}</td>
              <td>{task.state_name}</td>
              <td>{task.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
