#pragma once
// Process exit watchdog, platform layer (avatar-worker AW-01). Plain C++ and
// the OS API only: no Godot header, so <windows.h> never meets the bindings.
// client_exit_watchdog.cpp is the Godot-facing class.
#include <cstdint>
#include <string>

namespace rl_exit_watchdog {
constexpr int64_t MIN_TIMEOUT_MSEC = 100;
constexpr int64_t MAX_TIMEOUT_MSEC = 600000;
constexpr int64_t MAX_EXIT_CODE = 255;

enum Status : int32_t {
    ARMED = 0,
    INVALID_ARGUMENT = 1,
    THREAD_FAILED = 2,
    PIN_FAILED = 3,
    FIRING = 4,
};

struct Snapshot {
    bool armed = false, fired = false, thread_started = false, pinned = false;
    int64_t timeout_msec = 0, exit_code = 0, remaining_msec = 0;
    uint64_t arms = 0, disarms = 0;
    std::string reason;
};

// Arms (or re-arms: the latest call wins) a detached thread that, once
// `timeout_msec` passes without disarm(), appends one line to `log_path`
// (UTF-8, optional), lets a second parked thread copy it to stderr (waiting at
// most 200 ms, so a stderr pipe nobody reads cannot block it) and then ends
// the process with `exit_code`. Both threads start on the first arm().
// Pins this module first so an engine teardown that unloads extensions cannot
// unmap the waiting threads' code. Safe from any thread.
int32_t arm(int64_t timeout_msec, int32_t exit_code, const std::string &log_path, const std::string &reason);
// Cancels a pending deadline; the threads stay parked for a later arm().
// Returns whether a deadline was pending.
bool disarm();
Snapshot snapshot();
}
