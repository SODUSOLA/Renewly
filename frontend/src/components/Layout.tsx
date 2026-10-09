import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

// The frame around every signed-in page: brand, navigation, account menu.
export function Layout() {
  const { user, logout } = useAuth();
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <div className="topbar-inner">
          <NavLink to="/dashboard" className="brand">
            <img src="/favicon.svg" alt="" width="26" height="26" />
            Renewly
          </NavLink>
          <nav aria-label="Main" className="nav">
            <NavLink to="/dashboard">Dashboard</NavLink>
            <NavLink to="/documents">Documents</NavLink>
            <NavLink to="/vehicles">Vehicles</NavLink>
            <NavLink to="/settings">Settings</NavLink>
          </nav>
          <div className="account">
            <span className="muted small account-name">{user?.full_name}</span>
            <button type="button" className="btn btn-ghost btn-sm" onClick={logout}>
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main id="main" className="page">
        <Outlet />
      </main>
    </>
  );
}
