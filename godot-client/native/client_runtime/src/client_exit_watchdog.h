#pragma once
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/string.hpp>
#include <cstdint>

namespace godot {
// Process exit watchdog (avatar-worker AW-01) for src/runtime/exit_drain.gd.
// Main arms it right before SceneTree.quit(), after its bounded drains. If the
// process is still alive `timeout_msec` later, a detached native thread
// appends a line to `log_path`, lets a second one copy it to stderr (for at
// most 200 ms) and ends the process with `exit_code` (TerminateProcess on
// Windows, _exit elsewhere). The state is process-wide; instances are
// handles, any thread may call them. After arm() returns nothing here touches
// the engine again, and the library pins itself so an engine teardown that
// unloads extensions cannot unmap the threads.
// arm() returns 0 armed, 1 invalid argument (timeout 100..600000 ms, exit code
// 0..255), 2 thread failed, 3 pin failed, 4 already firing.
class RabbitLandsExitWatchdog : public RefCounted {
    GDCLASS(RabbitLandsExitWatchdog, RefCounted);
protected:
    static void _bind_methods();
public:
    Dictionary api_info() const;
    int64_t arm(int64_t timeout_msec, int64_t exit_code, const String &log_path, const String &reason);
    bool disarm();
    Dictionary state() const;
};
}
