#include "native_cape_constraint_kernel.h"
#include "../../shared/cape_constraint_math.h"
#include <godot_cpp/core/class_db.hpp>

namespace godot {
void NativeCapeConstraintKernel::_bind_methods() {
    ClassDB::bind_method(D_METHOD("step", "points", "previous", "rests",
                                 "lengths", "collision_world",
                                 "collision_pairs", "collision_axes",
                                 "collision_spans", "collision_radii",
                                 "collision_reaches", "fall", "damping",
                                 "forward", "plane_at", "anchor_y",
                                 "to_world", "settled"),
            &NativeCapeConstraintKernel::step);
}

bool NativeCapeConstraintKernel::step(Array points, Array previous,
        const Array &rests, const Array &lengths,
        const PackedVector3Array &collision_world,
        const Array &collision_pairs,
        const PackedVector3Array &collision_axes,
        const PackedFloat64Array &collision_spans,
        const PackedFloat64Array &collision_radii,
        const Array &collision_reaches, const Vector3 &fall, double damping,
        const Vector3 &forward, double plane_at, double anchor_y,
        const Transform3D &to_world, bool settled) const {
    return rl_cape::step(points,previous,rests,lengths,collision_world,collision_pairs,collision_axes,
        collision_spans,collision_radii,collision_reaches,fall,damping,forward,plane_at,anchor_y,to_world,settled);
}

} // namespace godot
