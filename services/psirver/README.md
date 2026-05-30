# Psirver

**Psirver**, the C++ code-execution backend.

Psirver is a standalone HTTP server (originally written for an Operating
Systems course) that runs submitted scripts as isolated jobs using
`fork`/`execvp`, capturing stdout/stderr, status, and supporting
termination. The Whetstone backend talks to it over loopback
(`127.0.0.1`) via `apps/backend/services/psirver_client.py`.

The C++ source lives in [`src/`](./src). Build and run:

```sh
cd src
make
export PSIRVER_HOME="$PWD/run"   # working dir for pid file, scripts/, jobs/
mkdir -p "$PSIRVER_HOME"
cp psirver "$PSIRVER_HOME"/
( cd "$PSIRVER_HOME" && ./psirver 8080 )   # binds 127.0.0.1:8080
```

The server binds to `127.0.0.1` only (asserted in `init_socket`) and never
on a routable interface.

## HTTP API

| Method | Path | Description |
| ------ | ---- | ----------- |
| `POST` | `/scripts/upload` | Multipart upload (`file` field). Returns the script id. |
| `GET`  | `/scripts` | List uploaded scripts. |
| `GET`  | `/scripts/{id}/delete` | Delete a script. |
| `POST` | `/scripts/{id}/run` | Start the script **asynchronously**. Body (`x-www-form-urlencoded`): `lang=python\|cpp` and optional `args=a,b,c`. Replies `202 Accepted` with `{"job_id": N}`. |
| `GET`  | `/jobs` | List jobs. |
| `GET`  | `/jobs/{id}` | Job status: `{job_id, status, stdout, stderr, exit_code}`. |
| `GET`  | `/jobs/{id}/stdout`, `/jobs/{id}/stderr` | Raw captured streams. |
| `POST` | `/jobs/{id}/terminate` | Send `SIGTERM` to a running job (also accepted as `GET`). |

## Async job model

Each run forks a child whose stdout/stderr are redirected (via `dup2`) to
per-job capture files under `jobs/`. For `python`, the child execs
`python3`; for `cpp`, it compiles with `clang++` and then execs the
resulting binary (compiler diagnostics land in the job's stderr). The
request thread does **not** `waitpid()`; a background reaper thread collects
exited children and transitions each job:

```
QUEUED -> RUNNING -> COMPLETED | FAILED | TERMINATED
```

The job table lives in `JobManager` (`src/Jobs.{hh,cc}`), an
`unordered_map<int, Job>` guarded by a mutex. Routing keeps the Factory
Method pattern (`Task::construct` in `src/TaskFactory.cc`).

## Execution limits (v1.0 security floor)

Psirver runs submitted code -- which may be AI-suggested -- so an unguarded
child could trivially take down the host with an infinite loop, a runaway
allocation, an output flood, or a stray `fork`. The v1.0 floor (SRS NFR-SEC-1)
contains those cases. Before `exec()`, each forked child (`RunTask::execute` in
`src/Tasks.cc`) is wrapped as follows:

- **Resource caps** (`apply_rlimits` in `src/Limits.cc`): `setrlimit` for
  `RLIMIT_CPU` (CPU seconds), `RLIMIT_AS` (virtual address space),
  `RLIMIT_FSIZE` (max bytes any single file may grow), and `RLIMIT_CORE = 0`
  (no core dumps from a killed runaway).
- **Wall-clock deadline**: `RLIMIT_CPU` only catches code that *burns* CPU; a
  job that sleeps or blocks on I/O would hang forever. The reaper thread
  (`JobManager::enforce_limits_locked`) enforces a hard wall-clock deadline,
  reusing the existing terminate path -- `SIGTERM` the job's process group, then
  `SIGKILL` after a grace window -- so a timed-out job surfaces as `TERMINATED`
  instead of hanging. (The Whetstone backend's own ~30 s poll ceiling sits
  *above* this deadline, so Psirver always terminates the job first.)
- **Private working directory**: the child `chdir`s into a per-job scratch dir
  (`jobs/<id>/`); the compiled C++ binary and any stray writes land there, and
  `HOME`/`TMPDIR` point at it.
- **Minimal environment**: the child does *not* inherit the server's
  environment (which may hold secrets/tokens). It is handed only `PATH` (so
  `execvp` can find `python3`/`clang++`), `HOME`, `TMPDIR`, and a few `LANG`/
  `PYTHON*` hints. (On macOS the system re-injects a non-sensitive
  `__CF_USER_TEXT_ENCODING` locale hint; that is expected and harmless.)
- **File-descriptor hygiene**: `stdin` is redirected from `/dev/null`,
  `stdout`/`stderr` go to the per-job capture files, and every other inherited
  descriptor (the listening socket, the request's client socket) is closed so
  the job cannot reach the server's fds.
- **Own process group**: each job is its own process group leader, so the whole
  subtree -- including a fork-bomb attempt or the C++ compile/run pair -- is
  killed as a unit (`kill(-pgid, ...)`). This is what makes a multi-process
  runaway *reliably* killable.

### Configuration

Defaults suit a single-file Python/C++ assignment and can be overridden at
startup via environment variables (resolved once in `job_limits()`):

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `PSIRVER_LIMIT_CPU_SECONDS` | `10` | `RLIMIT_CPU` soft+hard cap |
| `PSIRVER_LIMIT_AS_MB` | `2048` | `RLIMIT_AS` (virtual memory); `0` disables |
| `PSIRVER_LIMIT_FSIZE_MB` | `64` | `RLIMIT_FSIZE` per-file cap |
| `PSIRVER_LIMIT_WALL_SECONDS` | `15` | reaper wall-clock deadline; `0` disables |
| `PSIRVER_LIMIT_KILL_GRACE_SECONDS` | `3` | `SIGTERM` -> `SIGKILL` escalation window |

The `RLIMIT_AS` default is deliberately generous: clang++ and language runtimes
*reserve* large virtual ranges they never touch, so too tight a cap fails
legitimate work. 2 GiB lets a normal compile/run through while still catching a
genuine multi-GB allocation. **Caveat:** `RLIMIT_AS` is enforced on Linux (the
realistic deployment) but is effectively a *no-op on macOS* -- there the
wall-clock deadline is the backstop that contains a memory runaway. There is no
`RLIMIT_NPROC` cap because it is a per-real-user absolute count that would break
a normal multi-process desktop; fork containment instead comes from
process-group `SIGKILL` (and, on Linux, cgroup `pids.max` is the proper knob if
stricter isolation is ever required).

### Threat model

This is a **local, single-user** application: Psirver binds `127.0.0.1` only,
and the only client is the Whetstone backend on the same machine. The goal of
these limits is to **contain runaway or accidentally-abusive code** -- a student
(or an AI suggestion) producing an infinite loop, a memory hog, an output
flood, or an unintended `fork` -- so a bad cell degrades into a `FAILED` /
`TERMINATED` job instead of taking down the host.

The limits are **explicitly not** a security sandbox against a *determined local
attacker who already controls the machine*. Such an attacker has the user's own
privileges and can bypass these process-level caps; defending against them is a
non-goal at v1.0. Stated plainly so the limits are not mistaken for more than
they are.

#### Out of scope (v1.0)

- **Filesystem isolation.** The job runs as the same user and can read files
  that user can read; the scratch `chdir` and minimal env reduce accidental
  blast radius but are not a chroot/jail. (Future: a `chroot`/container or a
  dedicated low-privilege `psirver` user.)
- **Network isolation.** A job may open outbound sockets. (Future: a network
  namespace or seccomp filter on Linux.)
- **Syscall filtering.** No seccomp-bpf allowlist; a job may invoke any syscall
  available to the user.
- **Privilege separation.** Psirver runs as the invoking user, not a dedicated
  unprivileged account.
- **Defeating a determined local attacker**, side channels, or hardening of the
  HTTP parser beyond existing bounds.
- **`RLIMIT_AS` on macOS** (no-op; see the caveat above).

### Verifying containment

`src/limits_demo.sh` builds Psirver, launches it with deliberately tight limits,
and submits a battery of abusive jobs (CPU loop, output flood, memory hog,
blocking sleep, fork tree, plus normal Python/C++ jobs as no-false-positive
controls), asserting each is contained:

```sh
cd src
./limits_demo.sh   # prints PASS/FAIL per case, exits non-zero on any failure
```
