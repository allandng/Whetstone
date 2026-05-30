import { useEffect, useMemo, useState } from "react";
import type {
  CellRead,
  RequirementItemRead,
  RequirementStatus,
  SessionTimeline,
  TimelineEvent,
} from "../api";
import { fetchTimeline, listSessionCells } from "../api";

type Props = {
  sessionId: string;
};

const EVENT_LABELS: Record<string, string> = {
  cell_run: "CELL RUN",
  cell_result: "CELL RESULT",
  ai_exchange: "AI EXCHANGE",
  mode_switch: "MODE SWITCH",
  voice_note: "VOICE NOTE",
  requirement_status: "REQUIREMENT",
};

// Accent per event type, mirroring the workspace palette (emerald = run/done,
// sky = AI, amber = mode, violet = requirement, zinc = neutral).
const EVENT_TONE: Record<string, string> = {
  cell_run: "text-zinc-300",
  cell_result: "text-emerald-400",
  ai_exchange: "text-sky-400",
  mode_switch: "text-amber-400",
  voice_note: "text-zinc-300",
  requirement_status: "text-violet-400",
};

function eventLabel(type: string): string {
  return EVENT_LABELS[type] ?? type.replace(/_/g, " ").toUpperCase();
}

function eventTone(type: string): string {
  return EVENT_TONE[type] ?? "text-zinc-400";
}

function formatTimestamp(ts: string): string {
  const date = new Date(ts);
  return Number.isNaN(date.getTime()) ? ts : date.toLocaleTimeString();
}

function truncate(value: string, max = 140): string {
  return value.length > max ? `${value.slice(0, max)}…` : value;
}

function payloadStr(payload: Record<string, unknown>, key: string): string | undefined {
  return typeof payload[key] === "string" ? (payload[key] as string) : undefined;
}

// Short human-readable summary derived from an event's payload. Keys vary by
// event_type; fall back to a compact JSON dump for unknown shapes.
function summarize(event: TimelineEvent): string {
  const payload = event.payload ?? {};
  const str = (key: string) => payloadStr(payload, key);

  switch (event.event_type) {
    case "ai_exchange": {
      const kind = str("kind") ?? "ask";
      const question = str("question");
      return question ? `${kind}: ${truncate(question)}` : kind;
    }
    case "cell_run": {
      const code = str("code") ?? str("content");
      return code ? `Ran cell: ${truncate(code, 100)}` : "Ran a cell";
    }
    case "cell_result": {
      const status = str("status");
      const output = str("output") ?? str("error");
      const parts = [
        status ? `status=${status}` : undefined,
        output ? truncate(output, 100) : undefined,
      ].filter(Boolean);
      return parts.length ? parts.join(" — ") : "Cell result";
    }
    case "mode_switch": {
      const from = str("from");
      const to = str("to");
      return from && to ? `${from} → ${to}` : "Mode switched";
    }
    case "voice_note": {
      const text = str("text") ?? str("transcript");
      return text ? truncate(text) : "Voice note";
    }
    case "requirement_status": {
      const text = str("text");
      const from = str("from");
      const to = str("to");
      const transition = from && to ? `${from} → ${to}` : to ?? "updated";
      return text ? `${truncate(text, 90)} · ${transition}` : transition;
    }
    default: {
      const keys = Object.keys(payload);
      return keys.length ? truncate(JSON.stringify(payload)) : "(no details)";
    }
  }
}

// === Read-only state reconstruction =========================================
//
// reconstructAt is a PURE function of the fetched timeline + cells baseline. It
// allocates fresh view-model objects and never mutates its inputs, never calls
// the API, and never touches the live workspace (which lives in
// WorkspaceLayout and is not passed here). That is the whole read-only
// guarantee for replay: there is simply no write path reachable from this view.

type ReconCell = {
  id: string;
  language: string;
  content: string;
  output: string | null;
  status: string; // "" = not run at this point
  ranAt: boolean;
  synthetic: boolean; // referenced by an event but absent from the live list
};

type ReconRequirement = {
  id: string;
  text: string;
  status: RequirementStatus;
};

type ReconExchange = {
  id: string;
  kind: string;
  mode: string;
  question: string;
  response: string;
};

type Reconstruction = {
  cells: ReconCell[];
  requirements: ReconRequirement[];
  exchanges: ReconExchange[];
};

const STATUS_VALUES: RequirementStatus[] = ["not_started", "in_progress", "done"];

function asStatus(value: string | undefined): RequirementStatus | undefined {
  return value && (STATUS_VALUES as string[]).includes(value)
    ? (value as RequirementStatus)
    : undefined;
}

// Reconstruct the workspace as it stood right after events[0..cursor].
// Exported for unit testing: it is the pure core of timeline replay.
export function reconstructAt(
  events: TimelineEvent[],
  baselineCells: CellRead[],
  baselineRequirements: RequirementItemRead[],
  cursor: number,
): Reconstruction {
  const upTo = events.slice(0, cursor + 1);

  // --- Cells: start from the live identities/order, then replay runs/results.
  // A cell's content at a past point is only knowable from a cell_run's `code`;
  // with no edit events we fall back to the baseline (current) content.
  const cellOrder: string[] = [];
  const cellMap = new Map<string, ReconCell>();
  for (const cell of baselineCells) {
    cellOrder.push(cell.id);
    cellMap.set(cell.id, {
      id: cell.id,
      language: cell.language ?? "python",
      content: cell.content,
      output: null,
      status: "",
      ranAt: false,
      synthetic: false,
    });
  }
  const ensureCell = (id: string): ReconCell => {
    let cell = cellMap.get(id);
    if (!cell) {
      cell = {
        id,
        language: "?",
        content: "",
        output: null,
        status: "",
        ranAt: false,
        synthetic: true,
      };
      cellMap.set(id, cell);
      cellOrder.push(id);
    }
    return cell;
  };

  for (const event of upTo) {
    const id = payloadStr(event.payload, "cell_id");
    if (!id) continue;
    if (event.event_type === "cell_run") {
      const cell = ensureCell(id);
      const code = payloadStr(event.payload, "code");
      if (code !== undefined) cell.content = code;
    } else if (event.event_type === "cell_result") {
      const cell = ensureCell(id);
      cell.output = payloadStr(event.payload, "output") ?? null;
      cell.status = payloadStr(event.payload, "status") ?? cell.status;
      cell.ranAt = true;
    }
  }

  // --- Requirements: status at the cursor = the last `to` at-or-before it; if
  // the only transitions are later, use the earliest `from` (pre-change state);
  // if a requirement never changed at all, keep its baseline status.
  const latestTo = new Map<string, RequirementStatus>();
  const firstFrom = new Map<string, RequirementStatus>();
  events.forEach((event, index) => {
    if (event.event_type !== "requirement_status") return;
    const rid = payloadStr(event.payload, "requirement_id");
    if (!rid) return;
    if (!firstFrom.has(rid)) {
      const from = asStatus(payloadStr(event.payload, "from"));
      if (from) firstFrom.set(rid, from);
    }
    if (index <= cursor) {
      const to = asStatus(payloadStr(event.payload, "to"));
      if (to) latestTo.set(rid, to);
    }
  });
  const requirements: ReconRequirement[] = baselineRequirements.map((req) => ({
    id: req.id,
    text: req.text,
    status: latestTo.get(req.id) ?? firstFrom.get(req.id) ?? req.status,
  }));

  // --- AI exchanges as the thread stood at the cursor.
  const exchanges: ReconExchange[] = upTo
    .filter((event) => event.event_type === "ai_exchange")
    .map((event) => ({
      id: event.id,
      kind: payloadStr(event.payload, "kind") ?? "ask",
      mode: payloadStr(event.payload, "mode") ?? "direct",
      question: payloadStr(event.payload, "question") ?? "",
      response: payloadStr(event.payload, "response") ?? "",
    }));

  return {
    cells: cellOrder.map((id) => cellMap.get(id)!),
    requirements,
    exchanges,
  };
}

const REQ_STATUS_TONE: Record<RequirementStatus, string> = {
  not_started: "text-zinc-500",
  in_progress: "text-amber-400",
  done: "text-emerald-400",
};

function statusTone(status: string): string {
  if (status === "ok" || status === "done") return "text-emerald-400";
  if (status === "error" || status === "terminated") return "text-red-400";
  if (status === "timeout") return "text-amber-400";
  return "text-zinc-400";
}

export function Timeline({ sessionId }: Props) {
  const [timeline, setTimeline] = useState<SessionTimeline | null>(null);
  const [cells, setCells] = useState<CellRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [replay, setReplay] = useState(false);
  const [cursor, setCursor] = useState(0);

  useEffect(() => {
    if (!sessionId) {
      setTimeline(null);
      setCells([]);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        // Both are GETs. The cells baseline is best-effort: if it fails we can
        // still render the event stream and reconstruct requirements/exchanges.
        const [tl, cs] = await Promise.all([
          fetchTimeline(sessionId),
          listSessionCells(sessionId).catch(() => [] as CellRead[]),
        ]);
        if (cancelled) return;
        setTimeline(tl);
        setCells(cs);
        setCursor(0);
        setReplay(false);
      } catch (err: unknown) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setTimeline(null);
        setCells([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const events = timeline?.events ?? [];
  const safeCursor = events.length ? Math.min(cursor, events.length - 1) : 0;

  // Recomputed only when the inputs or the cursor change; pure and side-effect
  // free (see reconstructAt). Never written back anywhere.
  const reconstruction = useMemo(
    () =>
      reconstructAt(events, cells, timeline?.requirements ?? [], safeCursor),
    [events, cells, timeline?.requirements, safeCursor],
  );

  if (!sessionId) {
    return <p className="p-4 text-[12px] text-zinc-500">Enter a session ID above to load its timeline.</p>;
  }
  if (loading) {
    return <p className="p-4 text-[12px] text-zinc-500">Loading timeline…</p>;
  }
  if (error) {
    return <p className="p-4 text-[12px] text-red-400">Could not load timeline: {error}</p>;
  }

  if (events.length === 0) {
    return <p className="p-4 text-[12px] text-zinc-500">No events recorded yet.</p>;
  }

  const groups = timeline?.groups ?? {};
  const current = events[safeCursor];

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between gap-3 px-4 py-2 border-b border-zinc-900">
        <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-wider">
          {Object.entries(groups).map(([type, items]) => (
            <span
              key={type}
              className={`px-1.5 py-0.5 rounded border border-zinc-800 bg-zinc-900/60 font-semibold ${eventTone(type)}`}
            >
              {eventLabel(type)} · {items.length}
            </span>
          ))}
        </div>
        <button
          type="button"
          className="shrink-0 h-6 px-2 rounded bg-zinc-900 border border-zinc-800 text-[10.5px] font-medium text-zinc-300 hover:text-zinc-100 hover:border-zinc-700 transition-colors duration-150"
          onClick={() => {
            setReplay((on) => !on);
            setCursor(0);
          }}
        >
          {replay ? "Exit replay" : "Replay"}
        </button>
      </div>

      {replay ? (
        <ReplayView
          events={events}
          cursor={safeCursor}
          current={current}
          reconstruction={reconstruction}
          onScrub={setCursor}
        />
      ) : (
        <table className="w-full text-left border-collapse font-mono text-[12px]">
          <thead>
            <tr className="border-b border-zinc-900 text-[10px] text-zinc-500 uppercase tracking-wider">
              <th scope="col" className="p-3 w-24 font-semibold">
                Time
              </th>
              <th scope="col" className="p-3 w-40 font-semibold">
                Event
              </th>
              <th scope="col" className="p-3 font-semibold">
                Detail
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-900/60 text-zinc-400">
            {events.map((event) => (
              <tr key={event.id} className="hover:bg-zinc-900/30">
                <td className="p-3 text-zinc-500 align-top">{formatTimestamp(event.timestamp)}</td>
                <td className={`p-3 font-medium align-top ${eventTone(event.event_type)}`}>
                  {eventLabel(event.event_type)}
                </td>
                <td className="p-3 text-zinc-300 align-top">{summarize(event)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

type ReplayViewProps = {
  events: TimelineEvent[];
  cursor: number;
  current: TimelineEvent;
  reconstruction: Reconstruction;
  onScrub: (cursor: number) => void;
};

function ReplayView({ events, cursor, current, reconstruction, onScrub }: ReplayViewProps) {
  const atStart = cursor === 0;
  const atEnd = cursor === events.length - 1;

  return (
    <div className="flex-1 min-h-0 overflow-y-auto">
      <div className="sticky top-0 z-10 bg-zinc-950 border-b border-zinc-900 px-4 py-2 space-y-2">
        <div className="flex items-center gap-3">
          <button
            type="button"
            className="h-6 px-2 rounded bg-zinc-900 border border-zinc-800 font-mono text-[11px] text-zinc-300 hover:text-zinc-100 disabled:opacity-40"
            onClick={() => onScrub(Math.max(0, cursor - 1))}
            disabled={atStart}
          >
            ‹ Prev
          </button>
          <input
            type="range"
            min={0}
            max={events.length - 1}
            value={cursor}
            onChange={(e) => onScrub(Number(e.target.value))}
            aria-label="Scrub timeline"
            className="flex-1 accent-sky-500"
          />
          <button
            type="button"
            className="h-6 px-2 rounded bg-zinc-900 border border-zinc-800 font-mono text-[11px] text-zinc-300 hover:text-zinc-100 disabled:opacity-40"
            onClick={() => onScrub(Math.min(events.length - 1, cursor + 1))}
            disabled={atEnd}
          >
            Next ›
          </button>
        </div>
        <div className="flex items-center justify-between gap-3 font-mono text-[10px]">
          <span className="text-zinc-400">
            Step {cursor + 1} of {events.length}
          </span>
          <span className={`uppercase tracking-wider font-semibold ${eventTone(current.event_type)}`}>
            {eventLabel(current.event_type)} · {formatTimestamp(current.timestamp)}
          </span>
        </div>
        <p className="text-[11px] text-zinc-400 leading-snug">{summarize(current)}</p>
      </div>

      <div className="p-3 space-y-3">
        <p className="text-[10px] text-zinc-600 italic">
          Reconstructed view of this session as it stood at the selected event. Read-only — your live
          workspace is untouched.
        </p>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <ReqColumn requirements={reconstruction.requirements} />
          <CellColumn cells={reconstruction.cells} />
          <ExchangeColumn exchanges={reconstruction.exchanges} />
        </div>
      </div>
    </div>
  );
}

function Column({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <section className="rounded border border-zinc-900 bg-zinc-900/20 flex flex-col min-h-0">
      <div className="h-7 px-2.5 flex items-center justify-between border-b border-zinc-900">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400">{title}</span>
        <span className="font-mono text-[10px] text-zinc-600">{count}</span>
      </div>
      <div className="p-2 space-y-2">{children}</div>
    </section>
  );
}

function ReqColumn({ requirements }: { requirements: ReconRequirement[] }) {
  const done = requirements.filter((r) => r.status === "done").length;
  return (
    <Column title={`Requirements ${requirements.length ? `· ${done}/${requirements.length}` : ""}`} count={requirements.length}>
      {requirements.length === 0 ? (
        <p className="text-[11px] text-zinc-600 italic">No checklist for this session.</p>
      ) : (
        requirements.map((req) => (
          <div key={req.id} className="flex items-start gap-2">
            <span className={`mt-0.5 font-mono text-[9px] uppercase font-semibold tracking-wider ${REQ_STATUS_TONE[req.status]}`}>
              {req.status.replace("_", " ")}
            </span>
            <p className="text-[11px] text-zinc-300 leading-snug">{truncate(req.text, 120)}</p>
          </div>
        ))
      )}
    </Column>
  );
}

function CellColumn({ cells }: { cells: ReconCell[] }) {
  return (
    <Column title="Cells" count={cells.length}>
      {cells.length === 0 ? (
        <p className="text-[11px] text-zinc-600 italic">No cells.</p>
      ) : (
        cells.map((cell, index) => (
          <div key={cell.id} className="rounded border border-zinc-900 bg-zinc-950 overflow-hidden">
            <div className="h-6 px-2 flex items-center justify-between bg-zinc-900/40 border-b border-zinc-900">
              <span className="font-mono text-[9px] uppercase tracking-wider font-semibold text-zinc-500">
                {`Cell ${String(index + 1).padStart(2, "0")}`} · {cell.language}
                {cell.synthetic ? " · removed" : ""}
              </span>
              <span className={`font-mono text-[9px] uppercase font-semibold ${statusTone(cell.status)}`}>
                {cell.ranAt ? cell.status || "ok" : "not run"}
              </span>
            </div>
            <pre className="px-2 py-1.5 m-0 font-mono text-[10.5px] text-zinc-400 whitespace-pre-wrap max-h-24 overflow-hidden">
              {truncate(cell.content, 320) || "(empty)"}
            </pre>
            {cell.ranAt && cell.output != null && cell.output.length > 0 && (
              <pre className="px-2 py-1.5 m-0 border-t border-zinc-900 font-mono text-[10.5px] text-zinc-200 whitespace-pre-wrap max-h-24 overflow-hidden bg-black/30">
                {truncate(cell.output, 320)}
              </pre>
            )}
          </div>
        ))
      )}
    </Column>
  );
}

function ExchangeColumn({ exchanges }: { exchanges: ReconExchange[] }) {
  return (
    <Column title="AI exchanges" count={exchanges.length}>
      {exchanges.length === 0 ? (
        <p className="text-[11px] text-zinc-600 italic">No AI exchanges yet at this point.</p>
      ) : (
        exchanges.map((ex) => (
          <div key={ex.id} className="rounded border border-zinc-900 bg-zinc-950 p-2 space-y-1">
            <div className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-wider">
              <span className="text-sky-400 font-semibold">{ex.kind}</span>
              <span className="text-zinc-600">{ex.mode}</span>
            </div>
            {ex.question && <p className="text-[11px] text-zinc-300 leading-snug">{truncate(ex.question, 160)}</p>}
            {ex.response && <p className="text-[11px] text-zinc-500 leading-snug">{truncate(ex.response, 200)}</p>}
          </div>
        ))
      )}
    </Column>
  );
}

export default Timeline;
