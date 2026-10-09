import { useEffect, useState, type FormEvent } from "react";
import { fieldErrors } from "../api/client";
import type { Doc, DocInput, DocumentType, Vehicle } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { DEFAULT_OFFSETS, addDays, earliestReminderDate, todayIn } from "../lib/calendar";
import { TYPE_OPTIONS } from "../lib/status";
import { ErrorNotice } from "./ErrorNotice";
import { Field } from "./Field";
import { ReminderCalendar } from "./ReminderCalendar";

// Create/edit form for a document. It checks what it can on the client, and
// shows any field errors the server sends back next to the right input.
export function DocumentForm({
  initial,
  vehicles,
  submitting,
  serverError,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial?: Doc;
  vehicles: Vehicle[];
  submitting: boolean;
  serverError: unknown;
  submitLabel: string;
  onSubmit: (input: DocInput) => void;
  onCancel: () => void;
}) {
  const [type, setType] = useState<DocumentType>(initial?.type ?? "insurance");
  const [customLabel, setCustomLabel] = useState(initial?.custom_type_label ?? "");
  const [title, setTitle] = useState(initial?.title ?? "");
  const [vehicleId, setVehicleId] = useState(initial?.vehicle_id ?? "");
  const [documentNumber, setDocumentNumber] = useState(initial?.document_number ?? "");
  const [issueDate, setIssueDate] = useState(initial?.issue_date ?? "");
  const [expiryDate, setExpiryDate] = useState(initial?.expiry_date ?? "");
  // Reminders are kept as "days before expiry"; the calendar shows them as dates.
  const [offsets, setOffsets] = useState<number[]>(initial?.reminder_offsets ?? DEFAULT_OFFSETS);
  const { user } = useAuth();
  const today = todayIn(user?.timezone);
  // Until the user picks days themselves, a NEW document suggests the usual reminders,
  // minus any that would already be in the past for this expiry date.
  const [remindersTouched, setRemindersTouched] = useState(false);
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (initial || remindersTouched || !expiryDate) return;
    const earliest = earliestReminderDate({ issueDate: issueDate || null, expiryDate, today });
    setOffsets(DEFAULT_OFFSETS.filter((days) => addDays(expiryDate, -days) >= earliest));
  }, [initial, remindersTouched, expiryDate, issueDate, today]);

  const server = fieldErrors(serverError);
  const errors = { ...server, ...clientErrors };
  // A field-level server error is shown on the field; anything else goes in the banner.
  const bannerError = Object.keys(server).length > 0 ? null : serverError;

  function submit(event: FormEvent) {
    event.preventDefault();
    const found: Record<string, string> = {};
    if (!title.trim()) found.title = "Give the document a name.";
    if (!expiryDate) found.expiry_date = "Choose the expiry date.";
    if (type === "custom" && !customLabel.trim()) found.custom_type_label = "Say what kind of document this is.";
    if (issueDate && expiryDate && expiryDate < issueDate) found.expiry_date = "Expiry can't be before the issue date.";
    setClientErrors(found);
    if (Object.keys(found).length > 0) return;

    onSubmit({
      type,
      custom_type_label: type === "custom" ? customLabel.trim() : null,
      title: title.trim(),
      vehicle_id: vehicleId || null,
      document_number: documentNumber.trim() || null,
      issue_date: issueDate || null,
      expiry_date: expiryDate,
      reminder_offsets: offsets,
      notes: notes.trim() || null,
    });
  }

  return (
    <form onSubmit={submit} noValidate>
      <ErrorNotice error={bannerError} />
      <div className="form-grid">
        <Field label="Type" error={errors.type}>
          <select value={type} onChange={(e) => setType(e.target.value as DocumentType)}>
            {TYPE_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        {type === "custom" && (
          <Field label="What kind of document?" error={errors.custom_type_label}>
            <input value={customLabel} onChange={(e) => setCustomLabel(e.target.value)} maxLength={100} placeholder="e.g. Gym membership" />
          </Field>
        )}
        <Field label="Name" error={errors.title} hint="How you'll recognise it, e.g. “Car insurance”.">
          <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={150} required />
        </Field>
        <Field label="Vehicle (optional)" error={errors.vehicle_id}>
          <select value={vehicleId} onChange={(e) => setVehicleId(e.target.value)}>
            <option value="">Not linked to a vehicle</option>
            {vehicles.map((v) => (
              <option key={v.id} value={v.id}>
                {v.nickname} ({v.plate_number})
              </option>
            ))}
          </select>
        </Field>
        <Field label="Document number (optional)" error={errors.document_number}>
          <input value={documentNumber} onChange={(e) => setDocumentNumber(e.target.value)} maxLength={100} />
        </Field>
        <Field label="Issue date (optional)" error={errors.issue_date}>
          <input type="date" value={issueDate} onChange={(e) => setIssueDate(e.target.value)} />
        </Field>
        <Field label="Expiry date" error={errors.expiry_date}>
          <input type="date" value={expiryDate} onChange={(e) => setExpiryDate(e.target.value)} required />
        </Field>
      </div>
      <fieldset className="reminders">
        <legend>Reminders</legend>
        {expiryDate ? (
          <ReminderCalendar issueDate={issueDate || null} expiryDate={expiryDate} today={today} offsets={offsets} onChange={(next) => { setRemindersTouched(true); setOffsets(next); }} />
        ) : (
          <p className="calendar-placeholder">Choose an expiry date above, then pick your reminder days on a calendar.</p>
        )}
        {errors.reminder_offsets && <p className="field-error">{errors.reminder_offsets}</p>}
      </fieldset>
      <Field label="Notes (optional)" error={errors.notes}>
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} />
      </Field>
      <div className="actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? "Saving…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
