#!/usr/bin/env bash
#
# Psirver integration smoke test. Starts the built server in a throwaway
# PSIRVER_HOME on a private port, exercises the job API and the hardening
# behaviours, and exits non-zero on the first failure. Invoked by `make test`.
#
# No external deps beyond curl, nc, and a POSIX shell.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$SCRIPT_DIR/psirver"
PORT="${PSIRVER_TEST_PORT:-8099}"
HOST="127.0.0.1"
BASE="http://$HOST:$PORT"
HOME_DIR="$(mktemp -d "${TMPDIR:-/tmp}/psirver_test.XXXXXX")"

PASS=0
FAIL=0
ok()   { printf '  ok   %s\n' "$1"; PASS=$((PASS + 1)); }
bad()  { printf '  FAIL %s\n' "$1"; FAIL=$((FAIL + 1)); }

cleanup() {
  [ -n "${PSIRVER_PID:-}" ] && kill "$PSIRVER_PID" 2>/dev/null
  # Backstop: free the port if the child outlived the signal.
  local h; h="$(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  [ -n "$h" ] && kill -9 $h 2>/dev/null
  # Psirver makes per-script dirs read-only, so make them writable before rm.
  chmod -R u+rwx "$HOME_DIR" 2>/dev/null
  rm -rf "$HOME_DIR"
}
trap cleanup EXIT INT TERM

[ -x "$BIN" ] || { echo "psirver binary not built ($BIN); run make first" >&2; exit 2; }

# A short wall/CPU cap so the runaway test finishes quickly.
export PSIRVER_LIMIT_WALL_SECONDS=4
export PSIRVER_LIMIT_CPU_SECONDS=3

( cd "$HOME_DIR" && exec env PSIRVER_HOME="$HOME_DIR" "$BIN" "$PORT" ) >"$HOME_DIR/server.log" 2>&1 &
PSIRVER_PID=$!

# Wait for readiness (server up on /jobs).
ready=0
for _ in $(seq 1 50); do
  if curl -sf -o /dev/null "$BASE/jobs" 2>/dev/null; then ready=1; break; fi
  if ! kill -0 "$PSIRVER_PID" 2>/dev/null; then echo "server exited early; log:" >&2; cat "$HOME_DIR/server.log" >&2; exit 2; fi
  sleep 0.1
done
[ "$ready" = 1 ] || { echo "server did not become ready" >&2; cat "$HOME_DIR/server.log" >&2; exit 2; }

# --- Helpers ----------------------------------------------------------------
# Upload a script, returning its id. Args: <filename> <source>
upload() {
  curl -s -X POST "$BASE/scripts/upload" \
    -F "file=@-;filename=$1" <<<"$2" | tr -d '[:space:]'
}
# Run a script. Args: <script_id> <lang> -> prints job_id
run_script() {
  curl -s -X POST "$BASE/scripts/$1/run" --data "lang=$2&args=" \
    | sed -n 's/.*"job_id"[[:space:]]*:[[:space:]]*\([0-9]*\).*/\1/p'
}
# Poll a job until terminal (or timeout). Prints the final JSON.
poll() {
  local jid="$1" i json status
  for i in $(seq 1 100); do
    json="$(curl -s "$BASE/jobs/$jid")"
    status="$(printf '%s' "$json" | sed -n 's/.*"status"[[:space:]]*:[[:space:]]*"\([A-Z]*\)".*/\1/p')"
    case "$status" in COMPLETED|FAILED|TERMINATED) printf '%s' "$json"; return 0 ;; esac
    sleep 0.1
  done
  printf '%s' "$json"
}
server_alive() { curl -sf -o /dev/null "$BASE/jobs" 2>/dev/null; }

# --- Tests ------------------------------------------------------------------

# 1. Python execution
sid="$(upload script.py 'print(2 + 40)')"
jid="$(run_script "$sid" python)"
res="$(poll "$jid")"
case "$res" in *'"status": "COMPLETED"'*|*'"status":"COMPLETED"'*) ok "python job completes" ;; *) bad "python job completes ($res)" ;; esac
case "$res" in *42*) ok "python stdout captured" ;; *) bad "python stdout captured ($res)" ;; esac

# 2. C++ execution (regression net for the rlimit-scaling fix: a too-small
#    FSIZE/AS default would fail the clang++ compile here).
sid="$(upload script.cpp '#include <iostream>
int main(){ long s=0; for(int i=1;i<=100;i++) s+=i; std::cout<<s<<std::endl; }')"
jid="$(run_script "$sid" cpp)"
res="$(poll "$jid")"
case "$res" in *COMPLETED*) ok "c++ compiles and runs" ;; *) bad "c++ compiles and runs ($res)" ;; esac
case "$res" in *5050*) ok "c++ stdout captured" ;; *) bad "c++ stdout captured ($res)" ;; esac

# 3. Large output (regression net for the 1 GiB FSIZE default).
sid="$(upload big.py "print('x' * 5000)")"
jid="$(run_script "$sid" python)"
res="$(poll "$jid")"
case "$res" in *COMPLETED*) ok "large output not truncated by FSIZE" ;; *) bad "large output ($res)" ;; esac

# 4. Runaway loop is contained by the wall/CPU cap (not COMPLETED).
sid="$(upload loop.py 'while True: pass')"
jid="$(run_script "$sid" python)"
res="$(poll "$jid")"
case "$res" in *COMPLETED*) bad "runaway loop should not COMPLETE ($res)" ;; *) ok "runaway loop contained" ;; esac

# 5. Path-traversal upload is rejected and writes nothing outside scripts/.
code="$(printf 'POST /scripts/upload HTTP/1.1\r\nHost: x\r\nContent-Type: multipart/form-data; boundary=B\r\nContent-Length: 128\r\n\r\n--B\r\nContent-Disposition: form-data; name="file"; filename="../../escaped.txt"\r\n\r\nhi\r\n--B--\r\n' | nc -w2 "$HOST" "$PORT" | head -1)"
case "$code" in *400*) ok "traversal filename rejected (400)" ;; *) bad "traversal filename rejected ($code)" ;; esac
[ -e "$HOME_DIR/../escaped.txt" ] && bad "traversal escaped the home dir" || ok "traversal wrote nothing outside home"

# 6. SIGPIPE: clients that disconnect before reading the reply must not crash it.
for _ in 1 2 3 4 5; do printf 'GET /jobs HTTP/1.1\r\nHost: x\r\n\r\n' | nc -w1 "$HOST" "$PORT" >/dev/null 2>&1 & done
sleep 1
server_alive && ok "survives early client disconnects (SIGPIPE)" || bad "server died on early disconnect"

# 7. Malformed requests get a clean status and don't crash the server.
code="$(printf 'DELETE /jobs HTTP/1.1\r\nHost: x\r\n\r\n' | nc -w2 "$HOST" "$PORT" | head -1)"
case "$code" in *405*) ok "unsupported method -> 405" ;; *) bad "unsupported method ($code)" ;; esac
code="$(printf 'POST /scripts/upload HTTP/1.1\r\nHost: x\r\n\r\n' | nc -w2 "$HOST" "$PORT" | head -1)"
case "$code" in *411*) ok "missing Content-Length -> 411" ;; *) bad "missing Content-Length ($code)" ;; esac
server_alive && ok "server alive after malformed requests" || bad "server died on malformed request"

# --- Summary ----------------------------------------------------------------
echo
echo "psirver test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
