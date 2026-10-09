// A small fetch wrapper: adds the bearer token, parses the API's uniform error
// shape ({detail, code, request_id}) and reports expired sessions.

export const API_URL: string = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

let accessToken: string | null = null;

// The short-lived access token lives only in memory: a script injected into the page
// cannot find it in storage, and a reload simply gets a new one via the refresh cookie.
export const tokenStore = {
  get(): string | null {
    return accessToken;
  },
  set(token: string): void {
    accessToken = token;
  },
  clear(): void {
    accessToken = null;
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

// The auth provider registers a callback here so that when a session can no longer be
// renewed, the user is signed out and sent back to the login page.
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, string | undefined | null>;
  // Endpoints like login/register must not send the token or trigger the refresh flow.
  public?: boolean;
  // "text" returns the body as a string (used for CSV downloads); default is JSON.
  as?: "json" | "text";
}

// One HTTP call. `credentials: "include"` makes the browser send and store the
// HttpOnly refresh cookie (needed by login, refresh and logout).
async function request<T>(path: string, options: RequestOptions): Promise<T> {
  // API_URL may be absolute (https://api.example.com) or a same-origin prefix (/api).
  const url = new URL(API_URL + path, window.location.origin);
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
      credentials: "include",
    });
  } catch {
    throw new ApiError({ status: 0, message: "Network error", code: "network_error" });
  }

  if (response.status === 204) return undefined as T;
  if (response.ok && options.as === "text") return (await response.text()) as T;

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

  throw new ApiError({
    status: response.status,
    message,
    code: body.code,
    requestId: body.request_id ?? response.headers.get("X-Request-ID"),
    retryAfter: Number.isFinite(retry) && retry > 0 ? retry : null,
    problems,
  });
}

let refreshInFlight: Promise<string | null> | null = null;

// Trades the refresh cookie for a new access token and keeps it in memory.
// Returns the token, or null if the server says there is no valid session (a normal
// outcome for a signed-out visitor). Throws on network or server trouble, so a flaky
// connection never looks like "you were signed out". Concurrent callers (several
// requests failing at once, React StrictMode) share one call, because each refresh
// rotates the cookie and a second parallel one would race with the first.
export function refreshAccessToken(): Promise<string | null> {
  refreshInFlight ??= (async () => {
    try {
      const result = await request<{ access_token: string }>("/auth/refresh", { method: "POST", public: true });
      tokenStore.set(result.access_token);
      return result.access_token;
    } catch (error) {
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        tokenStore.clear();
        return null;
      }
      throw error;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

const isUnauthorized = (error: unknown): boolean => error instanceof ApiError && error.status === 401;

// Calls the API and returns the parsed JSON (undefined for 204). Throws ApiError.
// If a signed-in request gets a 401 (the 15-minute access token ran out), it silently
// refreshes once and retries; only when that fails is the user signed out.
export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  try {
    return await request<T>(path, options);
  } catch (error) {
    if (!isUnauthorized(error) || options.public) throw error;
    const fresh = await refreshAccessToken();
    if (!fresh) {
      onUnauthorized?.();
      throw error;
    }
    try {
      return await request<T>(path, options);
    } catch (retryError) {
      if (isUnauthorized(retryError)) onUnauthorized?.();
      throw retryError;
    }
  }
}
