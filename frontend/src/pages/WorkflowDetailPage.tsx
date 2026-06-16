import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { apiClient } from "../api/client";

export default function WorkflowDetailPage() {
  const { id } = useParams();

  const { data } = useQuery({
    queryKey: ["workflow", id],
    queryFn: async () => {
      const response = await apiClient.get(`/workflows/${id}/`);
      return response.data;
    },
    enabled: Boolean(id),
  });

  return (
    <div className="grid two">
      <div className="card">
        <h2>{data?.name ?? "Workflow"}</h2>
        <p>{data?.description}</p>
      </div>
      <div className="card">
        <h3>States</h3>
        <ul>
          {(data?.states ?? []).map((state: any) => (
            <li key={state.id}>{state.name}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
