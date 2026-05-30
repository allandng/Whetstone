import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CoPilotPane } from "./CoPilotPane";
import type { AiMode } from "../types";

function renderPane(mode: AiMode) {
  const onModeChange = vi.fn();
  const onSend = vi.fn();
  render(
    <CoPilotPane
      mode={mode}
      onModeChange={onModeChange}
      thread={[]}
      busy={false}
      onSend={onSend}
      draft=""
      onDraftChange={vi.fn()}
    />,
  );
  return { onModeChange, onSend };
}

// Unit-level contract for the toggle. The full toggle→request path lives in
// WorkspaceLayout.modeRoundTrip.test.tsx; this just pins the tab's own output.
describe("CoPilotPane mode toggle", () => {
  it("asks for socratic when the Socratic tab is clicked from direct", async () => {
    const { onModeChange } = renderPane("direct");
    await userEvent.click(screen.getByRole("tab", { name: "Socratic Mode" }));
    expect(onModeChange).toHaveBeenCalledWith("socratic");
  });

  it("asks for direct when the Direct tab is clicked from socratic", async () => {
    const { onModeChange } = renderPane("socratic");
    await userEvent.click(screen.getByRole("tab", { name: "Direct Help" }));
    expect(onModeChange).toHaveBeenCalledWith("direct");
  });

  it("marks the active mode's tab as selected", () => {
    renderPane("socratic");
    expect(screen.getByRole("tab", { name: "Socratic Mode" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("tab", { name: "Direct Help" })).toHaveAttribute(
      "aria-selected",
      "false",
    );
  });
});
