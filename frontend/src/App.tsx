import { Navigate, Route, Routes } from "react-router-dom";

import AppLayout from "./components/AppLayout";
import ProtectedRoute from "./components/ProtectedRoute";
import AuditPage from "./pages/AuditPage";
import DashboardPage from "./pages/DashboardPage";
import InstanceDetailPage from "./pages/InstanceDetailPage";
import InstancesPage from "./pages/InstancesPage";
import LoginPage from "./pages/LoginPage";
import NewWorkflowPage from "./pages/NewWorkflowPage";
import RegisterPage from "./pages/RegisterPage";
import UsersPage from "./pages/UsersPage";
import WorkflowDetailPage from "./pages/WorkflowDetailPage";
import WorkflowsPage from "./pages/WorkflowsPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route
        path="/"
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="workflows" element={<WorkflowsPage />} />
        <Route path="workflows/new" element={<NewWorkflowPage />} />
        <Route path="workflows/:id" element={<WorkflowDetailPage />} />
        <Route path="instances" element={<InstancesPage />} />
        <Route path="instances/:id" element={<InstanceDetailPage />} />
        <Route path="admin/audit" element={<AuditPage />} />
        <Route path="admin/users" element={<UsersPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
