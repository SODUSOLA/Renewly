import { vi } from "vitest";
import { ApiError, api, errorMessage, fieldErrors, setUnauthorizedHandler, tokenStore } from "./client";
import { mockApi } from "../test/utils";

afterEach(() => {
  setUnauthorizedHandler(null);
  vi.unstubAllGlobals();
});

describe("api()", () => {
  it("sends the bearer token and JSON body", async () => {
    tokenStore.set("tok123");
    const { calls } = mockApi({ "POST /vehicles": () => ({ status: 201, body: { id: "v1" } }) });
    await api("/vehicles", { method: "POST", body: { nickname: "Car" } });
    expect(calls[0].headers.get("Authorization")).toBe("Bearer tok123");
    expect(calls[0].headers.get("Content-Type")).toBe("application/json");
    expect(calls[0].body).toEqual({ nickname: "Car" });
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

  it("calls the unauthorized handler on a signed-in 401, but not on public calls", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockApi({
      "GET /dashboard": () => ({ status: 401, body: { detail: "Not authenticated", code: "unauthorized" } }),
      "POST /auth/login": () => ({ status: 401, body: { detail: "Incorrect email or password", code: "unauthorized" } }),
    });
    await api("/dashboard").catch(() => undefined);
    expect(handler).toHaveBeenCalledTimes(1);
    await api("/auth/login", { method: "POST", body: {}, public: true }).catch(() => undefined);
    expect(handler).toHaveBeenCalledTimes(1);
  });
});
