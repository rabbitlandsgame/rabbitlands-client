#include "client_exit_watchdog.h"
#include "client_exit_watchdog_os.h"
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/variant/char_string.hpp>

using namespace godot;

namespace {
std::string utf8(const String &text) {
    const CharString bytes = text.utf8();
    return std::string(bytes.get_data(), static_cast<size_t>(bytes.length()));
}
}

Dictionary RabbitLandsExitWatchdog::api_info() const {
    Dictionary info;
    info["exit_watchdog_api"] = 1;
    info["min_timeout_msec"] = rl_exit_watchdog::MIN_TIMEOUT_MSEC;
    info["max_timeout_msec"] = rl_exit_watchdog::MAX_TIMEOUT_MSEC;
    info["max_exit_code"] = rl_exit_watchdog::MAX_EXIT_CODE;
#ifdef _WIN32
    info["terminate"] = "TerminateProcess";
#else
    info["terminate"] = "_exit";
#endif
    return info;
}

int64_t RabbitLandsExitWatchdog::arm(int64_t timeout_msec, int64_t exit_code, const String &log_path, const String &reason) {
    if (exit_code < 0 || exit_code > rl_exit_watchdog::MAX_EXIT_CODE) return rl_exit_watchdog::INVALID_ARGUMENT;
    return rl_exit_watchdog::arm(timeout_msec, static_cast<int32_t>(exit_code), utf8(log_path), utf8(reason));
}

bool RabbitLandsExitWatchdog::disarm() { return rl_exit_watchdog::disarm(); }

Dictionary RabbitLandsExitWatchdog::state() const {
    const rl_exit_watchdog::Snapshot snapshot = rl_exit_watchdog::snapshot();
    Dictionary out;
    out["armed"] = snapshot.armed;
    out["fired"] = snapshot.fired;
    out["thread_started"] = snapshot.thread_started;
    out["pinned"] = snapshot.pinned;
    out["timeout_msec"] = snapshot.timeout_msec;
    out["exit_code"] = snapshot.exit_code;
    out["remaining_msec"] = snapshot.remaining_msec;
    out["arms"] = static_cast<int64_t>(snapshot.arms);
    out["disarms"] = static_cast<int64_t>(snapshot.disarms);
    out["reason"] = String::utf8(snapshot.reason.c_str());
    return out;
}

void RabbitLandsExitWatchdog::_bind_methods() {
    ClassDB::bind_method(D_METHOD("api_info"), &RabbitLandsExitWatchdog::api_info);
    ClassDB::bind_method(D_METHOD("arm", "timeout_msec", "exit_code", "log_path", "reason"), &RabbitLandsExitWatchdog::arm,
        DEFVAL(String()), DEFVAL(String()));
    ClassDB::bind_method(D_METHOD("disarm"), &RabbitLandsExitWatchdog::disarm);
    ClassDB::bind_method(D_METHOD("state"), &RabbitLandsExitWatchdog::state);
}
