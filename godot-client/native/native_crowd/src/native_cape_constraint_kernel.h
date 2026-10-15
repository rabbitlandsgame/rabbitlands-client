#pragma once

#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/packed_float32_array.hpp>
#include <godot_cpp/variant/packed_float64_array.hpp>
#include <godot_cpp/variant/packed_vector3_array.hpp>
#include <godot_cpp/variant/transform3d.hpp>

namespace godot {

// A narrow arithmetic kernel for one complete cape point-simulation step.
// Skeleton reads, rest construction and bone writes remain in cape_cloth.gd.
// The caller's point state is updated only after every input is validated and
// all three chains have completed successfully.
class NativeCapeConstraintKernel : public RefCounted {
    GDCLASS(NativeCapeConstraintKernel, RefCounted)

protected:
    static void _bind_methods();

public:
    bool step(Array points, Array previous, const Array &rests,
            const Array &lengths, const PackedVector3Array &collision_world,
            const Array &collision_pairs,
            const PackedVector3Array &collision_axes,
            const PackedFloat64Array &collision_spans,
            const PackedFloat64Array &collision_radii,
            const Array &collision_reaches, const Vector3 &fall,
            double damping, const Vector3 &forward, double plane_at,
            double anchor_y, const Transform3D &to_world, bool settled) const;
};

} // namespace godot
