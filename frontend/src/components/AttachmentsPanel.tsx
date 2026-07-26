import { ChangeEvent, DragEvent, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { MediaAsset } from "../types/api";
import { formatDateTime } from "../hooks/useWorkspace";

interface AttachmentsPanelProps {
  workflowInstanceId: string;
  currentUserId?: string;
  roles: string[];
}

const MANAGER_ROLES = new Set(["platform_admin", "workflow_designer"]);

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[i]}`;
}

function fileIcon(asset: MediaAsset): string {
  if (asset.content_type === "application/pdf") return "📄";
  if (asset.content_type === "application/zip") return "🗜️";
  if (asset.kind === "audio") return "🔊";
  return "📎";
}

export default function AttachmentsPanel({
  workflowInstanceId,
  currentUserId,
  roles,
}: AttachmentsPanelProps) {
  const qc = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [thumbUrls, setThumbUrls] = useState<Record<string, string>>({});

  const canUpload = useMemo(
    () => roles.some((r) => ["platform_admin", "workflow_designer", "approver", "participant"].includes(r)),
    [roles],
  );

  const { data: assets = [], isLoading } = useQuery<MediaAsset[]>({
    queryKey: ["media-assets", workflowInstanceId],
    queryFn: async () => {
      const resp = await apiClient.get(`/media/?workflow_instance=${encodeURIComponent(workflowInstanceId)}`);
      return resp.data?.results ?? [];
    },
    enabled: Boolean(workflowInstanceId),
  });

  useEffect(() => {
    let cancelled = false;
    const urlsToRevoke: string[] = [];

    (async () => {
      const imageAssets = assets.filter((a) => a.kind === "image");
      const nextUrls: Record<string, string> = {};

      await Promise.all(imageAssets.map(async (asset) => {
        try {
          const resp = await apiClient.get(asset.download_url, { responseType: "blob" });
          const blobUrl = URL.createObjectURL(resp.data);
          nextUrls[asset.id] = blobUrl;
          urlsToRevoke.push(blobUrl);
        } catch {
          // Keep non-fatal: individual thumbnails can fail while list still works.
        }
      }));

      if (!cancelled) setThumbUrls(nextUrls);
    })();

    return () => {
      cancelled = true;
      urlsToRevoke.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [assets]);

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("workflow_instance", workflowInstanceId);
      const resp = await apiClient.post("/media/", formData);
      return resp.data as MediaAsset;
    },
    onSuccess: () => {
      setUploadError(null);
      qc.invalidateQueries({ queryKey: ["media-assets", workflowInstanceId] });
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail;
      setUploadError(detail ?? (err?.response?.status === 403 ? "You do not have permission to upload files." : "Upload failed."));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (assetId: string) => {
      await apiClient.delete(`/media/${assetId}/`);
    },
    onSuccess: () => {
      setDeleteError(null);
      qc.invalidateQueries({ queryKey: ["media-assets", workflowInstanceId] });
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail;
      setDeleteError(detail ?? (err?.response?.status === 403 ? "You do not have permission to delete this file." : "Delete failed."));
    },
  });

  const handleUpload = (file?: File | null) => {
    if (!file) return;
    setUploadError(null);
    uploadMutation.mutate(file);
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    handleUpload(e.target.files?.[0]);
    e.target.value = "";
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
    if (!canUpload) return;
    handleUpload(e.dataTransfer.files?.[0]);
  };

  const canDelete = (asset: MediaAsset) =>
    Boolean(asset.uploaded_by && currentUserId && asset.uploaded_by === currentUserId)
    || roles.some((r) => MANAGER_ROLES.has(r));

  const downloadAsset = async (asset: MediaAsset) => {
    const resp = await apiClient.get(asset.download_url, { responseType: "blob" });
    const url = URL.createObjectURL(resp.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = asset.original_name || "attachment";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="card mt-4">
      <div className="card-header">
        <h3>Attachments</h3>
        <span className="badge badge-inactive">{assets.length}</span>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        onChange={handleFileChange}
        accept="image/jpeg,image/png,image/gif,application/pdf,application/zip"
        style={{ display: "none" }}
        disabled={!canUpload || uploadMutation.isPending}
      />

      <div
        onDragOver={(e) => { e.preventDefault(); if (canUpload) setIsDragOver(true); }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
        onClick={() => canUpload && fileInputRef.current?.click()}
        style={{
          border: `1px dashed ${isDragOver ? "var(--accent)" : "var(--border)"}`,
          borderRadius: 10,
          background: isDragOver ? "rgba(99,102,241,0.08)" : "var(--bg-elevated)",
          padding: 18,
          marginBottom: 14,
          textAlign: "center",
          cursor: canUpload ? "pointer" : "default",
        }}
      >
        {canUpload ? (
          <>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>
              {uploadMutation.isPending ? "Uploading…" : "Drag and drop a file, or click to browse"}
            </div>
            <div className="text-xs text-muted">Allowed: JPEG, PNG, GIF, PDF, ZIP · Max 20 MiB</div>
          </>
        ) : (
          <div className="text-sm text-muted">You need participant role or above to upload attachments.</div>
        )}
      </div>

      {uploadError && <div className="alert alert-error mb-2">{uploadError}</div>}
      {deleteError && <div className="alert alert-error mb-2">{deleteError}</div>}

      {isLoading ? (
        <p className="text-sm text-muted">Loading attachments…</p>
      ) : assets.length === 0 ? (
        <p className="text-sm text-muted">No attachments yet.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {assets.map((asset) => (
            <div
              key={asset.id}
              style={{
                display: "grid",
                gridTemplateColumns: "64px 1fr auto",
                gap: 12,
                alignItems: "center",
                border: "1px solid var(--border)",
                borderRadius: 10,
                padding: 10,
                background: "var(--bg-elevated)",
              }}
            >
              <div style={{ width: 64, height: 64, borderRadius: 8, overflow: "hidden", display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(255,255,255,0.03)" }}>
                {asset.kind === "image" && thumbUrls[asset.id] ? (
                  <img src={thumbUrls[asset.id]} alt={asset.original_name} loading="lazy" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                ) : (
                  <span style={{ fontSize: "1.35rem" }}>{fileIcon(asset)}</span>
                )}
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {asset.original_name}
                </div>
                <div className="text-xs text-muted">
                  {formatBytes(asset.size_bytes)} · {asset.uploaded_by_email ?? "Unknown uploader"} · {formatDateTime(asset.created_at)}
                </div>
              </div>
              <div className="flex gap-2 items-center">
                <button className="btn-secondary btn-sm" onClick={() => downloadAsset(asset)}>Download</button>
                {canDelete(asset) && (
                  <button
                    className="btn-danger btn-sm"
                    disabled={deleteMutation.isPending}
                    onClick={() => {
                      if (!window.confirm(`Delete "${asset.original_name}"? This cannot be undone.`)) return;
                      deleteMutation.mutate(asset.id);
                    }}
                  >
                    Delete
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
