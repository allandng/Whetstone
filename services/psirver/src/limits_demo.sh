#!/usr/bin/env bash
#
# limits_demo.sh -- demonstrate the v1.0 per-job execution limits (NFR-SEC-1).
#
# Builds Psirver, launches it with deliberately *tight* limits (so the demo
# finishes in seconds rather than at the production defaults), then submits a
# battery of abusive jobs and checks each one is contained instead of running
# unbounded:
#
#   cpu      busy loop            -> RLIMIT_CPU  (SIGXCPU)        -> FAILED
#   output   infinite print       -> RLIMIT_FSIZE (SIGXFSZ)      -> FAILED
#   mem      runaway allocation   -> RLIMIT_AS (Linux) /         -> FAILED or
#                                    wall-clock (macOS)              TERMINATED
#   sleep    blocks, no CPU       -> wall-clock deadline         -> TERMINATED
#   fork     spawns a process tree-> process-group SIGKILL       -> TERMINATED
#                                    (whole tree dies)
#   env      prints its env/cwd   -> minimal env, scratch cwd    -> COMPLETED
#   hello    normal python        -> no false positive          -> COMPLETED
#   hellocpp normal C++           -> compile+run still works     -> COMPLETED
#
# Usage:  ./limits_demo.sh
set -u

PORT="${PORT:-8077}"
BASE="http://127.0.0.1:${PORT}"
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/psirver_demo.XXXXXX")"
SRV_PID=""
FAILS=0

cleanup() {
  [ -n "$SRV_PID" ] && kill "$SRV_PID" 2>/dev/null
  # Reap any stragglers from the fork demo, just in case.
  pkill -f "psirver_demo.*forkbomb_demo.py" 2>/dev/null
  # UploadTask makes script dirs/files read-only, so restore write before rm.
  chmod -R u+rwx "$WORK" 2>/dev/null
  rm -rf "$WORK"
}
trap cleanup EXIT

say()  { printf '\n=== %s ===\n' "$*"; }
pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*"; FAILS=$((FAILS + 1)); }

# Extract one top-level field from a JSON object on stdin.
jget() { python3 -c "import sys,json;print(json.load(sys.stdin).get('$1',''))"; }

upload() { # $1 = path to script file -> prints script id
  curl -s -F "file=@$1" "$BASE/scripts/upload"
}
run() {    # $1 = script id, $2 = lang -> prints job id
  curl -s -X POST --data "lang=$2&args=" "$BASE/scripts/$1/run" | jget job_id
}
status() { curl -s "$BASE/jobs/$1"; }

wait_terminal() { # $1 = job id -> prints final status, waits up to ~20s
  local j s
  for _ in $(seq 1 100); do
    j="$(status "$1")"
    s="$(printf '%s' "$j" | jget status)"
    case "$s" in COMPLETED|FAILED|TERMINATED) printf '%s' "$s"; return 0;; esac
    sleep 0.2
  done
  printf '%s' "$s"
}

submit() { # $1 = script file, $2 = lang -> prints job id
  local sid
  sid="$(upload "$1")"
  run "$sid" "$2"
}

# --- build ----------------------------------------------------------------
say "Building Psirver"
make -C "$HERE" >/dev/null || { echo "build failed"; exit 1; }

# --- launch with tight limits --------------------------------------------
say "Launching Psirver on :$PORT with tight demo limits"
export PSIRVER_HOME="$WORK"
export PSIRVER_LIMIT_CPU_SECONDS=2
export PSIRVER_LIMIT_WALL_SECONDS=3
export PSIRVER_LIMIT_FSIZE_MB=8
export PSIRVER_LIMIT_AS_MB=256
export PSIRVER_LIMIT_KILL_GRACE_SECONDS=1
# A fake secret in the server's environment: the child must NOT inherit it.
export PSIRVER_FAKE_SECRET="topsecret-should-not-leak"

"$HERE/psirver" "$PORT" &
SRV_PID=$!
for _ in $(seq 1 50); do
  curl -s "$BASE/health" >/dev/null 2>&1 && break
  sleep 0.1
done
curl -s "$BASE/health" >/dev/null 2>&1 || { echo "server did not come up"; exit 1; }
echo "up (pid $SRV_PID), limits: cpu=2s wall=3s fsize=8MB as=256MB grace=1s"

# --- write the demo scripts ----------------------------------------------
cat > "$WORK/cpu.py"   <<'PY'
while True:
    pass
PY
cat > "$WORK/output.py" <<'PY'
while True:
    print("A" * 4096)
PY
cat > "$WORK/mem.py" <<'PY'
import time
hog = []
while True:
    hog.append(bytearray(10 * 1024 * 1024))  # 10 MB at a time
    time.sleep(0.05)
PY
cat > "$WORK/sleep.py" <<'PY'
import time
time.sleep(60)
PY
cat > "$WORK/forkbomb_demo.py" <<'PY'
import os, time
for _ in range(20):
    if os.fork() == 0:
        while True:
            time.sleep(1)
while True:
    time.sleep(1)
PY
cat > "$WORK/env.py" <<'PY'
import os
print("CWD", os.getcwd())
for k in sorted(os.environ):
    print("ENV", k)
PY
cat > "$WORK/hello.py" <<'PY'
print("hello world")
PY
cat > "$WORK/hello.cpp" <<'CPP'
#include <cstdio>
int main() { std::printf("hello from c++\n"); return 0; }
CPP

# --- CPU-bound ------------------------------------------------------------
say "CPU-bound busy loop (expect FAILED via RLIMIT_CPU)"
jid="$(submit "$WORK/cpu.py" python)"
st="$(wait_terminal "$jid")"
[ "$st" = FAILED ] && pass "cpu loop -> $st" || fail "cpu loop -> $st (want FAILED)"

# --- output flood ---------------------------------------------------------
say "Output flood (expect FAILED via RLIMIT_FSIZE, capped file)"
jid="$(submit "$WORK/output.py" python)"
st="$(wait_terminal "$jid")"
sz=$(wc -c < "$WORK/jobs/${jid}.out" 2>/dev/null | tr -d ' ')
if [ "$st" = FAILED ] && [ "${sz:-0}" -le 9000000 ]; then
  pass "output flood -> $st, capture file capped at ${sz} bytes (<= ~8MB)"
else
  fail "output flood -> $st, file=${sz} bytes (want FAILED, <=~8MB)"
fi

# --- memory hog -----------------------------------------------------------
say "Memory hog (expect FAILED on Linux/RLIMIT_AS or TERMINATED on macOS/wall)"
jid="$(submit "$WORK/mem.py" python)"
st="$(wait_terminal "$jid")"
case "$st" in
  FAILED|TERMINATED) pass "memory hog -> $st (contained, not unbounded)";;
  *) fail "memory hog -> $st (want FAILED or TERMINATED)";;
esac

# --- blocking sleep -------------------------------------------------------
say "Blocking sleep, no CPU (expect TERMINATED via wall-clock)"
jid="$(submit "$WORK/sleep.py" python)"
st="$(wait_terminal "$jid")"
[ "$st" = TERMINATED ] && pass "sleep -> $st" || fail "sleep -> $st (want TERMINATED)"

# --- process tree / fork containment -------------------------------------
say "Process tree (fork) -> whole group is reliably killable"
sid="$(upload "$WORK/forkbomb_demo.py")"
jid="$(run "$sid" python)"
sleep 0.8
before=$(pgrep -f forkbomb_demo.py | wc -l | tr -d ' ')
curl -s -X POST "$BASE/jobs/$jid/terminate" >/dev/null
st="$(wait_terminal "$jid")"
sleep 0.3
after=$(pgrep -f forkbomb_demo.py | wc -l | tr -d ' ')
if [ "$st" = TERMINATED ] && [ "${before:-0}" -ge 2 ] && [ "${after:-1}" -eq 0 ]; then
  pass "fork tree -> $st, processes ${before} -> ${after} (entire group killed)"
else
  fail "fork tree -> $st, processes ${before} -> ${after} (want TERMINATED, N -> 0)"
fi

# --- environment minimization + scratch cwd ------------------------------
say "Environment minimization (expect no leaked secret, scratch cwd)"
jid="$(submit "$WORK/env.py" python)"
st="$(wait_terminal "$jid")"
out="$(status "$jid" | jget stdout)"
if [ "$st" = COMPLETED ] && ! printf '%s' "$out" | grep -q PSIRVER_FAKE_SECRET \
   && printf '%s' "$out" | grep -q "CWD .*/jobs/"; then
  pass "env -> $st, secret not leaked, cwd is per-job scratch"
  printf '%s\n' "$out" | sed 's/^/      /'
else
  fail "env -> $st (want COMPLETED, no secret, scratch cwd)"
  printf '%s\n' "$out" | sed 's/^/      /'
fi

# --- normal jobs (no false positives) ------------------------------------
say "Normal python job (expect COMPLETED)"
jid="$(submit "$WORK/hello.py" python)"
st="$(wait_terminal "$jid")"
out="$(status "$jid" | jget stdout)"
if [ "$st" = COMPLETED ] && printf '%s' "$out" | grep -q "hello world"; then
  pass "hello.py -> $st"
else
  fail "hello.py -> $st out='$out' (want COMPLETED/hello world)"
fi

say "Normal C++ job (expect COMPLETED -- compile+run survives the sandbox)"
jid="$(submit "$WORK/hello.cpp" cpp)"
st="$(wait_terminal "$jid")"
out="$(status "$jid" | jget stdout)"
if [ "$st" = COMPLETED ] && printf '%s' "$out" | grep -q "hello from c++"; then
  pass "hello.cpp -> $st"
else
  fail "hello.cpp -> $st out='$out' (want COMPLETED/hello from c++)"
fi

# --- summary --------------------------------------------------------------
say "Summary"
if [ "$FAILS" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$FAILS CHECK(S) FAILED"
fi
exit "$FAILS"
