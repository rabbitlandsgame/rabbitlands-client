#include "native_world_effect_geometry.h"

#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/core/math.hpp>
#include <godot_cpp/variant/basis.hpp>
#include <godot_cpp/variant/packed_color_array.hpp>
#include <godot_cpp/variant/packed_vector3_array.hpp>

#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cmath>

namespace godot {
namespace {

constexpr double PI = 3.1415926535897932384626433832795;
constexpr double TAU = 6.283185307179586476925286766559;
constexpr double MAX_SCALAR = 10000.0;
constexpr double MAX_COORDINATE = 1000000.0;

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

bool bounded_color(const Color &value) {
    return std::abs(static_cast<double>(value.r)) <= MAX_SCALAR &&
            std::abs(static_cast<double>(value.g)) <= MAX_SCALAR &&
            std::abs(static_cast<double>(value.b)) <= MAX_SCALAR &&
            std::abs(static_cast<double>(value.a)) <= MAX_SCALAR;
}

bool bounded_vector(const Vector3 &value) {
    return std::abs(static_cast<double>(value.x)) <= MAX_COORDINATE &&
            std::abs(static_cast<double>(value.y)) <= MAX_COORDINATE &&
            std::abs(static_cast<double>(value.z)) <= MAX_COORDINATE;
}

bool is_blessing(int64_t effect_id) {
    switch (effect_id) {
        case 1:
        case 4:
        case 9:
        case 12:
        case 14:
        case 19:
        case 79:
            return true;
        default:
            return false;
    }
}

bool is_ward(int64_t effect_id) {
    switch (effect_id) {
        case 3:
        case 6:
        case 18:
        case 72:
        case 74:
        case 75:
        case 76:
        case 77:
        case 78:
        case 80:
        case 81:
        case 82:
        case 92:
            return true;
        default:
            return false;
    }
}

double power_curve(int64_t power, double midpoint, double maximum) {
    const int64_t tier = std::clamp<int64_t>(power, 1, 10);
    if (tier <= 5) {
        return Math::lerp(1.0, midpoint,
                static_cast<double>(tier - 1) / 4.0);
    }
    return Math::lerp(midpoint, maximum, Math::pow(
            static_cast<double>(tier - 5) / 5.0, 1.3));
}

int64_t power_count(int64_t base, int64_t power) {
    return static_cast<int64_t>(Math::round(
            static_cast<double>(base) * power_curve(power, 2.08, 4.5)));
}

int64_t arc_steps(double sweep) {
    return std::max<int64_t>(3, static_cast<int64_t>(
            Math::ceil(Math::abs(sweep) * 12.0)));
}

int64_t arc_vertices(double sweep) {
    return arc_steps(sweep) * 6;
}

int64_t expected_vertices(int64_t effect_id, int64_t power_level,
        double area_radius, bool has_flight) {
    int64_t count = 8 * 6;
    if (is_blessing(effect_id)) {
        count += power_count(20, power_level) * 12;
    } else if (is_ward(effect_id)) {
        count += 3 * arc_vertices(TAU * 0.75);
    } else {
        count += power_count(14, power_level) * 6;
    }
    if (has_flight) {
        count += 12;
    }
    if (area_radius > 0.0) {
        return count + 3 * arc_vertices(TAU);
    }
    switch (effect_id) {
        case 77:
        case 84:
            return count + 6 * 6;
        case 78:
        case 85:
            return count + 3 * arc_vertices(TAU);
        case 19:
            return count + power_count(10, power_level) * arc_vertices(TAU);
        case 18:
            return count + 5 * arc_vertices(TAU * 0.7);
        case 79:
            return count + 8 * 12;
        case 74:
            return count + 3 * arc_vertices(TAU * 0.6);
        case 76:
            return count + power_count(12, power_level) * 6;
        case 75:
            return count + 4 * arc_vertices(TAU * 0.85);
        case 80:
            return count + 6 * arc_vertices(TAU * 0.85);
        case 81:
            return count + 4 * 6;
        case 82:
            return count + 4 * arc_vertices(PI / 2.0);
        default:
            return count;
    }
}

struct SurfaceArrays {
    PackedVector3Array vertices;
    PackedColorArray colors;
    Vector3 *vertex_write = nullptr;
    Color *color_write = nullptr;
    int64_t cursor = 0;
    bool failed = false;

    explicit SurfaceArrays(int64_t vertex_count) {
        vertices.resize(vertex_count);
        colors.resize(vertex_count);
        if (vertex_count > 0) {
            vertex_write = vertices.ptrw();
            color_write = colors.ptrw();
        }
    }

    void vertex(const Vector3 &position, const Color &color) {
        assert(cursor >= 0 && cursor < vertices.size());
        vertex_write[cursor] = position;
        color_write[cursor] = color;
        ++cursor;
    }

    void line(const Vector3 &a, const Vector3 &b, double width,
            const Color &color, const Vector3 &normal = Vector3(0, 1, 0)) {
        if (failed || cursor < 0 || cursor + 6 > vertices.size()) {
            failed = true;
            return;
        }
        Vector3 side = (b - a).cross(normal).normalized() *
                static_cast<real_t>(width) * static_cast<real_t>(0.5);
        if (static_cast<double>(side.length_squared()) < 0.0000001) {
            side = Vector3(1, 0, 0) * static_cast<real_t>(width) *
                    static_cast<real_t>(0.5);
        }
        const Vector3 a_minus = a - side;
        const Vector3 a_plus = a + side;
        const Vector3 b_plus = b + side;
        const Vector3 b_minus = b - side;
        vertex(a_minus, color);
        vertex(a_plus, color);
        vertex(b_plus, color);
        vertex(a_minus, color);
        vertex(b_plus, color);
        vertex(b_minus, color);
    }

    void arc(const Vector3 &centre, double radius, double width,
            const Color &color, double start = 0.0, double sweep = TAU,
            const Basis &basis = Basis()) {
        const int64_t steps = arc_steps(sweep);
        double angle = start + sweep * static_cast<double>(0) /
                static_cast<double>(steps);
        Vector3 previous = centre + basis.xform(Vector3(
                static_cast<real_t>(Math::cos(angle)), 0,
                static_cast<real_t>(Math::sin(angle)))) *
                static_cast<real_t>(radius);
        for (int64_t step = 0; step < steps; ++step) {
            angle = start + sweep * static_cast<double>(step + 1) /
                    static_cast<double>(steps);
            const Vector3 next = centre + basis.xform(Vector3(
                    static_cast<real_t>(Math::cos(angle)), 0,
                    static_cast<real_t>(Math::sin(angle)))) *
                    static_cast<real_t>(radius);
            line(previous, next, width, color, basis.get_column(1));
            previous = next;
        }
    }

    void spark(const Vector3 &centre, double size, const Color &color) {
        if (failed || cursor < 0 || cursor + 12 > vertices.size()) {
            failed = true;
            return;
        }
        const Vector3 up = centre + Vector3(0, 1, 0) *
                static_cast<real_t>(size);
        const Vector3 down = centre - Vector3(0, 1, 0) *
                static_cast<real_t>(size);
        const Vector3 right = Vector3(1, 0, 0) * static_cast<real_t>(size) *
                static_cast<real_t>(0.38);
        vertex(up, color);
        vertex(centre + right, color);
        vertex(down, color);
        vertex(up, color);
        vertex(down, color);
        vertex(centre - right, color);
        const Vector3 forward = Vector3(0, 0, -1) *
                static_cast<real_t>(size) * static_cast<real_t>(0.38);
        vertex(up, color);
        vertex(centre + forward, color);
        vertex(down, color);
        vertex(up, color);
        vertex(down, color);
        vertex(centre - forward, color);
    }
};

double clamp_unit(double value) {
    return value < 0.0 ? 0.0 : (value > 1.0 ? 1.0 : value);
}

double smoothstep(double from, double to, double value) {
    const double x = clamp_unit((value - from) / (to - from));
    return x * x * (3.0 - 2.0 * x);
}

Color hex_color(uint8_t r, uint8_t g, uint8_t b) {
    return Color(static_cast<float>(r) / 255.0f,
            static_cast<float>(g) / 255.0f,
            static_cast<float>(b) / 255.0f, 1.0f);
}

Array pack(const SurfaceArrays &surface) {
    Array result;
    result.resize(2);
    result[0] = surface.vertices;
    result[1] = surface.colors;
    return result;
}

} // namespace

void NativeWorldEffectGeometry::_bind_methods() {
    ClassDB::bind_method(D_METHOD("build", "effect_id", "power_level",
                                 "elapsed", "progress", "impact", "palette",
                                 "size", "radius", "area_radius", "has_flight",
                                 "flight_contact"),
            &NativeWorldEffectGeometry::build);
}

Array NativeWorldEffectGeometry::build(int64_t effect_id, int64_t power_level,
        double elapsed, double progress, const Vector3 &impact,
        const Color &palette, double size, double radius, double area_radius,
        bool has_flight, const Vector3 &flight_contact) const {
    if (power_level < 1 || power_level > 10 || !std::isfinite(elapsed) ||
            std::abs(elapsed) > MAX_SCALAR ||
            !std::isfinite(progress) || progress < 0.0 || progress > 1.0 ||
            !std::isfinite(size) || size < 0.0 || size > MAX_SCALAR ||
            !std::isfinite(radius) || radius < 0.0 || radius > MAX_SCALAR ||
            !std::isfinite(area_radius) || area_radius < 0.0 ||
            area_radius > MAX_SCALAR || !finite_vector(impact) ||
            !bounded_vector(impact) || !finite_color(palette) ||
            !bounded_color(palette) ||
            !finite_vector(flight_contact) || !bounded_vector(flight_contact)) {
        return Array();
    }

    const int64_t vertex_count = expected_vertices(
            effect_id, power_level, area_radius, has_flight);
    if (vertex_count <= 0 || vertex_count > 25000) {
        return Array();
    }
    SurfaceArrays surface(vertex_count);
    Color color = palette;
    color.a = static_cast<float>(Math::sin(progress * PI) * 0.7);
    const Vector3 centre = impact + Vector3(0, static_cast<real_t>(0.065), 0);

    for (int64_t i = 0; i < 8; ++i) {
        const double angle = i * TAU / 8.0 + elapsed * 0.3;
        const Vector3 direction(Math::cos(angle), 0, Math::sin(angle));
        surface.line(centre + direction * static_cast<real_t>(0.56) *
                        static_cast<real_t>(radius),
                centre + direction * static_cast<real_t>(0.66) *
                        static_cast<real_t>(radius),
                0.022 * size, color);
    }

    if (is_blessing(effect_id)) {
        const int64_t count = power_count(20, power_level);
        for (int64_t i = 0; i < count; ++i) {
            const double height = Math::fposmod(
                    static_cast<double>(i) / count + elapsed * 0.6, 1.0);
            const double angle = i * 2.4 + elapsed * 2.0;
            Color tint = color.lerp(Color(1.0, 0.84, 0.40, color.a),
                    static_cast<real_t>(static_cast<double>(i % 3) / 3.0));
            tint.a = static_cast<float>(static_cast<double>(tint.a) *
                    Math::sin(height * PI));
            surface.spark(impact + Vector3(
                    static_cast<real_t>(Math::cos(angle) * 0.45 * radius),
                    static_cast<real_t>(height * 1.9),
                    static_cast<real_t>(Math::sin(angle) * 0.45 * radius)),
                    0.047 * size, tint);
        }
    } else if (is_ward(effect_id)) {
        for (int64_t i = 0; i < 3; ++i) {
            surface.arc(impact + Vector3(0,
                                static_cast<real_t>(0.6 + i * 0.35), 0),
                    0.56 * radius, 0.018 * size, color,
                    elapsed * (i % 2 == 0 ? 1.0 : -1.0) + i, TAU * 0.75);
        }
    } else {
        const int64_t count = power_count(14, power_level);
        for (int64_t i = 0; i < count; ++i) {
            const double angle = static_cast<double>(i) * 2.399;
            const Vector3 direction(Math::cos(angle),
                    Math::sin(i * 1.7) * 0.6, Math::sin(angle));
            const Vector3 point = impact + Vector3(0, static_cast<real_t>(0.95), 0) +
                    direction * static_cast<real_t>(0.12 + progress * 0.7) *
                    static_cast<real_t>(radius);
            surface.line(point,
                    point + direction * static_cast<real_t>(0.10) *
                            static_cast<real_t>(1.0 - progress) *
                            static_cast<real_t>(size),
                    0.014 * size, color);
        }
    }

    if (has_flight) {
        const double flash = 1.0 - smoothstep(0.0, 0.22, progress);
        surface.spark(flight_contact, 0.22 * flash * size,
                Color(1.0, 0.91, 0.70, static_cast<float>(flash * 0.85)));
    }

    const Vector3 identity_centre = impact +
            Vector3(0, static_cast<real_t>(0.08), 0);
    if (area_radius > 0.0) {
        for (int64_t wave = 0; wave < 3; ++wave) {
            const double phase = clamp_unit(progress * 1.6 - wave * 0.13);
            Color tint = color;
            tint.a = static_cast<float>(Math::sin(phase * PI) * 0.55);
            surface.arc(identity_centre, area_radius * phase, 0.025 * size,
                    tint, wave, TAU);
        }
    } else if (effect_id == 84 || effect_id == 77) {
        for (int64_t i = 0; i < 6; ++i) {
            const Vector3 ray(Math::cos(i * TAU / 6.0), 0.18,
                    Math::sin(i * TAU / 6.0));
            surface.line(identity_centre,
                    identity_centre + ray * static_cast<real_t>(radius) *
                            static_cast<real_t>(0.3 + progress),
                    0.026 * size, color);
        }
    } else if (effect_id == 85 || effect_id == 78) {
        for (int64_t i = 0; i < 3; ++i) {
            surface.arc(identity_centre + Vector3(0, static_cast<real_t>(0.8), 0),
                    radius * 0.6, 0.014 * size, color, elapsed + i, TAU,
                    Basis(Vector3(1, 0, 0), static_cast<real_t>(i * PI / 3.0)));
        }
    } else if (effect_id == 19) {
        const int64_t count = power_count(10, power_level);
        for (int64_t i = 0; i < count; ++i) {
            const double phase = Math::fposmod(progress + i * 0.073, 1.0);
            const double angle = i * 2.399 + progress * 2.0;
            const Vector3 coin = identity_centre + Vector3(
                    Math::cos(angle) * (1.0 - phase) * 0.5,
                    phase * 1.5,
                    Math::sin(angle) * (1.0 - phase) * 0.5);
            surface.arc(coin, 0.055 * size, 0.019 * size, color, 0, TAU,
                    Basis(Vector3(1, 0, 0), static_cast<real_t>(PI / 2.0)));
        }
    } else if (effect_id == 18) {
        for (int64_t i = 0; i < 5; ++i) {
            surface.arc(identity_centre + Vector3(0,
                                static_cast<real_t>(i * 0.35 + progress * 0.5), 0),
                    (0.7 - progress * 0.3) * radius, 0.016 * size, color,
                    elapsed * 3.0 + i, TAU * 0.7);
        }
    } else if (effect_id == 79) {
        for (int64_t i = 0; i < 8; ++i) {
            const Vector3 ray(Math::cos(i * TAU / 8.0), 0.4,
                    Math::sin(i * TAU / 8.0));
            surface.spark(identity_centre + ray * static_cast<real_t>(progress) *
                            static_cast<real_t>(radius),
                    0.06 * size * (1.0 - progress), color);
        }
    } else if (effect_id == 74) {
        const Color palette_colors[3] = {
                hex_color(0xff, 0x9a, 0x42), hex_color(0x8c, 0xe5, 0xff),
                hex_color(0xd5, 0xfa, 0x65)};
        for (int64_t i = 0; i < 3; ++i) {
            Color tint = palette_colors[i];
            tint.a = color.a;
            surface.arc(identity_centre + Vector3(0,
                                static_cast<real_t>(0.4 + i * 0.4), 0),
                    radius * 0.65, 0.028 * size, tint,
                    elapsed + i * TAU / 3.0, TAU * 0.6);
        }
    } else if (effect_id == 76) {
        const int64_t count = power_count(12, power_level);
        for (int64_t i = 0; i < count; ++i) {
            const double phase = Math::fposmod(elapsed * 0.85 + i * 0.13, 1.0);
            const double angle = i * 2.399;
            const Vector3 flame = identity_centre + Vector3(
                    Math::cos(angle) * 0.5 * radius, phase * 1.7,
                    Math::sin(angle) * 0.5 * radius);
            surface.line(flame,
                    flame + Vector3(0, static_cast<real_t>(0.14), 0),
                    0.025 * size,
                    Color(color.r, color.g, color.b,
                            static_cast<float>(color.a * (1.0 - phase))));
        }
    } else if (effect_id == 75 || effect_id == 80) {
        const int64_t count = effect_id == 80 ? 6 : 4;
        for (int64_t i = 0; i < count; ++i) {
            surface.arc(identity_centre + Vector3(0, static_cast<real_t>(0.85), 0),
                    radius * 0.6, 0.012 * size, color, elapsed + i, TAU * 0.85,
                    Basis(Vector3(1, 0, 0), static_cast<real_t>(i * PI / 6.0)));
        }
    } else if (effect_id == 81) {
        const Vector3 aim = identity_centre + Vector3(0, 1, 0);
        for (int64_t i = 0; i < 4; ++i) {
            const Vector3 ray(Math::cos(i * PI / 2.0),
                    Math::sin(i * PI / 2.0), 0);
            surface.line(aim + ray * static_cast<real_t>(0.3) *
                            static_cast<real_t>(radius),
                    aim + ray * static_cast<real_t>(0.55) *
                            static_cast<real_t>(radius),
                    0.025 * size, color, Vector3(0, 0, -1));
        }
    } else if (effect_id == 82) {
        const Color palette_colors[4] = {
                hex_color(0xff, 0x9a, 0x42), hex_color(0x8c, 0xe5, 0xff),
                hex_color(0xa1, 0x8b, 0xff), hex_color(0xd5, 0xfa, 0x65)};
        for (int64_t i = 0; i < 4; ++i) {
            Color tint = palette_colors[i];
            tint.a = color.a;
            surface.arc(identity_centre + Vector3(0,
                                static_cast<real_t>(0.5 + i * 0.2), 0),
                    radius * 0.5, 0.025 * size, tint,
                    elapsed * 2.0 + i * PI / 2.0, PI / 2.0);
        }
    }

    if (surface.failed || surface.cursor != vertex_count) {
        return Array();
    }
    return pack(surface);
}

} // namespace godot
