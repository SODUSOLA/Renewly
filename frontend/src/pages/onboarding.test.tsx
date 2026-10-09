import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { vi } from "vitest";
import { GettingStarted } from "../components/GettingStarted";
import { QuickAdd } from "../components/QuickAdd";
import { APP_TOUR, Tour, type TourStep } from "../components/Tour";
import { WelcomeDialog } from "../components/WelcomeDialog";
import { buildChecklist } from "../lib/onboarding";
import { makeDoc, mockApi, renderApp, SIGNED_IN, USER } from "../test/utils";
import { DashboardPage } from "./DashboardPage";
import { DocumentsPage } from "./DocumentsPage";
import { SettingsPage } from "./SettingsPage";
import { RegisterPage } from "./RegisterPage";
import { RequireAuth } from "../auth/RequireAuth";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

const NO_PROGRESS = { documents: 0, vehicles: 0, renewals: 0, renewals_with_cost: 0 };
const EMPTY_DASHBOARD = { today: "2026-10-09", counts: { expired: 0, expiring_soon: 0, valid: 0, total: 0 }, expired: [], expiring_soon: [], valid: [] };
const patchBody = (calls: { key: string; body: unknown }[]) => calls.filter((c) => c.key === "PATCH /auth/me/onboarding").map((c) => c.body);

// func to give every element a size, because jsdom has no layout (the tour only spotlights visible elements)
function giveElementsASize() {
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({ x: 20, y: 40, top: 40, left: 20, right: 220, bottom: 80, width: 200, height: 40, toJSON: () => ({}) } as DOMRect);
}

// ------------------------------------------------------------------ the welcome
describe("WelcomeDialog", () => {
  it("explains the idea in three steps and offers the tour or skipping", async () => {
    const onTour = vi.fn();
    const onSkip = vi.fn();
    render(<WelcomeDialog firstName="Ngozi" onTour={onTour} onSkip={onSkip} />);
    expect(screen.getByRole("dialog", { name: "Welcome, Ngozi" })).toBeInTheDocument();
    expect(screen.getByText("Add a document")).toBeInTheDocument();
    expect(screen.getByText("Pick your reminder days")).toBeInTheDocument();
    expect(screen.getByText("Renew it, then mark it as renewed")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Take a 1-minute tour" }));
    expect(onTour).toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Skip, I'll explore" }));
    expect(onSkip).toHaveBeenCalled();
  });

  it("treats Escape as 'skip'", async () => {
    const onSkip = vi.fn();
    render(<WelcomeDialog onTour={vi.fn()} onSkip={onSkip} />);
    await userEvent.keyboard("{Escape}");
    expect(onSkip).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------- the tour
describe("Tour", () => {
  const steps: TourStep[] = [
    { target: "a", title: "First", body: "About A" },
    { target: "b", title: "Second", body: "About B" },
    { target: "c", title: "Third", body: "About C" },
  ];

  // func to render some targets and the tour over them
  function setup(present: string[], onClose = vi.fn(), tour = steps) {
    giveElementsASize();
    render(
      <>
        {present.map((id) => (
          <button key={id} data-tour={id}>
            target {id}
          </button>
        ))}
        <Tour steps={tour} onClose={onClose} />
      </>,
    );
    return onClose;
  }

  it("walks through each step with Next and Back, and finishes with Done", async () => {
    const onClose = setup(["a", "b", "c"]);
    expect(await screen.findByRole("dialog", { name: "First" })).toHaveTextContent("Step 1 of 3");
    expect(screen.queryByRole("button", { name: "Back" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("dialog", { name: "Second" })).toHaveTextContent("About B");
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByRole("dialog", { name: "First" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("dialog", { name: "Third" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(onClose).toHaveBeenCalledWith(true);
  });

  it("can be skipped at any point, and Escape does the same", async () => {
    const onClose = setup(["a", "b", "c"]);
    await userEvent.click(await screen.findByRole("button", { name: "Skip tour" }));
    expect(onClose).toHaveBeenLastCalledWith(false);
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("moves with the arrow keys", async () => {
    setup(["a", "b", "c"]);
    await screen.findByRole("dialog", { name: "First" });
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("dialog", { name: "Second" })).toBeInTheDocument();
    await userEvent.keyboard("{ArrowLeft}");
    expect(screen.getByRole("dialog", { name: "First" })).toBeInTheDocument();
  });

  it("skips steps whose element isn't on the page (e.g. hidden on a phone)", async () => {
    setup(["a", "c"]); // no "b"
    expect(await screen.findByRole("dialog", { name: "First" })).toHaveTextContent("Step 1 of 2");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("dialog", { name: "Third" })).toHaveTextContent("Step 2 of 2");
  });

  it("closes straight away when nothing can be shown", async () => {
    const onClose = setup([]);
    await waitFor(() => expect(onClose).toHaveBeenCalledWith(false));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("puts the keyboard focus on Next so Enter moves on", async () => {
    setup(["a", "b", "c"]);
    await screen.findByRole("dialog", { name: "First" });
    expect(screen.getByRole("button", { name: "Next" })).toHaveFocus();
  });

  it("keeps the spotlight on its element when content loads in above it (no scroll or resize event)", async () => {
    let top = 40;
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(
      () => ({ x: 20, y: top, top, left: 20, right: 220, bottom: top + 40, width: 200, height: 40, toJSON: () => ({}) }) as DOMRect,
    );
    render(
      <>
        <button data-tour="a">target a</button>
        <Tour steps={steps.slice(0, 1)} onClose={vi.fn()} />
      </>,
    );
    const spot = await screen.findByTestId("tour").then((t) => t.querySelector(".tour-spot") as HTMLElement);
    expect(spot.style.top).toBe("34px"); // 40 minus the 6px padding
    top = 500; // something above it appeared and pushed it down
    await waitFor(() => expect(spot.style.top).toBe("494px"));
  });

  it("covers every part of the app in the real tour", () => {
    expect(APP_TOUR.map((s) => s.target)).toEqual(["summary", "add-document", "nav-documents", "nav-vehicles", "nav-reports", "nav-settings"]);
    expect(new Set(APP_TOUR.map((s) => s.title)).size).toBe(APP_TOUR.length);
  });
});

// -------------------------------------------------------------------- the checklist
describe("GettingStarted", () => {
  const view = (progress = NO_PROGRESS, onboarding = {}) => {
    const onDismiss = vi.fn();
    const onTour = vi.fn();
    render(
      <MemoryRouter>
        <GettingStarted summary={buildChecklist(progress, onboarding)} onDismiss={onDismiss} onTour={onTour} />
      </MemoryRouter>,
    );
    return { onDismiss, onTour };
  };

  it("shows progress and points the new user at the most useful next step", async () => {
    const { onTour, onDismiss } = view();
    expect(screen.getByRole("heading", { name: "Get started" })).toBeInTheDocument();
    expect(screen.getByText("1 of 6 done")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Getting started progress" })).toHaveAttribute("aria-valuenow", "1");
    const add = screen.getByRole("link", { name: "Add a document" });
    expect(add).toHaveAttribute("href", "/documents?new=1");
    expect(add).toHaveClass("btn-primary"); // the one to do next
    expect(screen.getByRole("link", { name: "Open settings" })).not.toHaveClass("btn-primary");
    await userEvent.click(screen.getByRole("button", { name: "Take the tour" }));
    expect(onTour).toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Hide the getting started checklist" }));
    expect(onDismiss).toHaveBeenCalled();
  });

  it("labels the optional and later steps so nothing feels overdue", () => {
    view();
    expect(screen.getByText("Optional")).toBeInTheDocument();
    expect(screen.getAllByText("When you next renew")).toHaveLength(2);
  });

  it("marks finished steps as done for screen readers and drops their button", () => {
    view({ ...NO_PROGRESS, documents: 1 });
    expect(screen.getByText("Add your first document").parentElement).toHaveTextContent("(done)");
    expect(screen.queryByRole("link", { name: "Add a document" })).not.toBeInTheDocument();
    expect(screen.getByText("2 of 6 done")).toBeInTheDocument();
  });

  it("changes its message once the essentials are done", () => {
    view({ ...NO_PROGRESS, documents: 1 }, { settings_reviewed: true });
    expect(screen.getByRole("heading", { name: "You're all set" })).toBeInTheDocument();
    expect(screen.getByText(/We'll email you before anything expires/)).toBeInTheDocument();
  });
});

describe("QuickAdd", () => {
  it("offers the common kinds of document, each opening the form set up for it", () => {
    render(
      <MemoryRouter>
        <QuickAdd />
      </MemoryRouter>,
    );
    const hrefs = Object.fromEntries(screen.getAllByRole("link").map((a) => [a.textContent, a.getAttribute("href")]));
    expect(hrefs).toEqual({
      "Driver's licence": "/documents?new=driver_license",
      "Car insurance": "/documents?new=insurance",
      "Vehicle registration": "/documents?new=vehicle_registration",
      "A permit": "/documents?new=permit",
      "Something else": "/documents?new=custom",
    });
  });
});

// ---------------------------------------------------------- the dashboard, end to end
describe("Dashboard: the first visit", () => {
  const newUser = (extra: Parameters<typeof mockApi>[0] = {}) =>
    mockApi({
      ...SIGNED_IN,
      "GET /vehicles": () => ({ body: [] }),
      "GET /dashboard": () => ({ body: EMPTY_DASHBOARD }),
      "GET /onboarding/progress": () => ({ body: NO_PROGRESS }),
      "PATCH /auth/me/onboarding": ({ body }) => ({ body: { ...USER, onboarding: body } }),
      ...extra,
    });

  it("welcomes a brand-new user once, and remembers the answer", async () => {
    const { calls } = newUser();
    renderApp(<DashboardPage />, "/dashboard");
    await screen.findByRole("dialog", { name: /Welcome/ });
    await userEvent.click(screen.getByRole("button", { name: "Skip, I'll explore" }));
    await waitFor(() => expect(patchBody(calls)).toEqual([{ tour_done: true }]));
    expect(screen.queryByRole("dialog", { name: /Welcome/ })).not.toBeInTheDocument();
  });

  it("starts the tour when asked, spotlighting the real dashboard", async () => {
    giveElementsASize();
    const { calls } = newUser();
    renderApp(<DashboardPage />, "/dashboard");
    await screen.findByRole("dialog", { name: /Welcome/ });
    await userEvent.click(screen.getByRole("button", { name: "Take a 1-minute tour" }));
    // This test renders the page without the navigation bar, so only the two on-page targets exist.
    expect(await screen.findByRole("dialog", { name: "Your documents at a glance" })).toHaveTextContent("Step 1 of 2");
    expect(patchBody(calls)).toEqual([{ tour_done: true }]);
    await userEvent.click(screen.getByRole("button", { name: "Skip tour" }));
    await waitFor(() => expect(screen.queryByTestId("tour")).not.toBeInTheDocument());
  });

  it("does not welcome someone who has already seen it, or who already has data", async () => {
    mockApi({ ...SIGNED_IN, "GET /vehicles": () => ({ body: [] }), "GET /dashboard": () => ({ body: EMPTY_DASHBOARD }), "GET /onboarding/progress": () => ({ body: { ...NO_PROGRESS, documents: 2 } }) });
    renderApp(<DashboardPage />, "/dashboard");
    await screen.findByRole("heading", { name: "No documents yet" });
    expect(screen.queryByRole("dialog", { name: /Welcome/ })).not.toBeInTheDocument();
  });

  it("shows the checklist, ticking steps from real data, and lets the user hide it", async () => {
    const { calls } = newUser({ "GET /onboarding/progress": () => ({ body: { ...NO_PROGRESS, documents: 1 } }) });
    renderApp(<DashboardPage />, "/dashboard");
    const card = await screen.findByRole("region", { name: /Get started|You're all set/ });
    expect(within(card).getByText("2 of 6 done")).toBeInTheDocument();
    await userEvent.click(within(card).getByRole("button", { name: "Hide the getting started checklist" }));
    await waitFor(() => expect(patchBody(calls)).toEqual([{ checklist_dismissed: true }]));
  });

  it("keeps the checklist hidden for someone who dismissed it", async () => {
    mockApi({
      ...SIGNED_IN,
      "GET /auth/me": () => ({ body: { ...USER, onboarding: { checklist_dismissed: true, tour_done: true } } }),
      "GET /vehicles": () => ({ body: [] }),
      "GET /dashboard": () => ({ body: EMPTY_DASHBOARD }),
    });
    renderApp(<DashboardPage />, "/dashboard");
    await screen.findByRole("heading", { name: "No documents yet" });
    expect(screen.queryByRole("heading", { name: "Get started" })).not.toBeInTheDocument();
  });

  it("starts the tour from the replay link (?tour=1)", async () => {
    giveElementsASize();
    mockApi({ ...SIGNED_IN, "GET /vehicles": () => ({ body: [] }), "GET /dashboard": () => ({ body: EMPTY_DASHBOARD }) });
    renderApp(<DashboardPage />, "/dashboard?tour=1");
    expect(await screen.findByRole("dialog", { name: "Your documents at a glance" })).toBeInTheDocument();
  });
});

// ------------------------------------------------------- adding the first document
describe("Documents: quick-start and the first-reminder confirmation", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-09T10:00:00Z"));
  });

  const documents = (extra: Parameters<typeof mockApi>[0] = {}) =>
    mockApi({
      ...SIGNED_IN,
      "GET /vehicles": () => ({ body: [] }),
      "GET /documents": () => ({ body: [] }),
      "GET /onboarding/progress": () => ({ body: NO_PROGRESS }),
      "PATCH /auth/me/onboarding": ({ body }) => ({ body: { ...USER, onboarding: body } }),
      ...extra,
    });

  it("opens the form already set up for the chosen kind of document", async () => {
    documents();
    renderApp(<DocumentsPage />, "/documents?new=insurance");
    const dialog = await screen.findByRole("dialog", { name: "Add a document" });
    expect(within(dialog).getByLabelText("Type")).toHaveValue("insurance");
    expect(within(dialog).getByLabelText("Name")).toHaveValue("Car insurance");
  });

  it("opens a blank form for ?new=1 and ignores unknown kinds", async () => {
    documents();
    renderApp(<DocumentsPage />, "/documents?new=nonsense");
    const dialog = await screen.findByRole("dialog", { name: "Add a document" });
    expect(within(dialog).getByLabelText("Name")).toHaveValue("");
  });

  it("offers the quick-start choices on the empty list", async () => {
    documents();
    renderApp(<DocumentsPage />, "/documents");
    expect(await screen.findByRole("link", { name: "Vehicle registration" })).toHaveAttribute("href", "/documents?new=vehicle_registration");
  });

  it("tells the user exactly when their first reminder email will arrive", async () => {
    documents({
      "POST /documents": ({ body }) => ({ status: 201, body: makeDoc({ ...(body as object), title: "Car insurance", expiry_date: "2026-10-31", reminder_offsets: [30, 14, 7, 1] }) }),
    });
    renderApp(<DocumentsPage />, "/documents?new=insurance");
    const dialog = await screen.findByRole("dialog", { name: "Add a document" });
    await userEvent.type(within(dialog).getByLabelText("Expiry date"), "2026-10-31");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add document" }));
    const notice = await screen.findByText(/is saved. We'll email you on 17 Oct 2026/);
    expect(notice).toHaveTextContent("14 days before expiry, around 8am (Africa/Lagos)");
    expect(screen.getByRole("link", { name: "Choose how you get reminders" })).toHaveAttribute("href", "/settings");
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText(/is saved/)).not.toBeInTheDocument();
  });
});

// ------------------------------------------------------------ settings: reviewed + replay
describe("Settings: the journey's last stop", () => {
  function Where() {
    const location = useLocation();
    return <p data-testid="where">{location.pathname + location.search}</p>;
  }

  const open = async (user = USER) => {
    const api = mockApi({
      ...SIGNED_IN,
      "GET /auth/me": () => ({ body: user }),
      "PATCH /auth/me/onboarding": ({ body }) => ({ body: { ...user, onboarding: { ...user.onboarding, ...(body as object) } } }),
    });
    renderApp(
      <Routes>
        <Route path="/dashboard" element={<Where />} />
        <Route element={<RequireAuth />}>
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Routes>,
      "/settings",
    );
    await screen.findByRole("heading", { name: "Settings" });
    return api;
  };

  it("marks the settings as reviewed on the first visit, and only once", async () => {
    const { calls } = await open();
    await waitFor(() => expect(patchBody(calls)).toEqual([{ settings_reviewed: true }]));
  });

  it("does not record it again for someone who has already reviewed them", async () => {
    const { calls } = await open({ ...USER, onboarding: { settings_reviewed: true } });
    await screen.findByText("Getting started");
    expect(patchBody(calls)).toEqual([]);
  });

  it("replays the tour on the dashboard", async () => {
    await open({ ...USER, onboarding: { settings_reviewed: true } });
    await userEvent.click(screen.getByRole("button", { name: "Take the tour again" }));
    expect(await screen.findByTestId("where")).toHaveTextContent("/dashboard?tour=1");
  });

  it("brings the checklist back", async () => {
    const { calls } = await open({ ...USER, onboarding: { settings_reviewed: true, checklist_dismissed: true } });
    await userEvent.click(screen.getByRole("button", { name: "Show the checklist" }));
    await waitFor(() => expect(patchBody(calls)).toEqual([{ checklist_dismissed: false }]));
    expect(await screen.findByTestId("where")).toHaveTextContent("/dashboard");
  });
});

describe("Sign-up page", () => {
  it("says what the user gets before asking for details", () => {
    mockApi({ "POST /auth/refresh": () => ({ status: 401, body: { detail: "Not authenticated", code: "unauthorized" } }) });
    renderApp(<RegisterPage />, "/register");
    expect(screen.getByText("Email reminders before your licence, insurance and permits expire")).toBeInTheDocument();
    expect(screen.getByText("Pick your own reminder days on a calendar")).toBeInTheDocument();
  });
});

// keep these imports referenced even if a test above is edited
void act;
void fireEvent;
