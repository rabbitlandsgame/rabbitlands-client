#pragma once
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/classes/ref.hpp>
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/packed_float64_array.hpp>
#include <godot_cpp/variant/packed_vector3_array.hpp>
#include <godot_cpp/variant/transform3d.hpp>
#include <memory>

namespace godot {
class RabbitLandsCapeBodySurface;

// Numeric material projection only. Godot retains all scene/bone ownership.
// One instance owns one cape's warm history; templates are copied at configure.
class RabbitLandsCapeProjector : public RefCounted {
    GDCLASS(RabbitLandsCapeProjector, RefCounted);
    struct Impl;
    std::unique_ptr<Impl> state;
protected:
    static void _bind_methods();
public:
    RabbitLandsCapeProjector();
    ~RabbitLandsCapeProjector();
    // Accepts current fitter field names with or without their '_' prefix.
    // Optional virtual_factors contains finite nonnegative barycentric weights;
    // absent or explicit uniform factors preserve the legacy mean-of-three path.
    bool configure(const Dictionary &data);
    Dictionary project(const Transform3D &world, const Transform3D &lower_frame,
        const Array &root_frames, const Array &body_poses,
        const PackedVector3Array &translations, const Dictionary &collisions,
        const PackedFloat64Array &mount_surface,
        const Ref<RabbitLandsCapeBodySurface> &body_surface,
        bool debug_buffers = false);
    void reset();
    Dictionary stats() const;
    Dictionary runtime_info() const;
};
}
