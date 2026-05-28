// Minimal client for the Whetstone backend. The backend runs on loopback
// (see apps/backend/config.py); override with VITE_API_BASE if needed.

export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ??
  "http://127.0.0.1:8000";

export type TimelineEvent = {
  id: string;
  session_id: string;
  timestamp: string;
  event_type: string;
  payload: Record<string, unknown>;
};

export type SessionTimeline = {
  session_id: string;
  events: TimelineEvent[];
  groups: Record<string, TimelineEvent[]>;
};

export async function fetchTimeline(
  sessionId: string,
): Promise<SessionTimeline> {
  const res = await fetch(
    `${API_BASE}/sessions/${encodeURIComponent(sessionId)}/timeline`,
  );
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(
      `Timeline request failed (${res.status})${detail ? `: ${detail}` : ""}`,
    );
  }
  return (await res.json()) as SessionTimeline;
}
