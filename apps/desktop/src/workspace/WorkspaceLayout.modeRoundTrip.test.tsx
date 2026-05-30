import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock the whole API surface WorkspaceLayout pulls in, so bootstrap resolves
// against a live-looking session and askStream just captures the request body.
// This is the regression guard for the Phase-2 bug where the co-pilot shipped a
// hardcoded mode="direct": it exercises the real toggle→state→request path, not
// the isolated client function.
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
    askStream: vi.fn(async (_body: unknown, handlers: { onDone?: () => void }) => {
      handlers.onDone?.();
    }),
    transcribeAudio: vi.fn(async () => ({ transcript: "" })),
  };
});

import * as api from "../api";
import { WorkspaceLayout } from "./WorkspaceLayout";

async function bootstrapAndAsk(question: string) {
  const user = userEvent.setup();
  render(<WorkspaceLayout onNavigateHome={() => {}} />);
  // Bootstrap is done once the restored cell's source textarea is on screen.
  await screen.findByLabelText("Cell 01 source");
  return { user, question };
}

async function sendQuestion(user: ReturnType<typeof userEvent.setup>, question: string) {
  const input = screen.getByRole("textbox", { name: "Ask the tutor a question" });
  await user.type(input, question);
  await user.click(screen.getByRole("button", { name: "Send message" }));
  await waitFor(() => expect(api.askStream).toHaveBeenCalled());
}

describe("co-pilot mode round-trip", () => {
  it("sends mode=socratic to /ai/ask after the user switches to Socratic", async () => {
    const { user, question } = await bootstrapAndAsk("what is a heap?");

    await user.click(screen.getByRole("tab", { name: "Socratic Mode" }));
    await sendQuestion(user, question);

    const askStream = vi.mocked(api.askStream);
    expect(askStream).toHaveBeenCalledTimes(1);
    const body = askStream.mock.calls[0][0] as { mode: string; question: string; session_id: string };
    expect(body.mode).toBe("socratic");
    expect(body.question).toBe(question);
    expect(body.session_id).toBe("s1");
  });

  it("sends mode=direct when the user never toggles", async () => {
    const { user, question } = await bootstrapAndAsk("hello");
    await sendQuestion(user, question);

    const askStream = vi.mocked(api.askStream);
    const body = askStream.mock.calls[0][0] as { mode: string };
    expect(body.mode).toBe("direct");
  });
});
