import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../../api/client";
import { MediaAsset } from "../../types/api";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default function SceneAssetField({
  workflowId,
  value,
  onChange,
  accept,
  error,
}: {
  workflowId: string;
  value?: string;
  onChange: (value: string) => void;
  accept?: string;
  error?: string;
}) {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const { data: assets = [] } = useQuery<MediaAsset[]>({
    queryKey: ["workflow-media-assets", workflowId],
    queryFn: async () => {
      const resp = await apiClient.get(`/media/?workflow_definition=${workflowId}`);
      return resp.data.results ?? resp.data ?? [];
    },
    enabled: Boolean(workflowId),
  });

  const upload = async (file: File) => {
    setUploading(true);
    setUploadError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("workflow_definition", workflowId);
      const resp = await apiClient.post("/media/", formData);
      const created = resp.data as MediaAsset;
      qc.setQueryData<MediaAsset[]>(["workflow-media-assets", workflowId], (current = []) => {
        const rest = current.filter((asset) => asset.id !== created.id);
        return [created, ...rest];
      });
      onChange(created.id);
    } catch (err: any) {
      setUploadError(
        err?.response?.data?.detail ??
        err?.response?.data?.file?.[0] ??
        "Upload failed."
      );
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const selectedAssetId = value && UUID_RE.test(value) ? value : "";
  const selectedAsset = assets.find((asset) => asset.id === selectedAssetId);
  const helper = selectedAsset
    ? `Using uploaded asset: ${selectedAsset.original_name}`
    : value
      ? "Using external URL"
      : "Paste a URL, pick an uploaded asset, or upload a new one.";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <input
        value={value ?? ""}
        onChange={(e) => {
          setUploadError(null);
          onChange(e.target.value);
        }}
        placeholder="https://… or uploaded asset id"
        style={{ fontFamily: "monospace", fontSize: "0.8rem" }}
      />

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto auto", gap: 8 }}>
        <select
          value={selectedAssetId}
          onChange={(e) => {
            setUploadError(null);
            onChange(e.target.value);
          }}
        >
          <option value="">Pick existing uploaded asset…</option>
          {assets.map((asset) => (
            <option key={asset.id} value={asset.id}>
              {asset.original_name}
            </option>
          ))}
        </select>

        <input
          ref={inputRef}
          type="file"
          accept={accept}
          style={{ display: "none" }}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) upload(file);
          }}
        />

        <button
          type="button"
          className="btn-secondary btn-sm"
          disabled={uploading}
          onClick={() => inputRef.current?.click()}
        >
          {uploading ? "Uploading…" : "Upload…"}
        </button>

        <button
          type="button"
          className="btn-ghost btn-sm"
          disabled={!value}
          onClick={() => {
            setUploadError(null);
            onChange("");
          }}
          style={{ paddingInline: 10 }}
        >
          Clear
        </button>
      </div>

      <div className="text-xs text-muted">{helper}</div>
      {error && <div className="text-xs" style={{ color: "var(--danger)" }}>{error}</div>}
      {uploadError && <div className="text-xs" style={{ color: "var(--danger)" }}>{uploadError}</div>}
    </div>
  );
}
