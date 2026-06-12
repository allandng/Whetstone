// The Practice area: a beginner "Learn to Code" course and a DSA problem
// bank organized by interview pattern. Both halves can seed a workspace
// session (spec + checklist + starter cell) via the backend's start routes;
// the DSA half can also ask the local model for a fresh variant of any
// problem the user struggled on.

import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  generateSimilarProblem,
  listCourse,
  listProblems,
  startLesson,
  startProblem,
  updateLessonProgress,
  updateProblemStatus,
  type ApiError,
} from "../api";
import type {
  LessonRead,
  ProblemDifficulty,
  ProblemRead,
  ProblemStatus,
} from "../types";

type Props = {
  /** Open the given session in the Workspace view. */
  onOpenSession: (sessionId: string) => void;
};

type Tab = "learn" | "problems";

// --- Markdown-lite rendering -------------------------------------------------
// Lesson bodies and problem prompts are markdown-lite: ``` fences for code,
// **bold**, *italic*, and `inline code`. A real markdown library is overkill
// for content we author ourselves, so this renders just those forms.

function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*\n]+\*|`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return <code key={i}>{part.slice(1, -1)}</code>;
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <em key={i}>{part.slice(1, -1)}</em>;
    }
    return part;
  });
}

function RichText({ text }: { text: string }) {
  const segments = text.split("```");
  return (
    <div className="practice-richtext">
      {segments.map((segment, i) =>
        i % 2 === 1 ? (
          <pre key={i}>{segment.replace(/^[a-z+]*\n/, "")}</pre>
        ) : (
          <div key={i} className="practice-richtext__prose">
            {renderInline(segment)}
          </div>
        ),
      )}
    </div>
  );
}

// --- Shared bits ---------------------------------------------------------------

const DIFFICULTY_OPTIONS: ProblemDifficulty[] = ["easy", "medium", "hard"];

const STATUS_LABELS: Record<ProblemStatus, string> = {
  not_started: "not started",
  attempted: "attempted",
  struggled: "struggled",
  solved: "solved",
};

function errMessage(err: unknown): string {
  return (err as ApiError)?.message ?? String(err);
}

// --- Learn tab -------------------------------------------------------------------

function LearnTab({
  lessons,
  onToggleComplete,
  onStartExercise,
  starting,
}: {
  lessons: LessonRead[];
  onToggleComplete: (lesson: LessonRead) => void;
  onStartExercise: (lesson: LessonRead) => void;
  starting: boolean;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(
    lessons[0]?.id ?? null,
  );
  const selected = lessons.find((l) => l.id === selectedId) ?? lessons[0];
  const doneCount = lessons.filter((l) => l.completed).length;

  if (!selected) {
    return <p className="practice-empty">The course failed to load.</p>;
  }

  return (
    <div className="practice-split">
      <aside className="practice-list">
        <div className="practice-list__meter">
          {doneCount}/{lessons.length} lessons complete
        </div>
        {lessons.map((lesson, index) => (
          <button
            key={lesson.id}
            type="button"
            className={
              lesson.id === selected.id
                ? "practice-item is-selected"
                : "practice-item"
            }
            onClick={() => setSelectedId(lesson.id)}
          >
            <span className="practice-item__title">
              {lesson.completed ? "✓ " : ""}
              {index + 1}. {lesson.title}
            </span>
            <span className="practice-item__sub">{lesson.summary}</span>
          </button>
        ))}
      </aside>

      <article className="practice-detail">
        <h2>{selected.title}</h2>
        <RichText text={selected.body} />

        <div className="practice-exercise">
          <h3>Exercise</h3>
          <p>{selected.exercise.description}</p>
          <pre>{selected.exercise.starter_code}</pre>
        </div>

        <div className="practice-actions">
          <button
            type="button"
            disabled={starting}
            onClick={() => onStartExercise(selected)}
          >
            {starting ? "Opening…" : "Try it in the Workspace"}
          </button>
          <button type="button" onClick={() => onToggleComplete(selected)}>
            {selected.completed ? "Mark incomplete" : "Mark complete"}
          </button>
        </div>
      </article>
    </div>
  );
}

// --- Problems tab -------------------------------------------------------------------

function ProblemsTab({
  problems,
  onRefresh,
  onOpenSession,
}: {
  problems: ProblemRead[];
  onRefresh: () => Promise<void>;
  onOpenSession: (sessionId: string) => void;
}) {
  const [patternFilter, setPatternFilter] = useState("all");
  const [difficultyFilter, setDifficultyFilter] = useState("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Hints revealed so far, per problem, so flipping between problems doesn't
  // spoil hints the user hasn't asked for.
  const [revealed, setRevealed] = useState<Record<string, number>>({});
  const [note, setNote] = useState("");
  const [starting, setStarting] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const patterns = useMemo(() => {
    const seen = new Map<string, string>();
    problems.forEach((p) => seen.set(p.pattern, p.pattern_label));
    return [...seen.entries()];
  }, [problems]);

  const visible = problems.filter(
    (p) =>
      (patternFilter === "all" || p.pattern === patternFilter) &&
      (difficultyFilter === "all" || p.difficulty === difficultyFilter),
  );
  const selected =
    visible.find((p) => p.id === selectedId) ?? visible[0] ?? null;

  const parentOf = (problem: ProblemRead) =>
    problems.find((p) => p.id === problem.parent_problem_id);

  const shownHints = selected ? (revealed[selected.id] ?? 0) : 0;

  const setStatus = async (problem: ProblemRead, status: ProblemStatus) => {
    setError(null);
    try {
      await updateProblemStatus(problem.id, status);
      await onRefresh();
    } catch (err) {
      setError(`Status update failed: ${errMessage(err)}`);
    }
  };

  const practiceNow = async (problem: ProblemRead) => {
    setStarting(true);
    setError(null);
    try {
      const { session_id } = await startProblem(problem.id);
      onOpenSession(session_id);
    } catch (err) {
      setError(`Could not open the workspace: ${errMessage(err)}`);
    } finally {
      setStarting(false);
    }
  };

  const generate = async (problem: ProblemRead) => {
    setGenerating(true);
    setError(null);
    try {
      const variant = await generateSimilarProblem(problem.id, {
        note: note.trim() || null,
      });
      setNote("");
      await onRefresh();
      setPatternFilter("all");
      setDifficultyFilter("all");
      setSelectedId(variant.id);
    } catch (err) {
      const status = (err as ApiError)?.status;
      setError(
        status === 503
          ? "The local model is not running — start llama-server (make dev) and try again."
          : status === 502
            ? "The model's reply wasn't a usable problem — this happens with small models; try again."
            : `Generation failed: ${errMessage(err)}`,
      );
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div>
      <div className="practice-filters">
        <select
          aria-label="Filter by pattern"
          value={patternFilter}
          onChange={(e) => setPatternFilter(e.currentTarget.value)}
        >
          <option value="all">All patterns</option>
          {patterns.map(([slug, label]) => (
            <option key={slug} value={slug}>
              {label}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by difficulty"
          value={difficultyFilter}
          onChange={(e) => setDifficultyFilter(e.currentTarget.value)}
        >
          <option value="all">All difficulties</option>
          {DIFFICULTY_OPTIONS.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </div>

      {error && <p className="practice-error">{error}</p>}

      {visible.length === 0 ? (
        <p className="practice-empty">No problems match these filters.</p>
      ) : (
        <div className="practice-split">
          <aside className="practice-list">
            {visible.map((problem) => (
              <button
                key={problem.id}
                type="button"
                className={
                  selected && problem.id === selected.id
                    ? "practice-item is-selected"
                    : "practice-item"
                }
                onClick={() => setSelectedId(problem.id)}
              >
                <span className="practice-item__title">
                  {problem.status === "solved" ? "✓ " : ""}
                  {problem.title}
                  {problem.source === "generated" ? " ✦" : ""}
                </span>
                <span className="practice-item__sub">
                  {problem.pattern_label} · {problem.difficulty} ·{" "}
                  {STATUS_LABELS[problem.status]}
                </span>
              </button>
            ))}
          </aside>

          {selected && (
            <article className="practice-detail">
              <h2>{selected.title}</h2>
              <p className="practice-detail__meta">
                {selected.pattern_label} · {selected.difficulty}
                {selected.source === "generated" && (
                  <>
                    {" "}
                    · ✦ generated by your local model
                    {parentOf(selected) ? ` from “${parentOf(selected)!.title}”` : ""}
                  </>
                )}
              </p>

              <RichText text={selected.prompt} />

              {selected.examples.length > 0 && (
                <div className="practice-examples">
                  <h3>Examples</h3>
                  {selected.examples.map((example, i) => (
                    <div key={i} className="practice-example">
                      <pre>
                        {example.input}
                        {"\n→ "}
                        {example.output}
                      </pre>
                      {example.explanation && <p>{example.explanation}</p>}
                    </div>
                  ))}
                </div>
              )}

              {selected.hints.length > 0 && (
                <div className="practice-hints">
                  <h3>Hints</h3>
                  {selected.hints.slice(0, shownHints).map((hint, i) => (
                    <p key={i} className="practice-hint">
                      {i + 1}. {hint}
                    </p>
                  ))}
                  {shownHints < selected.hints.length && (
                    <button
                      type="button"
                      onClick={() =>
                        setRevealed((r) => ({
                          ...r,
                          [selected.id]: shownHints + 1,
                        }))
                      }
                    >
                      Show hint {shownHints + 1} of {selected.hints.length}
                    </button>
                  )}
                </div>
              )}

              <div className="practice-actions">
                <button
                  type="button"
                  disabled={starting}
                  onClick={() => practiceNow(selected)}
                >
                  {starting ? "Opening…" : "Practice in the Workspace"}
                </button>
                <button
                  type="button"
                  disabled={selected.status === "solved"}
                  onClick={() => setStatus(selected, "solved")}
                >
                  Mark solved
                </button>
                <button
                  type="button"
                  disabled={selected.status === "struggled"}
                  onClick={() => setStatus(selected, "struggled")}
                >
                  I struggled
                </button>
              </div>

              <div className="practice-generate">
                <h3>More like this</h3>
                <p>
                  Your local model writes a brand-new problem with the same{" "}
                  {selected.pattern_label.toLowerCase()} pattern — useful when
                  this one gave you trouble and you want to re-test the idea.
                </p>
                <input
                  value={note}
                  onChange={(e) => setNote(e.currentTarget.value)}
                  placeholder="What tripped you up? (optional — steers the variant)"
                  disabled={generating}
                />
                <button
                  type="button"
                  disabled={generating}
                  onClick={() => generate(selected)}
                >
                  {generating
                    ? "The local model is writing a new problem…"
                    : "Generate a similar problem"}
                </button>
              </div>
            </article>
          )}
        </div>
      )}
    </div>
  );
}

// --- The view ---------------------------------------------------------------------

export function PracticeView({ onOpenSession }: Props) {
  const [tab, setTab] = useState<Tab>("learn");
  const [lessons, setLessons] = useState<LessonRead[] | null>(null);
  const [problems, setProblems] = useState<ProblemRead[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [startingLesson, setStartingLesson] = useState(false);

  const refreshProblems = async () => {
    setProblems(await listProblems());
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [courseData, problemData] = await Promise.all([
          listCourse(),
          listProblems(),
        ]);
        if (cancelled) return;
        setLessons(courseData);
        setProblems(problemData);
      } catch (err) {
        if (!cancelled) {
          setLoadError(
            `Could not reach the backend (${errMessage(err)}). Start it with make dev and reload.`,
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const toggleLessonComplete = async (lesson: LessonRead) => {
    try {
      const updated = await updateLessonProgress(lesson.id, !lesson.completed);
      setLessons(
        (ls) => ls?.map((l) => (l.id === updated.id ? updated : l)) ?? null,
      );
    } catch {
      // Leave the lesson as-is; the next reload shows the true state.
    }
  };

  const startLessonExercise = async (lesson: LessonRead) => {
    setStartingLesson(true);
    try {
      const { session_id } = await startLesson(lesson.id);
      onOpenSession(session_id);
    } catch (err) {
      setLoadError(`Could not open the workspace: ${errMessage(err)}`);
    } finally {
      setStartingLesson(false);
    }
  };

  return (
    <div className="practice">
      <h1>Practice</h1>
      <div className="practice-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "learn"}
          className={tab === "learn" ? "practice-tab is-active" : "practice-tab"}
          onClick={() => setTab("learn")}
        >
          Learn to Code
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "problems"}
          className={
            tab === "problems" ? "practice-tab is-active" : "practice-tab"
          }
          onClick={() => setTab("problems")}
        >
          DSA Problems
        </button>
      </div>

      {loadError ? (
        <p className="practice-error">{loadError}</p>
      ) : tab === "learn" ? (
        lessons === null ? (
          <p className="practice-empty">Loading the course…</p>
        ) : (
          <LearnTab
            lessons={lessons}
            onToggleComplete={toggleLessonComplete}
            onStartExercise={startLessonExercise}
            starting={startingLesson}
          />
        )
      ) : problems === null ? (
        <p className="practice-empty">Loading the problem bank…</p>
      ) : (
        <ProblemsTab
          problems={problems}
          onRefresh={refreshProblems}
          onOpenSession={onOpenSession}
        />
      )}
    </div>
  );
}

export default PracticeView;
