import { useQuery } from "@tanstack/react-query";

import { apiClient } from "../api/client";

export default function AuditPage() {
  const { data } = useQuery({
    queryKey: ["audit"],
    queryFn: async () => {
      const response = await apiClient.get("/audit/");
      return response.data.results;
    },
  });

  return (
    <div className="card">
      <h2>Audit Log</h2>
      <table className="table">
        <thead>
          <tr>
            <th>Action</th>
            <th>From</th>
            <th>To</th>
            <th>When</th>
          </tr>
        </thead>
        <tbody>
          {(data ?? []).map((row: any) => (
            <tr key={row.id}>
              <td>{row.action_type}</td>
              <td>{row.from_state}</td>
              <td>{row.to_state}</td>
              <td>{row.created_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
