#include "native_spell_flight_geometry.h"

#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/core/math.hpp>
#include <godot_cpp/variant/packed_color_array.hpp>
#include <godot_cpp/variant/packed_vector2_array.hpp>
#include <godot_cpp/variant/packed_vector3_array.hpp>
#include <godot_cpp/variant/vector2.hpp>

#include <algorithm>
#include <cmath>

namespace godot {
namespace {

constexpr int SEGMENTS = 28;
constexpr double AFTERGLOW = 0.24;
constexpr double PI = 3.1415926535897932384626433832795;
constexpr double TAU = 6.283185307179586476925286766559;

struct SurfaceArrays {
    PackedVector3Array vertices;
    PackedColorArray colors;
    PackedVector2Array uvs;
    int64_t cursor = 0;
    Vector3 *vertex_write = nullptr;
    Color *color_write = nullptr;
    Vector2 *uv_write = nullptr;

    explicit SurfaceArrays(int64_t vertex_count) {
        vertices.resize(vertex_count);
        colors.resize(vertex_count);
        uvs.resize(vertex_count);
        if (vertex_count > 0) {
            vertex_write = vertices.ptrw();
            color_write = colors.ptrw();
            uv_write = uvs.ptrw();
        }
    }

    void quad(const Vector3 &a, const Vector3 &b, const Vector3 &c,
            const Vector3 &d, const Color &color) {
        vertex_write[cursor] = a;
        vertex_write[cursor + 1] = b;
        vertex_write[cursor + 2] = c;
        vertex_write[cursor + 3] = a;
        vertex_write[cursor + 4] = c;
        vertex_write[cursor + 5] = d;
        for (int offset = 0; offset < 6; ++offset) {
            color_write[cursor + offset] = color;
        }
        uv_write[cursor] = Vector2(0, 0);
        uv_write[cursor + 1] = Vector2(0, 1);
        uv_write[cursor + 2] = Vector2(1, 1);
        uv_write[cursor + 3] = Vector2(0, 0);
        uv_write[cursor + 4] = Vector2(1, 1);
        uv_write[cursor + 5] = Vector2(1, 0);
        cursor += 6;
    }
};

double clamp_unit(double value) {
    return value < 0.0 ? 0.0 : (value > 1.0 ? 1.0 : value);
}

double smoothstep(double from, double to, double value) {
    if (from == to) {
        return from;
    }
    const double x = clamp_unit((value - from) / (to - from));
    return x * x * (3.0 - 2.0 * x);
}

bool finite_vector(const Vector3 &value) {
    return std::isfinite(static_cast<double>(value.x)) &&
            std::isfinite(static_cast<double>(value.y)) &&
            std::isfinite(static_cast<double>(value.z));
}

bool finite_color(const Color &value) {
    return std::isfinite(static_cast<double>(value.r)) &&
            std::isfinite(static_cast<double>(value.g)) &&
            std::isfinite(static_cast<double>(value.b)) &&
            std::isfinite(static_cast<double>(value.a));
}

Vector3 point_at(int64_t effect_id, const Vector3 &start,
        const Vector3 &destination, const Vector3 &side, const Vector3 &up,
        double path_spread, double path_arc, double progress,
        int64_t strand = 0) {
    const double p = clamp_unit(progress);
    const double envelope_value = Math::sin(p * PI);
    Vector3 offset = up * static_cast<real_t>(envelope_value) *
            static_cast<real_t>(path_arc);
    if (effect_id == 0 || effect_id == 73) {
        offset += side * static_cast<real_t>(Math::sin(
                p * TAU * 1.7 + strand * 2.1)) *
                static_cast<real_t>(envelope_value) * static_cast<real_t>(0.19) *
                static_cast<real_t>(path_spread);
    } else if (effect_id == 84) {
        offset += side * static_cast<real_t>(Math::sin(p * TAU * 3.0)) *
                static_cast<real_t>(envelope_value) * static_cast<real_t>(0.05);
    } else if (effect_id == 85) {
        const double angle = p * TAU * 4.0 + strand * PI;
        offset += (side * static_cast<real_t>(Math::cos(angle)) +
                up * static_cast<real_t>(Math::sin(angle))) *
                static_cast<real_t>(envelope_value) * static_cast<real_t>(0.15);
    } else if (effect_id == 83) {
        offset += side * static_cast<real_t>(Math::sin(
                p * TAU * 5.0 + strand * PI)) *
                static_cast<real_t>(envelope_value) * static_cast<real_t>(0.09);
    } else if (effect_id == 1) {
        offset += (up * static_cast<real_t>(envelope_value) *
                static_cast<real_t>(0.18) + side * static_cast<real_t>(Math::sin(
                p * TAU + strand * PI)) *
                static_cast<real_t>(envelope_value) * static_cast<real_t>(0.16)) *
                static_cast<real_t>(path_spread);
    } else if (effect_id == 10 || effect_id == 86) {
        const double angle = p * TAU * 2.0 + strand * 2.1;
        offset += (side * static_cast<real_t>(Math::cos(angle)) +
                up * static_cast<real_t>(Math::sin(angle))) *
                static_cast<real_t>(envelope_value) * static_cast<real_t>(0.16) *
                static_cast<real_t>(path_spread);
    } else {
        offset += side * static_cast<real_t>(Math::sin(
                p * TAU * 2.5 + strand * PI)) *
                static_cast<real_t>(envelope_value) * static_cast<real_t>(0.035);
    }
    return start.lerp(destination, static_cast<real_t>(p)) + offset;
}

void segment(SurfaceArrays &surface, const Vector3 &a, const Vector3 &b,
        double width, const Color &color, const Vector3 &view) {
    const Vector3 quad_side = (b - a).cross(view).normalized() *
            static_cast<real_t>(width) * static_cast<real_t>(0.5);
    surface.quad(a - quad_side, a + quad_side, b + quad_side,
            b - quad_side, color);
}

void glow(SurfaceArrays &surface, const Vector3 &centre, double radius,
        const Color &color, const Vector3 &right, const Vector3 &up) {
    const Vector3 scaled_right = right * static_cast<real_t>(radius);
    const Vector3 scaled_up = up * static_cast<real_t>(radius);
    surface.quad(centre - scaled_right - scaled_up,
            centre - scaled_right + scaled_up,
            centre + scaled_right + scaled_up,
            centre + scaled_right - scaled_up, color);
}

Array pack(const SurfaceArrays &ribbon, const SurfaceArrays &glow_surface) {
    Array result;
    result.resize(6);
    result[0] = ribbon.vertices;
    result[1] = ribbon.colors;
    result[2] = ribbon.uvs;
    result[3] = glow_surface.vertices;
    result[4] = glow_surface.colors;
    result[5] = glow_surface.uvs;
    return result;
}

} // namespace

void NativeSpellFlightGeometry::_bind_methods() {
    ClassDB::bind_method(D_METHOD("build", "effect_id", "tint", "start",
                                 "destination", "side", "up", "path_spread",
                                 "path_arc", "tail_fraction", "duration",
                                 "time", "view", "camera_right", "camera_up",
                                 "magnitude", "particle_count"),
            &NativeSpellFlightGeometry::build);
}

Array NativeSpellFlightGeometry::build(int64_t effect_id, const Color &tint,
        const Vector3 &start, const Vector3 &destination, const Vector3 &side,
        const Vector3 &up, double path_spread, double path_arc,
        double tail_fraction, double duration, double time, const Vector3 &view,
        const Vector3 &camera_right, const Vector3 &camera_up, double magnitude,
        int64_t particle_count) const {
    if (duration <= 0.0 || particle_count < 0 || particle_count > 81 ||
            !std::isfinite(path_spread) || !std::isfinite(path_arc) ||
            !std::isfinite(tail_fraction) || !std::isfinite(duration) ||
            !std::isfinite(time) || !std::isfinite(magnitude) ||
            !finite_color(tint) || !finite_vector(start) ||
            !finite_vector(destination) || !finite_vector(side) ||
            !finite_vector(up) || !finite_vector(view) ||
            !finite_vector(camera_right) || !finite_vector(camera_up)) {
        return Array();
    }
    const double p = clamp_unit(time / duration);
    const double fade = 1.0 - smoothstep(duration, duration + AFTERGLOW, time);
    const int64_t strands = (effect_id == 10 || effect_id == 86) ? 3 : 2;
    const int64_t ribbon_vertices = time >= 0.0 ? strands * SEGMENTS * 6 : 0;
    SurfaceArrays ribbon(ribbon_vertices);

    if (time >= 0.0) {
        for (int64_t strand = 0; strand < strands; ++strand) {
            const double head = clamp_unit((time - strand * 0.035) / duration);
            const double tail = std::max(0.0, head - tail_fraction);
            Vector3 previous = point_at(effect_id, start, destination, side, up,
                    path_spread, path_arc, Math::lerp(tail, head, 0.0), strand);
            for (int i = 0; i < SEGMENTS; ++i) {
                const double a = static_cast<double>(i) / SEGMENTS;
                const double b = static_cast<double>(i + 1) / SEGMENTS;
                Color color = tint.lerp(Color(1.0, 0.91, 0.66),
                        static_cast<real_t>(effect_id == 2 ? a * 0.42 : a * 0.16));
                color.a = static_cast<float>(Math::pow(a, 0.7) * fade *
                        (strand == 0 ? 0.85 : 0.42));
                const double width = (effect_id == 2 ? 0.13 : 0.085) *
                        (0.15 + a * 0.85) * magnitude;
                const Vector3 next = point_at(effect_id, start, destination,
                        side, up, path_spread, path_arc, Math::lerp(tail, head, b),
                        strand);
                segment(ribbon, previous, next, width, color, view);
                previous = next;
            }
        }
    }

    int64_t trail_quads = 0;
    if (time >= 0.0 && particle_count > 0) {
        for (int64_t i = 0; i < particle_count; ++i) {
            const double age = static_cast<double>(i) / particle_count;
            if (p - age * 0.42 > 0.0) {
                ++trail_quads;
            }
        }
    }
    SurfaceArrays glow_surface((3 + trail_quads) * 6);
    Vector3 head_position = point_at(effect_id, start, destination, side, up,
            path_spread, path_arc, p);
    double size = (effect_id == 2 ? 0.25 : 0.19) * magnitude;
    if (time < 0.0) {
        head_position = (effect_id == 10 || effect_id == 86) ? destination : start;
        size *= 0.60 + 0.15 * Math::sin(time * 24.0);
    }
    glow(glow_surface, head_position, size * 1.8,
            Color(tint.r, tint.g, tint.b, static_cast<float>(fade * 0.55)),
            camera_right, camera_up);
    glow(glow_surface, head_position, size,
            Color(tint.r, tint.g, tint.b, static_cast<float>(fade)),
            camera_right, camera_up);
    glow(glow_surface, head_position, size * 0.40,
            Color(1.0, 0.96, 0.83, static_cast<float>(fade)),
            camera_right, camera_up);

    if (time >= 0.0 && particle_count > 0) {
        for (int64_t i = 0; i < particle_count; ++i) {
            const double age = static_cast<double>(i) / particle_count;
            const double sample = p - age * 0.42;
            if (sample <= 0.0) {
                continue;
            }
            const double angle = i * 2.399 + time * 4.0;
            const Vector3 drift = (side * static_cast<real_t>(Math::cos(angle)) +
                    up * static_cast<real_t>(Math::sin(angle))) *
                    static_cast<real_t>(age) * static_cast<real_t>(0.38);
            const Vector3 point = point_at(effect_id, start, destination, side,
                    up, path_spread, path_arc, sample, i % 2) + drift;
            Color color = tint.lerp(Color(1.0, 0.80, 0.32),
                    static_cast<real_t>(effect_id == 2 ? 0.45 : 0.0));
            color.a = static_cast<float>((1.0 - age) * fade * 0.7);
            glow(glow_surface, point,
                    (0.025 + static_cast<double>(i % 3) * 0.009) * magnitude,
                    color, camera_right, camera_up);
        }
    }
    return pack(ribbon, glow_surface);
}

} // namespace godot
