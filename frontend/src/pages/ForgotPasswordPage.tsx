import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { AuthCard } from "../components/AuthCard";
import { ErrorNotice } from "../components/ErrorNotice";
import { Field } from "../components/Field";

// Ask for a password-reset email. The server answers the same way whether or not
// the address has an account, and so do we.
export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/forgot-password", { method: "POST", body: { email: email.trim() }, public: true });
      setSent(true);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <AuthCard title="Check your email">
        <p>If that address has an account, we've sent a reset link. It works for one hour.</p>
        <p className="auth-links">
          <Link to="/reset-password">I have my reset token</Link>
          <Link to="/login">Back to sign in</Link>
        </p>
      </AuthCard>
    );
  }
  return (
    <AuthCard title="Reset your password" subtitle="Enter your email and we'll send you a reset link.">
      <form onSubmit={submit} noValidate>
        <ErrorNotice error={error} />
        <Field label="Email">
          <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </Field>
        <button type="submit" className="btn btn-primary btn-block" disabled={busy || !email}>
          {busy ? "Sending…" : "Send reset link"}
        </button>
      </form>
      <p className="auth-links">
        <Link to="/login">Back to sign in</Link>
      </p>
    </AuthCard>
  );
}
