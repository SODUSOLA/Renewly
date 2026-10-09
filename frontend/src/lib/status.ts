import type { DocumentStatus, DocumentType } from "../api/types";

// Presentation for each status. Colour is never the only signal: each has a label and icon.
export const STATUS_META: Record<DocumentStatus, { label: string; icon: string }> = {
  expired: { label: "Expired", icon: "⚠" },
  expiring_soon: { label: "Expiring soon", icon: "⏳" },
  valid: { label: "Valid", icon: "✓" },
};

export const TYPE_LABELS: Record<DocumentType, string> = {
  driver_license: "Driver's license",
  insurance: "Insurance",
  vehicle_registration: "Vehicle registration",
  permit: "Permit",
  custom: "Other",
};

export const TYPE_OPTIONS = Object.entries(TYPE_LABELS) as [DocumentType, string][];

export function typeLabel(type: DocumentType, custom: string | null): string {
  return type === "custom" && custom ? custom : TYPE_LABELS[type];
}
