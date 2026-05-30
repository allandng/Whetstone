# Whetstone manual smoke test

A click-by-click pass to confirm the frontend works against a freshly started
stack. Assumes a cold machine — get the services up first with `make dev` (the
one-command launcher) or the per-service steps in [RUNNING.md](RUNNING.md).

**What each part needs running:**

- Workspace offline shell (Part 1): **nothing** — the UI boots and degrades
  gracefully with no services up.
- Workspace live (Part 2): the **FastAPI backend** (plus **llama-server** for the
  co-pilot, plus **Psirver** to actually execute a cell).
- Legacy Timeline view (Parts 3–5): the **FastAPI backend** only.
- Spec import (Part 6): the **backend + llama-server**.

> The three-pane **Workspace** is now the primary view. The legacy **Home** and
> **Timeline** views are still reachable from the sidebar — open them via the
> header **cog** (or the brand square), then use the **Workspace** link to return.
> Session/cell CRUD is wired, so running a cell records `cell_run`/`cell_result`
> on the timeline over HTTP; the CLI seed in Part 3 is only needed for a richer
> demo or to exercise the Timeline view in isolation.

---

## Part 1 — Launch the app (offline shell)

You can do this part with **no services running** — it verifies the workspace
boots and degrades gracefully.

1. Start the frontend:
   ```sh
   cd apps/desktop
   npm install      # first time only
   npm run tauri dev
   ```
   (No Rust toolchain? Use `npm run dev` and open <http://localhost:1420> in a
   browser — the whole workspace works there.)

**Expect:** the three-pane **Workspace** fills the window:

- **Header:** Whetstone brand square, breadcrumb (`local session / scratchpad.cpp`),
  a **Local engine** indicator, a **Dictate** button, and a settings **cog**.
- **Left — Tracked Requirements:** with the backend down it shows the empty
  state *"No spec attached…"* and a `0/0` count (no invented requirements).
- **Center — Notebook:** one seed C++ cell (`Cell 01 · CPP`) with **Run /
  Cancel / Clear**, line numbers, and an empty terminal reading *"No output
  recorded. Press Run."*
- **Right — AI co-pilot:** a **Direct Help / Socratic Mode** toggle, a model
  selector, and an intro hint.
- **Footer:** *"Sandbox offline · No activity yet"*, a **View full timeline**
  button, and a telemetry line ending in the API host.

With the backend down, the indicator reads **"Local engine · offline"** and the
footer reads **"Sandbox offline"**. Nothing errors out.

## Part 2 — Workspace panes (live vs. fallback)

Start the backend (RUNNING.md step 3); confirm
`curl -s http://127.0.0.1:8000/health` returns `{"status":"ok"}`, then reload.
The header should flip to **"Local engine · online"** and the footer to
**"Sandbox active"**. The workspace reuses the most recently modified session
(or creates one) on boot.

1. **Requirements (left).** With a spec attached to the session, the checklist
   loads from `GET /specs/{id}/requirements`; each row's label is synthesised
   from a leading code (e.g. `FR-SPEC-7`) or falls back to `R1`, `R2`, …
   Changing a status writes through `PATCH /requirements/{id}` (the change
   reverts if the request fails). Requirements that mention a complexity bound
   show an amber advisory. With no spec, the empty state from Part 1 stays.

2. **Run a cell (center).** Edit the seed cell if you like, then click **Run**.
   - **Live:** the cell is created (`POST /cells`) on first run and executed
     (`POST /cells/{id}/run`); the terminal shows the backend `status` and
     `last_output`, and the footer logs `Cell run · <status>`. Re-running after
     an edit issues a `PUT /cells/{id}` first.
   - **Cancel** aborts the *client* request only — the note reads *"Request
     cancelled; the server job continues to completion."* (there is no
     server-side terminate route).
   - **Psirver down / language unsupported:** the run still returns with
     `status="error"` and the failure as output — it never hard-fails.

3. **Ask the co-pilot (right), Direct mode.** Type a question and **Send**.
   - **Live (+ llama-server):** the answer **streams** in token-by-token from
     `POST /ai/ask` (SSE). A full-solution reply (prefixed by the backend's
     integrity marker) renders an **integrity note** banner.
   - **Backend up, llama-server down:** the tutor bubble shows the service
     error in red rather than streaming.
   - **Backend down:** the bubble reads *"Backend is offline — start it to ask
     the local co-pilot."*

4. **Socratic mode.** Switch the toggle to **Socratic Mode**.
   **Expect:** an amber notice *"Socratic mode not yet wired — the backend
   returns 501…"* and a **disabled** composer. (This is a scoped roadmap item;
   `POST /ai/ask` with `mode=socratic` returns 501.)

5. **Timeline drawer.** Click **View full timeline** in the footer.
   **Expect:** a slide-up drawer with the live session's events (the same
   component as the Timeline view); **Esc**, the **✕**, or the overlay closes
   it. Offline, it shows a "timeline unavailable while the backend is offline"
   note instead.

6. **Dictate** is a **visual placeholder** — toggling it shows the recording
   banner, but on-device voice capture isn't wired yet (`POST /ai/transcribe`
   is a stub).

## Part 2b — Legacy Home + Timeline (Tauri bridge)

1. Click the header **cog** (or brand square) to drop to the legacy **Home**
   view; the sidebar exposes **Workspace / Home / Timeline**.
2. In Home, type a name and click **Greet**.

**Expect:** `Hello, <name>! You've been greeted from Rust!` appears below the
form. (Tauri-only — skip it under the `npm run dev` browser fallback.) Click
**Workspace** to return.

## Part 3 — Seed a demo session

The Workspace already records events as you run cells and ask the co-pilot. To
exercise the **Timeline view** with one of every event type (without driving the
UI), seed a session directly. Run this **from `apps/backend` with the venv
active** (it uses the same SQLite file the backend serves):

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

1. From the workspace, click the header **cog** to reach the legacy shell, then
   click **Timeline** in the sidebar.
   - **Expect:** heading "Session Timeline", a session-ID input + **Load**
     button, and the hint *"Enter a session ID above to load its timeline."*
2. Paste the `SESSION_ID` into the input and click **Load**.

**Expect:**

- A **counts bar** of colored badges, one per type with its count:
  `MODE SWITCH · 1`, `CELL RUN · 1`, `CELL RESULT · 1`, `AI EXCHANGE · 1`,
  `VOICE NOTE · 1`.
- A **table of 5 rows**, oldest first (mode_switch → cell_run → cell_result →
  ai_exchange → voice_note), with **Time / Event / Detail** columns. The event
  label is color-coded (e.g. AI EXCHANGE in **sky**, CELL RESULT in **emerald**,
  MODE SWITCH in **amber**), and the detail is a one-line payload summary, e.g.
  - cell_run → `Ran cell: def bfs(g, s): ...`
  - cell_result → `status=ok — [0, 1, 2, 3]`
  - ai_exchange → `ask: Why is my BFS visiting nodes twice?`
  - mode_switch → `direct → socratic`
  - voice_note → `remember to handle the empty-graph case`

A bad/unknown session ID shows *"No events recorded yet."*; if the backend is
down you get *"Could not load timeline: …"*. The same component renders inside
the workspace's footer **timeline drawer** (Part 2, step 5).

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
