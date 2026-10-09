import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, fieldErrors } from "../api/client";
import type { Doc } from "../api/types";
import { useDeleteDocument, useDocument, useRenewals, useRenewDocument, useUpdateDocument, useVehicles } from "../api/queries";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DocumentForm } from "../components/DocumentForm";
import { ErrorNotice } from "../components/ErrorNotice";
import { Field } from "../components/Field";
import { Modal } from "../components/Modal";
import { Spinner } from "../components/Spinner";
import { StatusBadge } from "../components/StatusBadge";
import { addYears, describeDaysLeft, formatDate, formatNaira } from "../lib/dates";
import { typeLabel } from "../lib/status";

type Dialog = "edit" | "renew" | "delete" | null;

// One document: its details, renew/edit/delete actions and renewal history.
export function DocumentDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const document = useDocument(id);
  const renewals = useRenewals(id);
  const vehicles = useVehicles();
  const update = useUpdateDocument(id);
  const renew = useRenewDocument(id);
  const remove = useDeleteDocument();
  const [dialog, setDialog] = useState<Dialog>(null);

  function close() {
    setDialog(null);
    update.reset();
    renew.reset();
    remove.reset();
  }

  if (document.isPending) return <Spinner label="Loading document" />;
  if (document.isError) {
    const notFound = document.error instanceof ApiError && document.error.status === 404;
    return notFound ? (
      <div className="empty">
        <h2>Document not found</h2>
        <p className="muted">It may have been deleted.</p>
        <Link className="btn btn-primary" to="/documents">
          Back to documents
        </Link>
      </div>
    ) : (
      <ErrorNotice error={document.error} onRetry={() => document.refetch()} />
    );
  }

  const doc = document.data;
  const vehicle = vehicles.data?.find((v) => v.id === doc.vehicle_id);
  return (
    <>
      <p className="breadcrumb">
        <Link to="/documents">← Documents</Link>
      </p>
      <div className="page-head">
        <div>
          <h1>{doc.title}</h1>
          <p className="muted">
            {typeLabel(doc.type, doc.custom_type_label)}
            {vehicle ? ` · ${vehicle.nickname} (${vehicle.plate_number})` : ""}
          </p>
        </div>
        <StatusBadge status={doc.status} />
      </div>

      <div className="card">
        <p className="lead">
          {doc.status === "expired" ? "Expired " : "Expires "}
          <strong>{formatDate(doc.expiry_date)}</strong> ({describeDaysLeft(doc.days_left)})
        </p>
        <dl className="facts">
          {doc.document_number && <Fact label="Document number" value={doc.document_number} />}
          {doc.issue_date && <Fact label="Issued" value={formatDate(doc.issue_date)} />}
          <Fact label="Reminders" value={remindersText(doc)} />
          {doc.notes && <Fact label="Notes" value={doc.notes} />}
        </dl>
        <div className="actions actions-start">
          <button type="button" className="btn btn-primary" onClick={() => setDialog("renew")}>
            Mark as renewed
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => setDialog("edit")}>
            Edit
          </button>
          <button type="button" className="btn btn-ghost btn-danger-text" onClick={() => setDialog("delete")}>
            Delete
          </button>
        </div>
      </div>

      <section className="group" aria-labelledby="history">
        <h2 id="history">Renewal history</h2>
        {renewals.isPending ? (
          <Spinner label="Loading history" />
        ) : renewals.isError ? (
          <ErrorNotice error={renewals.error} onRetry={() => renewals.refetch()} />
        ) : renewals.data.length === 0 ? (
          <p className="muted">No renewals recorded yet.</p>
        ) : (
          <ul className="history">
            {renewals.data.map((r) => (
              <li key={r.id}>
                <strong>{formatDate(r.previous_expiry)}</strong> → <strong>{formatDate(r.new_expiry)}</strong>
                <span className="muted small">
                  {" "}
                  renewed {formatDate(r.renewed_on)}
                  {r.cost ? ` · ${formatNaira(r.cost)}` : ""}
                </span>
                {r.notes && <div className="muted small">{r.notes}</div>}
              </li>
            ))}
          </ul>
        )}
      </section>

      {dialog === "edit" && (
        <Modal title="Edit document" onClose={close}>
          <DocumentForm
            initial={doc}
            vehicles={vehicles.data ?? []}
            submitting={update.isPending}
            serverError={update.error}
            submitLabel="Save changes"
            onCancel={close}
            onSubmit={(input) => update.mutate(input, { onSuccess: close })}
          />
        </Modal>
      )}
      {dialog === "renew" && (
        <Modal title="Mark as renewed" onClose={close}>
          <RenewForm
            doc={doc}
            submitting={renew.isPending}
            serverError={renew.error}
            onCancel={close}
            onSubmit={(input) => renew.mutate(input, { onSuccess: close })}
          />
        </Modal>
      )}
      {dialog === "delete" && (
        <ConfirmDialog
          title="Delete this document?"
          message={`“${doc.title}” will disappear from your list and you'll stop getting reminders for it.`}
          confirmLabel="Delete"
          busy={remove.isPending}
          onCancel={close}
          onConfirm={() => remove.mutate(doc.id, { onSuccess: () => navigate("/documents", { replace: true }) })}
        />
      )}
    </>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

// "We'll email you 90, 30, 14, 7 and 1 days before expiry." / "Reminders are off."
function remindersText(doc: Doc): string {
  const o = doc.reminder_offsets;
  if (o.length === 0) return "Off";
  const list = o.length === 1 ? String(o[0]) : `${o.slice(0, -1).join(", ")} and ${o[o.length - 1]}`;
  return `${list} ${o.length === 1 && o[0] === 1 ? "day" : "days"} before expiry`;
}

// Renew: pick the new expiry (suggesting one year on) and optionally record the cost.
function RenewForm({
  doc,
  submitting,
  serverError,
  onSubmit,
  onCancel,
}: {
  doc: Doc;
  submitting: boolean;
  serverError: unknown;
  onSubmit: (input: { new_expiry: string; cost: string | null; notes: string | null }) => void;
  onCancel: () => void;
}) {
  const [newExpiry, setNewExpiry] = useState(addYears(doc.expiry_date, 1));
  const [cost, setCost] = useState("");
  const [notes, setNotes] = useState("");
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({});

  const server = fieldErrors(serverError);
  const errors = { ...server, ...clientErrors };
  // Field errors show on the fields; any other failure (e.g. a rule message) is a banner.
  const banner = Object.keys(server).length > 0 ? null : serverError;

  function submit(event: FormEvent) {
    event.preventDefault();
    const found: Record<string, string> = {};
    if (!newExpiry) found.new_expiry = "Choose the new expiry date.";
    else if (newExpiry <= doc.expiry_date) found.new_expiry = `Must be later than the current expiry (${formatDate(doc.expiry_date)}).`;
    if (cost && !/^\d+(\.\d{1,2})?$/.test(cost)) found.cost = "Enter the cost as a number, like 15000 or 15000.50.";
    setClientErrors(found);
    if (Object.keys(found).length > 0) return;
    onSubmit({ new_expiry: newExpiry, cost: cost || null, notes: notes.trim() || null });
  }

  return (
    <form onSubmit={submit} noValidate>
      <ErrorNotice error={banner} />
      <Field label="New expiry date" error={errors.new_expiry}>
        <input type="date" value={newExpiry} onChange={(e) => setNewExpiry(e.target.value)} required />
      </Field>
      <Field label="Cost in ₦ (optional)" error={errors.cost} hint="For your own records.">
        <input value={cost} onChange={(e) => setCost(e.target.value)} inputMode="decimal" placeholder="15000" />
      </Field>
      <Field label="Notes (optional)" error={errors.notes}>
        <input value={notes} onChange={(e) => setNotes(e.target.value)} />
      </Field>
      <p className="muted small">We'll start reminding you again before the new expiry date.</p>
      <div className="actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? "Saving…" : "Mark as renewed"}
        </button>
      </div>
    </form>
  );
}
