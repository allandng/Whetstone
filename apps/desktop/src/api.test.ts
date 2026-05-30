import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  API_BASE,
  askStream,
  createCell,
  listSessionCells,
  transcribeAudio,
} from "./api";
import type { CellCreate, CellRead } from "./types";

// The client calls the global fetch; every test installs a stub and asserts on
// the request it received. unstubAllGlobals (test/setup.ts) restores it after.
function stubFetch(impl: (url: string, init?: RequestInit) => unknown) {
  const mock = vi.fn(impl as never);
  vi.stubGlobal("fetch", mock);
  return mock;
}

function jsonResponse(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
    text: async () => JSON.stringify(data),
  };
}

// A minimal web ReadableStream of SSE bytes, so askStream's reader/decoder loop
// has something real to consume without pulling in a Response polyfill.
function sseStream(lines: string[]) {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const line of lines) controller.enqueue(encoder.encode(line));
      controller.close();
    },
  });
}

beforeEach(() => {
  // Guard the assumption the URL assertions rely on.
  expect(API_BASE).toBe("http://127.0.0.1:8000");
});

describe("listSessionCells", () => {
  it("GETs the session's cells and returns the parsed list", async () => {
    const cells: CellRead[] = [
      {
        id: "c1",
        session_id: "s1",
        cell_type: "code",
        language: "python",
        content: "print(1)",
        last_output: null,
        status: "idle",
        order_index: 0,
      },
    ];
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(cells)));

    const result = await listSessionCells("s1");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:8000/sessions/s1/cells");
    expect(init?.method).toBe("GET");
    expect(result).toEqual(cells);
  });

  it("encodes the session id into the path", async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse([])));
    await listSessionCells("a/b?c");
    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://127.0.0.1:8000/sessions/a%2Fb%3Fc/cells",
    );
  });
});

describe("createCell", () => {
  it("POSTs to /cells with the cell body as JSON", async () => {
    const body: CellCreate = {
      session_id: "s1",
      cell_type: "code",
      language: "cpp",
      content: "int main(){}",
    };
    const created: CellRead = {
      id: "c9",
      session_id: "s1",
      cell_type: "code",
      language: "cpp",
      content: "int main(){}",
      last_output: null,
      status: "idle",
      order_index: 1,
    };
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse(created)));

    const result = await createCell(body);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:8000/cells");
    expect(init?.method).toBe("POST");
    expect((init?.headers as Record<string, string>)["Content-Type"]).toBe(
      "application/json",
    );
    expect(JSON.parse(init?.body as string)).toEqual(body);
    expect(result).toEqual(created);
  });
});

describe("askStream", () => {
  it("POSTs /ai/ask carrying the requested mode in the body", async () => {
    const fetchMock = stubFetch(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        body: sseStream(['data: {"delta":"hi"}\n', 'data: {"done":true}\n']),
        text: async () => "",
      }),
    );
    const onDelta = vi.fn();
    const onDone = vi.fn();

    await askStream(
      { session_id: "s1", cell_id: "c1", question: "why?", mode: "socratic" },
      { onDelta, onDone },
    );

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:8000/ai/ask");
    expect(init?.method).toBe("POST");
    const sent = JSON.parse(init?.body as string);
    expect(sent.mode).toBe("socratic");
    expect(sent.question).toBe("why?");
    // And the SSE frames were decoded and dispatched.
    expect(onDelta).toHaveBeenCalledWith("hi");
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("preserves mode=direct when that is what the caller asked for", async () => {
    const fetchMock = stubFetch(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        body: sseStream(['data: {"done":true}\n']),
        text: async () => "",
      }),
    );
    await askStream(
      { session_id: "s1", cell_id: null, question: "go", mode: "direct" },
      { onDelta: vi.fn() },
    );
    expect(JSON.parse(fetchMock.mock.calls[0][1]?.body as string).mode).toBe(
      "direct",
    );
  });
});

describe("transcribeAudio", () => {
  it("POSTs /ai/transcribe as multipart with the audio blob", async () => {
    const fetchMock = stubFetch(() =>
      Promise.resolve(jsonResponse({ transcript: "hello world" })),
    );
    const blob = new Blob(["fake-audio"], { type: "audio/webm" });

    const result = await transcribeAudio(blob);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:8000/ai/transcribe");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBeInstanceOf(FormData);
    const form = init?.body as FormData;
    expect(form.get("audio")).not.toBeNull();
    expect(result).toEqual({ transcript: "hello world" });
  });

  it("throws an ApiError carrying the HTTP status on a non-OK response", async () => {
    stubFetch(() =>
      Promise.resolve({
        ok: false,
        status: 503,
        json: async () => ({}),
        text: async () => "whisper down",
      }),
    );
    await expect(
      transcribeAudio(new Blob(["x"], { type: "audio/webm" })),
    ).rejects.toMatchObject({ status: 503 });
  });
});
