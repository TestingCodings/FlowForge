import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import { UserProfile } from "../types/api";

const NAV = [
  {
    section: "Overview",
    links: [
      { to: "/dashboard", label: "Dashboard",  icon: <DashIcon /> },
      { to: "/instances", label: "Instances",  icon: <InstanceIcon /> },
      { to: "/tasks",     label: "My Tasks",   icon: <TaskIcon /> },
    ],
  },
  {
    section: "Configuration",
    links: [
      { to: "/workflows",            label: "Workflows",    icon: <WorkflowIcon /> },
      { to: "/workflows/new",        label: "New Workflow", icon: <PlusIcon /> },
      { to: "/workflows/templates",  label: "Templates",   icon: <TemplateIcon /> },
    ],
  },
  {
    section: "Administration",
    links: [
      { to: "/admin/audit", label: "Audit Log",  icon: <AuditIcon /> },
      { to: "/admin/users", label: "Users",      icon: <UsersIcon /> },
      { to: "/help",        label: "User Guide", icon: <HelpIcon /> },
    ],
  },
];

/* Role colours for demo switcher */
const ROLE_COLOUR: Record<string, string> = {
  platform_admin:    "#6366f1",
  workflow_designer: "#a855f7",
  approver:          "#3b82f6",
  participant:       "#22c55e",
  viewer:            "#6b7280",
};

function primaryRole(roles: string[]): string {
  const order = ["platform_admin", "workflow_designer", "approver", "participant", "viewer"];
  return roles.find(r => order.includes(r)) ?? roles[0] ?? "viewer";
}

export default function AppLayout() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const [switching, setSwitching] = useState(false);

  const { data: me } = useQuery<UserProfile>({
    queryKey: ["me"],
    queryFn: async () => (await apiClient.get("/auth/me/")).data,
    retry: false,
  });

  const { data: allUsers = [] } = useQuery<UserProfile[]>({
    queryKey: ["users"],
    queryFn: async () => (await apiClient.get("/users/")).data.results ?? [],
  });

  const initials = me
    ? `${me.first_name?.[0] ?? ""}${me.last_name?.[0] ?? ""}`.toUpperCase()
    : "?";

  const myRole = me ? primaryRole(me.roles) : "";
  const roleColour = ROLE_COLOUR[myRole] ?? "#6b7280";

  const logout = () => {
    localStorage.removeItem("ff_access_token");
    localStorage.removeItem("ff_refresh_token");
    navigate("/login");
  };

  const switchTo = async (user: UserProfile) => {
    if (user.id === me?.id) { setSwitcherOpen(false); return; }
    setSwitching(true);
    try {
      const res = await apiClient.post(`/users/demo-switch/`, { user_id: user.id });
      localStorage.setItem("ff_access_token",  res.data.access);
      localStorage.setItem("ff_refresh_token", res.data.refresh);
      // Reset all cached queries so the new user's data loads fresh
      await qc.resetQueries();
      setSwitcherOpen(false);
      navigate("/dashboard");
    } finally {
      setSwitching(false);
    }
  };

  /* Other users to switch to (exclude self) */
  const switchTargets = allUsers.filter(u => u.id !== me?.id);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <h1>FlowForge</h1>
          <p>Workflow Automation</p>
        </div>

        <nav className="sidebar-nav">
          {NAV.map((section) => (
            <div key={section.section}>
              <div className="sidebar-section-label">{section.section}</div>
              {section.links.map((link) => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
                  end={link.to === "/workflows"}
                >
                  {link.icon}
                  {link.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          {/* ── Demo user switcher ── */}
          {switchTargets.length > 0 && (
            <div style={{ marginBottom: 8, position: "relative" }}>
              <button
                onClick={() => setSwitcherOpen(o => !o)}
                disabled={switching}
                title="Switch demo user"
                style={{
                  width: "100%", display: "flex", alignItems: "center", gap: 8,
                  background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.25)",
                  borderRadius: 8, padding: "6px 10px", cursor: "pointer", color: "var(--text-secondary)",
                  fontSize: "0.75rem", fontWeight: 600, letterSpacing: ".03em",
                }}
              >
                <SwitchIcon />
                {switching ? "Switching…" : "Switch demo user"}
                <span style={{ marginLeft: "auto", opacity: .6 }}>{switcherOpen ? "▲" : "▼"}</span>
              </button>

              {switcherOpen && (
                <div style={{
                  position: "absolute", bottom: "calc(100% + 6px)", left: 0, right: 0,
                  background: "var(--bg-secondary)", border: "1px solid var(--border)",
                  borderRadius: 10, overflow: "hidden", zIndex: 50,
                  boxShadow: "0 8px 24px rgba(0,0,0,.4)",
                }}>
                  <div style={{ padding: "8px 12px 4px", fontSize: "0.68rem", color: "var(--text-muted)", fontWeight: 700, letterSpacing: ".08em", textTransform: "uppercase" }}>
                    Demo users
                  </div>
                  {switchTargets.map(u => {
                    const role = primaryRole(u.roles);
                    const colour = ROLE_COLOUR[role] ?? "#6b7280";
                    return (
                      <button
                        key={u.id}
                        onClick={() => switchTo(u)}
                        style={{
                          width: "100%", display: "flex", alignItems: "center", gap: 9,
                          padding: "8px 12px", background: "none", border: "none",
                          cursor: "pointer", textAlign: "left",
                          borderTop: "1px solid var(--border)",
                        }}
                        onMouseEnter={e => (e.currentTarget.style.background = "rgba(255,255,255,0.04)")}
                        onMouseLeave={e => (e.currentTarget.style.background = "none")}
                      >
                        <div style={{
                          width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
                          background: colour + "22", border: `2px solid ${colour}`,
                          display: "flex", alignItems: "center", justifyContent: "center",
                          fontSize: "0.68rem", fontWeight: 700, color: colour,
                        }}>
                          {u.first_name[0]}{u.last_name[0]}
                        </div>
                        <div>
                          <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-primary)" }}>
                            {u.first_name} {u.last_name}
                          </div>
                          <div style={{ fontSize: "0.68rem", color: colour, fontWeight: 600, textTransform: "capitalize" }}>
                            {role.replace("_", " ")}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ── Current user chip ── */}
          <div className="user-chip">
            <div
              className="user-avatar"
              style={{ background: roleColour + "33", border: `2px solid ${roleColour}`, color: roleColour }}
            >
              {initials}
            </div>
            <div className="user-info">
              <p>{me ? `${me.first_name} ${me.last_name}` : "Loading…"}</p>
              <span style={{ color: roleColour, fontWeight: 600, textTransform: "capitalize" }}>
                {myRole.replace("_", " ")}
              </span>
            </div>
          </div>
          <button className="btn-logout" onClick={logout}>
            <LogoutIcon /> Sign out
          </button>
        </div>
      </aside>

      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}

/* ─── Inline SVG icons ─── */
function DashIcon()     { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>; }
function InstanceIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>; }
function TaskIcon()     { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1 2-2V5a2 2 0 0 1 2-2h11"/></svg>; }
function WorkflowIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>; }
function PlusIcon()     { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>; }
function AuditIcon()    { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>; }
function UsersIcon()    { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>; }
function LogoutIcon()   { return <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>; }
function TemplateIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="5" rx="1"/><rect x="3" y="11" width="11" height="10" rx="1"/><rect x="17" y="11" width="4" height="10" rx="1"/></svg>; }
function HelpIcon()     { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>; }
function SwitchIcon()   { return <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M16 3l4 4-4 4"/><path d="M20 7H4"/><path d="M8 21l-4-4 4-4"/><path d="M4 17h16"/></svg>; }
