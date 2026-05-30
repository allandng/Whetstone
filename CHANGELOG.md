# Changelog

All notable changes to Whetstone are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-05-30

First release. Whetstone is a local-first, offline CS problem-solving
environment — a notebook workspace, an on-device AI tutor, and a replayable
session timeline, all running on the user's own machine.

### Added

- **Code execution** through Psirver, a C++ `fork`/`exec` job server: Python and
  C++ cells with captured stdout/stderr, status, and termination reason.
- **Notebook workspace** — run, edit, and add cells; cells are restored when a
  session is reopened.
- **Spec import → requirement tracking** — import a PDF or text assignment spec
  and turn it into a tracked checklist of requirements.
- **On-device LLM co-pilot** (llama.cpp / Gemma) in two modes: **Direct**
  (answers, with a full-solution academic-integrity banner) and **Socratic**
  (guiding questions and a graded hint ladder).
- **Session event log + timeline**, including a **step-back replay scrubber**
  that reconstructs session state at any past event (view-only — it never
  re-runs code or re-calls the model).
- **On-device voice dictation** into the co-pilot prompt (whisper.cpp).

### Security & hardening

- Per-job resource limits in Psirver — CPU time, wall-clock, address space, file
  size, and no core dumps — plus file-descriptor hygiene and a scrubbed child
  environment: the v1.0 execution "security floor" (SRS NFR-SEC-1).
- Psirver's `RLIMIT_FSIZE` now defaults to 1 GiB so `clang++` can compile C++
  cells on macOS; the headroom is inherited by every launch path rather than
  living only in the dev launcher.
- CORS restricted to the Tauri frontend origins (no wildcard), and loud-failure
  error handling so a dead service returns a clean 503 rather than a 500.

### Tooling & packaging

- One-command dev launcher (`make dev` / `scripts/dev.sh`) that brings up all
  four local services with preflight checks, readiness probes, and clean teardown.
- macOS (Apple Silicon) Tauri bundle via `make bundle` — packages the UI shell;
  the backend and model servers run separately.
- CI covering the backend and frontend test suites.

### Fixed

- Psirver `select_port` now accepts ports above 32767. The value was parsed into
  a signed 16-bit temporary, so a high port wrapped negative and was rejected.

### Known limitations

See the **Known limitations** section of the [README](README.md). In brief: the
co-pilot mode resets to Direct on a full reload; the integrity marker is
best-effort on a small model; the workspace breadcrumb is a cosmetic
`scratchpad.cpp` label; the bundle ships the UI shell only; and the
model-quality eval numbers are still provisional.

[1.0.0]: https://github.com/allandng/Whetstone/releases/tag/v1.0.0
