import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import { RequireAuth } from "../auth/RequireAuth";
import { mockApi, renderApp, SIGNED_IN, USER } from "../test/utils";
import { SettingsPage } from "./SettingsPage";

afterEach(() => vi.unstubAllGlobals());

// Renders the settings page for a signed-in user, with extra fake API routes.
async function open(routes: Parameters<typeof mockApi>[0] = {}) {
  const api = mockApi({ ...SIGNED_IN, ...routes });
  renderApp(
    <Routes>
      <Route element={<RequireAuth />}>
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
    </Routes>,
    "/settings",
  );
  await screen.findByRole("heading", { name: "Settings" });
  return api;
}

describe("SettingsPage", () => {
  it("shows the current settings and keeps Save disabled until something changes", async () => {
    await open();
    expect(screen.getByLabelText(/One email per document/)).toBeChecked();
    expect(screen.getByLabelText(/One daily summary/)).not.toBeChecked();
    expect(screen.getByLabelText("Full name")).toHaveValue("Ada Obi");
    expect(screen.getByLabelText("Email")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  });

  it("describes each choice so the user knows what they get", async () => {
    await open();
    expect(screen.getByText(/single email listing them, most urgent first/i)).toBeInTheDocument();
  });

  it("saves only what changed and confirms", async () => {
    const { calls } = await open({
      "PATCH /auth/me": ({ body }) => ({ body: { ...USER, ...(body as object) } }),
    });
    await userEvent.click(screen.getByLabelText(/One daily summary/));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(calls.find((c) => c.key === "PATCH /auth/me")?.body).toEqual({ reminder_style: "digest" });
    // Saved state becomes the new baseline, so there is nothing left to save.
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  });

  it("can change the name and timezone together", async () => {
    const { calls } = await open({
      "PATCH /auth/me": ({ body }) => ({ body: { ...USER, ...(body as object) } }),
    });
    const name = screen.getByLabelText("Full name");
    await userEvent.clear(name);
    await userEvent.type(name, "  Ada O.  ");
    await userEvent.selectOptions(screen.getByLabelText("Your timezone"), "Europe/London");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("Saved.");
    expect(calls.find((c) => c.key === "PATCH /auth/me")?.body).toEqual({ full_name: "Ada O.", timezone: "Europe/London" });
  });

  it("does not save an empty name", async () => {
    const { calls } = await open();
    await userEvent.clear(screen.getByLabelText("Full name"));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Tell us your name.")).toBeInTheDocument();
    expect(calls.some((c) => c.key === "PATCH /auth/me")).toBe(false);
  });

  it("shows the server's message when saving fails, and keeps the edits", async () => {
    await open({
      "PATCH /auth/me": () => ({ status: 500, body: { detail: "Internal server error", code: "internal_error", request_id: "r1" } }),
    });
    await userEvent.click(screen.getByLabelText(/One daily summary/));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side");
    expect(screen.getByLabelText(/One daily summary/)).toBeChecked();
    await waitFor(() => expect(screen.queryByText("Saved.")).not.toBeInTheDocument());
  });

  it("shows a field error from the server next to the timezone", async () => {
    await open({
      "PATCH /auth/me": () => ({
        status: 422,
        body: { detail: [{ loc: ["body", "timezone"], msg: "Value error, Unknown timezone." }], code: "validation_error" },
      }),
    });
    await userEvent.selectOptions(screen.getByLabelText("Your timezone"), "Europe/London");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Unknown timezone.")).toBeInTheDocument();
  });
});
