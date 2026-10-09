import { vi } from "vitest";
import { ApiError, api, errorMessage, fieldErrors, refreshAccessToken, setUnauthorizedHandler, tokenStore } from "./client";
import { mockApi } from "../test/utils";

afterEach(() => {
  setUnauthorizedHandler(null);
  vi.unstubAllGlobals();
});

const REFRESHED = { access_token: "fresh", token_type: "bearer", expires_in: 900 };
const UNAUTHORIZED = { detail: "Not authenticated", code: "unauthorized" };

describe("api()", () => {
  it("sends the bearer token, the JSON body and asks the browser to include cookies", async () => {
    tokenStore.set("tok123");
    const { calls, fake } = mockApi({ "POST /vehicles": () => ({ status: 201, body: { id: "v1" } }) });
    await api("/vehicles", { method: "POST", body: { nickname: "Car" } });
    expect(calls[0].headers.get("Authorization")).toBe("Bearer tok123");
    expect(calls[0].headers.get("Content-Type")).toBe("application/json");
    expect(calls[0].body).toEqual({ nickname: "Car" });
    expect((fake.mock.calls[0][1] as RequestInit).credentials).toBe("include");
  });

  it("omits the token on public endpoints", async () => {
    tokenStore.set("tok123");
    const { calls } = mockApi({ "POST /auth/login": () => ({ body: { access_token: "x" } }) });
    await api("/auth/login", { method: "POST", body: {}, public: true });
    expect(calls[0].headers.get("Authorization")).toBeNull();
  });

  it("returns undefined for 204", async () => {
    mockApi({ "DELETE /vehicles/1": () => ({ status: 204 }) });
    await expect(api("/vehicles/1", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("turns the API's error shape into an ApiError", async () => {
    mockApi({ "GET /documents/x": () => ({ status: 404, body: { detail: "Document not found", code: "not_found", request_id: "rid" } }) });
    const error = await api("/documents/x").catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, code: "not_found", requestId: "rid", message: "Document not found" });
  });

  it("exposes field errors from a 422 and strips pydantic's prefix", async () => {
    mockApi({
      "POST /documents": () => ({
        status: 422,
        body: { detail: [{ loc: ["body", "expiry_date"], msg: "Value error, expiry before issue" }], code: "validation_error" },
      }),
    });
    const error = await api("/documents", { method: "POST", body: {} }).catch((e) => e);
    expect(fieldErrors(error)).toEqual({ expiry_date: "expiry before issue" });
  });

  it("reads Retry-After on 429 and words it for people", async () => {
    mockApi({ "POST /auth/login": () => ({ status: 429, body: { detail: "Too many", code: "rate_limited" }, headers: { "Retry-After": "120" } }) });
    const error = (await api("/auth/login", { method: "POST", body: {}, public: true }).catch((e) => e)) as ApiError;
    expect(error.retryAfter).toBe(120);
    expect(errorMessage(error)).toBe("Too many attempts. Try again in 2 minutes.");
  });

  it("reports a network failure as status 0", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = (await api("/dashboard").catch((e) => e)) as ApiError;
    expect(error.status).toBe(0);
    expect(errorMessage(error)).toMatch(/can't reach the server/i);
  });

  it("hides server-fault details behind a friendly message", () => {
    const error = new ApiError({ status: 500, message: "Internal server error" });
    expect(errorMessage(error)).toBe("Something went wrong on our side. Please try again.");
  });
});

describe("silent session renewal", () => {
  it("refreshes once on a 401 and retries the request with the new token", async () => {
    tokenStore.set("expired");
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    const { calls } = mockApi({
      "GET /dashboard": () => (tokenStore.get() === "fresh" ? { body: { ok: true } } : { status: 401, body: UNAUTHORIZED }),
      "POST /auth/refresh": () => ({ body: REFRESHED }),
    });
    await expect(api("/dashboard")).resolves.toEqual({ ok: true });
    expect(calls.map((c) => c.key)).toEqual(["GET /dashboard", "POST /auth/refresh", "GET /dashboard"]);
    expect(calls[2].headers.get("Authorization")).toBe("Bearer fresh");
    expect(handler).not.toHaveBeenCalled();
  });

  it("shares one refresh between requests that fail at the same time", async () => {
    tokenStore.set("expired");
    const { calls } = mockApi({
      "GET /dashboard": () => (tokenStore.get() === "fresh" ? { body: { n: 1 } } : { status: 401, body: UNAUTHORIZED }),
      "GET /vehicles": () => (tokenStore.get() === "fresh" ? { body: [] } : { status: 401, body: UNAUTHORIZED }),
      "POST /auth/refresh": () => ({ body: REFRESHED }),
    });
    await Promise.all([api("/dashboard"), api("/vehicles")]);
    expect(calls.filter((c) => c.key === "POST /auth/refresh")).toHaveLength(1);
  });

  it("signs the user out when the session cannot be renewed", async () => {
    tokenStore.set("expired");
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockApi({
      "GET /dashboard": () => ({ status: 401, body: UNAUTHORIZED }),
      "POST /auth/refresh": () => ({ status: 401, body: UNAUTHORIZED }),
    });
    const error = (await api("/dashboard").catch((e) => e)) as ApiError;
    expect(error.status).toBe(401);
    expect(handler).toHaveBeenCalledTimes(1);
    expect(tokenStore.get()).toBeNull();
  });

  it("gives up after one retry instead of looping", async () => {
    tokenStore.set("expired");
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    const { calls } = mockApi({
      "GET /dashboard": () => ({ status: 401, body: UNAUTHORIZED }),
      "POST /auth/refresh": () => ({ body: REFRESHED }),
    });
    await api("/dashboard").catch(() => undefined);
    expect(calls.filter((c) => c.key === "GET /dashboard")).toHaveLength(2);
    expect(calls.filter((c) => c.key === "POST /auth/refresh")).toHaveLength(1);
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("does not sign the user out when the refresh fails for network reasons", async () => {
    tokenStore.set("expired");
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: URL | string) => {
        if (String(input).endsWith("/auth/refresh")) throw new TypeError("offline");
        return new Response(JSON.stringify(UNAUTHORIZED), { status: 401 });
      }),
    );
    const error = (await api("/dashboard").catch((e) => e)) as ApiError;
    expect(error.status).toBe(0);
    expect(handler).not.toHaveBeenCalled();
  });

  it("does not try to refresh after a failed public call such as a wrong password", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    const { calls } = mockApi({
      "POST /auth/login": () => ({ status: 401, body: { detail: "Incorrect email or password", code: "unauthorized" } }),
    });
    await api("/auth/login", { method: "POST", body: {}, public: true }).catch(() => undefined);
    expect(calls.map((c) => c.key)).toEqual(["POST /auth/login"]);
    expect(handler).not.toHaveBeenCalled();
  });
});

describe("refreshAccessToken()", () => {
  it("stores and returns the new token", async () => {
    mockApi({ "POST /auth/refresh": () => ({ body: REFRESHED }) });
    await expect(refreshAccessToken()).resolves.toBe("fresh");
    expect(tokenStore.get()).toBe("fresh");
  });

  it("returns null (and forgets the token) when there is no valid session", async () => {
    tokenStore.set("old");
    mockApi({ "POST /auth/refresh": () => ({ status: 401, body: UNAUTHORIZED }) });
    await expect(refreshAccessToken()).resolves.toBeNull();
    expect(tokenStore.get()).toBeNull();
  });

  it("throws on a server error so it is not mistaken for a sign-out", async () => {
    mockApi({ "POST /auth/refresh": () => ({ status: 500, body: { detail: "boom", code: "internal_error" } }) });
    await expect(refreshAccessToken()).rejects.toMatchObject({ status: 500 });
  });
});
