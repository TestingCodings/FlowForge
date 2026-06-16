import { Link, Outlet, useNavigate } from "react-router-dom";

export default function AppLayout() {
  const navigate = useNavigate();

  const logout = () => {
    localStorage.removeItem("ff_access_token");
    localStorage.removeItem("ff_refresh_token");
    navigate("/login");
  };

  return (
    <div className="app-shell">
      <div className="header">
        <h1>FlowForge</h1>
        <button className="secondary" onClick={logout}>Logout</button>
      </div>
      <nav className="nav">
        <Link to="/dashboard">Dashboard</Link>
        <Link to="/workflows">Workflows</Link>
        <Link to="/workflows/new">New Workflow</Link>
        <Link to="/instances">Instances</Link>
        <Link to="/admin/audit">Audit</Link>
        <Link to="/admin/users">Users</Link>
      </nav>
      <div style={{ marginTop: 16 }}>
        <Outlet />
      </div>
    </div>
  );
}
