import { Fragment, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import { UserProfile } from "../types/api";
import { formatDate } from "../hooks/useWorkspace";
import { useRoles } from "../hooks/useRoles";
import { useUsers } from "../hooks/useUsers";
import { useMyRoles } from "../hooks/useCapabilities";

export default function UsersPage() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<string | null>(null);
  const [pendingRoles, setPendingRoles] = useState<string[]>([]);
  const [saveMsg, setSaveMsg] = useState<Record<string, string>>({});

  const { data: users = [], isLoading } = useUsers();

  // Read from the API, not a constant: roles are data now, so a hardcoded
  // list would silently omit whatever this install has defined.
  const { data: roles = [] } = useRoles();
  const myRoles = useMyRoles();
  const myRank = roles
    .filter((r) => myRoles.includes(r.key))
    .reduce((top, r) => Math.max(top, r.rank), 0);

  const setRolesMutation = useMutation({
    mutationFn: async ({ userId, roles }: { userId: string; roles: string[] }) =>
      (await apiClient.post(`/users/${userId}/roles/`, { roles })).data,
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["users"] });
      setEditing(null);
      setSaveMsg((prev) => ({ ...prev, [vars.userId]: "Roles updated" }));
      setTimeout(() => setSaveMsg((prev) => { const n = { ...prev }; delete n[vars.userId]; return n; }), 3000);
    },
  });

  const startEdit = (user: UserProfile) => {
    setEditing(user.id);
    setPendingRoles([...user.roles]);
  };

  const toggleRole = (role: string) => {
    setPendingRoles((prev) =>
      prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role]
    );
  };


  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <h2>Users</h2>
          <p>Manage platform users and their roles</p>
        </div>
        <div className="text-sm text-muted">{users.length} users</div>
      </div>

      <div className="card">
        {isLoading ? (
          <div style={{ padding: "24px 0" }}>
            {[1, 2, 3].map((i) => (
              <div key={i} className="skeleton" style={{ height: 48, marginBottom: 8, borderRadius: 8 }} />
            ))}
          </div>
        ) : users.length === 0 ? (
          <div className="empty-state"><p>No users found.</p></div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>User</th>
                <th>Email</th>
                <th>Roles</th>
                <th>Joined</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                // Keyed Fragment, not <>. An unkeyed fragment wrapping two
                // <tr> siblings leaves React unable to match rows between
                // renders: expanding the editor row made reconciliation
                // remove a node that was no longer where it expected, which
                // takes the whole page down rather than warning.
                <Fragment key={user.id}>
                  <tr>
                    <td>
                      <div className="flex items-center gap-2">
                        <div className="user-avatar" style={{ width: 28, height: 28, fontSize: "0.7rem", flexShrink: 0 }}>
                          {user.first_name?.[0]}{user.last_name?.[0]}
                        </div>
                        <span style={{ fontWeight: 500 }}>{user.full_name}</span>
                      </div>
                    </td>
                    <td className="text-muted text-sm">{user.email}</td>
                    <td>
                      <div className="flex gap-2" style={{ flexWrap: "wrap" }}>
                        {user.roles.length === 0 ? (
                          <span className="text-muted text-xs">No roles</span>
                        ) : (
                          user.roles.map((r) => (
                            <span key={r} className={`badge badge-role-${r}`}>
                              {roles.find((x) => x.key === r)?.label ?? r}
                            </span>
                          ))
                        )}
                      </div>
                    </td>
                    <td className="text-muted text-sm">
                      {formatDate(user.date_joined)}
                    </td>
                    <td>
                      <div className="flex gap-2 items-center">
                        {saveMsg[user.id] && (
                          <span className="text-sm" style={{ color: "var(--success)" }}>{saveMsg[user.id]}</span>
                        )}
                        <button
                          className="btn-secondary btn-sm"
                          onClick={() => editing === user.id ? setEditing(null) : startEdit(user)}
                        >
                          {editing === user.id ? "Cancel" : "Edit roles"}
                        </button>
                      </div>
                    </td>
                  </tr>

                  {editing === user.id && (
                    <tr key={`${user.id}-edit`}>
                      <td colSpan={5} style={{ background: "var(--bg-elevated)", padding: "14px 16px" }}>
                        <div className="text-xs text-muted mb-2" style={{ fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                          Select roles for {user.full_name}
                        </div>
                        <div className="role-grid mb-4">
                          {roles.map((role) => {
                            // The API refuses an assignment above the
                            // assigner's own rank, so disable rather than
                            // let someone pick it and receive a 403.
                            const tooSenior = role.rank > myRank;
                            return (
                              <label
                                key={role.key}
                                className={`role-option ${pendingRoles.includes(role.key) ? "selected" : ""}`}
                                title={tooSenior ? "More senior than your own role" : role.capabilities.join(", ")}
                                style={tooSenior ? { opacity: 0.45, cursor: "not-allowed" } : undefined}
                                onClick={() => { if (!tooSenior) toggleRole(role.key); }}
                              >
                                <input
                                  type="checkbox"
                                  readOnly
                                  disabled={tooSenior}
                                  checked={pendingRoles.includes(role.key)}
                                />
                                {role.label}
                              </label>
                            );
                          })}
                        </div>
                        <div className="flex gap-2">
                          <button
                            className="btn-primary btn-sm"
                            onClick={() => setRolesMutation.mutate({ userId: user.id, roles: pendingRoles })}
                            disabled={setRolesMutation.isPending}
                          >
                            {setRolesMutation.isPending ? "Saving…" : "Save roles"}
                          </button>
                          <button className="btn-secondary btn-sm" onClick={() => setEditing(null)}>
                            Cancel
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card mt-4">
        <div className="card-header">
          <h3>Role definitions</h3>
          <a className="btn-secondary btn-sm" href="/admin/roles">Manage roles</a>
        </div>
        <table className="table">
          <thead><tr><th>Role</th><th>Permitted</th></tr></thead>
          <tbody>
            {roles.map((role) => (
              <tr key={role.id}>
                <td><span className={`badge badge-role-${role.key}`}>{role.label}</span></td>
                <td className="text-sm text-muted">
                  {role.capabilities.length === 0
                    ? "Nothing yet"
                    : role.capabilities.join(", ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
