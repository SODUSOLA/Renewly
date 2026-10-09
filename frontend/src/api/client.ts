// A small fetch wrapper: adds the bearer token, parses the API's uniform error
// shape ({detail, code, request_id}) and reports expired sessions.

export const API_URL: string = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

const TOKEN_KEY = "renewly.token";

// The token lives in localStorage so a refresh keeps you signed in. Every access
// is wrapped because storage can be blocked (private windows, strict settings).
export const tokenStore = {
  get(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string): void {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* stay signed in for this tab only */
    }
  },
  clear(): void {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* nothing to clear */
    }
  },
};

interface FieldProblem {
  loc: (string | number)[];
  msg: string;
}

// An error response from the API (or a network failure, with status 0).
export class ApiError extends Error {
  status: number;
  code: string;
  requestId: string | null;
  retryAfter: number | null;
  problems: FieldProblem[];

  constructor(init: {
    status: number;
    message: string;
    code?: string;
    requestId?: string | null;
    retryAfter?: number | null;
    problems?: FieldProblem[];
  }) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code ?? "unknown";
    this.requestId = init.requestId ?? null;
    this.retryAfter = init.retryAfter ?? null;
    this.problems = init.problems ?? [];
  }
}

// Field-level messages from a 422, keyed by field name ("expiry_date" -> "Field required").
export function fieldErrors(error: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (error instanceof ApiError) {
    for (const p of error.problems) {
      const field = p.loc[p.loc.length - 1];
      if (typeof field === "string" && !(field in out)) {
        out[field] = p.msg.replace(/^Value error, /, "");
      }
    }
  }
  return out;
}

// One human-readable sentence for any error.
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 0) return "Can't reach the server. Check your connection and try again.";
    if (error.status === 429) {
      const wait = error.retryAfter ? ` Try again in ${formatWait(error.retryAfter)}.` : "";
      return `Too many attempts.${wait}`;
    }
    if (error.status >= 500) return "Something went wrong on our side. Please try again.";
    return error.message;
  }
  return "Something went wrong. Please try again.";
}

function formatWait(seconds: number): string {
  if (seconds < 90) return `${seconds} seconds`;
  return `${Math.ceil(seconds / 60)} minutes`;
}

let onUnauthorized: (() => void) | null = null;

// The auth provider registers a callback here so any 401 on a signed-in request
// signs the user out and returns them to the login page.
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, string | undefined | null>;
  // Endpoints like login/register must not trigger the "session expired" flow.
  public?: boolean;
}

// Calls the API and returns the parsed JSON (undefined for 204). Throws ApiError.
export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = new URL(API_URL + path);
  for (const [key, value] of Object.entries(options.query ?? {})) {
    if (value) url.searchParams.set(key, value);
  }
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const token = tokenStore.get();
  if (token && !options.public) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: options.method ?? "GET",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new ApiError({ status: 0, message: "Network error", code: "network_error" });
  }

  if (response.status === 204) return undefined as T;

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    /* non-JSON body */
  }

  if (response.ok) return payload as T;

  const body = (payload ?? {}) as { detail?: unknown; code?: string; request_id?: string };
  const problems = Array.isArray(body.detail) ? (body.detail as FieldProblem[]) : [];
  const message =
    typeof body.detail === "string"
      ? body.detail
      : problems.length > 0
        ? "Please check the highlighted fields."
        : `Request failed (${response.status})`;
  const retry = Number(response.headers.get("Retry-After"));

  const error = new ApiError({
    status: response.status,
    message,
    code: body.code,
    requestId: body.request_id ?? response.headers.get("X-Request-ID"),
    retryAfter: Number.isFinite(retry) && retry > 0 ? retry : null,
    problems,
  });
  if (response.status === 401 && !options.public) onUnauthorized?.();
  throw error;
}
