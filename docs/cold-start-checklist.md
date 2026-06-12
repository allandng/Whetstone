# Cold-start checklist — first run on a clean machine

The one test that matters before shipping to others: can someone who is **not
the author**, on a **fresh macOS (Apple Silicon)** machine, get from `git clone`
to a working tutor by following the docs? Run this end to end on a clean box (or
a new user account). Tick each box; where a step fails, the **Blocker** note says
what it means.

The whole stack runs locally — there is no hosted backend — so "it works" means
all four local services come up and the desktop window talks to them.

---

## 1. Prerequisites (install, then verify)

- [ ] **Xcode Command Line Tools** — `xcode-select --install`
  Verify: `clang++ --version` prints a version.
  Blocker if missing: Psirver won't build and C++ cells can't compile.
- [ ] **Python 3.11+** — verify: `python3 --version` ≥ 3.11.
- [ ] **Node 18+ and npm** — verify: `node --version`, `npm --version`.
- [ ] **Rust + Tauri prerequisites** (only to run the desktop *window*; you can
  skip this and use the browser UI) — verify: `cargo --version`.
- [ ] **llama.cpp built, `llama-server` on PATH** — verify: `which llama-server`.
  Blocker if missing: the AI tutor returns 503 (cells still run).
- [ ] **whisper.cpp built, `whisper-server` on PATH** — verify: `which whisper-server`.
  Blocker if missing: voice dictation returns 503 (everything else works).

## 2. Clone

- [ ] `git clone https://github.com/allandng/Whetstone.git && cd Whetstone`

## 3. Models (large; not in the repo)

- [ ] **Gemma** → `models/gemma-4-e4b.gguf`
  ```sh
  huggingface-cli download ggml-org/gemma-4-E4B-it-GGUF gemma-4-E4B-it-Q4_K_M.gguf \
    --local-dir models --local-dir-use-symlinks False
  mv models/gemma-4-E4B-it-Q4_K_M.gguf models/gemma-4-e4b.gguf
  ```
  Verify: `ls -la models/gemma-4-e4b.gguf` (~5.3 GB).
- [ ] **Whisper** → `models/ggml-base.bin` (from your whisper.cpp checkout)
  ```sh
  bash ./models/download-ggml-model.sh base
  cp models/ggml-base.bin /path/to/Whetstone/models/ggml-base.bin
  ```
  Verify: `ls -la models/ggml-base.bin`.

> No models yet? You can still verify the core: `make dev ARGS="--skip-llm --skip-stt"`
> brings up just the backend + Psirver (cells run; tutor/voice 503).

## 4. Bring up the stack

- [ ] `make dev`
  Expect: a preflight pass, then each service printed with its port and an
  `[ok] ... ready`. First run builds Psirver and the backend venv (a minute or two).
  - [ ] Psirver `127.0.0.1:8080`
  - [ ] llama-server `127.0.0.1:8081` (slow first load while weights map in)
  - [ ] whisper-server `127.0.0.1:8082`
  - [ ] backend `127.0.0.1:8000`
  Blocker: if it fails at preflight it names the exact missing file/port — fix
  that and re-run. It should never come up half-wired.
- [ ] In a second terminal, start the window:
  `cd apps/desktop && npm run tauri dev`
  (No Rust? `npm run dev`, then open <http://localhost:1420> in a browser.)

## 5. Prove it works (the actual acceptance)

- [ ] **Python cell** — run the seed/first cell or a `print(2+2)` cell → output `4`,
  status ok.
- [ ] **C++ cell** — add a C++ cell that prints something → compiles and runs.
  Blocker if it fails with "Filesize limit exceeded": the Psirver `RLIMIT_FSIZE`
  default regressed (should be 1 GiB). 
- [ ] **Spec import** — import a short PDF or paste text → a requirement checklist
  appears (needs llama-server).
- [ ] **Tutor — Direct** — ask a question → a streamed answer. **Socratic** —
  toggle and ask → guiding questions / hints, composer stays enabled.
- [ ] **Voice** — toggle Dictate, speak, toggle off → transcript lands in the
  prompt (needs whisper-server). Blocker if 503: whisper-server isn't running.
- [ ] **Timeline** — open the timeline drawer → run/result events; the Replay
  scrubber steps through them.
- [ ] **Edit persistence** — edit a cell, switch away and back (or reload) →
  the edit is still there (autosave).

## 6. Tear down

- [ ] `Ctrl-C` in the `make dev` terminal → all four services stop and their
  ports are freed (verify: `lsof -i tcp:8000` is empty).

---

### If something here fails

That failure *is* the finding — note the exact step and message. The most likely
first-run walls are: a model path/name mismatch (step 3), `llama-server` /
`whisper-server` not on PATH (step 1), or the long llama-server weight-load time
being mistaken for a hang (step 4 — give it up to ~10 min on first load).

For the full per-service detail and troubleshooting, see [`RUNNING.md`](../RUNNING.md);
for a click-by-click UI pass, [`SMOKE_TEST.md`](../SMOKE_TEST.md).
