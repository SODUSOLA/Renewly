import { Navigate, Outlet, useLocation } from "react-router-dom";
import { Spinner } from "../components/Spinner";
import { useAuth } from "./AuthContext";

// Wraps the signed-in pages: waits for the session check, then either renders
// the page or sends the visitor to /login (remembering where they were headed).
export function RequireAuth() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Spinner label="Loading your account" fullPage />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <Outlet />;
}
