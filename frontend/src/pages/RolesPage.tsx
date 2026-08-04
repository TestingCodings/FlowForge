import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { Role } from "../types/api";
import { useRoles } from "../hooks/useRoles";
import { useCan, useMyRoles } from "../hooks/useCapabilities";
import Hint from "../components/Hint";

/**
 * Role management (docs/ROLES.md step 3).
 *
 * Roles are data, so a client can have a "Site Manager" rather than being
 * told to imagine one. What a role may *do* is still drawn from a closed set
 * of capabilities, because each maps to a real check in the code: a creator
 * composes from them and can never invent a permission nothing enforces.
 */

/** Grouped for scanning. The API is the authority on which exist. */
const CAPABILITY_GROUPS: { group: string; caps: { key: string; blurb: string }[] }[] = [
  {
    group: "Workflows",
    caps: [
      { key: "workflow.view", blurb: "See workflows and their boards" },
      { key: "workflow.design", blurb: "Build and edit workflows, forms and rules" },
      { key: "workflow.publish", blurb: "Publish a new version" },
    ],
  },
  {
    group: "Work",
    caps: [
      { key: "instance.view", blurb: "See instances" },
      { key: "instance.create", blurb: "Start new work" },
      { key: "instance.transition", blurb: "Move work forward" },
      { key: "instance.approve", blurb: "Fire transitions needing approval" },
      { key: "instance.comment", blurb: "Comment on work" },
      { key: "instance.metadata", blurb: "Edit fields on work" },
      { key: "instance.relate", blurb: "Re-parent and link work" },
      { key: "form.submit", blurb: "Submit state forms" },
    ],
  },
  {
    group: "Files",
    caps: [
      { key: "media.upload", blurb: "Attach files" },
      { key: "media.delete", blurb: "Remove anyone's attachments" },
    ],
  },
  {
    group: "Administration",
    caps: [
      { key: "user.view", blurb: "See the user list" },
      { key: "user.create", blurb: "Invite users" },
      { key: "user.assign_roles", blurb: "Change what people can do" },
      { key: "secret.manage", blurb: "Manage stored credentials" },
      { key: "hook.manage", blurb: "Manage hooks and triggers" },
      { key: "audit.view", blurb: "Read the audit log" },
      { key: "workspace.manage", blurb: "Brand the workspace and manage roles" },
    ],
  },
];

const EMPTY = { key: "", label: "", capabilities: [] as string[], rank: 10 };

export default function RolesPage() {
  const qc = useQueryClient();
  const can = useCan();
  const myRoles = useMyRoles();
  const { data: roles = [], isLoading } = useRoles();

  const [draft, setDraft] = useState({ ...EMPTY });
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const mayManage = can("workspace.manage");
  const myRank = roles
    .filter((r) => myRoles.includes(r.key))
    .reduce((top, r) => Math.max(top, r.rank), 0);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["roles"] });
    qc.invalidateQueries({ queryKey: ["users"] });
  };

  const fail = (err: any, fallback: string) =>
    setError(err?.response?.data?.detail ?? fallback);

  const createRole = useMutation({
    mutationFn: async () => (await apiClient.post("/roles/", draft)).data,
    onSuccess: () => {
      refresh();
      setDraft({ ...EMPTY });
      setCreating(false);
      setError(null);
      setNotice("Role created");
      setTimeout(() => setNotice(null), 3000);
    },
    onError: (err) => fail(err, "Could not create the role."),
  });

  const saveRole = useMutation({
    mutationFn: async (role: Role) =>
      (await apiClient.patch(`/roles/${role.id}/`, {
        label: role.label,
        capabilities: role.capabilities,
        rank: role.rank,
      })).data,
    onSuccess: () => {
      refresh();
      setEditingId(null);
      setError(null);
      setNotice("Role updated");
      setTimeout(() => setNotice(null), 3000);
    },
    onError: (err) => fail(err, "Could not save the role."),
  });

  const deleteRole = useMutation({
    mutationFn: async (role: Role) => apiClient.delete(`/roles/${role.id}/`),
    onSuccess: () => {
      refresh();
      setError(null);
      setNotice("Role deleted");
      setTimeout(() => setNotice(null), 3000);
    },
    onError: (err) => fail(err, "Could not delete the role."),
  });

  const [edited, setEdited] = useState<Role | null>(null);
  const startEdit = (role: Role) => {
    setEditingId(role.id);
    setEdited({ ...role, capabilities: [...role.capabilities] });
    setError(null);
  };

  const toggle = (list: string[], cap: string) =>
    list.includes(cap) ? list.filter((c) => c !== cap) : [...list, cap];

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <h2>Roles</h2>
          <p>
            What each kind of person may do. Built-in roles are fixed; add your own
            to match how your organisation actually works.
          </p>
        </div>
        {mayManage && !creating && (
          <button className="btn-primary btn-sm" onClick={() => { setCreating(true); setError(null); }}>
            + New role
          </button>
        )}
      </div>

      {notice && <div className="alert alert-success mb-4"><span>✓</span> {notice}</div>}
      {error && (
        <div className="alert alert-error mb-4">
          <span>⚠</span>
          <div style={{ flex: 1 }}>{error}</div>
          <button className="btn-ghost btn-sm" onClick={() => setError(null)}>✕</button>
        </div>
      )}

      {!mayManage && (
        <div className="alert alert-info mb-4">
          <span>ℹ</span>
          <div>You can see how roles are configured, but changing them needs workspace administration.</div>
        </div>
      )}

      {creating && (
        <div className="card mb-4">
          <div className="card-header"><h3>New role</h3></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: 12, marginBottom: 14 }}>
            <div className="form-group" style={{ margin: 0 }}>
              <label htmlFor="role-label">Name</label>
              <input
                id="role-label"
                value={draft.label}
                placeholder="Site Manager"
                onChange={(e) => {
                  const label = e.target.value;
                  setDraft((d) => ({
                    ...d,
                    label,
                    // The key is derived while it has not been hand-edited.
                    // It is permanent once created, because app bundles
                    // reference roles by key.
                    key: label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, ""),
                  }));
                }}
              />
            </div>
            <div className="form-group" style={{ margin: 0 }}>
              <label htmlFor="role-key">Identifier</label>
              <input
                id="role-key"
                value={draft.key}
                onChange={(e) => setDraft((d) => ({ ...d, key: e.target.value }))}
                style={{ fontFamily: "ui-monospace, monospace" }}
              />
            </div>
            <div className="form-group" style={{ margin: 0 }}>
              <label htmlFor="role-rank">Seniority</label>
              <input
                id="role-rank"
                type="number"
                min={1}
                max={myRank}
                value={draft.rank}
                onChange={(e) => setDraft((d) => ({ ...d, rank: Number(e.target.value) }))}
                style={{ width: 110 }}
              />
            </div>
          </div>
          <p className="text-xs text-muted" style={{ marginBottom: 12 }}>
            Seniority decides who can assign this role: nobody can hand out a role
            more senior than their own. Yours is {myRank}.
          </p>

          <CapabilityPicker
            selected={draft.capabilities}
            onToggle={(cap) => setDraft((d) => ({ ...d, capabilities: toggle(d.capabilities, cap) }))}
          />

          <div className="flex gap-2" style={{ marginTop: 14 }}>
            <button
              className="btn-primary btn-sm"
              disabled={!draft.key || !draft.label || createRole.isPending}
              onClick={() => createRole.mutate()}
            >
              {createRole.isPending ? "Creating…" : "Create role"}
            </button>
            <button className="btn-secondary btn-sm" onClick={() => { setCreating(false); setDraft({ ...EMPTY }); }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="skeleton" style={{ height: 200, borderRadius: 14 }} />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {roles.map((role) => {
            const isEditing = editingId === role.id && edited;
            return (
              <div key={role.id} className="card">
                <div className="card-header" style={{ alignItems: "center" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <h3 style={{ margin: 0 }}>{role.label}</h3>
                    <code className="text-xs text-muted">{role.key}</code>
                    {role.is_system ? (
                      <span className="badge" title="Built in; cannot be changed">Built in</span>
                    ) : (
                      <span className="badge badge-role-participant">Custom</span>
                    )}
                    <span className="text-xs text-muted">
                      seniority {role.rank} · {role.assigned_count} user{role.assigned_count === 1 ? "" : "s"}
                    </span>
                  </div>
                  {mayManage && !role.is_system && (
                    <div className="flex gap-2">
                      <button
                        className="btn-secondary btn-sm"
                        onClick={() => (isEditing ? setEditingId(null) : startEdit(role))}
                      >
                        {isEditing ? "Cancel" : "Edit"}
                      </button>
                      <button
                        className="btn-ghost btn-sm"
                        disabled={deleteRole.isPending}
                        onClick={() => deleteRole.mutate(role)}
                      >
                        Delete
                      </button>
                    </div>
                  )}
                </div>

                {isEditing ? (
                  <>
                    <CapabilityPicker
                      selected={edited!.capabilities}
                      onToggle={(cap) =>
                        setEdited((e) => (e ? { ...e, capabilities: toggle(e.capabilities, cap) } : e))
                      }
                    />
                    <button
                      className="btn-primary btn-sm"
                      style={{ marginTop: 12 }}
                      disabled={saveRole.isPending}
                      onClick={() => saveRole.mutate(edited!)}
                    >
                      {saveRole.isPending ? "Saving…" : "Save changes"}
                    </button>
                  </>
                ) : (
                  <div className="flex gap-2" style={{ flexWrap: "wrap" }}>
                    {role.capabilities.length === 0 ? (
                      <span className="text-xs text-muted">Permitted nothing yet.</span>
                    ) : (
                      role.capabilities.map((c) => (
                        <code key={c} className="text-xs" style={{
                          background: "var(--bg-elevated)", padding: "2px 7px", borderRadius: 5,
                        }}>{c}</code>
                      ))
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function CapabilityPicker({
  selected, onToggle,
}: {
  selected: string[];
  onToggle: (cap: string) => void;
}) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 14 }}>
      {CAPABILITY_GROUPS.map(({ group, caps }) => (
        <div key={group}>
          <div className="text-xs text-muted mb-2" style={{
            fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em",
          }}>
            {group}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {caps.map(({ key, blurb }) => (
              <label key={key} style={{ display: "flex", gap: 8, alignItems: "flex-start", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={selected.includes(key)}
                  onChange={() => onToggle(key)}
                  style={{ width: 15, height: 15, marginTop: 3, accentColor: "#6366f1" }}
                />
                <span>
                  <span style={{ fontSize: "0.85rem" }}>{blurb}</span>
                  <code className="text-xs text-muted" style={{ display: "block" }}>{key}</code>
                </span>
              </label>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
