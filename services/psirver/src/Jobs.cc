#include "Jobs.hh"

#include <cerrno>
#include <chrono>
#include <csignal>
#include <ctime>
#include <string>
#include <sys/stat.h>
#include <sys/wait.h>

#include "Limits.hh"
#include "utils.hh"

JobManager job_manager;

const char *to_string(JobStatus status)
{
  switch (status) {
    case JobStatus::Queued:     return "QUEUED";
    case JobStatus::Running:    return "RUNNING";
    case JobStatus::Completed:  return "COMPLETED";
    case JobStatus::Failed:     return "FAILED";
    case JobStatus::Terminated: return "TERMINATED";
  }
  return "UNKNOWN";
}

void JobManager::start()
{
  ::mkdir(JOBS_PATH, S_IRWXU); // best effort; EEXIST is fine

  bool expected = false;
  if (running_.compare_exchange_strong(expected, true)) {
    reaper_ = std::thread([this]() { reaper_loop(); });
    reaper_.detach();
  }
}

int JobManager::create(int script_id)
{
  std::lock_guard<std::mutex> lock(mu_);
  const int id = next_id_++;

  Job job;
  job.job_id = id;
  job.script_id = script_id;
  job.status = JobStatus::Queued;
  job.stdout_path = std::string(JOBS_PATH) + std::to_string(id) + ".out";
  job.stderr_path = std::string(JOBS_PATH) + std::to_string(id) + ".err";

  jobs_[id] = job;
  return id;
}

void JobManager::set_running(int job_id, pid_t pid)
{
  std::lock_guard<std::mutex> lock(mu_);
  auto it = jobs_.find(job_id);
  if (it == jobs_.end()) {
    return;
  }

  it->second.pid = pid;
  it->second.status = JobStatus::Running;
  it->second.started_at = std::chrono::steady_clock::now();

  // The child may have exited before we got here; apply any buffered status.
  auto pe = pending_exits_.find(pid);
  if (pe != pending_exits_.end()) {
    apply_status_locked(it->second, pe->second);
    pending_exits_.erase(pe);
  }
}

bool JobManager::get(int job_id, Job &out) const
{
  std::lock_guard<std::mutex> lock(mu_);
  auto it = jobs_.find(job_id);
  if (it == jobs_.end()) {
    return false;
  }
  out = it->second;
  return true;
}

bool JobManager::request_terminate(int job_id)
{
  std::lock_guard<std::mutex> lock(mu_);
  auto it = jobs_.find(job_id);
  if (it == jobs_.end()) {
    return false;
  }

  Job &job = it->second;
  if (job.status == JobStatus::Running && job.pid > 0 && !job.sigterm_at) {
    job.termination_requested = true;
    job.sigterm_at = std::chrono::steady_clock::now();
    // Signal the whole process group (the child is its group leader) so a
    // multi-process job -- a fork-bomb attempt, or the C++ compile/run pair --
    // dies as a unit. The reaper escalates to SIGKILL if SIGTERM is ignored.
    ::kill(-job.pid, SIGTERM);
  }
  return true;
}

std::vector<Job> JobManager::list() const
{
  std::lock_guard<std::mutex> lock(mu_);
  std::vector<Job> out;
  out.reserve(jobs_.size());
  for (const auto &kv : jobs_) {
    out.push_back(kv.second);
  }
  return out;
}

void JobManager::on_child_exit(pid_t pid, int wait_status)
{
  std::lock_guard<std::mutex> lock(mu_);
  for (auto &kv : jobs_) {
    if (kv.second.pid == pid && kv.second.status == JobStatus::Running) {
      apply_status_locked(kv.second, wait_status);
      return;
    }
  }
  // The child finished before set_running() recorded its pid; buffer it.
  pending_exits_[pid] = wait_status;
}

void JobManager::apply_status_locked(Job &job, int wait_status)
{
  if (WIFEXITED(wait_status)) {
    const int code = WEXITSTATUS(wait_status);
    job.exit_code = code;
    if (job.termination_requested) {
      job.status = JobStatus::Terminated;
    } else {
      job.status = (code == 0) ? JobStatus::Completed : JobStatus::Failed;
    }
  } else if (WIFSIGNALED(wait_status)) {
    const int sig = WTERMSIG(wait_status);
    job.exit_code = 128 + sig; // conventional shell encoding
    job.status = (job.termination_requested || sig == SIGTERM)
                   ? JobStatus::Terminated
                   : JobStatus::Failed;
  }
}

// Enforce per-job wall-clock deadlines and push pending terminations through
// to SIGKILL. Called once per reaper tick with mu_ held.
//
// setrlimit(RLIMIT_CPU) only catches a job that burns CPU; a job that sleeps or
// blocks on I/O would otherwise hang forever. The wall-clock deadline here is
// the backstop, and it reuses the same terminate path (SIGTERM the group, then
// SIGKILL after a grace window) so a timed-out job surfaces as TERMINATED.
void JobManager::enforce_limits_locked()
{
  const JobLimits &lim = job_limits();
  const auto now = std::chrono::steady_clock::now();

  for (auto &kv : jobs_) {
    Job &job = kv.second;
    if (job.status != JobStatus::Running || job.pid <= 0) {
      continue;
    }

    if (job.sigterm_at) {
      // Already asked to stop. Escalate to SIGKILL once the grace window has
      // elapsed -- this is what makes a SIGTERM-ignoring process or a job that
      // keeps re-forking reliably killable.
      if (now - *job.sigterm_at >=
          std::chrono::seconds(lim.kill_grace_seconds)) {
        ::kill(-job.pid, SIGKILL);
      }
      continue;
    }

    if (lim.wall_seconds > 0 &&
        now - job.started_at >= std::chrono::seconds(lim.wall_seconds)) {
      job.termination_requested = true;
      job.timed_out = true;
      job.sigterm_at = now;
      ::kill(-job.pid, SIGTERM);
    }
  }
}

void JobManager::reaper_loop()
{
  while (running_.load()) {
    // Reap every child that has already exited.
    int wait_status;
    pid_t pid;
    while ((pid = ::waitpid(-1, &wait_status, WNOHANG)) > 0) {
      on_child_exit(pid, wait_status);
    }

    // Enforce wall-clock deadlines and escalate pending terminations.
    {
      std::lock_guard<std::mutex> lock(mu_);
      enforce_limits_locked();
    }

    struct timespec ts{0, 50L * 1000L * 1000L}; // 50 ms
    ::nanosleep(&ts, nullptr);
  }
}
