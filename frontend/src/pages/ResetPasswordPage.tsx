import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, api, fieldErrors } from "../api/client";
import { AuthCard } from "../components/AuthCard";
import { ErrorNotice } from "../components/ErrorNotice";
import { Field } from "../components/Field";

// Choose a new password using the token from the reset email (prefilled from the link).
export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const [token, setToken] = useState(params.get("token") ?? "");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/reset-password", { method: "POST", body: { token: token.trim(), new_password: password }, public: true });
      setDone(true);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <AuthCard title="Password updated">
        <p>You can now sign in with your new password.</p>
        <Link className="btn btn-primary btn-block" to="/login">
          Sign in
        </Link>
      </AuthCard>
    );
  }
  const server = fieldErrors(error);
  const badToken = error instanceof ApiError && error.status === 400;
  return (
    <AuthCard title="Choose a new password">
      <form onSubmit={submit} noValidate>
        <ErrorNotice error={badToken || Object.keys(server).length ? null : error} />
        <Field
          label="Reset token"
          error={badToken ? "This token is invalid or has expired. Request a new link." : server.token}
          hint={params.get("token") ? undefined : "Paste the token from the email."}
        >
          <input value={token} onChange={(e) => setToken(e.target.value)} required autoComplete="off" />
        </Field>
        <Field label="New password" error={server.new_password} hint="At least 8 characters.">
          <input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </Field>
        <button type="submit" className="btn btn-primary btn-block" disabled={busy || !token || password.length < 8}>
          {busy ? "Saving…" : "Update password"}
        </button>
      </form>
      <p className="auth-links">
        <Link to="/forgot-password">Send me a new link</Link>
        <Link to="/login">Back to sign in</Link>
      </p>
    </AuthCard>
  );
}
