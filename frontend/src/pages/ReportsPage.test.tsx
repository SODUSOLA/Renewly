import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { ReportsPage } from "./ReportsPage";
import { DocumentDetailPage } from "./DocumentDetailPage";
import { Route, Routes } from "react-router-dom";
import { RequireAuth } from "../auth/RequireAuth";
import { makeDoc, mockApi, renderApp, SIGNED_IN } from "../test/utils";

afterEach(() => vi.unstubAllGlobals());

// func to build a report like the API returns, overriding any part
function makeReport(overrides: Record<string, unknown> = {}) {
  const months = Array.from({ length: 12 }, (_, i) => ({ month: i + 1, total: "0.00", renewals: 0 }));
  months[0] = { month: 1, total: "150000.50", renewals: 1 };
  months[2] = { month: 3, total: "37000.25", renewals: 3 };
  return {
    year: 2026,
    currency: "NGN",
    available_years: [2026, 2025],
    totals: { total: "187000.75", previous_year_total: "100000.00", renewals: 5, renewals_with_cost: 4 },
    by_month: months,
    by_type: [
      { label: "Insurance", total: "170000.50", renewals: 2 },
      { label: "Permit", total: "5000.25", renewals: 1 },
    ],
    by_vehicle: [
      { label: "Corolla (ABC123)", total: "182000.50", renewals: 3, vehicle_id: "v1" },
      { label: "No vehicle", total: "5000.25", renewals: 2, vehicle_id: null },
    ],
    missing_cost: [{ renewal_id: "r9", document_id: "d9", title: "Gym", renewed_on: "2026-07-01" }],
    missing_cost_count: 1,
    ...overrides,
  };
}

// func to open the reports page with a fake API
async function open(report: object, extra: Parameters<typeof mockApi>[0] = {}) {
  const api = mockApi({ ...SIGNED_IN, "GET /reports/costs": () => ({ body: report }), ...extra });
  renderApp(<ReportsPage />, "/reports");
  await screen.findByRole("heading", { name: "Reports" });
  return api;
}

describe("ReportsPage", () => {
  it("shows the totals, the comparison with last year and what is missing", async () => {
    await open(makeReport());
    expect(await screen.findByText("₦187,000.75")).toBeInTheDocument();
    expect(screen.getByText("Spent in 2026")).toBeInTheDocument();
    expect(screen.getByText(/↑ 87% more than 2025 \(₦100,000.00\)/)).toBeInTheDocument();
    expect(screen.getByText("4 with a cost recorded")).toBeInTheDocument();
    expect(screen.getByText("Totals are understated until added")).toBeInTheDocument();
  });

  it("gives the chart a text equivalent for screen readers", async () => {
    await open(makeReport());
    const chart = await screen.findByRole("img", { name: /Spending by month in 2026/ });
    const label = chart.getAttribute("aria-label")!;
    expect(label).toContain("January ₦150,000.50");
    expect(label).toContain("March ₦37,000.25");
    expect(label).toContain("February ₦0.00");
  });

  it("ranks types and vehicles with each one's share of the total", async () => {
    await open(makeReport());
    const byType = await screen.findByRole("region", { name: "By type" });
    expect(within(byType).getByText("Insurance")).toBeInTheDocument();
    expect(within(byType).getByText("₦170,000.50")).toBeInTheDocument();
    expect(within(byType).getByText("2 renewals · 91%")).toBeInTheDocument();
    const byVehicle = screen.getByRole("region", { name: "By vehicle" });
    expect(within(byVehicle).getByText("No vehicle")).toBeInTheDocument();
  });

  it("links each renewal that needs a cost to its document", async () => {
    await open(makeReport());
    const link = await screen.findByRole("link", { name: /Gym/ });
    expect(link).toHaveAttribute("href", "/documents/d9");
  });

  it("says when nothing is recorded for the year and offers no download", async () => {
    await open(makeReport({ totals: { total: "0.00", previous_year_total: "0.00", renewals: 0, renewals_with_cost: 0 }, missing_cost: [], missing_cost_count: 0 }));
    expect(await screen.findByRole("heading", { name: "No renewals in 2026" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download CSV" })).toBeDisabled();
  });

  it("handles a year with no previous-year spending", async () => {
    await open(makeReport({ totals: { total: "500.00", previous_year_total: "0.00", renewals: 1, renewals_with_cost: 1 }, missing_cost: [], missing_cost_count: 0 }));
    expect(await screen.findByText("Nothing recorded in 2025")).toBeInTheDocument();
    expect(screen.getByText("Nothing to fill in")).toBeInTheDocument();
  });

  it("requests another year when the selector changes", async () => {
    const seen: (string | null)[] = [];
    mockApi({
      ...SIGNED_IN,
      "GET /reports/costs": ({ url }) => {
        seen.push(url.searchParams.get("year"));
        return { body: makeReport({ year: Number(url.searchParams.get("year") ?? 2026) }) };
      },
    });
    renderApp(<ReportsPage />, "/reports");
    await userEvent.selectOptions(await screen.findByLabelText("Year"), "2025");
    await waitFor(() => expect(seen).toContain("2025"));
    expect(seen[0]).toBeNull(); // the first load lets the server choose the current year
  });

  it("downloads the CSV for the year shown", async () => {
    const created: Blob[] = [];
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: (b: Blob) => (created.push(b), "blob:fake"), revokeObjectURL: vi.fn() }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const { calls } = await open(makeReport(), {
      "GET /reports/costs.csv": ({ url }) => ({ body: "x", status: 200, headers: { "Content-Type": "text/csv" }, ...{ csv: url.searchParams.get("year") } }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Download CSV" }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(calls.some((c) => c.key === "GET /reports/costs.csv")).toBe(true);
    expect(created).toHaveLength(1);
    click.mockRestore();
  });

  it("offers a retry when the report cannot load", async () => {
    mockApi({ ...SIGNED_IN, "GET /reports/costs": () => ({ status: 500, body: { detail: "boom", code: "internal_error" } }) });
    renderApp(<ReportsPage />, "/reports");
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side");
  });
});

describe("editing a renewal's cost from the document page", () => {
  // func to open a document with one renewal that has no cost
  async function openDocument(routes: Parameters<typeof mockApi>[0] = {}) {
    const api = mockApi({
      ...SIGNED_IN,
      "GET /documents/d1": () => ({ body: makeDoc() }),
      "GET /vehicles": () => ({ body: [] }),
      "GET /documents/d1/renewals": () => ({
        body: [{ id: "r1", previous_expiry: "2026-03-01", new_expiry: "2027-03-01", renewed_on: "2026-02-20", cost: null, notes: null }],
      }),
      ...routes,
    });
    renderApp(
      <Routes>
        <Route element={<RequireAuth />}>
          <Route path="/documents/:id" element={<DocumentDetailPage />} />
        </Route>
      </Routes>,
      "/documents/d1",
    );
    await screen.findByRole("heading", { name: "Car insurance" });
    return api;
  }

  it("adds a missing cost and sends it as a string", async () => {
    const { calls } = await openDocument({
      "PATCH /documents/d1/renewals/r1": () => ({ body: { id: "r1", cost: "15000.50" } }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Add cost" }));
    await userEvent.type(screen.getByLabelText("Cost in ₦"), "15000.50");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.key === "PATCH /documents/d1/renewals/r1")).toBe(true));
    expect(calls.find((c) => c.key === "PATCH /documents/d1/renewals/r1")?.body).toEqual({ cost: "15000.50", notes: null });
  });

  it("rejects a cost that isn't a number before calling the server", async () => {
    const { calls } = await openDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Add cost" }));
    await userEvent.type(screen.getByLabelText("Cost in ₦"), "lots");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText(/Enter the cost as a number/)).toBeInTheDocument();
    expect(calls.some((c) => c.key.startsWith("PATCH"))).toBe(false);
  });
});
