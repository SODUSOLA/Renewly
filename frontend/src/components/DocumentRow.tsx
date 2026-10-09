import { Link } from "react-router-dom";
import type { Doc, Vehicle } from "../api/types";
import { describeDaysLeft, formatDate } from "../lib/dates";
import { typeLabel } from "../lib/status";
import { StatusBadge } from "./StatusBadge";

// One document in a list: title, what/which vehicle, expiry and status.
export function DocumentRow({ doc, vehicles }: { doc: Doc; vehicles?: Vehicle[] }) {
  const vehicle = vehicles?.find((v) => v.id === doc.vehicle_id);
  return (
    <li>
      <Link to={`/documents/${doc.id}`} className="doc-row">
        <div className="doc-main">
          <span className="doc-title">{doc.title}</span>
          <span className="muted small">
            {typeLabel(doc.type, doc.custom_type_label)}
            {vehicle ? ` · ${vehicle.nickname} (${vehicle.plate_number})` : ""}
          </span>
        </div>
        <div className="doc-side">
          <StatusBadge status={doc.status} />
          <span className="muted small">
            {formatDate(doc.expiry_date)} · {doc.status === "expired" ? "expired " : "expires "}
            {describeDaysLeft(doc.days_left)}
          </span>
        </div>
      </Link>
    </li>
  );
}
