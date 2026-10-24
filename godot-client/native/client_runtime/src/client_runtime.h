#pragma once
#include "client_core.h"
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/packed_int64_array.hpp>
#include <godot_cpp/variant/packed_int32_array.hpp>
#include <godot_cpp/variant/packed_float64_array.hpp>
#include <vector>

namespace godot {
class RabbitLandsClientRuntime : public RefCounted {
    GDCLASS(RabbitLandsClientRuntime, RefCounted);
    RlRuntime *core = nullptr;
    int64_t owner_thread = 0;
    int32_t last_status = 0;
    uint64_t calls = 0, records_planned = 0;
    std::vector<RlPlanRecord> inputs;
    std::vector<RlPlanResult> outputs;
    bool on_owner_thread();
protected:
    static void _bind_methods();
public:
    RabbitLandsClientRuntime();
    ~RabbitLandsClientRuntime();
    Dictionary runtime_info() const;
    int64_t get_last_status() const;
    int64_t reset_epoch(int64_t epoch);
    int64_t register_rig(const PackedInt32Array &parents, const PackedFloat64Array &rest, const PackedFloat64Array &pose);
    bool unregister_rig(int64_t handle);
    PackedInt64Array plan_batch(const PackedInt64Array &records, int64_t epoch, int64_t tick);
};
}
