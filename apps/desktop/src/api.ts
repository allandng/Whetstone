// Typed client for the Whetstone backend. The backend runs on loopback
// (see apps/backend/config.py); override with VITE_API_BASE if needed.
//
// Every shape here mirrors apps/backend/schemas.py — the backend is the source
// of truth. Routes that don't exist yet are marked with a TODO and the calling
// UI falls back to local state so the app stays usable offline.

import type {
  AskRequest,
  AttachSpecRequest,
  CellCreate,
  CellRead,
  CellUpdate,
  ComplexityResponse,
  ExplainErrorResponse,
  RequirementItemRead,
  RequirementUpdate,
  SessionCreate,
  SessionRead,
  SessionTimeline,
  SpecImportResponse,
  TranscribeResponse,
} from "./types";

export type * from "./types";

export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ??
  "http://127.0.0.1:8000";

const enc = encodeURIComponent;

/** Error carrying the HTTP status, so callers can branch (e.g. 501, 404). */
export type ApiError = Error & { status?: number };

async function json<T>(
  method: string,
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw Object.assign(
      new Error(`${method} ${path} failed (${res.status})${detail ? `: ${detail}` : ""}`),
      { status: res.status },
    ) as ApiError;
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// --- Sessions --------------------------------------------------------------

export function listSessions(): Promise<SessionRead[]> {
  return json<SessionRead[]>("GET", "/sessions");
}

export function createSession(body: SessionCreate = {}): Promise<SessionRead> {
  return json<SessionRead>("POST", "/sessions", body);
}

export function getSession(sessionId: string): Promise<SessionRead> {
  return json<SessionRead>("GET", `/sessions/${enc(sessionId)}`);
}

export function deleteSession(sessionId: string): Promise<{ status: string }> {
  return json("DELETE", `/sessions/${enc(sessionId)}`);
}

export function attachSpec(sessionId: string, specId: string): Promise<SessionRead> {
  const body: AttachSpecRequest = { spec_id: specId };
  return json<SessionRead>("POST", `/sessions/${enc(sessionId)}/spec`, body);
}

export function fetchTimeline(sessionId: string): Promise<SessionTimeline> {
  return json<SessionTimeline>("GET", `/sessions/${enc(sessionId)}/timeline`);
}

// --- Cells -----------------------------------------------------------------

/** List a session's cells in stable order (order_index), each with its last
 *  output. Lets the notebook restore prior cells and outputs on session open. */
export function listSessionCells(sessionId: string): Promise<CellRead[]> {
  return json<CellRead[]>("GET", `/sessions/${enc(sessionId)}/cells`);
}

export function createCell(body: CellCreate): Promise<CellRead> {
  return json<CellRead>("POST", "/cells", body);
}

export function updateCell(cellId: string, body: CellUpdate): Promise<CellRead> {
  return json<CellRead>("PUT", `/cells/${enc(cellId)}`, body);
}

/** Run a code cell. The backend submits to Psirver and polls to completion
 *  server-side, returning the terminal CellRead (status + last_output). There
 *  is no incremental stdout stream and no terminate route, so `signal` only
 *  aborts the client request — the server job continues to completion. */
export function runCell(cellId: string, signal?: AbortSignal): Promise<CellRead> {
  return json<CellRead>("POST", `/cells/${enc(cellId)}/run`, undefined, signal);
}

export function deleteCell(cellId: string): Promise<{ status: string }> {
  return json("DELETE", `/cells/${enc(cellId)}`);
}

// --- Spec / requirements ---------------------------------------------------

export function listRequirements(specId: string): Promise<RequirementItemRead[]> {
  return json<RequirementItemRead[]>("GET", `/specs/${enc(specId)}/requirements`);
}

export function updateRequirement(
  requirementId: string,
  body: RequirementUpdate,
): Promise<RequirementItemRead> {
  return json<RequirementItemRead>("PATCH", `/requirements/${enc(requirementId)}`, body);
}

export function importSpec(input: {
  file?: File;
  rawText?: string;
}): Promise<SpecImportResponse> {
  const form = new FormData();
  if (input.file) form.append("file", input.file);
  else if (input.rawText != null) form.append("raw_text", input.rawText);
  return fetch(`${API_BASE}/specs/import`, { method: "POST", body: form }).then(
    async (res) => {
      if (!res.ok) {
        const detail = await res.text().catch(() => "");
        throw Object.assign(
          new Error(`POST /specs/import failed (${res.status})${detail ? `: ${detail}` : ""}`),
          { status: res.status },
        ) as ApiError;
      }
      return (await res.json()) as SpecImportResponse;
    },
  );
}

// --- AI co-pilot -----------------------------------------------------------

export type AskStreamHandlers = {
  onDelta: (text: string) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
};

/** Stream a tutor reply from POST /ai/ask (Server-Sent Events). The reply's
 *  style follows body.mode — Direct answers, Socratic guides with questions and
 *  a hint ladder — but the stream shape is identical. Throws an ApiError on a
 *  non-OK response; network failures (backend down) reject so callers can
 *  degrade gracefully. */
export async function askStream(
  body: AskRequest,
  handlers: AskStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE}/ai/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    const detail = await res.text().catch(() => "");
    throw Object.assign(
      new Error(`POST /ai/ask failed (${res.status})${detail ? `: ${detail}` : ""}`),
      { status: res.status },
    ) as ApiError;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (!line.startsWith("data:")) continue;
      const data = line.slice(5).trim();
      if (!data) continue;
      let obj: { delta?: string; error?: string; done?: boolean };
      try {
        obj = JSON.parse(data);
      } catch {
        continue;
      }
      if (typeof obj.delta === "string") handlers.onDelta(obj.delta);
      else if (typeof obj.error === "string") {
        handlers.onError?.(obj.error);
        return;
      } else if (obj.done) {
        handlers.onDone?.();
        return;
      }
    }
  }
  handlers.onDone?.();
}

export function explainError(
  cellId: string,
  errorText: string,
): Promise<ExplainErrorResponse> {
  return json<ExplainErrorResponse>("POST", "/ai/explain-error", {
    cell_id: cellId,
    error_text: errorText,
  });
}

export function complexity(cellId: string): Promise<ComplexityResponse> {
  return json<ComplexityResponse>("POST", "/ai/complexity", { cell_id: cellId });
}

/** Transcribe recorded audio on-device via POST /ai/transcribe (FR-VOICE-1).
 *  The blob is uploaded as multipart form-data under the `audio` field, matching
 *  the backend's UploadFile param. Throws an ApiError on a non-OK response (e.g.
 *  503 when whisper-server is down) so callers can surface a clean failure. */
export async function transcribeAudio(
  audio: Blob,
  signal?: AbortSignal,
): Promise<TranscribeResponse> {
  const form = new FormData();
  form.append("audio", audio, "recording.webm");
  const res = await fetch(`${API_BASE}/ai/transcribe`, {
    method: "POST",
    body: form,
    signal,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw Object.assign(
      new Error(`POST /ai/transcribe failed (${res.status})${detail ? `: ${detail}` : ""}`),
      { status: res.status },
    ) as ApiError;
  }
  return (await res.json()) as TranscribeResponse;
}
