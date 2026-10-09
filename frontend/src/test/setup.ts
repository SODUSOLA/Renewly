import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import { tokenStore } from "../api/client";

// Unmount rendered components and forget any in-memory token between tests.
afterEach(() => {
  cleanup();
  tokenStore.clear();
});
