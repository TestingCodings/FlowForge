import { Navigate } from "react-router-dom";

export default function ProtectedRoute({ children }: { children: JSX.Element }) {
  const token = localStorage.getItem("ff_access_token");
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return children;
}
