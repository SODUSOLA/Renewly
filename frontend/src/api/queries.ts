// React Query hooks: one per API operation. Mutations invalidate the lists they
// affect so every screen shows fresh data.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { Dashboard, Doc, DocInput, DocumentStatus, DocumentType, RenewInput, Renewal, Vehicle, VehicleInput } from "./types";

export const keys = {
  dashboard: ["dashboard"] as const,
  documents: ["documents"] as const,
  document: (id: string) => ["documents", id] as const,
  renewals: (id: string) => ["documents", id, "renewals"] as const,
  vehicles: ["vehicles"] as const,
};

export function useDashboard() {
  return useQuery({ queryKey: keys.dashboard, queryFn: () => api<Dashboard>("/dashboard") });
}

export interface DocFilters {
  status?: DocumentStatus | "";
  type?: DocumentType | "";
  vehicle_id?: string;
}

export function useDocuments(filters: DocFilters) {
  return useQuery({
    queryKey: [...keys.documents, "list", filters],
    queryFn: () => api<Doc[]>("/documents", { query: { ...filters } }),
  });
}

export function useDocument(id: string) {
  return useQuery({ queryKey: keys.document(id), queryFn: () => api<Doc>(`/documents/${id}`) });
}

export function useRenewals(id: string) {
  return useQuery({ queryKey: keys.renewals(id), queryFn: () => api<Renewal[]>(`/documents/${id}/renewals`) });
}

export function useVehicles() {
  return useQuery({ queryKey: keys.vehicles, queryFn: () => api<Vehicle[]>("/vehicles") });
}

// Anything that changes documents also changes the dashboard (and vice versa).
function useRefreshDocuments() {
  const client = useQueryClient();
  return () => Promise.all([
    client.invalidateQueries({ queryKey: keys.documents }),
    client.invalidateQueries({ queryKey: keys.dashboard }),
  ]);
}

export function useCreateDocument() {
  const refresh = useRefreshDocuments();
  return useMutation({
    mutationFn: (input: DocInput) => api<Doc>("/documents", { method: "POST", body: input }),
    onSuccess: refresh,
  });
}

export function useUpdateDocument(id: string) {
  const refresh = useRefreshDocuments();
  return useMutation({
    mutationFn: (input: Partial<DocInput>) => api<Doc>(`/documents/${id}`, { method: "PATCH", body: input }),
    onSuccess: refresh,
  });
}

export function useDeleteDocument() {
  const refresh = useRefreshDocuments();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/documents/${id}`, { method: "DELETE" }),
    onSuccess: refresh,
  });
}

export function useRenewDocument(id: string) {
  const refresh = useRefreshDocuments();
  return useMutation({
    mutationFn: (input: RenewInput) => api<Doc>(`/documents/${id}/renew`, { method: "POST", body: input }),
    onSuccess: refresh,
  });
}

export function useCreateVehicle() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: VehicleInput) => api<Vehicle>("/vehicles", { method: "POST", body: input }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.vehicles }),
  });
}

export function useUpdateVehicle(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<VehicleInput>) => api<Vehicle>(`/vehicles/${id}`, { method: "PATCH", body: input }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.vehicles }),
  });
}

export function useDeleteVehicle() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/vehicles/${id}`, { method: "DELETE" }),
    // Deleting a vehicle detaches its documents, so document lists change too.
    onSuccess: () => Promise.all([
      client.invalidateQueries({ queryKey: keys.vehicles }),
      client.invalidateQueries({ queryKey: keys.documents }),
      client.invalidateQueries({ queryKey: keys.dashboard }),
    ]),
  });
}
