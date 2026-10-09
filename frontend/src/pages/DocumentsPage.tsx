import { useSearchParams } from "react-router-dom";
import { useState } from "react";
import type { DocumentStatus, DocumentType } from "../api/types";
import { useCreateDocument, useDocuments, useVehicles } from "../api/queries";
import { DocumentForm } from "../components/DocumentForm";
import { DocumentRow } from "../components/DocumentRow";
import { ErrorNotice } from "../components/ErrorNotice";
import { Modal } from "../components/Modal";
import { Spinner } from "../components/Spinner";
import { STATUS_META, TYPE_OPTIONS } from "../lib/status";

// All documents, filterable by status, type and vehicle (filters live in the URL
// so a filtered view can be bookmarked or linked from the dashboard).
export function DocumentsPage() {
  const [params, setParams] = useSearchParams();
  const status = (params.get("status") ?? "") as DocumentStatus | "";
  const type = (params.get("type") ?? "") as DocumentType | "";
  const vehicleId = params.get("vehicle_id") ?? "";
  const [adding, setAdding] = useState(params.get("new") === "1");

  const documents = useDocuments({ status, type, vehicle_id: vehicleId || undefined });
  const vehicles = useVehicles();
  const create = useCreateDocument();
  const filtered = Boolean(status || type || vehicleId);

  function setFilter(name: string, value: string) {
    const next = new URLSearchParams(params);
    next.delete("new");
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next, { replace: true });
  }

  function closeAdd() {
    setAdding(false);
    create.reset();
    if (params.has("new")) {
      const next = new URLSearchParams(params);
      next.delete("new");
      setParams(next, { replace: true });
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>Documents</h1>
        <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>
          + Add document
        </button>
      </div>

      <div className="filters" role="group" aria-label="Filters">
        <label>
          <span className="sr-only">Status</span>
          <select value={status} onChange={(e) => setFilter("status", e.target.value)}>
            <option value="">All statuses</option>
            {(Object.keys(STATUS_META) as DocumentStatus[]).map((s) => (
              <option key={s} value={s}>
                {STATUS_META[s].label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="sr-only">Type</span>
          <select value={type} onChange={(e) => setFilter("type", e.target.value)}>
            <option value="">All types</option>
            {TYPE_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="sr-only">Vehicle</span>
          <select value={vehicleId} onChange={(e) => setFilter("vehicle_id", e.target.value)}>
            <option value="">All vehicles</option>
            {vehicles.data?.map((v) => (
              <option key={v.id} value={v.id}>
                {v.nickname}
              </option>
            ))}
          </select>
        </label>
        {filtered && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setParams({}, { replace: true })}>
            Clear filters
          </button>
        )}
      </div>

      {documents.isPending ? (
        <Spinner label="Loading documents" />
      ) : documents.isError ? (
        <ErrorNotice error={documents.error} onRetry={() => documents.refetch()} />
      ) : documents.data.length === 0 ? (
        <div className="empty">
          <h2>{filtered ? "No documents match" : "No documents yet"}</h2>
          <p className="muted">{filtered ? "Try different filters." : "Add a document and we'll remind you before it expires."}</p>
          {!filtered && (
            <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>
              Add your first document
            </button>
          )}
        </div>
      ) : (
        <ul className="doc-list" aria-label="Documents">
          {documents.data.map((doc) => (
            <DocumentRow key={doc.id} doc={doc} vehicles={vehicles.data} />
          ))}
        </ul>
      )}

      {adding && (
        <Modal title="Add a document" onClose={closeAdd}>
          <DocumentForm
            vehicles={vehicles.data ?? []}
            submitting={create.isPending}
            serverError={create.error}
            submitLabel="Add document"
            onCancel={closeAdd}
            onSubmit={(input) => create.mutate(input, { onSuccess: closeAdd })}
          />
        </Modal>
      )}
    </>
  );
}
