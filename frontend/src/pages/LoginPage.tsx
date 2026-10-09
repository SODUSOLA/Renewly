import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { fieldErrors } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AuthCard } from "../components/AuthCard";
import { ErrorNotice } from "../components/ErrorNotice";
import { Field } from "../components/Field";

// Sign in with email and password, then continue to where the visitor was headed.
export function LoginPage() {
  const { user, login, sessionExpired } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/dashboard";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  if (user) return <Navigate to={from} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const server = fieldErrors(error);
  return (
    <AuthCard title="Welcome back" subtitle="Sign in to see what's expiring.">
      {sessionExpired && !error && (
        <div className="notice notice-info" role="status">
          Your session ended. Please sign in again.
        </div>
      )}
      <form onSubmit={submit} noValidate>
        <ErrorNotice error={Object.keys(server).length ? null : error} />
        <Field label="Email" error={server.email}>
          <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </Field>
        <Field label="Password" error={server.password}>
          <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </Field>
        <button type="submit" className="btn btn-primary btn-block" disabled={busy || !email || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="auth-links">
        <Link to="/forgot-password">Forgot your password?</Link>
        <span>
          New here? <Link to="/register">Create an account</Link>
        </span>
      </p>
    </AuthCard>
  );
}
