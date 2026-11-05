#include "client_exit_watchdog_os.h"
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <mutex>
#include <thread>
#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <dlfcn.h>
#include <fcntl.h>
#include <unistd.h>
#endif

namespace rl_exit_watchdog {
namespace {
using Clock = std::chrono::steady_clock;
// How long the firing thread lets the stderr line go out before it ends the
// process anyway (a stderr pipe nobody reads must not keep a hung exit alive).
constexpr auto REPORT_WAIT = std::chrono::milliseconds(200);

struct State {
    std::mutex mutex;
    std::condition_variable wake, report_wake;
    bool armed = false, fired = false, watcher_started = false, reporter_started = false, pinned = false;
    bool report_ready = false, reported = false;
    Clock::time_point armed_at{}, deadline{};
    int64_t timeout_msec = 0;
    int32_t exit_code = 0;
    uint64_t arms = 0, disarms = 0;
#ifdef _WIN32
    std::wstring log_path;
#else
    std::string log_path;
#endif
    std::string reason;
    char reason_text[96] = {};
    char line[512] = {};
    size_t line_length = 0;
};

// Allocated once and never freed: no static destructor may run while the
// watchdog threads wait on this mutex (process exit on Linux runs them with
// other threads still alive).
State &state() {
    static State *value = new State();
    return *value;
}

// Keeps this library mapped until the process ends. Godot unloads extension
// libraries during its own teardown, which is exactly when a hang is watched;
// a pinned module's FreeLibrary/dlclose is a no-op.
bool pin_module() {
#ifdef _WIN32
    HMODULE module = nullptr;
    return GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
        reinterpret_cast<LPCWSTR>(&pin_module), &module) != 0;
#else
    Dl_info info{};
    if (dladdr(reinterpret_cast<void *>(&pin_module), &info) == 0 || info.dli_fname == nullptr) return false;
    // The handle is kept on purpose (one extra reference, RTLD_NODELETE).
    return dlopen(info.dli_fname, RTLD_NOW | RTLD_NOLOAD | RTLD_NODELETE) != nullptr;
#endif
}

// What fires runs while the rest of the process may be wedged, so it takes no
// lock it does not own: no heap allocation and no C stdio (whose locks a hung
// thread may hold), only a stack-formatted line and direct OS writes.
void write_all(
#ifdef _WIN32
    HANDLE target,
#else
    int target,
#endif
    const char *text, size_t length) {
#ifdef _WIN32
    DWORD written = 0;
    WriteFile(target, text, static_cast<DWORD>(length), &written, nullptr);
#else
    while (length > 0) {
        const ssize_t written = write(target, text, length);
        if (written <= 0) return;
        text += written;
        length -= static_cast<size_t>(written);
    }
#endif
}

void append_to_log(const State &s) {
    if (s.log_path.empty()) return;
#ifdef _WIN32
    const HANDLE file = CreateFileW(s.log_path.c_str(), FILE_APPEND_DATA,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) return;
    write_all(file, s.line, s.line_length);
    CloseHandle(file);
#else
    const int file = open(s.log_path.c_str(), O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0644);
    if (file < 0) return;
    write_all(file, s.line, s.line_length);
    close(file);
#endif
}

void write_stderr(const State &s) {
#ifdef _WIN32
    const HANDLE target = GetStdHandle(STD_ERROR_HANDLE);
    if (target == nullptr || target == INVALID_HANDLE_VALUE) return;
    write_all(target, s.line, s.line_length);
#else
    write_all(STDERR_FILENO, s.line, s.line_length);
#endif
}

[[noreturn]] void end_process(int32_t code) {
#ifdef _WIN32
    TerminateProcess(GetCurrentProcess(), static_cast<UINT>(code));
#endif
    _exit(code);
}

void format_line(State &s, long long waited) {
    const std::time_t now = std::time(nullptr);
    std::tm parts{};
#ifdef _WIN32
    const bool dated = gmtime_s(&parts, &now) == 0;
#else
    const bool dated = gmtime_r(&now, &parts) != nullptr;
#endif
    char stamp[32] = "unknown-time";
    if (dated)
        std::snprintf(stamp, sizeof(stamp), "%04d-%02d-%02dT%02d:%02d:%02dZ", parts.tm_year + 1900, parts.tm_mon + 1,
            parts.tm_mday, parts.tm_hour, parts.tm_min, parts.tm_sec);
    const int length = std::snprintf(s.line, sizeof(s.line),
        "%s exit_watchdog fired: process still running %lld ms after quit was requested; "
        "ending it with exit code %d (reason=%s)\n", stamp, waited, static_cast<int>(s.exit_code), s.reason_text);
    s.line_length = length <= 0 ? 0 : (static_cast<size_t>(length) < sizeof(s.line) ? static_cast<size_t>(length) : sizeof(s.line) - 1);
}

// The firing thread. It never calls into the engine: by the time it fires,
// the engine may be half torn down (the case it exists for).
void watch() {
    State &s = state();
    std::unique_lock<std::mutex> lock(s.mutex);
    for (;;) {
        if (!s.armed) {
            s.wake.wait(lock);
            continue;
        }
        const Clock::time_point deadline = s.deadline;
        if (Clock::now() < deadline) {
            s.wake.wait_until(lock, deadline);
            continue;
        }
        break;
    }
    // From here on arm() refuses (FIRING) and nothing else writes the line,
    // the path or the code, so they are read without the lock below.
    s.fired = true;
    const int32_t code = s.exit_code;
    format_line(s, static_cast<long long>(
        std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now() - s.armed_at).count()));
    s.report_ready = true;
    lock.unlock();
    s.report_wake.notify_all();
    append_to_log(s);
    lock.lock();
    s.report_wake.wait_for(lock, REPORT_WAIT, [&s] { return s.reported; });
    lock.unlock();
    end_process(code);
}

// Writes the stderr line for watch(), which does not wait for it longer than
// REPORT_WAIT: a full pipe blocks only this thread.
void report() {
    State &s = state();
    std::unique_lock<std::mutex> lock(s.mutex);
    s.report_wake.wait(lock, [&s] { return s.report_ready; });
    lock.unlock();
    write_stderr(s);
    lock.lock();
    s.reported = true;
    lock.unlock();
    s.report_wake.notify_all();
}

bool start(void (*body)(), bool &started) {
    if (started) return true;
    try {
        std::thread(body).detach();
    } catch (...) {
        return false;
    }
    started = true;
    return true;
}
}

int32_t arm(int64_t timeout_msec, int32_t exit_code, const std::string &log_path, const std::string &reason) {
    if (timeout_msec < MIN_TIMEOUT_MSEC || timeout_msec > MAX_TIMEOUT_MSEC || exit_code < 0 || exit_code > MAX_EXIT_CODE)
        return INVALID_ARGUMENT;
    State &s = state();
    std::unique_lock<std::mutex> lock(s.mutex);
    if (s.fired) return FIRING;
    if (!s.pinned) {
        s.pinned = pin_module();
        if (!s.pinned) return PIN_FAILED;
    }
    if (!start(report, s.reporter_started) || !start(watch, s.watcher_started)) return THREAD_FAILED;
#ifdef _WIN32
    s.log_path.clear();
    if (!log_path.empty()) {
        const int size = static_cast<int>(log_path.size());
        const int count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, log_path.data(), size, nullptr, 0);
        if (count > 0) {
            s.log_path.assign(static_cast<size_t>(count), L'\0');
            if (MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, log_path.data(), size, s.log_path.data(), count) != count)
                s.log_path.clear();
        }
    }
#else
    s.log_path = log_path;
#endif
    s.reason = reason;
    std::snprintf(s.reason_text, sizeof(s.reason_text), "%s", reason.c_str());
    s.armed = true;
    s.timeout_msec = timeout_msec;
    s.exit_code = exit_code;
    s.armed_at = Clock::now();
    s.deadline = s.armed_at + std::chrono::milliseconds(timeout_msec);
    ++s.arms;
    lock.unlock();
    s.wake.notify_all();
    return ARMED;
}

bool disarm() {
    State &s = state();
    std::unique_lock<std::mutex> lock(s.mutex);
    const bool pending = s.armed && !s.fired;
    if (pending) {
        s.armed = false;
        ++s.disarms;
    }
    lock.unlock();
    s.wake.notify_all();
    return pending;
}

Snapshot snapshot() {
    State &s = state();
    std::lock_guard<std::mutex> lock(s.mutex);
    Snapshot out;
    out.armed = s.armed;
    out.fired = s.fired;
    out.thread_started = s.watcher_started && s.reporter_started;
    out.pinned = s.pinned;
    out.timeout_msec = s.timeout_msec;
    out.exit_code = s.exit_code;
    out.arms = s.arms;
    out.disarms = s.disarms;
    out.reason = s.reason;
    if (s.armed && !s.fired) {
        const auto left = std::chrono::duration_cast<std::chrono::milliseconds>(s.deadline - Clock::now()).count();
        out.remaining_msec = left > 0 ? static_cast<int64_t>(left) : 0;
    }
    return out;
}
}
