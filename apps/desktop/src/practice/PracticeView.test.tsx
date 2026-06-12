import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Contract tests for the Practice view: the course tab tracks progress, the
// problems tab reveals hints gradually, and both hand sessions to the
// workspace via the start routes. The api module is mocked wholesale — these
// pin the view's behavior, not the HTTP layer (api.test.ts covers that).

const lesson = (id: string, title: string, completed = false) => ({
  id,
  title,
  summary: `${title} summary`,
  body: `Some prose with **bold** and a fence:\n\n\`\`\`python\nprint(1)\n\`\`\`\n\nMore prose.`,
  exercise: {
    description: `${title} exercise`,
    starter_code: "print('try me')",
    language: "python",
  },
  completed,
});

const problem = (overrides: Record<string, unknown> = {}) => ({
  id: "p1",
  slug: "festival-wristbands",
  title: "Festival Wristbands",
  pattern: "arrays-hashing",
  pattern_label: "Arrays & Hashing",
  difficulty: "easy",
  prompt: "Find the first repeated ID.",
  examples: [{ input: "ids = [1, 2, 1]", output: "1", explanation: "1 repeats." }],
  hints: ["Nudge.", "Bigger hint.", "Near-spoiler."],
  starter_code: "def f(ids):\n    return -1\n",
  language: "python",
  source: "builtin",
  parent_problem_id: null,
  status: "not_started",
  created_at: "2026-06-01T00:00:00Z",
  ...overrides,
});

vi.mock("../api", () => ({
  listCourse: vi.fn(),
  listProblems: vi.fn(),
  updateLessonProgress: vi.fn(),
  updateProblemStatus: vi.fn(),
  startLesson: vi.fn(),
  startProblem: vi.fn(),
  generateSimilarProblem: vi.fn(),
}));

import * as api from "../api";
import { PracticeView } from "./PracticeView";

const mocked = vi.mocked(api);

beforeEach(() => {
  vi.clearAllMocks();
  mocked.listCourse.mockResolvedValue([
    lesson("01-a", "Values and variables"),
    lesson("02-b", "Loops"),
  ]);
  mocked.listProblems.mockResolvedValue([
    problem(),
    problem({
      id: "p2",
      slug: "warmer-days",
      title: "Warmer Days Ahead",
      pattern: "stack",
      pattern_label: "Stack",
      difficulty: "medium",
    }),
  ]);
});

describe("PracticeView — Learn tab", () => {
  it("lists lessons and marks one complete", async () => {
    mocked.updateLessonProgress.mockResolvedValue(
      lesson("01-a", "Values and variables", true),
    );
    render(<PracticeView onOpenSession={vi.fn()} />);

    expect(
      await screen.findByText(/1\. Values and variables/),
    ).toBeInTheDocument();
    expect(screen.getByText("0/2 lessons complete")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Mark complete" }));
    expect(mocked.updateLessonProgress).toHaveBeenCalledWith("01-a", true);
    expect(await screen.findByText("1/2 lessons complete")).toBeInTheDocument();
  });

  it("opens a lesson exercise in the workspace", async () => {
    mocked.startLesson.mockResolvedValue({ session_id: "sess-9", spec_id: "spec-9" });
    const onOpenSession = vi.fn();
    render(<PracticeView onOpenSession={onOpenSession} />);

    await userEvent.click(
      await screen.findByRole("button", { name: "Try it in the Workspace" }),
    );
    await waitFor(() => expect(onOpenSession).toHaveBeenCalledWith("sess-9"));
    expect(mocked.startLesson).toHaveBeenCalledWith("01-a");
  });
});

describe("PracticeView — DSA Problems tab", () => {
  const openProblemsTab = async () => {
    render(<PracticeView onOpenSession={vi.fn()} />);
    await userEvent.click(
      await screen.findByRole("tab", { name: "DSA Problems" }),
    );
  };

  it("shows the bank and reveals hints one at a time", async () => {
    await openProblemsTab();

    expect(await screen.findByRole("heading", { name: "Festival Wristbands" })).toBeInTheDocument();
    expect(screen.queryByText(/Nudge\./)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Show hint 1 of 3" }));
    expect(screen.getByText(/Nudge\./)).toBeInTheDocument();
    expect(screen.queryByText(/Bigger hint\./)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Show hint 2 of 3" }));
    expect(screen.getByText(/Bigger hint\./)).toBeInTheDocument();
  });

  it("starts a practice session and hands it to the workspace", async () => {
    mocked.startProblem.mockResolvedValue({ session_id: "sess-1", spec_id: "spec-1" });
    const onOpenSession = vi.fn();
    render(<PracticeView onOpenSession={onOpenSession} />);
    await userEvent.click(await screen.findByRole("tab", { name: "DSA Problems" }));

    await userEvent.click(
      await screen.findByRole("button", { name: "Practice in the Workspace" }),
    );
    await waitFor(() => expect(onOpenSession).toHaveBeenCalledWith("sess-1"));
    expect(mocked.startProblem).toHaveBeenCalledWith("p1");
  });

  it("generates a similar problem with the user's note and selects it", async () => {
    const variant = problem({
      id: "p3",
      slug: "festival-wristbands-variant-abc",
      title: "Conveyor Belt Duplicates",
      source: "generated",
      parent_problem_id: "p1",
    });
    mocked.generateSimilarProblem.mockResolvedValue(variant);
    mocked.listProblems
      .mockResolvedValueOnce([problem(), problem({ id: "p2", title: "Other", pattern_label: "Stack" })])
      .mockResolvedValue([problem(), problem({ id: "p2", title: "Other", pattern_label: "Stack" }), variant]);

    await openProblemsTab();
    await screen.findByRole("heading", { name: "Festival Wristbands" });

    await userEvent.type(
      screen.getByPlaceholderText(/What tripped you up/),
      "forgot the set",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Generate a similar problem" }),
    );

    expect(
      await screen.findByRole("heading", { name: "Conveyor Belt Duplicates" }),
    ).toBeInTheDocument();
    expect(mocked.generateSimilarProblem).toHaveBeenCalledWith("p1", {
      note: "forgot the set",
    });
    expect(screen.getByText(/generated by your local model/)).toBeInTheDocument();
  });

  it("explains a 503 as the local model being down", async () => {
    const err = Object.assign(new Error("503"), { status: 503 });
    mocked.generateSimilarProblem.mockRejectedValue(err);
    await openProblemsTab();
    await screen.findByRole("heading", { name: "Festival Wristbands" });

    await userEvent.click(
      screen.getByRole("button", { name: "Generate a similar problem" }),
    );
    expect(
      await screen.findByText(/local model is not running/),
    ).toBeInTheDocument();
  });
});
