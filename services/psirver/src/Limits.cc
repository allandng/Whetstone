#include "Limits.hh"

#include <cstdlib>

// Read an unsigned environment override, multiplied by `scale` (e.g. MB ->
// bytes). Returns `dflt` when the variable is unset or not a number.
static rlim_t env_rlim(const char *name, rlim_t dflt, rlim_t scale)
{
  const char *v = std::getenv(name);
  if (!v || !*v) {
    return dflt;
  }
  char *end = nullptr;
  unsigned long long n = std::strtoull(v, &end, 10);
  if (end == v) {
    return dflt; // not a number
  }
  return static_cast<rlim_t>(n) * scale;
}

static unsigned env_uint(const char *name, unsigned dflt)
{
  const char *v = std::getenv(name);
  if (!v || !*v) {
    return dflt;
  }
  char *end = nullptr;
  unsigned long n = std::strtoul(v, &end, 10);
  if (end == v) {
    return dflt;
  }
  return static_cast<unsigned>(n);
}

const JobLimits &job_limits()
{
  // Resolved once on first use (thread-safe in C++11+).
  static const JobLimits limits = [] {
    JobLimits l;
    // 10 s of CPU: an intro assignment finishes in well under a second; a busy
    // loop is caught quickly via SIGXCPU.
    l.cpu_seconds = env_rlim("PSIRVER_LIMIT_CPU_SECONDS", 10, 1);
    // 2 GiB of virtual address space. Generous enough that clang++ and a normal
    // Python/C++ program (whose runtimes reserve large virtual ranges they
    // never touch) run fine, but a genuine multi-GB runaway is caught on Linux.
    // NOTE: RLIMIT_AS is a no-op on macOS -- the wall-clock cap is the
    // cross-platform backstop for memory runaways. 0 disables the cap.
    l.address_bytes =
        env_rlim("PSIRVER_LIMIT_AS_MB", 2048, 1024ull * 1024ull);
    // 64 MiB per output file: ample for legitimate assignment output, but an
    // unbounded print loop trips SIGXFSZ instead of filling the disk.
    l.file_bytes = env_rlim("PSIRVER_LIMIT_FSIZE_MB", 64, 1024ull * 1024ull);
    // 15 s wall clock catches a job that sleeps/blocks (and so never trips the
    // CPU cap). Kept well under the backend's ~30 s poll ceiling so the job
    // terminates and is reported, rather than the backend giving up first.
    l.wall_seconds = env_uint("PSIRVER_LIMIT_WALL_SECONDS", 15);
    // Grace between SIGTERM and SIGKILL, so a well-behaved job can flush and
    // exit, but one that ignores SIGTERM (or keeps re-forking) is force-killed.
    l.kill_grace_seconds = env_uint("PSIRVER_LIMIT_KILL_GRACE_SECONDS", 3);
    return l;
  }();
  return limits;
}

// Set one rlimit to a hard+soft cap of `value`; 0 means "leave unset".
static void set_one(int resource, rlim_t value)
{
  if (value == 0) {
    return;
  }
  struct rlimit r;
  r.rlim_cur = value;
  r.rlim_max = value;
  ::setrlimit(resource, &r); // best effort; not all caps exist on every OS
}

void apply_rlimits(const JobLimits &l)
{
  set_one(RLIMIT_CPU, l.cpu_seconds);
  set_one(RLIMIT_FSIZE, l.file_bytes);
  set_one(RLIMIT_AS, l.address_bytes);

  // No core dumps: a job killed by SIGXCPU/SIGXFSZ/SIGSEGV must not dump a huge
  // core into its scratch dir.
  struct rlimit none;
  none.rlim_cur = 0;
  none.rlim_max = 0;
  ::setrlimit(RLIMIT_CORE, &none);
}
