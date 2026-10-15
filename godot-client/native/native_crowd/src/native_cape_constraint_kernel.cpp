#include "native_cape_constraint_kernel.h"

#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/core/math.hpp>
#include <godot_cpp/variant/packed_float32_array.hpp>
#include <godot_cpp/variant/vector2i.hpp>
#include <godot_cpp/variant/variant.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <vector>

namespace godot {
namespace {

constexpr int CHAIN_COUNT = 3;
constexpr int POINT_COUNT = 5;
constexpr int LINK_COUNT = POINT_COUNT - 1;
constexpr int RELAX_PASSES = 2;
constexpr double TELEPORT = 1.5;

bool finite_vector(const Vector3 &value) {
    return std::isfinite(static_cast<double>(value.x)) &&
            std::isfinite(static_cast<double>(value.y)) &&
            std::isfinite(static_cast<double>(value.z));
}

bool finite_transform(const Transform3D &value) {
    return finite_vector(value.origin) &&
            finite_vector(value.basis.get_column(0)) &&
            finite_vector(value.basis.get_column(1)) &&
            finite_vector(value.basis.get_column(2));
}

bool finite_vector_array(const PackedVector3Array &values) {
    if (values.is_empty()) {
        return true;
    }
    const Vector3 *read = values.ptr();
    for (int64_t index = 0; index < values.size(); ++index) {
        if (!finite_vector(read[index])) {
            return false;
        }
    }
    return true;
}

bool finite_float32_array(const PackedFloat32Array &values) {
    if (values.is_empty()) {
        return true;
    }
    const float *read = values.ptr();
    for (int64_t index = 0; index < values.size(); ++index) {
        if (!std::isfinite(static_cast<double>(read[index]))) {
            return false;
        }
    }
    return true;
}

bool validate_inputs(const Array &points, const Array &previous,
        const Array &rests, const Array &lengths,
        const PackedVector3Array &collision_world,
        const Array &collision_pairs,
        const PackedVector3Array &collision_axes,
        const PackedFloat64Array &collision_spans,
        const PackedFloat64Array &collision_radii,
        const Array &collision_reaches, const Vector3 &fall, double damping,
        const Vector3 &forward, double plane_at, double anchor_y,
        const Transform3D &to_world, bool settled) {
    if (points.size() != CHAIN_COUNT || previous.size() != CHAIN_COUNT ||
            rests.size() != CHAIN_COUNT || lengths.size() != CHAIN_COUNT ||
            points.is_read_only() || previous.is_read_only() ||
            !finite_vector(fall) || !finite_vector(forward) ||
            !finite_transform(to_world) || !std::isfinite(damping) ||
            !std::isfinite(plane_at) || !std::isfinite(anchor_y) ||
            !finite_vector_array(collision_world)) {
        return false;
    }

    for (int chain = 0; chain < CHAIN_COUNT; ++chain) {
        if (points[chain].get_type() != Variant::PACKED_VECTOR3_ARRAY ||
                previous[chain].get_type() != Variant::PACKED_VECTOR3_ARRAY ||
                rests[chain].get_type() != Variant::PACKED_VECTOR3_ARRAY ||
                lengths[chain].get_type() != Variant::PACKED_FLOAT32_ARRAY) {
            return false;
        }
        const PackedVector3Array chain_points = points[chain];
        const PackedVector3Array chain_previous = previous[chain];
        const PackedVector3Array chain_rest = rests[chain];
        const PackedFloat32Array chain_lengths = lengths[chain];
        if (chain_rest.size() != POINT_COUNT ||
                chain_lengths.size() != LINK_COUNT ||
                !finite_vector_array(chain_rest) ||
                !finite_float32_array(chain_lengths)) {
            return false;
        }
        // The GDScript path resets both arrays whenever points has the wrong
        // size or the modifier is unsettled. Previous is read only otherwise.
        const bool resets = !settled || chain_points.size() != POINT_COUNT;
        if (!resets && chain_previous.size() != POINT_COUNT) {
            return false;
        }
        if ((!chain_points.is_empty() && !finite_vector_array(chain_points)) ||
                (!chain_previous.is_empty() &&
                        !finite_vector_array(chain_previous))) {
            return false;
        }
    }

    const int64_t capsule_count = collision_pairs.size();
    if (capsule_count > 4 || collision_axes.size() != capsule_count ||
            collision_spans.size() != capsule_count ||
            collision_radii.size() != capsule_count ||
            collision_reaches.size() != capsule_count ||
            !finite_vector_array(collision_axes)) {
        return false;
    }
    for (int64_t capsule = 0; capsule < capsule_count; ++capsule) {
        if (collision_pairs[capsule].get_type() != Variant::VECTOR2I ||
                collision_reaches[capsule].get_type() !=
                        Variant::PACKED_FLOAT32_ARRAY ||
                !std::isfinite(collision_spans[capsule]) ||
                !std::isfinite(collision_radii[capsule])) {
            return false;
        }
        const Vector2i pair = collision_pairs[capsule];
        const PackedFloat32Array reach = collision_reaches[capsule];
        if (pair.x < 0 || pair.y < 0 ||
                pair.x >= collision_world.size() ||
                pair.y >= collision_world.size() ||
                !finite_float32_array(reach)) {
            return false;
        }
    }
    return true;
}

struct CapsuleDescriptor {
    Vector3 a;
    Vector3 axis;
    double span = 0.0;
    double radius = 0.0;
    PackedFloat32Array reach;
    const float *reach_read = nullptr;
};

Vector3 push_out_of_capsule(const Transform3D &to_world, Vector3 point,
        const CapsuleDescriptor &capsule) {
    const Vector3 &a = capsule.a;
    const Vector3 &axis = capsule.axis;
    double radius = capsule.radius;
    const double span = capsule.span;
    const double travel = span < 1e-9
            ? 0.0
            : Math::clamp(static_cast<double>((point - a).dot(axis)) / span,
                      0.0, 1.0);
    if (!capsule.reach.is_empty()) {
        const double at =
                travel * static_cast<double>(capsule.reach.size() - 1);
        const int64_t low = static_cast<int64_t>(at);
        const int64_t high = std::min(low + 1, capsule.reach.size() - 1);
        radius = std::max(radius,
                Math::lerp(static_cast<double>(capsule.reach_read[low]),
                        static_cast<double>(capsule.reach_read[high]),
                        at - static_cast<double>(low)));
    }
    const Vector3 near = a + axis * static_cast<real_t>(travel);
    const Vector3 away = point - near;
    const real_t gap = away.length();
    if (static_cast<double>(gap) < radius) {
        const Vector3 direction = static_cast<double>(gap) > 1e-5
                ? away / gap
                : -to_world.basis.get_column(2).normalized();
        point = near + direction * static_cast<real_t>(radius);
    }
    return point;
}

} // namespace

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
    if (!validate_inputs(points, previous, rests, lengths, collision_world,
                collision_pairs, collision_axes, collision_spans,
                collision_radii, collision_reaches, fall, damping, forward,
                plane_at, anchor_y, to_world, settled)) {
        return false;
    }

    const Vector3 *collision_world_read = collision_world.is_empty()
            ? nullptr
            : collision_world.ptr();
    const Vector3 *collision_axes_read = collision_axes.is_empty()
            ? nullptr
            : collision_axes.ptr();
    const double *collision_spans_read = collision_spans.is_empty()
            ? nullptr
            : collision_spans.ptr();
    const double *collision_radii_read = collision_radii.is_empty()
            ? nullptr
            : collision_radii.ptr();
    std::vector<CapsuleDescriptor> capsules;
    capsules.reserve(static_cast<std::size_t>(collision_pairs.size()));
    for (int64_t capsule = 0; capsule < collision_pairs.size(); ++capsule) {
        const Vector2i pair = collision_pairs[capsule];
        CapsuleDescriptor descriptor;
        descriptor.a = collision_world_read[pair.x];
        descriptor.axis = collision_axes_read[capsule];
        descriptor.span = collision_spans_read[capsule];
        descriptor.radius = collision_radii_read[capsule];
        descriptor.reach = collision_reaches[capsule];
        descriptor.reach_read = descriptor.reach.is_empty()
                ? nullptr
                : descriptor.reach.ptr();
        capsules.push_back(descriptor);
    }

    std::array<PackedVector3Array, CHAIN_COUNT> solved_points;
    std::array<PackedVector3Array, CHAIN_COUNT> solved_previous;
    for (int chain = 0; chain < CHAIN_COUNT; ++chain) {
        const PackedVector3Array rest = rests[chain];
        const PackedFloat32Array chain_lengths = lengths[chain];
        const Vector3 *rest_read = rest.ptr();
        const float *lengths_read = chain_lengths.ptr();
        PackedVector3Array chain_points = points[chain];
        PackedVector3Array chain_previous = previous[chain];
        if (chain_points.size() != rest.size() || !settled) {
            chain_points = rest.duplicate();
            chain_previous = rest.duplicate();
        }
        Vector3 *points_write = chain_points.ptrw();
        Vector3 *previous_write = chain_previous.ptrw();
        points_write[0] = rest_read[0];
        previous_write[0] = rest_read[0];
        if (points_write[1].distance_to(rest_read[1]) >
                static_cast<real_t>(TELEPORT)) {
            chain_points = rest.duplicate();
            chain_previous = rest.duplicate();
            points_write = chain_points.ptrw();
            previous_write = chain_previous.ptrw();
        }

        for (int index = 1; index < POINT_COUNT; ++index) {
            const Vector3 current = points_write[index];
            points_write[index] =
                    current + (current - previous_write[index]) *
                                      static_cast<real_t>(damping) +
                            fall;
            previous_write[index] = current;
        }
        for (int pass = 0; pass < RELAX_PASSES; ++pass) {
            for (int index = 1; index < POINT_COUNT; ++index) {
                const Vector3 offset = points_write[index] -
                        points_write[index - 1];
                const real_t length = offset.length();
                if (static_cast<double>(length) > 1e-6) {
                    points_write[index] = points_write[index - 1] +
                            offset * static_cast<real_t>(
                                    static_cast<double>(
                                            lengths_read[index - 1]) /
                                    static_cast<double>(length));
                }
            }
            for (int index = 1; index < POINT_COUNT; ++index) {
                Vector3 point = points_write[index];
                for (const CapsuleDescriptor &capsule : capsules) {
                    point = push_out_of_capsule(to_world, point, capsule);
                }
                if (forward != Vector3()) {
                    const double ahead =
                            static_cast<double>(point.dot(forward)) - plane_at;
                    if (ahead > 0.0) {
                        point -= forward * static_cast<real_t>(ahead);
                    }
                }
                if (static_cast<double>(point.y) > anchor_y) {
                    point.y = static_cast<real_t>(anchor_y);
                }
                points_write[index] = point;
            }
        }
        solved_points[chain] = chain_points;
        solved_previous[chain] = chain_previous;
    }

    // Array is reference-counted, so these six assignments update the caller's
    // outer containers. No caller-visible state changed before this commit.
    for (int chain = 0; chain < CHAIN_COUNT; ++chain) {
        points[chain] = solved_points[chain];
        previous[chain] = solved_previous[chain];
    }
    return true;
}

} // namespace godot
