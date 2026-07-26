import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { MediaAsset } from "../types/api";

/**
 * Upload control for `file` / `image` form fields.
 *
 * The field's value is a **MediaAsset id**, not a URL. That distinction is the
 * whole point: a pasted link rots, points outside the system, and carries no
 * access control, whereas an asset id resolves to a real uploaded file the
 * backend can verify belongs to this instance.
 *
 * Uploads are anchored to the instance as they happen, so the file is a
 * first-class attachment the moment it is chosen — even if the form is never
 * submitted. That is deliberate: losing an uploaded screenshot because a
 * validation error blocked the submit would be worse than an orphan asset.
 */
export default function FormFileField({
  value,
  onChange,
  workflowInstanceId,
  accept,
  disabled,
}: {
  value: string | null;
  onChange: (assetId: string | null) => void;
  workflowInstanceId: string;
  accept?: string;
  disabled?: boolean;
}) {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Kept locally so the filename shows immediately after upload without
  // waiting for the assets list to refetch.
  const [asset, setAsset] = useState<MediaAsset | null>(null);

  const upload = async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("workflow_instance", workflowInstanceId);
      const resp = await apiClient.post("/media/", formData);
      const created = resp.data as MediaAsset;
      setAsset(created);
      onChange(created.id);
      // The attachments panel lists the same assets; keep it in step.
      qc.invalidateQueries({ queryKey: ["media-assets", workflowInstanceId] });
    } catch (err: any) {
      // The backend rejects by magic bytes and size, so its message is more
      // useful than anything we could infer from the File object here.
      setError(
        err?.response?.data?.detail ??
        err?.response?.data?.file?.[0] ??
        "Upload failed."
      );
    } finally {
      setUploading(false);
    }
  };

  const clear = () => {
    setAsset(null);
    setError(null);
    onChange(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        disabled={disabled || uploading}
        style={{ display: "none" }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) upload(file);
        }}
      />

      {value ? (
        <div
          style={{
            display: "flex", alignItems: "center", gap: 10, padding: "8px 12px",
            border: "1px solid var(--border)", borderRadius: 8,
          }}
        >
          <span aria-hidden>📎</span>
          <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {asset?.original_name ?? "Attached file"}
          </span>
          <a
            href={`/api/media/${value}/download/`}
            onClick={(e) => {
              // Downloads are authenticated, so a plain link would 401.
              e.preventDefault();
              apiClient
                .get(`/media/${value}/download/`, { responseType: "blob" })
                .then((r) => {
                  const url = URL.createObjectURL(r.data);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = asset?.original_name ?? "download";
                  a.click();
                  URL.revokeObjectURL(url);
                })
                .catch(() => setError("Could not download this file."));
            }}
            className="text-xs"
            style={{ color: "var(--accent-light)" }}
          >
            Download
          </a>
          {!disabled && (
            <button type="button" className="btn-secondary btn-sm" onClick={clear}>
              Replace
            </button>
          )}
        </div>
      ) : (
        <button
          type="button"
          className="btn-secondary"
          disabled={disabled || uploading}
          onClick={() => inputRef.current?.click()}
          style={{ width: "100%", justifyContent: "center" }}
        >
          {uploading ? "Uploading…" : "Choose a file…"}
        </button>
      )}

      {error && (
        <div className="text-xs" style={{ color: "var(--danger)", marginTop: 4 }}>
          {error}
        </div>
      )}
    </div>
  );
}
