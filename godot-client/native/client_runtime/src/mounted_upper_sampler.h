#pragma once
#include <godot_cpp/classes/ref.hpp>
#include <godot_cpp/classes/animation.hpp>
#include <godot_cpp/classes/skeleton3d.hpp>
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/packed_float64_array.hpp>
#include <godot_cpp/variant/packed_int32_array.hpp>
#include <vector>

namespace godot {
// Immutable clip/rig caches and event-updated capture rotations. All engine
// resources remain adapter-owned on the owner thread; no scene pointer persists.
class MountedUpperSampler {
    struct Track { int bone, track; };
    struct Clip {
        Ref<Animation> animation;
        std::vector<Track> rotations;
        std::vector<int> parent_tracks;
        double facing = 0.;
    };
    size_t bone_count = 0;
    int spine = -1;
    std::vector<int> mask, chain;
    std::vector<Basis> parent_rests;
    std::vector<Quaternion> parent_defaults, captured;
    Quaternion neutral_spine;
    Basis reference_parent, spine_rest;
    std::vector<Clip> clips;
public:
    bool configure(Skeleton3D *skeleton, const PackedInt32Array &upper_bones,
        const PackedInt32Array &parent_chain, const PackedFloat64Array &definition);
    bool set_clips(Skeleton3D *skeleton, const Array &animations, const PackedFloat64Array &facings);
    bool set_capture(const PackedFloat64Array &rotations);
    // state = [action(-1 or 0..9), clipTime, blendWeight, returning(0|1)].
    // Operates on complete parent-local pose10 values before any scene commit.
    bool apply(std::vector<double> &values, size_t offset, const double *state) const;
};
}
