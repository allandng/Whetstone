#pragma once
#include <atomic>
#include <mutex>
#include <optional>
#include <string>
#include <sys/types.h>
#include <thread>
#include <unordered_map>
#include <vector>

// Asynchronous job tracking.
//
// A Job is created QUEUED, flips to RUNNING once RunTask has forked its
// child, and reaches a terminal state (COMPLETED / FAILED / TERMINATED)
// when the background reaper thread observes the child exit. The
// JobManager owns the job table behind a mutex; request threads and the
// reaper thread both go through it.

enum class JobStatus { Queued, Running, Completed, Failed, Terminated };

// Wire form of a status: "QUEUED", "RUNNING", ...
const char *to_string(JobStatus status);

struct Job {
  int job_id = 0;
  int script_id = 0;
  pid_t pid = -1;
  JobStatus status = JobStatus::Queued;
  std::string stdout_path;
  std::string stderr_path;
  std::optional<int> exit_code;
  bool termination_requested = false;
};

class JobManager {
public:
  // Create the jobs/ output directory and launch the reaper thread.
  void start();

  // Reserve a job id and its output file paths; status starts QUEUED.
  int create(int script_id);

  // Record the forked child's pid and flip the job to RUNNING. If the
  // child has already exited (it finished before this call), the buffered
  // wait status is applied immediately.
  void set_running(int job_id, pid_t pid);

  bool get(int job_id, Job &out) const;

  // SIGTERM a RUNNING job's process. Returns false only if the job id is
  // unknown.
  bool request_terminate(int job_id);

  std::vector<Job> list() const;

  // Called by the reaper when waitpid() reports a child exit.
  void on_child_exit(pid_t pid, int wait_status);

private:
  void reaper_loop();
  // Compute a job's terminal state from a wait() status. Caller holds mu_.
  void apply_status_locked(Job &job, int wait_status);

  mutable std::mutex mu_;
  std::unordered_map<int, Job> jobs_;
  // Wait statuses observed before the matching set_running() call.
  std::unordered_map<pid_t, int> pending_exits_;
  int next_id_ = 1;

  std::thread reaper_;
  std::atomic<bool> running_{false};
};

extern JobManager job_manager;
