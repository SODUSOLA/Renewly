import type { DocumentStatus } from "../api/types";
import { STATUS_META } from "../lib/status";

// Coloured pill with an icon and text, so status never depends on colour alone.
export function StatusBadge({ status }: { status: DocumentStatus }) {
  const meta = STATUS_META[status];
  return (
    <span className={`badge badge-${status}`}>
      <span aria-hidden="true">{meta.icon}</span> {meta.label}
    </span>
  );
}
