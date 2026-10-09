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
import { makeDoc, mockApi, renderApp, USER } from "../test/utils";

afterEach(() => vi.unstubAllGlobals());

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>;
}

describe("LoginPage", () => {
  it("signs in, stores the token and goes to the dashboard", async () => {
    mockApi({
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
    mockApi({ "POST /auth/login": () => ({ status: 401, body: { detail: "Incorrect email or password", code: "unauthorized" } }) });
    renderApp(<LoginPage />, "/login");
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "nope-nope");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password");
    expect(tokenStore.get()).toBeNull();
    expect(screen.getByLabelText("Email")).toHaveValue("ada@example.com");
  });

  it("tells the user when they are rate limited", async () => {
    mockApi({ "POST /auth/login": () => ({ status: 429, body: { detail: "Too many", code: "rate_limited" }, headers: { "Retry-After": "45" } }) });
    renderApp(<LoginPage />, "/login");
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "whatever1");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Try again in 45 seconds");
  });
});

describe("RegisterPage", () => {
  it("explains a duplicate email next to the email field", async () => {
    mockApi({ "POST /auth/register": () => ({ status: 409, body: { detail: "Email already registered", code: "conflict" } }) });
    renderApp(<RegisterPage />, "/register");
    await userEvent.type(screen.getByLabelText("Full name"), "Ada Obi");
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText(/already has an account/i)).toBeInTheDocument();
  });

  it("checks the password length before calling the server", async () => {
    const { fake } = mockApi({});
    renderApp(<RegisterPage />, "/register");
    await userEvent.type(screen.getByLabelText("Full name"), "Ada Obi");
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "short");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Use at least 8 characters.")).toBeInTheDocument();
    expect(fake).not.toHaveBeenCalled();
  });
});

describe("RequireAuth", () => {
  it("sends signed-out visitors to the login page", async () => {
    mockApi({});
    renderApp(
      <Routes>
        <Route path="/login" element={<Where />} />
        <Route element={<RequireAuth />}>
          <Route path="/dashboard" element={<p>secret</p>} />
        </Route>
      </Routes>,
      "/dashboard",
    );
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/login"));
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });

  it("signs the user out when the stored token is rejected", async () => {
    tokenStore.set("expired");
    mockApi({ "GET /auth/me": () => ({ status: 401, body: { detail: "Not authenticated", code: "unauthorized" } }) });
    renderApp(
      <Routes>
        <Route path="/login" element={<Where />} />
        <Route element={<RequireAuth />}>
          <Route path="/dashboard" element={<p>secret</p>} />
        </Route>
      </Routes>,
      "/dashboard",
    );
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/login"));
    expect(tokenStore.get()).toBeNull();
  });
});

describe("DashboardPage", () => {
  it("groups documents and shows counts, status labels and days left", async () => {
    tokenStore.set("tok");
    mockApi({
      "GET /auth/me": () => ({ body: USER }),
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
    tokenStore.set("tok");
    mockApi({
      "GET /auth/me": () => ({ body: USER }),
      "GET /vehicles": () => ({ body: [] }),
      "GET /dashboard": () => ({ body: { today: "2026-10-08", counts: { expired: 0, expiring_soon: 0, valid: 0, total: 0 }, expired: [], expiring_soon: [], valid: [] } }),
    });
    renderApp(<DashboardPage />, "/dashboard");
    expect(await screen.findByRole("heading", { name: "No documents yet" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add your first document" })).toHaveAttribute("href", "/documents?new=1");
  });

  it("offers a retry when loading fails", async () => {
    tokenStore.set("tok");
    mockApi({
      "GET /auth/me": () => ({ body: USER }),
      "GET /vehicles": () => ({ body: [] }),
      "GET /dashboard": () => ({ status: 500, body: { detail: "Internal server error", code: "internal_error", request_id: "abc" } }),
    });
    renderApp(<DashboardPage />, "/dashboard");
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("DocumentForm", () => {
  function setup(onSubmit = vi.fn()) {
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

  it("rejects bad reminder offsets with a clear message", async () => {
    setup();
    await userEvent.type(screen.getByLabelText("Name"), "Insurance");
    await userEvent.type(screen.getByLabelText("Expiry date"), "2027-01-01");
    const offsets = screen.getByLabelText("Remind me this many days before");
    await userEvent.clear(offsets);
    await userEvent.type(offsets, "7, soon");
    await userEvent.click(screen.getByRole("button", { name: "Add document" }));
    expect(screen.getByText(/"soon" is not a whole number/)).toBeInTheDocument();
  });

  it("submits clean data: trimmed text, sorted offsets, nulls for blanks", async () => {
    const onSubmit = setup();
    await userEvent.type(screen.getByLabelText("Name"), "  Car insurance ");
    await userEvent.type(screen.getByLabelText("Expiry date"), "2027-03-01");
    const offsets = screen.getByLabelText("Remind me this many days before");
    await userEvent.clear(offsets);
    await userEvent.type(offsets, "7, 30");
    await userEvent.click(screen.getByRole("button", { name: "Add document" }));
    expect(onSubmit).toHaveBeenCalledWith({
      type: "insurance", custom_type_label: null, title: "Car insurance", vehicle_id: null,
      document_number: null, issue_date: null, expiry_date: "2027-03-01", reminder_offsets: [30, 7], notes: null,
    });
  });
});
