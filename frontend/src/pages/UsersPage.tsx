import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import { UserProfile, ALL_ROLES, RoleName } from "../types/api";

export default function UsersPage() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<string | null>(null);
  const [pendingRoles, setPendingRoles] = useState<RoleName[]>([]);
  const [saveMsg, setSaveMsg] = useState<Record<string, string>>({});

  const { data, isLoading } = useQuery<{ results: UserProfile[] }>({
    queryKey: ["users"],
    queryFn: async () => (await apiClient.get("/users/")).data,
  });

  const setRolesMutation = useMutation({
    mutationFn: async ({ userId, roles }: { userId: string; roles: RoleName[] }) =>
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
    setPendingRoles(user.roles as RoleName[]);
  };

  const toggleRole = (role: RoleName) => {
    setPendingRoles((prev) =>
      prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role]
    );
  };

  const users: UserProfile[] = (data as any)?.results ?? (Array.isArray(data) ? data : []);

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
                <>
                  <tr key={user.id}>
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
                              {roleLabel(r)}
                            </span>
                          ))
                        )}
                      </div>
                    </td>
                    <td className="text-muted text-sm">
                      {new Date(user.date_joined).toLocaleDateString()}
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
                          {ALL_ROLES.map(({ value, label }) => (
                            <label
                              key={value}
                              className={`role-option ${pendingRoles.includes(value) ? "selected" : ""}`}
                              onClick={() => toggleRole(value)}
                            >
                              <input type="checkbox" readOnly checked={pendingRoles.includes(value)} />
                              {label}
                            </label>
                          ))}
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
                </>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card mt-4">
        <div className="card-header"><h3>Role Definitions</h3></div>
        <table className="table">
          <thead><tr><th>Role</th><th>Permissions</th></tr></thead>
          <tbody>
            <tr><td><span className="badge badge-role-platform_admin">Platform Admin</span></td><td className="text-sm text-muted">Full access — manage users, workflows, audit data, and system config</td></tr>
            <tr><td><span className="badge badge-role-workflow_designer">Workflow Designer</span></td><td className="text-sm text-muted">Create and edit workflow definitions, states, transitions and rules</td></tr>
            <tr><td><span className="badge badge-role-approver">Approver</span></td><td className="text-sm text-muted">Approve transitions that require sign-off; view assigned instances</td></tr>
            <tr><td><span className="badge badge-role-participant">Participant</span></td><td className="text-sm text-muted">Submit and progress workflow instances; complete assigned tasks</td></tr>
            <tr><td><span className="badge badge-role-viewer">Viewer</span></td><td className="text-sm text-muted">Read-only access to instances and audit trails</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

function roleLabel(role: string) {
  return ALL_ROLES.find((r) => r.value === role)?.label ?? role;
}
