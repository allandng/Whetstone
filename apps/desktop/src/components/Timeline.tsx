import { useEffect, useState } from "react";
import type { SessionTimeline, TimelineEvent } from "../api";
import { fetchTimeline } from "../api";

type Props = {
  sessionId: string;
};

const EVENT_LABELS: Record<string, string> = {
  cell_run: "CELL RUN",
  cell_result: "CELL RESULT",
  ai_exchange: "AI EXCHANGE",
  mode_switch: "MODE SWITCH",
  voice_note: "VOICE NOTE",
};

// Accent per event type, mirroring the workspace palette (emerald = run/done,
// sky = AI, amber = mode, zinc = neutral).
const EVENT_TONE: Record<string, string> = {
  cell_run: "text-zinc-300",
  cell_result: "text-emerald-400",
  ai_exchange: "text-sky-400",
  mode_switch: "text-amber-400",
  voice_note: "text-zinc-300",
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

// Short human-readable summary derived from an event's payload. Keys vary by
// event_type; fall back to a compact JSON dump for unknown shapes.
function summarize(event: TimelineEvent): string {
  const payload = event.payload ?? {};
  const str = (key: string): string | undefined =>
    typeof payload[key] === "string" ? (payload[key] as string) : undefined;

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
    default: {
      const keys = Object.keys(payload);
      return keys.length ? truncate(JSON.stringify(payload)) : "(no details)";
    }
  }
}

export function Timeline({ sessionId }: Props) {
  const [timeline, setTimeline] = useState<SessionTimeline | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [replay, setReplay] = useState(false);
  const [cursor, setCursor] = useState(0);

  useEffect(() => {
    if (!sessionId) {
      setTimeline(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchTimeline(sessionId)
      .then((data) => {
        if (cancelled) return;
        setTimeline(data);
        setCursor(0);
        setReplay(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setTimeline(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  if (!sessionId) {
    return <p className="p-4 text-[12px] text-zinc-500">Enter a session ID above to load its timeline.</p>;
  }
  if (loading) {
    return <p className="p-4 text-[12px] text-zinc-500">Loading timeline…</p>;
  }
  if (error) {
    return <p className="p-4 text-[12px] text-red-400">Could not load timeline: {error}</p>;
  }

  const events = timeline?.events ?? [];
  if (events.length === 0) {
    return <p className="p-4 text-[12px] text-zinc-500">No events recorded yet.</p>;
  }

  const groups = timeline?.groups ?? {};
  const safeCursor = Math.min(cursor, events.length - 1);
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
        <div className="p-4 space-y-3">
          <div className="flex items-center justify-between gap-3 font-mono text-[11px] text-zinc-400">
            <button
              type="button"
              className="h-6 px-2 rounded bg-zinc-900 border border-zinc-800 text-zinc-300 hover:text-zinc-100 disabled:opacity-40"
              onClick={() => setCursor((c) => Math.max(0, c - 1))}
              disabled={safeCursor === 0}
            >
              ‹ Prev
            </button>
            <span>
              Step {safeCursor + 1} of {events.length}
            </span>
            <button
              type="button"
              className="h-6 px-2 rounded bg-zinc-900 border border-zinc-800 text-zinc-300 hover:text-zinc-100 disabled:opacity-40"
              onClick={() => setCursor((c) => Math.min(events.length - 1, c + 1))}
              disabled={safeCursor === events.length - 1}
            >
              Next ›
            </button>
          </div>
          <EventRow event={current} />
        </div>
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

function EventRow({ event }: { event: TimelineEvent }) {
  return (
    <div className="rounded border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className={`font-mono text-[10px] uppercase tracking-wider font-semibold ${eventTone(event.event_type)}`}>
          {eventLabel(event.event_type)}
        </span>
        <time className="font-mono text-[10px] text-zinc-500">{formatTimestamp(event.timestamp)}</time>
      </div>
      <p className="text-[12px] text-zinc-300 leading-relaxed">{summarize(event)}</p>
    </div>
  );
}

export default Timeline;
