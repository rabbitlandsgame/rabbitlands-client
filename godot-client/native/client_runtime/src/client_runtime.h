#pragma once
#include "client_core.h"
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/packed_int64_array.hpp>
#include <godot_cpp/variant/packed_int32_array.hpp>
#include <godot_cpp/variant/packed_float64_array.hpp>
#include <vector>
#include <unordered_map>
#include <memory>
#include "mounted_upper_sampler.h"
#include "mounted_rein_renderer.h"
#include <godot_cpp/variant/packed_vector3_array.hpp>
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
        std::shared_ptr<MountedUpperSampler> upper;
        std::shared_ptr<MountedReinRenderer> reins;
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
    uint64_t upper_solved = 0, upper_applied = 0, pose_upper_us = 0;
    uint64_t mounted_cape_attempts = 0, mounted_cape_calls = 0, mounted_cape_us = 0;
    uint64_t rein_calls = 0, rein_us = 0, rein_attempts = 0, rein_failures = 0;
    bool mounted_operation = false, cancel_mounted_apply = false;
    bool template_bone_commit = false;
    uint64_t bone_transform_commits = 0, bone_guarded_trs_commits = 0;
    uint64_t reentrant_rejections = 0;
    std::vector<uint64_t> pending_rider_removals, pending_rig_removals;
    bool solve_mounted_impl(const PackedInt64Array &records, const PackedFloat64Array &samples,
        const PackedFloat64Array &upper, int64_t epoch, bool apply);
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
    bool set_mounted_lean(int64_t rider, double degrees);
    bool step_mounted_cape(Array points, Array previous, const Array &rests, const Array &lengths,
        const PackedVector3Array &collision_world, const Array &collision_pairs,
        const PackedVector3Array &collision_axes, const PackedFloat64Array &collision_spans,
        const PackedFloat64Array &collision_radii, const Array &collision_reaches,
        const Vector3 &fall, double damping, const Vector3 &forward, double plane_at,
        double anchor_y, const Transform3D &to_world, bool settled, const PackedFloat64Array &surface);
    bool configure_mounted_reins(int64_t rider, Node3D *reins, MeshInstance3D *straps, Skeleton3D *pony,
        const PackedInt32Array &bones, const PackedFloat64Array &anchors, const PackedFloat64Array &parameters, const Array &paths);
    Dictionary mounted_rein_snapshot(int64_t rider, bool geometry) const;
    bool configure_mounted_upper(int64_t rider, const PackedInt32Array &bones, const PackedInt32Array &chain,
        const PackedFloat64Array &definition, const Array &animations, const PackedFloat64Array &facings);
    bool set_mounted_upper_clips(int64_t rider, const Array &animations, const PackedFloat64Array &facings);
    bool set_mounted_upper_capture(int64_t rider, const PackedFloat64Array &rotations);
    bool solve_mounted_presentation_batch(const PackedInt64Array &records, const PackedFloat64Array &samples,
        const PackedFloat64Array &upper, int64_t epoch, bool apply);
    bool solve_mounted_batch(const PackedInt64Array &records, const PackedFloat64Array &samples, int64_t epoch, bool apply);
    PackedInt64Array mounted_pose_metadata() const;
    PackedFloat64Array mounted_pose_values() const;
    PackedFloat64Array mounted_contact_errors(int64_t actor, int64_t generation, int64_t frame) const;
    PackedInt64Array plan_batch(const PackedInt64Array &records, int64_t epoch, int64_t tick);
};
}
