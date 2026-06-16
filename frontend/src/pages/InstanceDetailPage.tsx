import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";

import { apiClient } from "../api/client";

export default function InstanceDetailPage() {
  const { id } = useParams();
  const [message, setMessage] = useState("");

  const { data, refetch } = useQuery({
    queryKey: ["instance", id],
    queryFn: async () => {
      const response = await apiClient.get(`/instances/${id}/`);
      return response.data;
    },
    enabled: Boolean(id),
  });

  const transition = async () => {
    try {
      const transitionsResponse = await apiClient.get("/transitions/");
      const transitions = transitionsResponse.data.results;
      const candidate = transitions.find((t: any) => t.from_state === data.current_state);
      if (!candidate) {
        setMessage("No available transition from current state");
        return;
      }
      await apiClient.post(`/instances/${id}/transition/`, { transition_id: candidate.id });
      setMessage("Transition applied");
      refetch();
    } catch {
      setMessage("Transition failed");
    }
  };

  return (
    <div className="grid two">
      <div className="card">
        <h2>{data?.reference_number}</h2>
        <p>Workflow: {data?.workflow_definition_name}</p>
        <p>Current state: {data?.current_state_name}</p>
        <button onClick={transition}>Advance Instance</button>
        {message ? <p>{message}</p> : null}
      </div>
      <div className="card">
        <h3>Metadata</h3>
        <pre>{JSON.stringify(data?.metadata ?? {}, null, 2)}</pre>
      </div>
    </div>
  );
}
