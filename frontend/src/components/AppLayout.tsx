import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
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
      { to: "/workflows",     label: "Workflows",    icon: <WorkflowIcon /> },
      { to: "/workflows/new", label: "New Workflow",  icon: <PlusIcon /> },
    ],
  },
  {
    section: "Administration",
    links: [
      { to: "/admin/audit", label: "Audit Log", icon: <AuditIcon /> },
      { to: "/admin/users", label: "Users",     icon: <UsersIcon /> },
    ],
  },
];

export default function AppLayout() {
  const navigate = useNavigate();

  const { data: me } = useQuery<UserProfile>({
    queryKey: ["me"],
    queryFn: async () => {
      const res = await apiClient.get("/auth/me/");
      return res.data;
    },
    retry: false,
  });

  const initials = me
    ? `${me.first_name?.[0] ?? ""}${me.last_name?.[0] ?? ""}`.toUpperCase()
    : "?";

  const logout = () => {
    localStorage.removeItem("ff_access_token");
    localStorage.removeItem("ff_refresh_token");
    navigate("/login");
  };

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
          <div className="user-chip">
            <div className="user-avatar">{initials}</div>
            <div className="user-info">
              <p>{me ? `${me.first_name} ${me.last_name}` : "Loading…"}</p>
              <span>{me?.email ?? ""}</span>
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
function TaskIcon()     { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>; }
function WorkflowIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>; }
function PlusIcon()     { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>; }
function AuditIcon()    { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>; }
function UsersIcon()    { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>; }
function LogoutIcon()   { return <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>; }
