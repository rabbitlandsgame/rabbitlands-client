#pragma once
#include "client_core.h"
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/packed_int64_array.hpp>
#include <godot_cpp/variant/packed_int32_array.hpp>
#include <godot_cpp/variant/packed_float64_array.hpp>
#include <vector>
#include <unordered_map>
#include <godot_cpp/classes/skeleton3d.hpp>
#include <godot_cpp/classes/node3d.hpp>

namespace godot {
class RabbitLandsClientRuntime : public RefCounted {
    GDCLASS(RabbitLandsClientRuntime, RefCounted);
    RlRuntime *core = nullptr;
    int64_t owner_thread = 0;
    int32_t last_status = 0;
    uint64_t calls = 0, records_planned = 0;
    std::vector<RlPlanRecord> inputs;
    std::vector<RlPlanResult> outputs;
    struct RiderBinding {
        int64_t actor = -1, generation = 0, last_frame = -1;
        uint64_t skeleton = 0, visual = 0, owner = 0, rig = 0;
        size_t bones = 0;
    };
    std::unordered_map<uint64_t,size_t> rig_sizes;
    std::unordered_map<uint64_t,RiderBinding> riders;
    std::vector<RlMountedRecord> mounted_inputs;
    std::vector<RlMountedResult> mounted_outputs;
    std::vector<double> mounted_values;
    size_t mounted_value_count = 0;
    uint64_t pose_calls = 0, poses_solved = 0, poses_applied = 0;
    uint64_t pose_attempts = 0, pose_total_us = 0, pose_convert_us = 0;
    uint64_t pose_solve_us = 0, pose_validate_us = 0, pose_apply_us = 0;
    bool mounted_operation = false, cancel_mounted_apply = false;
    uint64_t reentrant_rejections = 0;
    std::vector<uint64_t> pending_rider_removals, pending_rig_removals;
    bool on_owner_thread() const;
    bool can_mutate();
    bool resolve_mounted_target(const RiderBinding &binding, Skeleton3D *&skeleton, Node3D *&visual) const;
    void finish_mounted_operation();
    struct MountedOperationGuard {
        RabbitLandsClientRuntime &owner;
        explicit MountedOperationGuard(RabbitLandsClientRuntime &value);
        ~MountedOperationGuard();
    };
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
    int64_t register_mounted_rider(int64_t rig, const PackedInt32Array &bones, const PackedFloat64Array &constants,
        const PackedInt32Array &thumbs, const PackedFloat64Array &grips);
    bool bind_mounted_rider(int64_t rider, Skeleton3D *skeleton, Node3D *visual, Node3D *owner, int64_t actor, int64_t generation);
    bool unregister_mounted_rider(int64_t rider);
    bool solve_mounted_batch(const PackedInt64Array &records, const PackedFloat64Array &samples, int64_t epoch, bool apply);
    PackedInt64Array mounted_pose_metadata() const;
    PackedFloat64Array mounted_pose_values() const;
    PackedFloat64Array mounted_contact_errors(int64_t actor, int64_t generation, int64_t frame) const;
    PackedInt64Array plan_batch(const PackedInt64Array &records, int64_t epoch, int64_t tick);
};
}
