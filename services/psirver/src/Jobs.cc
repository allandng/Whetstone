#include "Jobs.hh"

#include <cerrno>
#include <csignal>
#include <ctime>
#include <string>
#include <sys/stat.h>
#include <sys/wait.h>

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
  if (job.status == JobStatus::Running && job.pid > 0) {
    job.termination_requested = true;
    ::kill(job.pid, SIGTERM);
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

void JobManager::reaper_loop()
{
  while (running_.load()) {
    int wait_status;
    pid_t pid = ::waitpid(-1, &wait_status, WNOHANG);
    if (pid > 0) {
      on_child_exit(pid, wait_status);
      continue; // drain remaining exits before sleeping
    }
    // No child ready (pid == 0) or none exist yet (ECHILD): poll politely.
    struct timespec ts{0, 50L * 1000L * 1000L}; // 50 ms
    ::nanosleep(&ts, nullptr);
  }
}
