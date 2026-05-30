import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { CellRead, RequirementItemRead, SessionTimeline, TimelineEvent } from "../api";

// Timeline pulls its data over two GETs; stub them so the component test below
// drives a known event stream. The reconstructAt unit tests don't touch the API
// at all (it's pure), but the mock has to exist for the module to import.
const fetchTimeline = vi.fn<(id: string) => Promise<SessionTimeline>>();
const listSessionCells = vi.fn<(id: string) => Promise<CellRead[]>>();
vi.mock("../api", () => ({
  fetchTimeline: (id: string) => fetchTimeline(id),
  listSessionCells: (id: string) => listSessionCells(id),
}));

import Timeline, { reconstructAt } from "./Timeline";

let seq = 0;
function ev(event_type: string, payload: Record<string, unknown>): TimelineEvent {
  seq += 1;
  return {
    id: `e${seq}`,
    session_id: "s1",
    timestamp: "2026-01-01T00:00:00Z",
    event_type,
    payload,
  };
}

function cell(over: Partial<CellRead> = {}): CellRead {
  return {
    id: "c1",
    session_id: "s1",
    cell_type: "code",
    language: "python",
    content: "print(1)",
    last_output: null,
    status: "idle",
    order_index: 0,
    ...over,
  };
}

function req(over: Partial<RequirementItemRead> = {}): RequirementItemRead {
  return { id: "r1", spec_id: "sp1", text: "Implement X", status: "not_started", ...over };
}

// === reconstructAt: pure core ===============================================

describe("reconstructAt", () => {
  it("applies a cell_result only once the cursor reaches it", () => {
    const events = [
      ev("cell_run", { cell_id: "c1", code: "print(42)" }),
      ev("cell_result", { cell_id: "c1", status: "ok", output: "42" }),
    ];
    const baseline = [cell()];

    // Cursor on the run: content updated from the event, but no output yet.
    const atRun = reconstructAt(events, baseline, [], 0);
    expect(atRun.cells[0].content).toBe("print(42)");
    expect(atRun.cells[0].ranAt).toBe(false);
    expect(atRun.cells[0].output).toBeNull();

    // Cursor on the result: output and status now reflect the run.
    const atResult = reconstructAt(events, baseline, [], 1);
    expect(atResult.cells[0].ranAt).toBe(true);
    expect(atResult.cells[0].status).toBe("ok");
    expect(atResult.cells[0].output).toBe("42");
  });

  it("reveals AI exchanges progressively as the cursor advances", () => {
    const events = [
      ev("cell_run", { cell_id: "c1", code: "x" }),
      ev("ai_exchange", { kind: "ask", mode: "socratic", question: "why?", response: "because" }),
    ];
    expect(reconstructAt(events, [cell()], [], 0).exchanges).toHaveLength(0);
    const later = reconstructAt(events, [cell()], [], 1);
    expect(later.exchanges).toHaveLength(1);
    expect(later.exchanges[0]).toMatchObject({ mode: "socratic", question: "why?" });
  });

  it("derives a requirement's status from the last transition at-or-before the cursor", () => {
    const events = [
      ev("requirement_status", { requirement_id: "r1", from: "not_started", to: "in_progress" }),
      ev("requirement_status", { requirement_id: "r1", from: "in_progress", to: "done" }),
    ];
    const baseline = [req({ status: "done" })];
    expect(reconstructAt(events, [], baseline, 0).requirements[0].status).toBe("in_progress");
    expect(reconstructAt(events, [], baseline, 1).requirements[0].status).toBe("done");
  });

  it("falls back to the earliest pre-change state when all transitions are in the future", () => {
    const events = [
      ev("cell_run", { cell_id: "c1", code: "x" }),
      ev("requirement_status", { requirement_id: "r1", from: "not_started", to: "done" }),
    ];
    // Cursor 0 is before the only requirement event: show its pre-change `from`.
    const recon = reconstructAt(events, [], [req({ status: "done" })], 0);
    expect(recon.requirements[0].status).toBe("not_started");
  });

  it("keeps a requirement's baseline status when it never changed", () => {
    const events = [ev("cell_run", { cell_id: "c1", code: "x" })];
    const recon = reconstructAt(events, [], [req({ status: "in_progress" })], 0);
    expect(recon.requirements[0].status).toBe("in_progress");
  });

  it("surfaces a cell referenced by events but absent from the baseline as synthetic", () => {
    const events = [ev("cell_result", { cell_id: "ghost", status: "ok", output: "boo" })];
    const recon = reconstructAt(events, [cell()], [], 0);
    const ghost = recon.cells.find((c) => c.id === "ghost");
    expect(ghost).toBeDefined();
    expect(ghost?.synthetic).toBe(true);
  });

  it("does not mutate its inputs", () => {
    const events = [ev("cell_run", { cell_id: "c1", code: "mutated?" })];
    const baseline = [cell({ content: "original" })];
    reconstructAt(events, baseline, [], 0);
    // The baseline object is untouched; the reconstruction allocates its own.
    expect(baseline[0].content).toBe("original");
  });
});

// === Scrubber wiring: slider drives reconstructAt with the cursor ============

const REPLAY_EVENTS = () => {
  seq = 0;
  return [
    ev("cell_run", { cell_id: "c1", code: "print(1)" }),
    ev("cell_result", { cell_id: "c1", status: "ok", output: "OUT_42" }),
    ev("ai_exchange", { kind: "ask", mode: "socratic", question: "EXPLAIN_HEAPS", response: "r" }),
  ];
};

function mockTimeline() {
  const events = REPLAY_EVENTS();
  fetchTimeline.mockResolvedValue({
    session_id: "s1",
    events,
    groups: {
      cell_run: [events[0]],
      cell_result: [events[1]],
      ai_exchange: [events[2]],
    },
    requirements: [],
  });
  listSessionCells.mockResolvedValue([cell()]);
}

async function enterReplay() {
  render(<Timeline sessionId="s1" />);
  const replayBtn = await screen.findByRole("button", { name: "Replay" });
  fireEvent.click(replayBtn);
  // Replay opens at cursor 0.
  return screen.getByRole("slider", { name: "Scrub timeline" });
}

describe("Timeline replay scrubber", () => {
  it("reconstructs at the first event, then a later state when scrubbed to the end", async () => {
    mockTimeline();
    const slider = await enterReplay();

    // Cursor 0: the cell hasn't run and there are no exchanges yet.
    expect(screen.getByText("Step 1 of 3")).toBeInTheDocument();
    expect(screen.getByText("not run")).toBeInTheDocument();
    expect(screen.getByText("No AI exchanges yet at this point.")).toBeInTheDocument();

    // Drag the scrubber to the last event.
    fireEvent.change(slider, { target: { value: "2" } });

    // The reconstruction advanced: cell ran (no "not run") and the exchange shows.
    expect(screen.getByText("Step 3 of 3")).toBeInTheDocument();
    expect(screen.queryByText("not run")).toBeNull();
    expect(screen.queryByText("No AI exchanges yet at this point.")).toBeNull();
  });

  it("reconstructs exactly up to the scrubbed cursor (right-cursor wiring)", async () => {
    mockTimeline();
    const slider = await enterReplay();

    // Scrub to the middle event (cell_result), one before the ai_exchange.
    fireEvent.change(slider, { target: { value: "1" } });

    expect(screen.getByText("Step 2 of 3")).toBeInTheDocument();
    // cell_result at index 1 has been applied…
    expect(screen.queryByText("not run")).toBeNull();
    // …but the ai_exchange at index 2 has NOT — proving cursor=1, not 2.
    expect(screen.getByText("No AI exchanges yet at this point.")).toBeInTheDocument();
  });
});
