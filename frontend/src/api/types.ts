// Shapes of the API's JSON. They mirror docs/api.md.

export type DocumentType =
  | "driver_license"
  | "insurance"
  | "vehicle_registration"
  | "permit"
  | "custom";

export type DocumentStatus = "valid" | "expiring_soon" | "expired";

export interface User {
  id: string;
  email: string;
  full_name: string;
  timezone: string;
  created_at: string;
}

export interface Vehicle {
  id: string;
  nickname: string;
  plate_number: string;
  make: string | null;
  model: string | null;
  year: number | null;
  created_at: string;
  updated_at: string;
}

export interface VehicleInput {
  nickname: string;
  plate_number: string;
  make?: string | null;
  model?: string | null;
  year?: number | null;
}

export interface Doc {
  id: string;
  vehicle_id: string | null;
  type: DocumentType;
  custom_type_label: string | null;
  title: string;
  document_number: string | null;
  issue_date: string | null;
  expiry_date: string;
  reminder_offsets: number[];
  notes: string | null;
  created_at: string;
  updated_at: string;
  status: DocumentStatus;
  days_left: number;
}

export interface DocInput {
  vehicle_id?: string | null;
  type: DocumentType;
  custom_type_label?: string | null;
  title: string;
  document_number?: string | null;
  issue_date?: string | null;
  expiry_date: string;
  reminder_offsets?: number[];
  notes?: string | null;
}

export interface RenewInput {
  new_expiry: string;
  cost?: string | null;
  notes?: string | null;
}

export interface Renewal {
  id: string;
  previous_expiry: string;
  new_expiry: string;
  renewed_on: string;
  cost: string | null;
  notes: string | null;
}

export interface Dashboard {
  today: string;
  counts: { expired: number; expiring_soon: number; valid: number; total: number };
  expired: Doc[];
  expiring_soon: Doc[];
  valid: Doc[];
}
