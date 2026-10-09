import { Link } from "react-router-dom";

// Shown for any address the app doesn't have a page for.
export function NotFoundPage() {
  return (
    <main className="auth-page">
      <div className="auth-card">
        <h1>Page not found</h1>
        <p className="muted">That address doesn't lead anywhere.</p>
        <Link className="btn btn-primary btn-block" to="/dashboard">
          Go to your dashboard
        </Link>
      </div>
    </main>
  );
}
