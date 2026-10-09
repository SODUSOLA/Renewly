import { useState, type FormEvent } from "react";
import { fieldErrors } from "../api/client";
import type { Vehicle, VehicleInput } from "../api/types";
import { ErrorNotice } from "./ErrorNotice";
import { Field } from "./Field";

// Create/edit form for a vehicle.
export function VehicleForm({
  initial,
  submitting,
  serverError,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial?: Vehicle;
  submitting: boolean;
  serverError: unknown;
  submitLabel: string;
  onSubmit: (input: VehicleInput) => void;
  onCancel: () => void;
}) {
  const [nickname, setNickname] = useState(initial?.nickname ?? "");
  const [plate, setPlate] = useState(initial?.plate_number ?? "");
  const [make, setMake] = useState(initial?.make ?? "");
  const [model, setModel] = useState(initial?.model ?? "");
  const [year, setYear] = useState(initial?.year ? String(initial.year) : "");
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({});

  const server = fieldErrors(serverError);
  const errors = { ...server, ...clientErrors };
  const bannerError = Object.keys(server).length > 0 ? null : serverError;

  function submit(event: FormEvent) {
    event.preventDefault();
    const found: Record<string, string> = {};
    if (!nickname.trim()) found.nickname = "Give the vehicle a name.";
    if (!plate.trim()) found.plate_number = "Enter the plate number.";
    const yearNumber = year.trim() ? Number(year) : null;
    if (yearNumber !== null && (!Number.isInteger(yearNumber) || yearNumber < 1900 || yearNumber > 2100)) {
      found.year = "Enter a year between 1900 and 2100.";
    }
    setClientErrors(found);
    if (Object.keys(found).length > 0) return;
    onSubmit({
      nickname: nickname.trim(),
      plate_number: plate.trim(),
      make: make.trim() || null,
      model: model.trim() || null,
      year: yearNumber,
    });
  }

  return (
    <form onSubmit={submit} noValidate>
      <ErrorNotice error={bannerError} />
      <div className="form-grid">
        <Field label="Name" error={errors.nickname} hint="e.g. “Work car”.">
          <input value={nickname} onChange={(e) => setNickname(e.target.value)} maxLength={100} required />
        </Field>
        <Field label="Plate number" error={errors.plate_number} hint="Spaces and case don't matter.">
          <input value={plate} onChange={(e) => setPlate(e.target.value)} maxLength={20} required />
        </Field>
        <Field label="Make (optional)" error={errors.make}>
          <input value={make} onChange={(e) => setMake(e.target.value)} maxLength={60} />
        </Field>
        <Field label="Model (optional)" error={errors.model}>
          <input value={model} onChange={(e) => setModel(e.target.value)} maxLength={60} />
        </Field>
        <Field label="Year (optional)" error={errors.year}>
          <input value={year} onChange={(e) => setYear(e.target.value)} inputMode="numeric" maxLength={4} />
        </Field>
      </div>
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
