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

// Shortcuts for adding a first document: the kind to preselect and a sensible starting name.
export const QUICK_ADD: { type: DocumentType; label: string; title: string }[] = [
  { type: "driver_license", label: "Driver's licence", title: "Driver's licence" },
  { type: "insurance", label: "Car insurance", title: "Car insurance" },
  { type: "vehicle_registration", label: "Vehicle registration", title: "Vehicle registration" },
  { type: "permit", label: "A permit", title: "" },
  { type: "custom", label: "Something else", title: "" },
];

// The shortcut for a document type, if the text is one (used to read ?new=insurance).
export function quickAddFor(value: string | null): (typeof QUICK_ADD)[number] | undefined {
  return QUICK_ADD.find((q) => q.type === value);
}
