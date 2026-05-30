# Running Whetstone locally

Whetstone is a Tauri + React desktop app over a local FastAPI backend. The
backend orchestrates three independent loopback services. Everything binds to
`127.0.0.1` only.

| Piece | Bind | `config.py` fields | Notes |
| --- | --- | --- | --- |
| llama-server (LLM) | `127.0.0.1:8081` | `llm_host`, `llm_port`, `llm_model` | OpenAI-compatible; serves Gemma 4 E4B |
| Psirver (code exec) | `127.0.0.1:8080` | `psirver_host`, `psirver_port` | C++ job server |
| FastAPI backend | `127.0.0.1:8000` | `host`, `port` | orchestration + SQLite |
| Tauri frontend | `localhost:1420` (Vite) | — | desktop window |
| whisper-server (STT) | `127.0.0.1:8082` | `stt_host`, `stt_port`, `stt_model` | optional; `/ai/transcribe` is still a stub |

The defaults in `apps/backend/config.py` already describe this layout, so if
you start each service on the port in the table above, **no environment
variables are required**. See [Configuration](#configuration) to change ports
or the model.

## Quick start — `make dev`

The launcher starts the four local services (everything except the desktop
window) in one command:

```sh
make dev                              # or: bash scripts/dev.sh
make dev ARGS="--skip-llm --skip-stt" # backend + Psirver only (no models yet)
```

What it does:

- **Preflight, then start.** It checks every prerequisite up front — the Psirver
  binary (built automatically if missing), the backend venv (created on first
  run), each model file, and that each port is free — and **fails loudly with
  the exact reason before starting anything** if something's missing, rather
  than coming up half-wired and hanging.
- **Clear startup output.** Each service prints starting → ready (or failed)
  with its port; readiness is an actual health probe, so llama-server's line
  only goes green once the model has loaded.
- **Clean shutdown.** `Ctrl-C` tears down all four and frees their ports
  (`8000/8080/8081/8082`) — no orphaned llama-server holding the GPU.
- **Logs** stream to the console and to `.dev-logs/<service>.log`.

Then start the desktop window in a second terminal:

```sh
cd apps/desktop && npm run tauri dev    # or: npm run dev   (browser fallback)
```

Skip flags: `--skip-llm`, `--skip-stt`, `--skip-psirver`. Ports and model paths
are configurable — see [Configuration](#configuration). The rest of this file
documents starting each service **by hand**, which the launcher automates; reach
for it when you want one service in isolation or the backend with `--reload`.

## Prerequisites (cold machine, macOS / Apple Silicon)

- Xcode Command Line Tools — provides `clang++` (Psirver build + C++ cells) and `python3`.
- Python 3.11+.
- Node.js 18+ and npm.
- Rust toolchain + [Tauri prerequisites](https://tauri.app/start/prerequisites/) — needed for `npm run tauri dev`. (You can skip these and run the UI in a browser instead — see step 4.)
- `llama.cpp` built locally, so `llama-server` is on your `PATH`.
- A Gemma 4 E4B GGUF model file on disk.

## Start order

> `make dev` performs steps 1–3 below for you (in this order, with readiness
> checks). The manual steps are here for running a service in isolation.

Start the services first, then the backend, then the frontend:

1. llama-server  →  2. Psirver  →  3. FastAPI backend  →  4. Tauri frontend

The backend's service clients connect lazily, so it will **boot** even if
llama-server or Psirver are down — it only fails (loudly, per request) when an
endpoint actually needs them. Starting the services first just means the first
"run a cell" or "import a spec" works immediately.

Use a separate terminal tab per long-running process.

---

### 1. llama-server (Gemma 4 E4B)

Point `-m` at your GGUF file. The port **must** be `8081` to match
`llm_port`, and `--alias` should match `llm_model` (`gemma-4-e4b`) so the
model name the backend sends is recognized.

```sh
# Set this to wherever your GGUF lives:
GEMMA_GGUF="$HOME/models/gemma-4-e4b/gemma-4-e4b-Q4_K_M.gguf"

llama-server \
  -m "$GEMMA_GGUF" \
  --host 127.0.0.1 --port 8081 \
  --alias gemma-4-e4b \
  -c 8192 \
  -ngl 99            # offload all layers to Metal on Apple Silicon
```

Verify (should list the model):

```sh
curl -s http://127.0.0.1:8081/v1/models
```

> llama.cpp serves a single loaded model and largely ignores the requested
> `model` field, so a mismatched name still works — but setting `--alias
> gemma-4-e4b` keeps it tidy and future-proof.

### 2. Psirver (C++ code execution)

Build once, then run it from a working directory it owns (it writes a pid
file plus `scripts/` and `jobs/` there). The port argument **must** be `8080`
to match `psirver_port`.

```sh
cd services/psirver/src
make
export PSIRVER_HOME="$PWD/run"        # working dir for pid file, scripts/, jobs/
mkdir -p "$PSIRVER_HOME"
cp psirver "$PSIRVER_HOME"/
( cd "$PSIRVER_HOME" && ./psirver 8080 )   # binds 127.0.0.1:8080
```

Verify (should return a JSON list, empty at first):

```sh
curl -s http://127.0.0.1:8080/jobs
```

### 3. FastAPI backend

```sh
cd apps/backend
python -m venv .venv && source .venv/bin/activate
pip install -e .                      # pulls fastapi, sqlmodel, pdfplumber, python-multipart, ...
uvicorn main:app --reload             # binds 127.0.0.1:8000 by default
```

Verify:

```sh
curl -s http://127.0.0.1:8000/health   # -> {"status":"ok"}
```

Interactive API docs (Swagger UI) are at <http://127.0.0.1:8000/docs>. The
SQLite database is created on first start at `apps/backend/whetstone.db`.

### 4. Tauri frontend

```sh
cd apps/desktop
npm install
npm run tauri dev
```

`tauri dev` automatically runs Vite (`npm run dev`, fixed port `1420`) and
opens the desktop window. First launch compiles the Rust shell and is slow;
later launches are fast.

**No Rust / Tauri toolchain?** Run the web build instead:

```sh
cd apps/desktop
npm install
npm run dev          # then open http://localhost:1420 in a browser
```

The Timeline panel works fully in a browser (it just calls the backend over
loopback; CORS is open). The Home view's **Greet** button calls into Rust via
Tauri and will only work inside the desktop window.

---

## Configuration

Settings live in `apps/backend/config.py` and are read from environment
variables (prefix `WHETSTONE_`) or an optional `.env` file in `apps/backend/`
(loaded relative to where you launch `uvicorn`). All have working defaults.

| Env var | Default | Purpose |
| --- | --- | --- |
| `WHETSTONE_DATABASE_URL` | `sqlite:///./whetstone.db` | SQLite database location |
| `WHETSTONE_DATA_DIR` | `./data` | app-managed files (uploads, exports) |
| `WHETSTONE_HOST` | `127.0.0.1` | backend bind host (informational — see note) |
| `WHETSTONE_PORT` | `8000` | backend bind port (informational — see note) |
| `WHETSTONE_PSIRVER_HOST` | `127.0.0.1` | Psirver host |
| `WHETSTONE_PSIRVER_PORT` | `8080` | Psirver port |
| `WHETSTONE_LLM_HOST` | `127.0.0.1` | llama-server host |
| `WHETSTONE_LLM_PORT` | `8081` | llama-server port |
| `WHETSTONE_LLM_MODEL` | `gemma-4-e4b` | model name sent to llama-server |
| `WHETSTONE_STT_HOST` | `127.0.0.1` | whisper-server host |
| `WHETSTONE_STT_PORT` | `8082` | whisper-server port |
| `WHETSTONE_STT_MODEL` | `whisper-base` | transcription model name |

Example `apps/backend/.env`:

```dotenv
WHETSTONE_LLM_PORT=8081
WHETSTONE_LLM_MODEL=gemma-4-e4b
```

> **Note on host/port:** `uvicorn` binds via its own CLI flags, not these
> settings. To actually move the backend, pass it explicitly *and* keep the
> config in sync, e.g. `uvicorn main:app --host 127.0.0.1 --port 9000` with
> `WHETSTONE_PORT=9000`. The default `uvicorn main:app` already binds
> `127.0.0.1:8000`, matching the defaults.

**Frontend → backend URL.** The desktop app targets `http://127.0.0.1:8000`
by default. Override it with a Vite env var in `apps/desktop/.env`:

```dotenv
VITE_API_BASE=http://127.0.0.1:9000
```

### Launcher environment (`make dev`)

The launcher reads the same `WHETSTONE_*` settings above, plus a few that point
at the model **files** and binaries (these are launcher concerns — `config.py`
only stores model *names*, never paths):

| Env var | Default | Purpose |
| --- | --- | --- |
| `WHETSTONE_MODELS_DIR` | `./models` | where the launcher looks for model files |
| `WHETSTONE_GEMMA_GGUF` | `./models/gemma-4-e4b.gguf` | Gemma GGUF passed to `llama-server -m` |
| `WHETSTONE_WHISPER_GGML` | `./models/ggml-base.bin` | Whisper model passed to `whisper-server -m` |
| `WHETSTONE_LLAMA_SERVER` | `llama-server` | llama-server binary (if not on `PATH`) |
| `WHETSTONE_WHISPER_SERVER` | `whisper-server` | whisper-server binary (if not on `PATH`) |
| `WHETSTONE_LLAMA_SERVER_ARGS` | `-c 8192 -ngl 99` | extra llama-server flags |
| `PSIRVER_LIMIT_FSIZE_MB` | `1024` (launcher default) | Psirver per-file cap; see the C++ note below |

See the **README → "Getting the models"** section for how to download the two
model files into `models/`.

> **C++ cells and the file-size cap.** Psirver's own default `RLIMIT_FSIZE` is
> 64 MB, which is too tight for `clang++` on macOS — a trivial C++ cell fails
> with `clang++: error: ... Filesize limit exceeded`. The launcher therefore
> raises `PSIRVER_LIMIT_FSIZE_MB` to `1024` by default; the CPU and wall-clock
> caps still contain a genuine runaway. If you run Psirver by hand, export
> `PSIRVER_LIMIT_FSIZE_MB` yourself (see the Psirver README → Configuration).

## Shutting down

Under `make dev`, **`Ctrl-C` stops all four services and frees their ports** —
nothing is left orphaned.

When running services by hand, `Ctrl-C` each terminal. To stop a detached
Psirver, find it by port:

```sh
lsof -ti tcp:8080 | xargs kill
```
