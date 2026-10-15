#pragma once

#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/color.hpp>
#include <godot_cpp/variant/vector3.hpp>

namespace godot {

class NativeSpellFlightGeometry : public RefCounted {
    GDCLASS(NativeSpellFlightGeometry, RefCounted)

protected:
    static void _bind_methods();

public:
    Array build(int64_t effect_id, const Color &tint,
            const Vector3 &start, const Vector3 &destination,
            const Vector3 &side, const Vector3 &up,
            double path_spread, double path_arc, double tail_fraction,
            double duration, double time, const Vector3 &view,
            const Vector3 &camera_right, const Vector3 &camera_up,
            double magnitude, int64_t particle_count) const;
};

} // namespace godot
