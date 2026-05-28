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
