// Registers jest-dom's matchers (toBeInTheDocument, toBeDisabled, …) on
// Vitest's expect, and clears the DOM + mocks between tests so suites can't
// bleed state into one another.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Call history is cleared by the runner (clearMocks in vitest.config.ts). Here
// we just unmount React trees and drop any stubbed globals (e.g. fetch).
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
