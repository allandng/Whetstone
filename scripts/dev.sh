#!/usr/bin/env bash
#
# Whetstone dev launcher — start the local backend services in one command.
#
#   scripts/dev.sh [--skip-llm] [--skip-stt] [--skip-psirver] [--help]
#
# Brings up (with preflight checks, readiness probes, and clean teardown):
#
#   1. Psirver         127.0.0.1:8080   C++ code execution
#   2. llama-server    127.0.0.1:8081   Gemma LLM (OpenAI-compatible)
#   3. whisper-server  127.0.0.1:8082   speech-to-text
#   4. FastAPI backend 127.0.0.1:8000   orchestration + SQLite
#
# The Tauri/React frontend is NOT started here — run it separately:
#     cd apps/desktop && npm run tauri dev    (or `npm run dev` for the browser)
#
# Ctrl-C tears down all four services and frees their ports. Prerequisites are
# checked up front: if a model file, the Psirver binary, or a port is missing,
# the launcher fails loudly *before* starting anything, rather than coming up
# half-wired and hanging.
#
set -euo pipefail

# --- Resolve paths ---------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- Configuration (override via environment) ------------------------------
HOST="127.0.0.1"
BACKEND_PORT="${WHETSTONE_PORT:-8000}"
PSIRVER_PORT="${WHETSTONE_PSIRVER_PORT:-8080}"
LLM_PORT="${WHETSTONE_LLM_PORT:-8081}"
STT_PORT="${WHETSTONE_STT_PORT:-8082}"

# Model *alias* the backend asks llama-server for (mirrors config.py default).
LLM_ALIAS="${WHETSTONE_LLM_MODEL:-gemma-4-e4b}"

# Model *files* (paths). config.py only stores model names, never paths — the
# file location is a launcher concern, passed to the model servers via -m.
MODELS_DIR="${WHETSTONE_MODELS_DIR:-$ROOT/models}"
GEMMA_GGUF="${WHETSTONE_GEMMA_GGUF:-$MODELS_DIR/gemma-4-e4b.gguf}"
WHISPER_GGML="${WHETSTONE_WHISPER_GGML:-$MODELS_DIR/ggml-base.bin}"

# Service binaries (override if not on PATH).
LLAMA_SERVER_BIN="${WHETSTONE_LLAMA_SERVER:-llama-server}"
WHISPER_SERVER_BIN="${WHETSTONE_WHISPER_SERVER:-whisper-server}"

# Extra args appended to each model server's command line.
LLAMA_SERVER_ARGS="${WHETSTONE_LLAMA_SERVER_ARGS:--c 8192 -ngl 99}"
WHISPER_SERVER_ARGS="${WHETSTONE_WHISPER_SERVER_ARGS:-}"

# clang++ on macOS writes sizable intermediates when compiling a C++ cell, so
# Psirver's default RLIMIT_FSIZE (64 MB) trips "Filesize limit exceeded" on even
# a trivial program. Give compiles headroom for dev unless the dev set it; the
# CPU and wall-clock caps still contain a genuine runaway. Exported so the
# Psirver child inherits it (see Psirver README → Configuration).
export PSIRVER_LIMIT_FSIZE_MB="${PSIRVER_LIMIT_FSIZE_MB:-1024}"

# Readiness timeouts (seconds). Model servers load weights before serving, so
# they get a generous window; the backend and Psirver come up fast.
PSIRVER_READY_TIMEOUT="${WHETSTONE_PSIRVER_READY_TIMEOUT:-20}"
LLM_READY_TIMEOUT="${WHETSTONE_LLM_READY_TIMEOUT:-600}"
STT_READY_TIMEOUT="${WHETSTONE_STT_READY_TIMEOUT:-300}"
BACKEND_READY_TIMEOUT="${WHETSTONE_BACKEND_READY_TIMEOUT:-60}"

LOG_DIR="$ROOT/.dev-logs"
RUN_DIR="$ROOT/.dev-run"

PSIRVER_SRC="$ROOT/services/psirver/src"
PSIRVER_BIN="$PSIRVER_SRC/psirver"
BACKEND_DIR="$ROOT/apps/backend"
VENV="$BACKEND_DIR/.venv"

# --- Flags -----------------------------------------------------------------
RUN_LLM=1
RUN_STT=1
RUN_PSIRVER=1

usage() {
  cat <<EOF
Whetstone dev launcher — start the four local services in one command.

Usage: scripts/dev.sh [options]

Options:
  --skip-llm       Don't start llama-server  (LLM endpoints will return 503).
  --skip-stt       Don't start whisper-server (voice transcription will 503).
  --skip-psirver   Don't start Psirver        (cell execution will error).
  -h, --help       Show this help and exit.

Services & ports (override with WHETSTONE_*_PORT):
  Psirver          ${HOST}:${PSIRVER_PORT}
  llama-server     ${HOST}:${LLM_PORT}
  whisper-server   ${HOST}:${STT_PORT}
  FastAPI backend  ${HOST}:${BACKEND_PORT}

Model files (paths — override via env):
  WHETSTONE_GEMMA_GGUF   = ${GEMMA_GGUF}
  WHETSTONE_WHISPER_GGML = ${WHISPER_GGML}

The Tauri/React frontend is started separately:
  cd apps/desktop && npm run tauri dev      # or: npm run dev  (browser)
EOF
}

for arg in "$@"; do
  case "$arg" in
    --skip-llm) RUN_LLM=0 ;;
    --skip-stt) RUN_STT=0 ;;
    --skip-psirver) RUN_PSIRVER=0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $arg" >&2; usage >&2; exit 2 ;;
  esac
done

# --- Pretty output ---------------------------------------------------------
if [ -t 1 ]; then
  C_RESET=$'\033[0m'; C_INFO=$'\033[36m'; C_OK=$'\033[32m'
  C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_DIM=$'\033[2m'
else
  C_RESET=; C_INFO=; C_OK=; C_WARN=; C_ERR=; C_DIM=
fi
info() { printf '%s %s\n' "${C_INFO}[dev]${C_RESET}" "$*"; }
ok()   { printf '%s %s\n' "${C_OK}[ok]${C_RESET} " "$*"; }
warn() { printf '%s %s\n' "${C_WARN}[warn]${C_RESET}" "$*"; }
err()  { printf '%s %s\n' "${C_ERR}[err]${C_RESET}" "$*" >&2; }

# --- Service registry (parallel arrays; bash 3.2 has no assoc arrays) -------
NAMES=()
PIDS=()
SVC_PORTS=()
LOGS=()
record() { NAMES+=("$1"); PIDS+=("$2"); SVC_PORTS+=("$3"); LOGS+=("$4"); }

# --- Teardown --------------------------------------------------------------
CLEANED=0
TAIL_PID=""
cleanup() {
  [ "$CLEANED" = "1" ] && return 0
  CLEANED=1
  trap - INT TERM EXIT
  printf '\n'
  info "shutting down…"
  local i pid
  # Polite SIGTERM, newest service first.
  for (( i=${#PIDS[@]}-1; i>=0; i-- )); do
    pid="${PIDS[$i]}"
    if kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done
  sleep 2
  # SIGKILL anything that ignored SIGTERM.
  for (( i=${#PIDS[@]}-1; i>=0; i-- )); do
    pid="${PIDS[$i]}"
    if kill -0 "$pid" 2>/dev/null; then
      kill -KILL "$pid" 2>/dev/null || true
    fi
  done
  # Backstop: free the loopback ports we started on, in case a service spawned
  # a child that outlived it (e.g. a model server still holding the GPU/port).
  # Scoped to the exact ports we own and just preflighted as free.
  local p holders
  if [ "${#SVC_PORTS[@]}" -gt 0 ]; then
    for p in "${SVC_PORTS[@]}"; do
      [ -n "$p" ] || continue
      holders="$(lsof -ti tcp:"$p" 2>/dev/null || true)"
      [ -n "$holders" ] && kill -KILL $holders 2>/dev/null || true
    done
  fi
  [ -n "$TAIL_PID" ] && kill "$TAIL_PID" 2>/dev/null || true
  ok "all services stopped."
}
trap cleanup INT TERM EXIT

# --- Helpers ---------------------------------------------------------------
port_holders() { lsof -ti tcp:"$1" 2>/dev/null || true; }

# Block until a URL is reachable, or the backing process dies, or we time out.
#   wait_ready <name> <url> <timeout> <mode: health|connect> <pid>
# health  -> requires a 2xx (curl -f); use for real /health endpoints.
# connect -> any HTTP response counts as "up"; use when there's no health route.
wait_ready() {
  local name="$1" url="$2" timeout="$3" mode="$4" pid="$5"
  local waited=0
  info "waiting for $name to be ready ($url)…"
  while [ "$waited" -lt "$timeout" ]; do
    if ! kill -0 "$pid" 2>/dev/null; then
      err "$name exited before becoming ready — see ${LOG_DIR}/."
      return 1
    fi
    if [ "$mode" = "health" ]; then
      if curl -sf -o /dev/null "$url" 2>/dev/null; then ok "$name ready"; return 0; fi
    else
      if curl -s -o /dev/null "$url" 2>/dev/null; then ok "$name ready"; return 0; fi
    fi
    sleep 1
    waited=$((waited + 1))
  done
  err "$name did not become ready within ${timeout}s ($url)."
  return 1
}

ensure_venv() {
  if [ -x "$VENV/bin/python" ]; then
    return 0
  fi
  info "creating backend venv + installing deps (first run, may take a minute)…"
  python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  ( cd "$BACKEND_DIR" && "$VENV/bin/python" -m pip install --quiet -e . )
  ok "backend venv ready ($VENV)"
}

# --- Preflight -------------------------------------------------------------
mkdir -p "$LOG_DIR" "$RUN_DIR"

ERRORS=()
preflight_err() { ERRORS+=("$1"); }

info "preflight checks…"

command -v python3 >/dev/null 2>&1 || \
  preflight_err "python3 not found on PATH (needed for the FastAPI backend)."
command -v curl >/dev/null 2>&1 || \
  preflight_err "curl not found on PATH (needed for readiness probes)."

# Backend port is always used.
[ -n "$(port_holders "$BACKEND_PORT")" ] && \
  preflight_err "backend port $BACKEND_PORT in use by PID(s): $(port_holders "$BACKEND_PORT"). Stop it or set WHETSTONE_PORT."

if [ "$RUN_PSIRVER" = "1" ]; then
  [ -n "$(port_holders "$PSIRVER_PORT")" ] && \
    preflight_err "Psirver port $PSIRVER_PORT in use by PID(s): $(port_holders "$PSIRVER_PORT"). Stop it or set WHETSTONE_PSIRVER_PORT."
  if [ ! -x "$PSIRVER_BIN" ]; then
    info "Psirver binary not built — building (make -C services/psirver/src)…"
    if make -C "$PSIRVER_SRC" >"$LOG_DIR/psirver-build.log" 2>&1; then
      ok "Psirver built."
    else
      preflight_err "Psirver build failed — see $LOG_DIR/psirver-build.log (needs clang++ / Xcode CLT)."
    fi
  fi
fi

if [ "$RUN_LLM" = "1" ]; then
  [ -n "$(port_holders "$LLM_PORT")" ] && \
    preflight_err "llama-server port $LLM_PORT in use by PID(s): $(port_holders "$LLM_PORT"). Stop it or set WHETSTONE_LLM_PORT."
  command -v "$LLAMA_SERVER_BIN" >/dev/null 2>&1 || \
    preflight_err "llama-server binary '$LLAMA_SERVER_BIN' not found on PATH. Build llama.cpp (README → Getting the models) or pass --skip-llm."
  [ -f "$GEMMA_GGUF" ] || \
    preflight_err "Gemma GGUF not found at: $GEMMA_GGUF. Download it (README → Getting the models), set WHETSTONE_GEMMA_GGUF, or pass --skip-llm."
fi

if [ "$RUN_STT" = "1" ]; then
  [ -n "$(port_holders "$STT_PORT")" ] && \
    preflight_err "whisper-server port $STT_PORT in use by PID(s): $(port_holders "$STT_PORT"). Stop it or set WHETSTONE_STT_PORT."
  command -v "$WHISPER_SERVER_BIN" >/dev/null 2>&1 || \
    preflight_err "whisper-server binary '$WHISPER_SERVER_BIN' not found on PATH. Build whisper.cpp (README → Getting the models) or pass --skip-stt."
  [ -f "$WHISPER_GGML" ] || \
    preflight_err "Whisper model not found at: $WHISPER_GGML. Download it (README → Getting the models), set WHETSTONE_WHISPER_GGML, or pass --skip-stt."
fi

# Backend venv is required regardless; build it now so a pip failure stops us
# before any model server is launched.
ensure_venv || preflight_err "backend venv setup failed — see output above."

if [ "${#ERRORS[@]}" -gt 0 ]; then
  err "preflight failed — not starting anything:"
  for e in "${ERRORS[@]}"; do
    printf '      - %s\n' "$e" >&2
  done
  exit 1
fi
ok "preflight passed."

# --- Launch ----------------------------------------------------------------
# Order: services first, backend last, so the first cell-run / spec-import
# request lands on already-warm services. The backend boots even if a service
# is down (clients connect lazily), so this ordering is for warmth, not safety.

if [ "$RUN_PSIRVER" = "1" ]; then
  PSIRVER_HOME="$RUN_DIR/psirver"
  mkdir -p "$PSIRVER_HOME"
  cp "$PSIRVER_BIN" "$PSIRVER_HOME/psirver"
  info "starting Psirver on ${HOST}:${PSIRVER_PORT}…"
  # Psirver requires PSIRVER_HOME (its working dir for the pid file, scripts/,
  # and per-job scratch); it exits immediately to syslog if it's unset.
  ( cd "$PSIRVER_HOME" && exec env PSIRVER_HOME="$PSIRVER_HOME" \
      ./psirver "$PSIRVER_PORT" ) \
    >"$LOG_DIR/psirver.log" 2>&1 &
  record "Psirver" "$!" "$PSIRVER_PORT" "$LOG_DIR/psirver.log"
fi

if [ "$RUN_LLM" = "1" ]; then
  info "starting llama-server on ${HOST}:${LLM_PORT} (model: $GEMMA_GGUF)…"
  # shellcheck disable=SC2086  # LLAMA_SERVER_ARGS is intentionally word-split.
  ( exec "$LLAMA_SERVER_BIN" -m "$GEMMA_GGUF" --host "$HOST" --port "$LLM_PORT" \
      --alias "$LLM_ALIAS" $LLAMA_SERVER_ARGS ) \
    >"$LOG_DIR/llm.log" 2>&1 &
  record "llama-server" "$!" "$LLM_PORT" "$LOG_DIR/llm.log"
fi

if [ "$RUN_STT" = "1" ]; then
  info "starting whisper-server on ${HOST}:${STT_PORT} (model: $WHISPER_GGML)…"
  # shellcheck disable=SC2086  # WHISPER_SERVER_ARGS is intentionally word-split.
  ( exec "$WHISPER_SERVER_BIN" -m "$WHISPER_GGML" --host "$HOST" --port "$STT_PORT" \
      $WHISPER_SERVER_ARGS ) \
    >"$LOG_DIR/stt.log" 2>&1 &
  record "whisper-server" "$!" "$STT_PORT" "$LOG_DIR/stt.log"
fi

info "starting FastAPI backend on ${HOST}:${BACKEND_PORT}…"
( cd "$BACKEND_DIR" && exec env \
    WHETSTONE_PORT="$BACKEND_PORT" \
    WHETSTONE_PSIRVER_PORT="$PSIRVER_PORT" \
    WHETSTONE_LLM_PORT="$LLM_PORT" \
    WHETSTONE_LLM_MODEL="$LLM_ALIAS" \
    WHETSTONE_STT_PORT="$STT_PORT" \
    "$VENV/bin/python" -m uvicorn main:app --host "$HOST" --port "$BACKEND_PORT" ) \
  >"$LOG_DIR/backend.log" 2>&1 &
record "backend" "$!" "$BACKEND_PORT" "$LOG_DIR/backend.log"

# --- Readiness (in the same order) -----------------------------------------
# Each probe also fails fast if its process exits early; any failure trips the
# EXIT trap, which tears the rest down.
idx=0
for name in "${NAMES[@]}"; do
  pid="${PIDS[$idx]}"
  port="${SVC_PORTS[$idx]}"
  case "$name" in
    Psirver)
      wait_ready "$name" "http://${HOST}:${port}/jobs" "$PSIRVER_READY_TIMEOUT" health "$pid" || exit 1 ;;
    llama-server)
      wait_ready "$name" "http://${HOST}:${port}/health" "$LLM_READY_TIMEOUT" health "$pid" || exit 1 ;;
    whisper-server)
      wait_ready "$name" "http://${HOST}:${port}/" "$STT_READY_TIMEOUT" connect "$pid" || exit 1 ;;
    backend)
      wait_ready "$name" "http://${HOST}:${port}/health" "$BACKEND_READY_TIMEOUT" health "$pid" || exit 1 ;;
  esac
  idx=$((idx + 1))
done

# --- Up --------------------------------------------------------------------
printf '\n'
ok "all services up:"
idx=0
for name in "${NAMES[@]}"; do
  printf '      %-15s http://%s:%s\n' "$name" "$HOST" "${SVC_PORTS[$idx]}"
  idx=$((idx + 1))
done
printf '\n'
info "frontend (separate terminal):  ${C_DIM}cd apps/desktop && npm run tauri dev${C_RESET}"
info "logs: ${C_DIM}${LOG_DIR}/${C_RESET}    swagger: ${C_DIM}http://${HOST}:${BACKEND_PORT}/docs${C_RESET}"
info "press ${C_DIM}Ctrl-C${C_RESET} to stop everything."
printf '\n'

# Stream all service logs to the console, then watch for a service dying.
tail -n +1 -F "${LOGS[@]}" &
TAIL_PID=$!

while true; do
  idx=0
  for name in "${NAMES[@]}"; do
    if ! kill -0 "${PIDS[$idx]}" 2>/dev/null; then
      warn "$name exited — shutting the rest down."
      exit 1
    fi
    idx=$((idx + 1))
  done
  sleep 2
done
