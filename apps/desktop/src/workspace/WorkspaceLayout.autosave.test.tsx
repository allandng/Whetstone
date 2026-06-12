import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Integration guard for the data-loss fix: editing a cell must persist to the
// backend on its own (debounced PUT), not only when the cell is Run. Renders the
// real WorkspaceLayout against a mocked api and asserts updateCell is called with
// the edited content after the autosave debounce.
vi.mock("../api", () => {
  const session = {
    id: "s1",
    title: "Test Session",
    created_at: "2026-01-01T00:00:00Z",
    modified_at: "2026-01-01T00:00:00Z",
    spec_id: null,
  };
  const cell = {
    id: "c1",
    session_id: "s1",
    cell_type: "code",
    language: "python",
    content: "print(1)",
    last_output: null,
    status: "idle",
    order_index: 0,
  };
  return {
    API_BASE: "http://127.0.0.1:8000",
    listSessions: vi.fn(async () => [session]),
    createSession: vi.fn(async () => session),
    listSessionCells: vi.fn(async () => [cell]),
    createCell: vi.fn(async () => cell),
    listRequirements: vi.fn(async () => []),
    runCell: vi.fn(async () => cell),
    updateCell: vi.fn(async () => cell),
    updateRequirement: vi.fn(async () => ({})),
    askStream: vi.fn(),
    transcribeAudio: vi.fn(async () => ({ transcript: "" })),
  };
});

import * as api from "../api";
import { WorkspaceLayout } from "./WorkspaceLayout";

describe("cell autosave (data-loss fix)", () => {
  it("PUTs the edited content after the debounce, without running the cell", async () => {
    const user = userEvent.setup();
    render(<WorkspaceLayout onNavigateHome={() => {}} />);

    const textarea = await screen.findByLabelText("Cell 01 source");
    await user.type(textarea, "  # edited");

    // Autosave fires on its own (debounced), not via Run.
    await waitFor(
      () => expect(vi.mocked(api.updateCell)).toHaveBeenCalled(),
      { timeout: 2500 },
    );
    const calls = vi.mocked(api.updateCell).mock.calls;
    const [cellId, body] = calls[calls.length - 1] as [string, { content?: string }];
    expect(cellId).toBe("c1");
    expect(body.content).toContain("# edited");
    // The run path was never taken.
    expect(vi.mocked(api.runCell)).not.toHaveBeenCalled();
  });
});
