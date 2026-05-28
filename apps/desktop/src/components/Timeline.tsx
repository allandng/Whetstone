import { useEffect, useState } from "react";
import type { SessionTimeline, TimelineEvent } from "../api";
import { fetchTimeline } from "../api";
import "./Timeline.css";

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

function eventLabel(type: string): string {
  return EVENT_LABELS[type] ?? type.replace(/_/g, " ").toUpperCase();
}

function eventClass(type: string): string {
  return `badge badge--${type.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`;
}

function formatTimestamp(ts: string): string {
  const date = new Date(ts);
  return Number.isNaN(date.getTime()) ? ts : date.toLocaleString();
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

function EventCard({ event }: { event: TimelineEvent }) {
  return (
    <div className="event-card">
      <div className="event-card__head">
        <span className={eventClass(event.event_type)}>
          {eventLabel(event.event_type)}
        </span>
        <time className="event-card__time">
          {formatTimestamp(event.timestamp)}
        </time>
      </div>
      <p className="event-card__summary">{summarize(event)}</p>
    </div>
  );
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
    return (
      <p className="timeline__hint">
        Enter a session ID above to load its timeline.
      </p>
    );
  }
  if (loading) {
    return <p className="timeline__hint">Loading timeline…</p>;
  }
  if (error) {
    return <p className="timeline__error">Could not load timeline: {error}</p>;
  }

  const events = timeline?.events ?? [];
  if (events.length === 0) {
    return <p className="timeline__hint">No events recorded yet.</p>;
  }

  const groups = timeline?.groups ?? {};
  const safeCursor = Math.min(cursor, events.length - 1);
  const current = events[safeCursor];

  return (
    <div className="timeline">
      <div className="timeline__toolbar">
        <div className="timeline__counts">
          {Object.entries(groups).map(([type, items]) => (
            <span key={type} className={eventClass(type)}>
              {eventLabel(type)} · {items.length}
            </span>
          ))}
        </div>
        <button
          type="button"
          className="timeline__replay-toggle"
          onClick={() => {
            setReplay((on) => !on);
            setCursor(0);
          }}
        >
          {replay ? "Exit replay" : "Replay"}
        </button>
      </div>

      {replay ? (
        <div className="timeline__replay">
          <div className="timeline__replay-controls">
            <button
              type="button"
              onClick={() => setCursor((c) => Math.max(0, c - 1))}
              disabled={safeCursor === 0}
            >
              ‹ Prev
            </button>
            <span className="timeline__replay-position">
              Step {safeCursor + 1} of {events.length}
            </span>
            <button
              type="button"
              onClick={() =>
                setCursor((c) => Math.min(events.length - 1, c + 1))
              }
              disabled={safeCursor === events.length - 1}
            >
              Next ›
            </button>
          </div>
          <EventCard event={current} />
        </div>
      ) : (
        <ol className="timeline__list">
          {events.map((event) => (
            <li key={event.id}>
              <EventCard event={event} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export default Timeline;
