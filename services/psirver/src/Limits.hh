#pragma once
#include <sys/resource.h>

// Per-job execution limits -- the v1.0 "security floor" (SRS NFR-SEC-1).
//
// These caps contain *runaway or accidentally-abusive* student code: an
// infinite loop, a runaway allocation, an output flood, a stray fork. They are
// deliberately NOT a sandbox against a determined local attacker who already
// controls the machine (see services/psirver/README.md for the threat model).
//
// Defaults are sized for a single-file Python / C++ assignment. Each value can
// be overridden at startup via an environment variable, so an operator can
// retune without recompiling. A value of 0 disables that particular cap.
struct JobLimits {
  rlim_t   cpu_seconds;        // PSIRVER_LIMIT_CPU_SECONDS      -> RLIMIT_CPU
  rlim_t   address_bytes;      // PSIRVER_LIMIT_AS_MB            -> RLIMIT_AS
  rlim_t   file_bytes;         // PSIRVER_LIMIT_FSIZE_MB        -> RLIMIT_FSIZE
  unsigned wall_seconds;       // PSIRVER_LIMIT_WALL_SECONDS    -> reaper deadline
  unsigned kill_grace_seconds; // PSIRVER_LIMIT_KILL_GRACE_SECONDS -> SIGTERM->SIGKILL
};

// Resolve the limits once: compile-time defaults overlaid with any environment
// overrides. Safe to call from any thread; reads getenv() and must therefore be
// called in the parent, never in the post-fork child.
const JobLimits &job_limits();

// Apply the rlimit-based caps (CPU, address space, file size, no core dumps) to
// the *current* process. Call in the forked child after fork() and before
// exec(): it uses only async-signal-safe calls, so it is safe in the child of a
// multithreaded server. Failures are ignored (best effort).
void apply_rlimits(const JobLimits &limits);
