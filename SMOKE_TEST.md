# Whetstone manual smoke test

A click-by-click pass to confirm the frontend works against a freshly started
stack. Assumes a cold machine — get the services up first with
[RUNNING.md](RUNNING.md).

**What each part needs running:**

- Timeline panel (Parts 1–5): the **FastAPI backend** only.
- Spec import (Part 6): the **backend + llama-server**.

> Current-skeleton caveat: session/cell CRUD endpoints are still stubs, and the
> only frontend panel is the **Timeline**. So we seed a demo session from the
> command line (Part 3), and spec import is verified through the API rather than
> a checklist UI (Part 6). That's expected at this stage.

---

## Part 1 — Launch the app

1. Start the backend (see RUNNING.md step 3); confirm
   `curl -s http://127.0.0.1:8000/health` returns `{"status":"ok"}`.
2. Start the frontend:
   ```sh
   cd apps/desktop
   npm install      # first time only
   npm run tauri dev
   ```
   (No Rust toolchain? Use `npm run dev` and open <http://localhost:1420> in a
   browser — the Timeline works there.)

**Expect:** a window with a left **sidebar** ("Whetstone" brand, plus **Home**
and **Timeline** buttons) and a main area showing the Home view ("Welcome to
Tauri + React"). **Home** is highlighted as the active tab.

## Part 2 — Home sanity check (Tauri bridge)

1. In the Home view, type a name into the input and click **Greet**.

**Expect:** the text `Hello, <name>! You've been greeted from Rust!` appears
below the form. (This only works in the Tauri desktop window, not a plain
browser — skip it if you're using the `npm run dev` fallback.)

## Part 3 — Seed a demo session

Because session creation isn't wired to the UI yet, create a session with a few
events directly. Run this **from `apps/backend` with the venv active** (it uses
the same SQLite file the backend serves):

```sh
cd apps/backend
source .venv/bin/activate
python - <<'PY'
from db import create_db_and_tables, session_scope
from models import Session as S
from events import emit_event

create_db_and_tables()
with session_scope() as db:
    sess = S(title="Smoke-test session")
    db.add(sess); db.commit(); db.refresh(sess)
    sid = sess.id
    emit_event(db, session_id=sid, event_type="mode_switch",
               payload={"from": "direct", "to": "socratic"})
    emit_event(db, session_id=sid, event_type="cell_run",
               payload={"cell_id": "c1", "code": "def bfs(g, s): ..."})
    emit_event(db, session_id=sid, event_type="cell_result",
               payload={"cell_id": "c1", "status": "ok", "output": "[0, 1, 2, 3]"})
    emit_event(db, session_id=sid, event_type="ai_exchange",
               payload={"kind": "ask",
                        "question": "Why is my BFS visiting nodes twice?",
                        "response": "Check that you mark a node visited when you enqueue it..."})
    emit_event(db, session_id=sid, event_type="voice_note",
               payload={"text": "remember to handle the empty-graph case"})
print("SESSION_ID:", sid)
PY
```

**Copy the printed `SESSION_ID`.** It writes one event of each type
(mode_switch, cell_run, cell_result, ai_exchange, voice_note).

## Part 4 — Timeline list view

1. Click **Timeline** in the sidebar.
   - **Expect:** heading "Session Timeline", a session-ID input + **Load**
     button, and the hint *"Enter a session ID above to load its timeline."*
2. Paste the `SESSION_ID` into the input and click **Load**.

**Expect:**

- A **counts bar** of colored badges, one per type with its count:
  `MODE SWITCH · 1`, `CELL RUN · 1`, `CELL RESULT · 1`, `AI EXCHANGE · 1`,
  `VOICE NOTE · 1`.
- A **vertical list of 5 event cards**, oldest first (mode_switch → cell_run →
  cell_result → ai_exchange → voice_note). Each card shows:
  - a colored **type badge** (e.g. AI EXCHANGE in purple),
  - a **timestamp** (your local time),
  - a **one-line summary** from the payload, e.g.
    - cell_run → `Ran cell: def bfs(g, s): ...`
    - cell_result → `status=ok — [0, 1, 2, 3]`
    - ai_exchange → `ask: Why is my BFS visiting nodes twice?`
    - mode_switch → `direct → socratic`
    - voice_note → `remember to handle the empty-graph case`

A bad/unknown session ID shows *"No events recorded yet."*; if the backend is
down you get *"Could not load timeline: …"*.

## Part 5 — Replay mode

1. Click **Replay** (top-right of the panel).

**Expect:**

- The list collapses to a **single event card** plus controls reading
  **Step 1 of 5**.
- **‹ Prev** is **disabled** on the first step.
- Clicking **Next ›** advances one event at a time (2 of 5, 3 of 5, …); the
  card content and badge change to match.
- On **Step 5 of 5**, **Next ›** is **disabled**; **‹ Prev** steps back.
- Clicking **Exit replay** returns to the full vertical list.

> Replay is **UI state only** — it does not re-run code or re-call the AI. It
> just walks the recorded events.

## Part 6 — Spec import (needs llama-server)

There's no checklist UI in this slice, so verify import through the API. Start
llama-server (RUNNING.md step 1) first.

1. Import a spec from raw text:
   ```sh
   curl -s -X POST http://127.0.0.1:8000/specs/import \
     -F 'raw_text=Write bfs(graph, start) returning nodes in BFS order. Handle disconnected graphs. Add unit tests for the empty graph and a single node.'
   ```
   **Expect:** an immediate `{"spec_id":"…","status":"extracting"}`. Copy the
   `spec_id`. (For a PDF instead: `-F 'file=@/path/to/assignment.pdf'`.)

2. Watch the backend (uvicorn) console. Within a few seconds you should see
   `Extracted N requirements for spec <id>.` If llama-server is unreachable
   you'll instead see `Requirement extraction failed for spec <id>: …`.

3. Poll the checklist (re-run until it's populated):
   ```sh
   curl -s http://127.0.0.1:8000/specs/<SPEC_ID>/requirements | python -m json.tool
   ```
   **Expect:** a JSON array of requirement objects, each with `text` and
   `status: "not_started"` — one concrete obligation per item (e.g. "Implement
   bfs(graph, start)", "Handle disconnected graphs", "Add a unit test for the
   empty graph", …).

4. (Optional) Mark one done — confirms manual edits persist:
   ```sh
   curl -s -X PATCH http://127.0.0.1:8000/requirements/<REQUIREMENT_ID> \
     -H 'Content-Type: application/json' -d '{"status":"done"}'
   ```
   **Expect:** the returned object has `"status":"done"`.

5. (Optional) Attach the spec to your smoke-test session:
   ```sh
   curl -s -X POST http://127.0.0.1:8000/sessions/<SESSION_ID>/spec \
     -H 'Content-Type: application/json' -d '{"spec_id":"<SPEC_ID>"}'
   ```
   **Expect:** the session JSON comes back with `"spec_id"` set.

You can also drive all of this from the Swagger UI at
<http://127.0.0.1:8000/docs> using **Try it out**.

> If `/specs/import` returns `extracting` but the requirements list stays empty,
> llama-server isn't reachable on `127.0.0.1:8081` (or the model didn't return a
> JSON array). The import itself still succeeded — only the background
> extraction no-opped. Check the uvicorn console for the reason.

---

## Quick troubleshooting

| Symptom | Likely cause |
| --- | --- |
| "Could not load timeline" in the panel | Backend not running on `:8000`, or wrong port — check `curl /health`. |
| Timeline says "No events recorded yet." | Wrong session ID, or events weren't seeded — re-run Part 3 and recopy the ID. |
| **Greet** does nothing | Running in a plain browser (`npm run dev`) instead of the Tauri window. |
| `/specs/import` works but requirements stay empty | llama-server down or not on `:8081` — `curl http://127.0.0.1:8081/v1/models`. |
| Spec import returns 400 | Sent neither a `file` nor non-empty `raw_text`. |
