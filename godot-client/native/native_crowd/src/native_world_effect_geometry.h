#pragma once

#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/color.hpp>
#include <godot_cpp/variant/vector3.hpp>

namespace godot {

class NativeWorldEffectGeometry : public RefCounted {
    GDCLASS(NativeWorldEffectGeometry, RefCounted)

protected:
    static void _bind_methods();

public:
    Array build(int64_t effect_id, int64_t power_level, double elapsed,
            double progress, const Vector3 &impact, const Color &palette,
            double size, double radius, double area_radius, bool has_flight,
            const Vector3 &flight_contact) const;
};

} // namespace godot
