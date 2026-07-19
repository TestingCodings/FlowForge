import { Navigate, Route, Routes } from "react-router-dom";

import AppLayout from "./components/AppLayout";
import ProtectedRoute from "./components/ProtectedRoute";
import AuditPage from "./pages/AuditPage";
import DashboardPage from "./pages/DashboardPage";
import InstanceDetailPage from "./pages/InstanceDetailPage";
import InstancesPage from "./pages/InstancesPage";
import LoginPage from "./pages/LoginPage";
import NewWorkflowPage from "./pages/NewWorkflowPage";
import WorkflowBuilderPage from "./pages/WorkflowBuilderPage";
import RegisterPage from "./pages/RegisterPage";
import UsersPage from "./pages/UsersPage";
import HelpPage from "./pages/HelpPage";
import WorkflowDetailPage from "./pages/WorkflowDetailPage";
import WorkflowsPage from "./pages/WorkflowsPage";
import WorkspacePage from "./pages/WorkspacePage";
import WorkflowViewPage from "./pages/WorkflowViewPage";

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
        <Route path="workflows/new" element={<WorkflowBuilderPage />} />
        <Route path="workflows/:id/edit" element={<WorkflowBuilderPage />} />
        <Route path="workflows/templates" element={<NewWorkflowPage />} />
        <Route path="workflows/:id" element={<WorkflowDetailPage />} />
        <Route path="workflows/:id/view" element={<WorkflowViewPage />} />
        <Route path="workflows/:id/board" element={<WorkflowViewPage />} />
        <Route path="instances" element={<InstancesPage />} />
        <Route path="instances/:id" element={<InstanceDetailPage />} />
        <Route path="tasks" element={<DashboardPage />} />
        <Route path="admin/audit" element={<AuditPage />} />
        <Route path="admin/users" element={<UsersPage />} />
        <Route path="admin/workspace" element={<WorkspacePage />} />
        <Route path="help" element={<HelpPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
