import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { fieldErrors } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AuthCard } from "../components/AuthCard";
import { ErrorNotice } from "../components/ErrorNotice";
import { Field } from "../components/Field";
import { detectTimezone, timezoneOptions } from "../lib/timezones";

// Create an account. The timezone matters: it decides when reminders are sent.
export function RegisterPage() {
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [timezone, setTimezone] = useState(detectTimezone);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({});

  if (user) return <Navigate to="/dashboard" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found: Record<string, string> = {};
    if (!fullName.trim()) found.full_name = "Tell us your name.";
    if (password.length < 8) found.password = "Use at least 8 characters.";
    setClientErrors(found);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    setError(null);
    try {
      await register({ email: email.trim(), password, full_name: fullName.trim(), timezone });
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const errors = { ...fieldErrors(error), ...clientErrors };
  // A 409 (email taken) has no field list, so show it under the email field.
  if (error && (error as { status?: number }).status === 409) errors.email = "That email already has an account. Try signing in.";
  const banner = Object.keys(errors).length ? null : error;
  return (
    <AuthCard title="Create your account" subtitle="Track your documents and get reminded in time.">
      <ul className="value-props">
        <li>Email reminders before your licence, insurance and permits expire</li>
        <li>Pick your own reminder days on a calendar</li>
        <li>See what you spend on renewals</li>
      </ul>
      <form onSubmit={submit} noValidate>
        <ErrorNotice error={banner} />
        <Field label="Full name" error={errors.full_name}>
          <input autoComplete="name" value={fullName} onChange={(e) => setFullName(e.target.value)} required autoFocus />
        </Field>
        <Field label="Email" error={errors.email}>
          <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </Field>
        <Field label="Password" error={errors.password} hint="At least 8 characters.">
          <input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </Field>
        <Field label="Your timezone" error={errors.timezone} hint="Reminders arrive at 8am in this timezone.">
          <select value={timezone} onChange={(e) => setTimezone(e.target.value)}>
            {timezoneOptions(timezone).map((tz) => (
              <option key={tz} value={tz}>
                {tz.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </Field>
        <button type="submit" className="btn btn-primary btn-block" disabled={busy || !email || !password}>
          {busy ? "Creating account…" : "Create account"}
        </button>
      </form>
      <p className="auth-links">
        <span>
          Already have an account? <Link to="/login">Sign in</Link>
        </span>
      </p>
    </AuthCard>
  );
}
