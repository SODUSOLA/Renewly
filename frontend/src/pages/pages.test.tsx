import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation } from "react-router-dom";
import { vi } from "vitest";
import { tokenStore } from "../api/client";
import { DocumentForm } from "../components/DocumentForm";
import { DashboardPage } from "./DashboardPage";
import { LoginPage } from "./LoginPage";
import { RegisterPage } from "./RegisterPage";
import { RequireAuth } from "../auth/RequireAuth";
import { makeDoc, mockApi, renderApp, SIGNED_IN, SIGNED_OUT, USER } from "../test/utils";

// Fake API for a visitor with no session / with a valid session cookie.
const signedOut = (routes: Parameters<typeof mockApi>[0]) => mockApi({ ...SIGNED_OUT, ...routes });
const signedIn = (routes: Parameters<typeof mockApi>[0]) => mockApi({ ...SIGNED_IN, ...routes });

afterEach(() => vi.unstubAllGlobals());

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>;
}

describe("LoginPage", () => {
  it("signs in, stores the token and goes to the dashboard", async () => {
    signedOut({
      "POST /auth/login": ({ body }) => {
        expect(body).toEqual({ email: "ada@example.com", password: "correct-horse" });
        return { body: { access_token: "tok", token_type: "bearer" } };
      },
      "GET /auth/me": () => ({ body: USER }),
    });
    renderApp(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/dashboard" element={<Where />} />
      </Routes>,
      "/login",
    );
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/dashboard"));
    expect(tokenStore.get()).toBe("tok");
  });

  it("shows the server's message for wrong credentials and keeps the form", async () => {
    signedOut({ "POST /auth/login": () => ({ status: 401, body: { detail: "Incorrect email or password", code: "unauthorized" } }) });
    renderApp(<LoginPage />, "/login");
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "nope-nope");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password");
    expect(tokenStore.get()).toBeNull();
    expect(screen.getByLabelText("Email")).toHaveValue("ada@example.com");
  });

  it("tells the user when they are rate limited", async () => {
    signedOut({ "POST /auth/login": () => ({ status: 429, body: { detail: "Too many", code: "rate_limited" }, headers: { "Retry-After": "45" } }) });
    renderApp(<LoginPage />, "/login");
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "whatever1");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Try again in 45 seconds");
  });
});

describe("RegisterPage", () => {
  it("explains a duplicate email next to the email field", async () => {
    signedOut({ "POST /auth/register": () => ({ status: 409, body: { detail: "Email already registered", code: "conflict" } }) });
    renderApp(<RegisterPage />, "/register");
    await userEvent.type(screen.getByLabelText("Full name"), "Ada Obi");
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText(/already has an account/i)).toBeInTheDocument();
  });

  it("checks the password length before calling the server", async () => {
    const { fake } = signedOut({});
    renderApp(<RegisterPage />, "/register");
    await waitFor(() => expect(fake).toHaveBeenCalledTimes(1)); // only the first-load session check
    await userEvent.type(screen.getByLabelText("Full name"), "Ada Obi");
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "short");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Use at least 8 characters.")).toBeInTheDocument();
    expect(fake).toHaveBeenCalledTimes(1); // still just the session check: nothing was submitted
  });
});

describe("RequireAuth", () => {
  it("sends visitors without a session to the login page, quietly", async () => {
    signedOut({});
    renderApp(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route path="/dashboard" element={<p>secret</p>} />
        </Route>
      </Routes>,
      "/dashboard",
    );
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
    expect(screen.queryByText(/session ended/i)).not.toBeInTheDocument();
  });

  it("restores the session on page load from the refresh cookie", async () => {
    signedIn({});
    renderApp(
      <Routes>
        <Route element={<RequireAuth />}>
          <Route path="/dashboard" element={<p>secret</p>} />
        </Route>
      </Routes>,
      "/dashboard",
    );
    expect(await screen.findByText("secret")).toBeInTheDocument();
    expect(tokenStore.get()).toBe("tok");
  });

  it("explains it when a session ends while the user is signed in", async () => {
    let refreshes = 0;
    mockApi({
      "POST /auth/refresh": () =>
        ++refreshes === 1
          ? { body: { access_token: "tok", token_type: "bearer", expires_in: 900 } }
          : { status: 401, body: { detail: "Not authenticated", code: "unauthorized" } },
      "GET /auth/me": () => ({ body: USER }),
      "GET /vehicles": () => ({ status: 401, body: { detail: "Not authenticated", code: "unauthorized" } }),
      "GET /dashboard": () => ({ status: 401, body: { detail: "Not authenticated", code: "unauthorized" } }),
    });
    renderApp(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route path="/dashboard" element={<DashboardPage />} />
        </Route>
      </Routes>,
      "/dashboard",
    );
    expect(await screen.findByText(/your session ended/i)).toBeInTheDocument();
    expect(tokenStore.get()).toBeNull();
  });
});

describe("DashboardPage", () => {
  it("groups documents and shows counts, status labels and days left", async () => {
    signedIn({
      "GET /vehicles": () => ({ body: [] }),
      "GET /dashboard": () => ({
        body: {
          today: "2026-10-08",
          counts: { expired: 1, expiring_soon: 1, valid: 1, total: 3 },
          expired: [makeDoc({ id: "a", title: "Old permit", status: "expired", days_left: -3, expiry_date: "2026-10-05" })],
          expiring_soon: [makeDoc({ id: "b", title: "Licence", status: "expiring_soon", days_left: 1, expiry_date: "2026-10-09" })],
          valid: [makeDoc({ id: "c", title: "Insurance" })],
        },
      }),
    });
    renderApp(<DashboardPage />, "/dashboard");
    const expired = await screen.findByRole("region", { name: /expired/i });
    expect(within(expired).getByText("Old permit")).toBeInTheDocument();
    expect(within(expired).getByText(/expired 3 days ago/)).toBeInTheDocument();
    expect(screen.getByText(/expires tomorrow/)).toBeInTheDocument();
    expect(screen.getByText("1 document has expired. Renew it soon.")).toBeInTheDocument();
    const summary = screen.getByRole("region", { name: "Summary" });
    expect(within(summary).getByRole("link", { name: /expired/i })).toHaveAttribute("href", "/documents?status=expired");
  });

  it("invites the user to add a first document when there are none", async () => {
    signedIn({
      "GET /vehicles": () => ({ body: [] }),
      "GET /dashboard": () => ({ body: { today: "2026-10-08", counts: { expired: 0, expiring_soon: 0, valid: 0, total: 0 }, expired: [], expiring_soon: [], valid: [] } }),
    });
    renderApp(<DashboardPage />, "/dashboard");
    expect(await screen.findByRole("heading", { name: "No documents yet" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add your first document" })).toHaveAttribute("href", "/documents?new=1");
  });

  it("offers a retry when loading fails", async () => {
    signedIn({
      "GET /vehicles": () => ({ body: [] }),
      "GET /dashboard": () => ({ status: 500, body: { detail: "Internal server error", code: "internal_error", request_id: "abc" } }),
    });
    renderApp(<DashboardPage />, "/dashboard");
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("DocumentForm", () => {
  beforeEach(() => {
    // The form decides what "today" is (for which reminder days are allowed); pin it.
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-09T10:00:00Z"));
  });
  afterEach(() => vi.useRealTimers());

  function setup(onSubmit = vi.fn()) {
    signedIn({});
    renderApp(<DocumentForm vehicles={[]} submitting={false} serverError={null} submitLabel="Add document" onSubmit={onSubmit} onCancel={() => undefined} />);
    return onSubmit;
  }

  it("requires a name and an expiry date", async () => {
    const onSubmit = setup();
    await userEvent.click(screen.getByRole("button", { name: "Add document" }));
    expect(screen.getByText("Give the document a name.")).toBeInTheDocument();
    expect(screen.getByText("Choose the expiry date.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("asks for a label when the type is 'Other'", async () => {
    const onSubmit = setup();
    await userEvent.selectOptions(screen.getByLabelText("Type"), "custom");
    await userEvent.type(screen.getByLabelText("Name"), "Gym");
    await userEvent.type(screen.getByLabelText("Expiry date"), "2027-01-01");
    await userEvent.click(screen.getByRole("button", { name: "Add document" }));
    expect(screen.getByText("Say what kind of document this is.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("shows the reminder calendar only once there is an expiry date", async () => {
    setup();
    expect(screen.getByText(/Choose an expiry date above, then pick your reminder days/)).toBeInTheDocument();
    expect(screen.queryByRole("grid")).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Expiry date"), "2027-03-01");
    expect(await screen.findByRole("grid")).toBeInTheDocument();
    expect(screen.getByText("4 of 4 reminders")).toBeInTheDocument();
  });

  it("submits clean data: trimmed text, the default reminders, nulls for blanks", async () => {
    const onSubmit = setup();
    await userEvent.type(screen.getByLabelText("Name"), "  Car insurance ");
    await userEvent.type(screen.getByLabelText("Expiry date"), "2027-03-01");
    await userEvent.click(screen.getByRole("button", { name: "Add document" }));
    expect(onSubmit).toHaveBeenCalledWith({
      type: "insurance", custom_type_label: null, title: "Car insurance", vehicle_id: null,
      document_number: null, issue_date: null, expiry_date: "2027-03-01", reminder_offsets: [30, 14, 7, 1], notes: null,
    });
  });

  it("suggests only the default reminders that are still possible for a near expiry date", async () => {
    setup();
    await userEvent.type(screen.getByLabelText("Expiry date"), "2026-10-31"); // 22 days from the pinned "today"
    expect(await screen.findByText("3 of 4 reminders")).toBeInTheDocument(); // 14, 7 and 1: not the 30-day one
    expect(screen.queryByText(/passed/)).not.toBeInTheDocument();
  });

  it("stops adjusting the suggested reminders once the user has chosen their own", async () => {
    setup();
    await userEvent.type(screen.getByLabelText("Expiry date"), "2026-10-31");
    await userEvent.click(await screen.findByRole("button", { name: "Clear all" }));
    await userEvent.clear(screen.getByLabelText("Expiry date"));
    await userEvent.type(screen.getByLabelText("Expiry date"), "2026-12-31");
    expect(await screen.findByText("0 of 4 reminders")).toBeInTheDocument();
  });

  it("sends the reminders chosen on the calendar as days before expiry", async () => {
    const onSubmit = setup();
    await userEvent.type(screen.getByLabelText("Name"), "Licence");
    await userEvent.type(screen.getByLabelText("Expiry date"), "2026-10-31");
    await userEvent.click(await screen.findByRole("button", { name: "Clear all" }));
    await userEvent.click(screen.getByRole("button", { name: /^Saturday, 24 October 2026/ }));
    await userEvent.click(screen.getByRole("button", { name: /^Saturday, 17 October 2026/ }));
    await userEvent.click(screen.getByRole("button", { name: "Add document" }));
    expect(onSubmit.mock.calls[0][0].reminder_offsets).toEqual([14, 7]);
  });

  it("explains in the form when a chosen day is outside the allowed range", async () => {
    const onSubmit = setup();
    await userEvent.type(screen.getByLabelText("Name"), "Licence");
    await userEvent.type(screen.getByLabelText("Issue date (optional)"), "2026-10-01");
    await userEvent.type(screen.getByLabelText("Expiry date"), "2026-10-31");
    await userEvent.click(screen.getByRole("button", { name: /^Monday, 5 October 2026/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That day has already passed");
    await userEvent.click(screen.getByRole("button", { name: "Add document" }));
    expect(onSubmit.mock.calls[0][0].reminder_offsets).not.toContain(26); // the refused day was not added
  });
});
