import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { AuthProvider } from "../auth/AuthContext";

type Handler = (request: { url: URL; method: string; body: unknown }) => { status?: number; body?: unknown; headers?: Record<string, string> };

// Replaces fetch with a fake API. `routes` maps "METHOD /path" to a handler; an
// unknown route fails the test loudly instead of silently returning nothing.
export function mockApi(routes: Record<string, Handler>) {
  const calls: { key: string; body: unknown; headers: Headers }[] = [];
  const fake = vi.fn(async (input: URL | string, init?: RequestInit) => {
    const url = new URL(String(input));
    const method = init?.method ?? "GET";
    const key = `${method} ${url.pathname}`;
    const handler = routes[key];
    if (!handler) throw new Error(`Unexpected request: ${key}`);
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ key, body, headers: new Headers(init?.headers as HeadersInit) });
    const result = handler({ url, method, body });
    const status = result.status ?? 200;
    return new Response(status === 204 ? null : JSON.stringify(result.body ?? {}), {
      status,
      headers: { "Content-Type": "application/json", ...result.headers },
    });
  });
  vi.stubGlobal("fetch", fake);
  return { calls, fake };
}

// Renders a screen with everything the real app provides: data cache, router, auth.
export function renderApp(ui: ReactElement, route = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <AuthProvider>{ui}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

export const USER = { id: "u1", email: "ada@example.com", full_name: "Ada Obi", timezone: "Africa/Lagos", reminder_style: "each", report_emails: true, onboarding: {}, created_at: "2026-10-01T00:00:00Z" };

export function makeDoc(overrides: Record<string, unknown> = {}) {
  return {
    id: "d1", vehicle_id: null, type: "insurance", custom_type_label: null, title: "Car insurance",
    document_number: null, issue_date: null, expiry_date: "2027-03-01", reminder_offsets: [90, 30, 14, 7, 1],
    notes: null, created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z",
    status: "valid", days_left: 144, ...overrides,
  };
}

const UNAUTHORIZED = { detail: "Not authenticated", code: "unauthorized" };

// Routes for a visitor with NO session: the first-load refresh is rejected.
export const SIGNED_OUT = {
  "POST /auth/refresh": () => ({ status: 401, body: UNAUTHORIZED }),
};

// Routes for a visitor with a valid refresh cookie: refresh succeeds, /auth/me works.
export const SIGNED_IN = {
  "POST /auth/refresh": () => ({ body: { access_token: "tok", token_type: "bearer", expires_in: 900 } }),
  "GET /auth/me": () => ({ body: USER }),
  // An established user by default (has a document), so the welcome and tour stay out of the way.
  "GET /onboarding/progress": () => ({ body: { documents: 1, vehicles: 0, renewals: 0, renewals_with_cost: 0 } }),
};
