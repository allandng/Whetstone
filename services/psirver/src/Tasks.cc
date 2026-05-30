#include <dirent.h>
#include <cassert>
#include <syslog.h>
#include <algorithm>
#include <fcntl.h>
#include <limits.h>
#include <sys/stat.h>
#include <fstream>
#include <memory>
#include <ctime>
#include <sstream>
#include <sys/wait.h>
#include "Tasks.hh"
#include "utils.hh"
#include "Jobs.hh"
#include "Limits.hh"
#include "json.hpp"
#include <sys/types.h>
#include <unistd.h>

// The child replaces its environment with a minimal allowlist before exec();
// execvp() reads this global both to locate the binary (via PATH) and to pass
// the environment to the new program.
extern char **environ;

static std::vector<std::unique_ptr<Script>> scripts;

// Used for locking and unlocking the `scripts` vector
static std::mutex script_mutex;

// Read an entire file into a string (binary-safe). Returns "" if the file
// cannot be opened, which is the right answer for a job that has not yet
// produced output.
static std::string read_file(const std::string &path)
{
  std::ifstream in(path, std::ios::binary);
  if (!in) {
    return {};
  }
  std::ostringstream ss;
  ss << in.rdbuf();
  return ss.str();
}

/**
 * Delete all uploaded scripts and their storage directories.
 *
 * This function iterates over the global `scripts` table and, for each
 * script entry, reconstructs the corresponding directory path
 * `SCRIPTS_PATH/<id>` and file path `SCRIPTS_PATH/<id>/<filename>`.
 * It then attempts to make the directory user-accessible and the file
 * user-writable, removes the script file, and removes the script's
 * subdirectory.
 *
 * The function performs best-effort cleanup only: it does not check
 * or report failures from `chmod()`, `remove()`, or `rmdir()`, and it
 * does not send any client response. Its intended use is bulk
 * shutdown-time cleanup rather than request-time error handling.
 *
 */

void Script::terminate_all()
{
  for (std::size_t id = 0 ; id < scripts.size(); ++id) {
    if(!scripts[id]) {
      continue;
    }
    const std::string script_dir =
      std::string(SCRIPTS_PATH) + std::to_string(id);
    const std::string script_filename =
      script_dir + "/" + scripts[id]->get_name();

    ::chmod(script_dir.c_str(), S_IRWXU);
    ::chmod(script_filename.c_str(), S_IWUSR);
    ::remove(script_filename.c_str());
    ::rmdir(script_dir.c_str());
  }
}

// Do the job, reply to the client, and return to the main loop

int HealthTask::execute()
{
  reply(client, "HTTP/1.1 200 OK", "OK");
  return 0;
}

int TeapotTask::execute()
{
  reply(client, "HTTP/1.1 418 I am a teapot", "I am a teapot (maybe)");
  return 0;
}

/**
 * Format this script as one line of the `/scripts` listing.
 *
 * The returned line contains three comma-separated fields: the
 * numeric script ID, the original script filename, and the file's
 * last modification timestamp (`mtime`) formatted as `MM/DD/YYYY
 * HH:mm:ss` in local time. The method obtains `mtime` by calling
 * `stat()` on the script file located at `SCRIPTS_PATH/<id>/<name>`.
 *
 * If the file cannot be stat'ed, the method returns an empty string.
 *
 * The timestamp is initialized to `"00/00/0000 00:00:00"` and is
 * replaced with the formatted local modification time if that time
 * can be converted successfully via `localtime_r()`. If local-time
 * conversion fails, the method still returns a valid listing line,
 * but with the default placeholder timestamp.
 *
 * @return A comma-separated listing line for this script, or an empty
 *         string on failure.
 */

const std::string Script::format() const
{
  const std::string script_filename =
    std::string(SCRIPTS_PATH) + std::to_string(script_id) + "/" + name;

  struct stat st;
  if (::stat(script_filename.c_str(), &st) != 0) {
    return "";
  }

  char buf[20] = "00/00/0000 00:00:00";
  std::tm tm_result;
  if (::localtime_r(&st.st_mtime, &tm_result) != nullptr) {
    ::strftime(buf, sizeof(buf), "%m/%d/%Y %H:%M:%S", &tm_result);
  }

  return std::to_string(script_id) + ',' + name + ',' + buf;
}

/**
 * Roll back a failed script upload and report the failure to the client.
 *
 * This helper removes the in-memory script entry identified by `which`,
 * logs the failure to syslog together with the current `errno` message,
 * attempts to delete the partially created script file from
 * `SCRIPTS_PATH/<which>/<filename>`, and sends an HTTP 500 response to the
 * client.
 *
 * The file removal is best-effort: failure to delete the file is ignored.
 * The directory itself is not removed by this method.
 *
 * The `msg` argument supplies context for the log entry, typically the path
 * or operation that failed.
 *
 * @param which Index of the script slot to clear from the global `scripts`
 *              table.
 * @param msg   Context string to include in the error log.
 */

void UploadTask::cleanup(std::size_t which, const std::string &msg)
{
  scripts[which].reset();

  const std::string script_filename =
    std::string(SCRIPTS_PATH) + std::to_string(which) + "/" + filename;

  syslog(LOG_ERR, "%s: %s", msg.c_str(), strerror(errno));
  ::remove(script_filename.c_str()); // OK to fail
  reply(client, "HTTP/1.1 500 Internal Server Error",
	"Internal Server Error");
}

/**
 * Upload the current script to the server-side script repository.
 *
 * This method assigns the uploaded script the smallest non-negative
 * available script ID, stores metadata for that script in the global
 * `scripts` table, and writes the script body to the corresponding file
 * under `SCRIPTS_PATH/<script_id>/`.
 *
 * The method first locates the first empty slot in `scripts`; if no such
 * slot exists, it appends a new entry. It then ensures that the target
 * script directory exists and is temporarily writable by the user. If the
 * directory does not exist, it is created; if it exists but is not a
 * directory, the upload fails.
 *
 * The script contents are written to a file named `filename` inside that
 * directory. If the file already exists and cannot be opened because it is
 * read-only, the method attempts to restore user write permission and retry
 * the open. After a successful write, the file permissions are restricted
 * to user-read only, and the directory permissions are restricted to
 * user-read and user-execute only.
 *
 * On success, the method sends an HTTP 200 response whose body contains the
 * assigned script ID and returns 0.
 *
 * On any failure, the method invokes `cleanup()` to remove partially written
 * state, sends an HTTP 500 response, and returns 1.
 *
 * @return 0 on success; 1 on failure.
 */

int UploadTask::execute()
{
  script_mutex.lock();

  // Find the next available script ID
  std::size_t script_id = 0;
  for (; script_id < scripts.size() && scripts[script_id]; ++script_id) {
    // Do nothing
  }

  Script *s = new Script(script_id, filename);
  if(script_id == scripts.size()) {
    scripts.emplace_back(s);
  } else {
    scripts[script_id].reset(s);
  }

  script_mutex.unlock();

  const std::string script_dir =
    std::string(SCRIPTS_PATH) + std::to_string(script_id);
  const std::string script_filename = script_dir + "/" + filename;

  // If the directory already exists, make it writable
  // Else, create it
  struct stat st;
  if (::stat(script_dir.c_str(), &st) == 0) {
    if (!S_ISDIR(st.st_mode)) {
      cleanup(script_id, script_dir + " not a directory");
      return 1;
    }
    if (::chmod(script_dir.c_str(), S_IRWXU) != 0) {
      cleanup(script_id, script_dir);
      return 1;
    }
  } else {
    if (::mkdir(script_dir.c_str(), S_IRWXU) != 0) {
      cleanup(script_id, script_dir);
      return 1;
    }
  }

  {
    // Create the script file
    std::ofstream out(script_filename.c_str(), std::ios::out | std::ios::trunc);
    if (!out) {
      // The script file may already exist and be read-only
      ::chmod(script_filename.c_str(), S_IWUSR);
      out.clear();
      out.open(script_filename.c_str(), std::ios::out | std::ios::trunc);
      if(!out) {
	cleanup(script_id, script_filename);
	return 1;
      }
    }

    out << script;
    if (!out) {
      cleanup(script_id, script_filename);
      return 1;
    }
  } // close file before chmod

  // Make the file read-only
  if (::chmod(script_filename.c_str(), S_IRUSR) != 0) {
    cleanup(script_id, script_filename);
    return 1;
  }

  // Make the directory read-only
  if(::chmod(script_dir.c_str(), S_IRUSR | S_IXUSR) != 0) {
    cleanup(script_id, script_dir);
    return 1;
  }

  reply(client, "HTTP/1.1 200 OK", std::to_string(script_id).c_str());
  return 0;
}
/**
 * Return the current script listing to the client.
 *
 * This method scans the global `scripts` table in increasing order of
 * script ID and builds a plain-text listing of all currently
 * registered scripts. Each non-null script entry contributes one
 * output line produced by `Script::format()`. Non-empty formatted
 * lines are appended to the response body, separated by newline
 * characters.
 *
 * If no scripts are currently registered, the response body is empty.
 * In both the empty and non-empty cases, the method replies with
 * HTTP status 200 OK.
 *
 * Concurrency note:
 * Iteration over the shared `scripts` table must be protected by the
 * surrounding lock so that the listing reflects a consistent snapshot.
 *
 * @return Always returns 0.
 */

int ScriptListTask::execute()
{
  std::string listing;

  script_mutex.lock();

  for (std::size_t i = 0; i < scripts.size(); ++i) {
    if (scripts[i]) {
      const std::string line = scripts[i]->format();
      if (!line.empty()) {
	listing += line + "\n";
      }
    }
  }

  script_mutex.unlock();

  reply(client, "HTTP/1.1 200 OK", listing.c_str());
  return 0;
}
/**
 * Delete a previously uploaded script.
 *
 * This method handles the `/scripts/<id>/delete` endpoint. It first
 * checks whether `script_id` designates an existing script entry in
 * the global `scripts` table. If the ID is out of range or the
 * corresponding slot is empty, the method replies with HTTP 404 Not
 * Found and returns 1.
 *
 * For an existing script, the method removes the in-memory metadata
 * entry from `scripts`.
 *
 * After releasing the lock, the method restores write/search
 * permissions as needed, deletes the script file, and removes the
 * script subdirectory. If any filesystem operation fails, the method
 * logs the error with `syslog`, replies with HTTP 500 Internal Server
 * Error, and returns 1.
 *
 * On success, the method replies with HTTP 200 OK and returns the
 * deleted script ID as the response body.
 *
 * Concurrency note: Access to the shared `scripts` table must be
 * protected by the surrounding lock so that existence checking and
 * removal of the in-memory entry are atomic with respect to other
 * tasks.
 *
 * @return 0 on success; 1 if the script does not exist or if deletion
 * fails.
 */

int DeleteTask::execute()
{
  std::string script_dir;
  std::string script_filename;

  {
    std::lock_guard<std::mutex> lock(script_mutex);

    if (script_id >= scripts.size() || !scripts[script_id]) {
      reply(client, "HTTP/1.1 404 Not Found", "Not Found");
      return 1;
    }

    script_dir = std::string(SCRIPTS_PATH) + std::to_string(script_id);
    script_filename = script_dir + "/" + scripts[script_id]->get_name();

    scripts[script_id].reset();
  } // lock_guard unlocks here

  if (   ::chmod(script_dir.c_str(), S_IRWXU) != 0
      || ::chmod(script_filename.c_str(), S_IWUSR) != 0
      || ::remove(script_filename.c_str()) != 0
      || ::rmdir(script_dir.c_str()) != 0) {
    syslog(LOG_ERR, "%s: %s", script_filename.c_str(), strerror(errno));
    reply(client, "HTTP/1.1 500 Internal Server Error",
          "Internal Server Error");
    return 1;
  }

  reply(client, "HTTP/1.1 200 OK", std::to_string(script_id).c_str());
  return 0;
}

// Asynchronous job execution -----------------------------------------------
//
// RunTask no longer blocks on the child: it forks, redirects the child's
// stdout/stderr to per-job capture files, execs the interpreter (Python) or
// compiles-then-runs (C++), records the job as RUNNING, and replies 202
// Accepted with the job id. The background reaper (see Jobs.cc) collects the
// child's exit status and transitions the job to its terminal state.

int RunTask::execute()
{
  // Resolve the script path under lock, then release it before forking.
  std::string script_filename;
  {
    std::lock_guard<std::mutex> lock(script_mutex);
    if (script_id >= scripts.size() || !scripts[script_id]) {
      reply(client, "HTTP/1.1 404 Not Found", "Not Found");
      return 1;
    }
    script_filename = std::string(SCRIPTS_PATH) + std::to_string(script_id) +
                      "/" + scripts[script_id]->get_name();
  }

  const int job_id = job_manager.create(static_cast<int>(script_id));
  Job job;
  job_manager.get(job_id, job); // for the capture-file paths

  const bool is_cpp =
    (language == "cpp" || language == "c++" || language == "cxx");

  // Build everything the child needs *before* forking. After fork() in a
  // multithreaded process only async-signal-safe work is permitted, so we
  // allocate no std::strings past this point in the child.

  // Resolve the per-job resource limits here (getenv() is not safe post-fork).
  const JobLimits &limits = job_limits();

  // The child chdir()s into a private scratch directory, so every path it
  // touches must be absolute. PSIRVER_HOME is the server's cwd.
  char cwd[PATH_MAX];
  if (::getcwd(cwd, sizeof(cwd)) == nullptr) {
    syslog(LOG_ERR, "getcwd: %s", strerror(errno));
    reply(client, "HTTP/1.1 500 Internal Server Error",
          "Internal Server Error");
    return 1;
  }
  const std::string home = cwd;

  // Capture files stay where JobStatusTask expects them; the compiled binary
  // and the job's working directory live inside a private scratch dir.
  const std::string abs_script = home + "/" + script_filename;
  const std::string abs_out    = home + "/" + job.stdout_path;
  const std::string abs_err    = home + "/" + job.stderr_path;
  const std::string scratch    = home + "/" + JOBS_PATH + std::to_string(job_id);
  const std::string bin_path   = scratch + "/a.out";

  ::mkdir(scratch.c_str(), S_IRWXU); // best effort; EEXIST is fine

  // Minimal child environment: drop the server's environment (which may hold
  // secrets/tokens) and expose only what python3 / clang++ need. PATH must
  // survive so execvp() can still locate the interpreter / compiler; HOME and
  // TMPDIR point at the scratch dir so any stray writes stay contained.
  const char *parent_path = ::getenv("PATH");
  std::vector<std::string> env_storage = {
    std::string("PATH=") +
      (parent_path && *parent_path ? parent_path : "/usr/bin:/bin:/usr/local/bin"),
    "HOME=" + scratch,
    "TMPDIR=" + scratch,
    "LANG=en_US.UTF-8",
    "PYTHONUNBUFFERED=1",
    "PYTHONIOENCODING=utf-8",
    "PYTHONDONTWRITEBYTECODE=1",
  };
  std::vector<char *> env_vec;
  for (auto &s : env_storage) {
    env_vec.push_back(const_cast<char *>(s.c_str()));
  }
  env_vec.push_back(nullptr);

  // argv for the program to run (Python interpreter, or the compiled binary).
  std::vector<std::string> argv_storage;
  if (is_cpp) {
    argv_storage.push_back(bin_path);
  } else {
    argv_storage.push_back("python3");
    argv_storage.push_back(abs_script);
  }
  for (const auto &a : args) {
    argv_storage.push_back(a);
  }
  std::vector<char *> argv_vec;
  for (auto &s : argv_storage) {
    argv_vec.push_back(const_cast<char *>(s.c_str()));
  }
  argv_vec.push_back(nullptr);

  // argv for the C++ compile step: clang++ -x c++ -O0 -o <bin> <src>
  std::vector<std::string> cc_storage = {
    "clang++", "-x", "c++", "-O0", "-o", bin_path, abs_script};
  std::vector<char *> cc_vec;
  for (auto &s : cc_storage) {
    cc_vec.push_back(const_cast<char *>(s.c_str()));
  }
  cc_vec.push_back(nullptr);

  pid_t child = fork();
  if (child < 0) {
    syslog(LOG_ERR, "Fork: %s", strerror(errno));
    reply(client, "HTTP/1.1 500 Internal Server Error",
          "Internal Server Error");
    return 1;
  }

  if (child == 0) {
    // ---- child ----
    // Put the job in its own process group (== this pid) so the entire subtree
    // -- a fork-bomb attempt, or the C++ compile/run pair -- can be killed as a
    // unit. The parent makes the same call to close the setpgid/exec race.
    ::setpgid(0, 0);

    int null_fd = ::open("/dev/null", O_RDONLY);
    int out_fd =
      ::open(abs_out.c_str(), O_WRONLY | O_CREAT | O_TRUNC, S_IRUSR | S_IWUSR);
    int err_fd =
      ::open(abs_err.c_str(), O_WRONLY | O_CREAT | O_TRUNC, S_IRUSR | S_IWUSR);
    if (null_fd < 0 || out_fd < 0 || err_fd < 0) {
      _exit(127);
    }
    ::dup2(null_fd, STDIN_FILENO);
    ::dup2(out_fd, STDOUT_FILENO);
    ::dup2(err_fd, STDERR_FILENO);
    // Close every other inherited descriptor (the listening socket, this
    // request's client socket, and the dup source fds) so the job cannot reach
    // the server's file descriptors. Walk up to the process's actual fd limit
    // so a client socket with a high number cannot slip through.
    struct rlimit nofile;
    int max_fd = 256;
    if (::getrlimit(RLIMIT_NOFILE, &nofile) == 0 &&
        nofile.rlim_cur != RLIM_INFINITY && nofile.rlim_cur > 0) {
      max_fd = static_cast<int>(nofile.rlim_cur);
    }
    for (int fd = 3; fd < max_fd; ++fd) {
      ::close(fd);
    }

    // Hand over the minimal environment and confine the working directory to
    // the per-job scratch area before applying the resource caps.
    environ = env_vec.data();
    if (::chdir(scratch.c_str()) != 0) {
      _exit(127);
    }
    apply_rlimits(limits);

    if (is_cpp) {
      // Compile first; compiler diagnostics land in the captured stderr.
      pid_t cc = ::fork();
      if (cc == 0) {
        ::execvp("clang++", cc_vec.data());
        _exit(127); // exec failed
      }
      if (cc < 0) {
        _exit(127);
      }
      int st;
      while (::waitpid(cc, &st, 0) < 0 && errno == EINTR) {
        // retry
      }
      if (!WIFEXITED(st)) {
        _exit(1);
      }
      if (WEXITSTATUS(st) != 0) {
        _exit(WEXITSTATUS(st)); // compilation failed -> job FAILED
      }
      ::execv(bin_path.c_str(), argv_vec.data());
      _exit(127);
    } else {
      ::execvp("python3", argv_vec.data());
      _exit(127); // exec failed
    }
  }

  // ---- parent ---- (does NOT waitpid here; the reaper does)
  // Mirror the child's setpgid() so the job's process group exists no matter
  // which of parent/child runs first; harmless if the child already did it.
  ::setpgid(child, child);
  job_manager.set_running(job_id, child);

  const std::string body = "{\"job_id\":" + std::to_string(job_id) + "}";
  reply_data(client, "HTTP/1.1 202 Accepted", body, "application/json");
  return 0;
}

// GET /jobs : list all known jobs as a JSON array.
int JobListTask::execute()
{
  json::Value arr = json::Value::make_array();
  for (const Job &job : job_manager.list()) {
    json::Value entry = json::Value::make_object();
    entry.set("job_id", json::Value::make_number(job.job_id));
    entry.set("script_id", json::Value::make_number(job.script_id));
    entry.set("status", json::Value::make_string(to_string(job.status)));
    arr.array->push_back(entry);
  }
  reply_data(client, "HTTP/1.1 200 OK", json::dump(arr), "application/json");
  return 0;
}

// GET /jobs/<id> : status plus captured stdout/stderr and exit code.
int JobStatusTask::execute()
{
  Job job;
  if (!job_manager.get(static_cast<int>(job_id), job)) {
    reply(client, "HTTP/1.1 404 Not Found", "Not Found");
    return 1;
  }

  json::Value v = json::Value::make_object();
  v.set("job_id", json::Value::make_number(job.job_id));
  v.set("status", json::Value::make_string(to_string(job.status)));
  v.set("stdout", json::Value::make_string(read_file(job.stdout_path)));
  v.set("stderr", json::Value::make_string(read_file(job.stderr_path)));
  if (job.exit_code.has_value()) {
    v.set("exit_code", json::Value::make_number(*job.exit_code));
  } else {
    v.set("exit_code", json::Value::make_null());
  }

  reply_data(client, "HTTP/1.1 200 OK", json::dump(v), "application/json");
  return 0;
}

// POST /jobs/<id>/terminate : SIGTERM the running process.
int TerminateTask::execute()
{
  if (!job_manager.request_terminate(static_cast<int>(job_id))) {
    reply(client, "HTTP/1.1 404 Not Found", "Not Found");
    return 1;
  }

  Job job;
  job_manager.get(static_cast<int>(job_id), job);

  json::Value v = json::Value::make_object();
  v.set("job_id", json::Value::make_number(job.job_id));
  v.set("status", json::Value::make_string(to_string(job.status)));
  reply_data(client, "HTTP/1.1 200 OK", json::dump(v), "application/json");
  return 0;
}

// GET /jobs/<id>/stderr : raw captured stderr.
int StderrTask::execute()
{
  Job job;
  if (!job_manager.get(static_cast<int>(job_id), job)) {
    reply(client, "HTTP/1.1 404 Not Found", "Not Found");
    return 1;
  }
  reply_data(client, "HTTP/1.1 200 OK", read_file(job.stderr_path),
             "text/plain; charset=utf-8");
  return 0;
}

// GET /jobs/<id>/stdout : raw captured stdout.
int StdoutTask::execute()
{
  Job job;
  if (!job_manager.get(static_cast<int>(job_id), job)) {
    reply(client, "HTTP/1.1 404 Not Found", "Not Found");
    return 1;
  }
  reply_data(client, "HTTP/1.1 200 OK", read_file(job.stdout_path),
             "text/plain; charset=utf-8");
  return 0;
}
