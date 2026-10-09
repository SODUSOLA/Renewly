import { useState } from "react";
import { Link } from "react-router-dom";
import type { Vehicle } from "../api/types";
import { useCreateVehicle, useDeleteVehicle, useUpdateVehicle, useVehicles } from "../api/queries";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ErrorNotice } from "../components/ErrorNotice";
import { Modal } from "../components/Modal";
import { Spinner } from "../components/Spinner";
import { VehicleForm } from "../components/VehicleForm";

type Dialog = { kind: "add" } | { kind: "edit"; vehicle: Vehicle } | { kind: "delete"; vehicle: Vehicle } | null;

// The user's vehicles: add, edit, delete, and jump to each one's documents.
export function VehiclesPage() {
  const vehicles = useVehicles();
  const [dialog, setDialog] = useState<Dialog>(null);
  const create = useCreateVehicle();
  const remove = useDeleteVehicle();

  function close() {
    setDialog(null);
    create.reset();
    remove.reset();
  }

  return (
    <>
      <div className="page-head">
        <h1>Vehicles</h1>
        <button type="button" className="btn btn-primary" onClick={() => setDialog({ kind: "add" })}>
          + Add vehicle
        </button>
      </div>

      {vehicles.isPending ? (
        <Spinner label="Loading vehicles" />
      ) : vehicles.isError ? (
        <ErrorNotice error={vehicles.error} onRetry={() => vehicles.refetch()} />
      ) : vehicles.data.length === 0 ? (
        <div className="empty">
          <h2>No vehicles yet</h2>
          <p className="muted">Add a vehicle to group its insurance, registration and permits together.</p>
          <button type="button" className="btn btn-primary" onClick={() => setDialog({ kind: "add" })}>
            Add your first vehicle
          </button>
        </div>
      ) : (
        <ul className="vehicle-list">
          {vehicles.data.map((v) => (
            <li key={v.id} className="card vehicle">
              <div>
                <p className="doc-title">{v.nickname}</p>
                <p className="plate">{v.plate_number}</p>
                <p className="muted small">{[v.make, v.model, v.year].filter(Boolean).join(" · ") || "No details added"}</p>
              </div>
              <div className="actions actions-start">
                <Link className="btn btn-ghost btn-sm" to={`/documents?vehicle_id=${v.id}`}>
                  Documents
                </Link>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setDialog({ kind: "edit", vehicle: v })}>
                  Edit
                </button>
                <button type="button" className="btn btn-ghost btn-sm btn-danger-text" onClick={() => setDialog({ kind: "delete", vehicle: v })}>
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {dialog?.kind === "add" && (
        <Modal title="Add a vehicle" onClose={close}>
          <VehicleForm
            submitting={create.isPending}
            serverError={create.error}
            submitLabel="Add vehicle"
            onCancel={close}
            onSubmit={(input) => create.mutate(input, { onSuccess: close })}
          />
        </Modal>
      )}
      {dialog?.kind === "edit" && <EditVehicle vehicle={dialog.vehicle} onClose={close} />}
      {dialog?.kind === "delete" && (
        <ConfirmDialog
          title="Delete this vehicle?"
          message={`“${dialog.vehicle.nickname}” will be removed. Its documents are kept, just no longer linked to a vehicle.`}
          confirmLabel="Delete"
          busy={remove.isPending}
          onCancel={close}
          onConfirm={() => remove.mutate(dialog.vehicle.id, { onSuccess: close })}
        />
      )}
    </>
  );
}

// Edit dialog (its own component because the update hook is tied to one vehicle id).
function EditVehicle({ vehicle, onClose }: { vehicle: Vehicle; onClose: () => void }) {
  const update = useUpdateVehicle(vehicle.id);
  return (
    <Modal title="Edit vehicle" onClose={onClose}>
      <VehicleForm
        initial={vehicle}
        submitting={update.isPending}
        serverError={update.error}
        submitLabel="Save changes"
        onCancel={onClose}
        onSubmit={(input) => update.mutate(input, { onSuccess: onClose })}
      />
    </Modal>
  );
}
