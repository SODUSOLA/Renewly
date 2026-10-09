import { useState, type FormEvent } from "react";
import { fieldErrors } from "../api/client";
import type { ReminderStyle } from "../api/types";
import { useAuth, type ProfileChanges } from "../auth/AuthContext";
import { ErrorNotice } from "../components/ErrorNotice";
import { Field } from "../components/Field";
import { timezoneOptions } from "../lib/timezones";

const STYLES: { value: ReminderStyle; title: string; description: string }[] = [
  {
    value: "each",
    title: "One email per document",
    description: "Each reminder arrives on its own, like “Car insurance expires in 7 days”.",
  },
  {
    value: "digest",
    title: "One daily summary",
    description: "When several things are due on the same day, you get a single email listing them, most urgent first.",
  },
];

// Account settings: how and when reminders arrive, plus name and timezone.
export function SettingsPage() {
  const { user, updateProfile } = useAuth();
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [timezone, setTimezone] = useState(user?.timezone ?? "Africa/Lagos");
  const [style, setStyle] = useState<ReminderStyle>(user?.reminder_style ?? "each");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [nameError, setNameError] = useState<string>();

  if (!user) return null;

  // Only what actually changed is sent.
  const changes: ProfileChanges = {};
  if (fullName.trim() !== user.full_name) changes.full_name = fullName.trim();
  if (timezone !== user.timezone) changes.timezone = timezone;
  if (style !== user.reminder_style) changes.reminder_style = style;
  const dirty = Object.keys(changes).length > 0;

  function edited<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value);
      setSaved(false);
    };
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!fullName.trim()) return setNameError("Tell us your name.");
    setNameError(undefined);
    setBusy(true);
    setError(null);
    try {
      await updateProfile(changes);
      setSaved(true);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const server = fieldErrors(error);
  return (
    <>
      <div className="page-head">
        <h1>Settings</h1>
      </div>
      <form className="card" onSubmit={submit} noValidate>
        {saved && (
          <div className="notice notice-success" role="status">
            Saved.
          </div>
        )}
        <ErrorNotice error={Object.keys(server).length ? null : error} />

        <section className="section">
          <fieldset>
            <legend>How should we send reminders?</legend>
            {STYLES.map((option) => (
              <label key={option.value} className="choice">
                <input
                  type="radio"
                  name="reminder_style"
                  value={option.value}
                  checked={style === option.value}
                  onChange={() => edited(setStyle)(option.value)}
                />
                <span>
                  <strong>{option.title}</strong>
                  <span className="muted small">{option.description}</span>
                </span>
              </label>
            ))}
          </fieldset>
        </section>

        <section className="section">
          <div className="form-grid">
            <Field label="Email" hint="Your sign-in address can't be changed here.">
              <input value={user.email} disabled readOnly />
            </Field>
            <Field label="Full name" error={nameError ?? server.full_name}>
              <input value={fullName} onChange={(e) => edited(setFullName)(e.target.value)} maxLength={150} autoComplete="name" />
            </Field>
            <Field label="Your timezone" error={server.timezone} hint="Reminders arrive at 8am in this timezone.">
              <select value={timezone} onChange={(e) => edited(setTimezone)(e.target.value)}>
                {timezoneOptions(timezone).map((tz) => (
                  <option key={tz} value={tz}>
                    {tz.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        </section>

        <div className="actions">
          <button type="submit" className="btn btn-primary" disabled={busy || !dirty}>
            {busy ? "Saving…" : "Save changes"}
          </button>
        </div>
      </form>
    </>
  );
}
