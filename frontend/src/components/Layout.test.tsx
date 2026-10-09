import { screen, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import { RequireAuth } from "../auth/RequireAuth";
import { mockApi, renderApp, SIGNED_IN } from "../test/utils";
import { Layout } from "./Layout";

afterEach(() => vi.unstubAllGlobals());

describe("Layout", () => {
  it("keeps the main navigation to four links so it fits a phone, with Settings beside Sign out", async () => {
    mockApi({ ...SIGNED_IN });
    renderApp(
      <Routes>
        <Route element={<RequireAuth />}>
          <Route element={<Layout />}>
            <Route path="/dashboard" element={<p>home</p>} />
          </Route>
        </Route>
      </Routes>,
      "/dashboard",
    );
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav).getAllByRole("link").map((a) => a.textContent)).toEqual(["Dashboard", "Documents", "Vehicles", "Reports"]);
    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute("href", "/settings");
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });
});
