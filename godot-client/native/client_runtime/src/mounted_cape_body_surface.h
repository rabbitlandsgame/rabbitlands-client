#pragma once
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/plane.hpp>
#include <godot_cpp/variant/transform3d.hpp>
#include <cstdint>
#include <array>
#include <unordered_map>
#include <vector>

namespace godot {
// Numeric posterior envelope only. Scene selection, resource lifetimes and
// skeleton ownership remain with CapeMountedBodySurface in GDScript.
class RabbitLandsCapeBodySurface : public RefCounted {
    GDCLASS(RabbitLandsCapeBodySurface, RefCounted);
    struct Surface {
        std::vector<Vector3> vertices, points;
        std::vector<int32_t> indices, starts, slots;
        std::vector<float> weights;
        std::vector<double> sums;
    };
    struct Source {
        std::vector<int32_t> bones, used_binds;
        std::vector<Surface> surfaces;
    };
    struct Triangle {
        Vector2 uv, ab, ac, low, high;
        Vector3 heights, normal, outward;
        double inverse_area=0;
    };
    struct Candidate { real_t z; uint32_t index; };
    struct GridCell {
        std::vector<Candidate> coarse;
        std::vector<Candidate> fine;
        std::array<uint32_t, 17> offsets{};
        bool refined = false;
    };
    using Grid = std::unordered_map<uint64_t, GridCell>;
    std::vector<Source> sources;
    std::vector<Triangle> triangles;
    Grid grid;
    std::vector<Transform3D> pose_context;
    Vector3 context_origin;
    Transform3D to_world, from_world;
    Basis normal_to_world;
    int64_t owner_thread=0, bone_count=0, vertex_count=0;
    uint64_t configure_us=0, prepare_us=0, pose_cache_hits=0;
    bool configured=false, prepared=false, pose_cache_hit=false, subgrid_enabled=false;
    uint64_t coarse_references=0, fine_references=0, refined_cells=0, coarse_max_candidates=0;
    static void build_subgrid(Grid &cells, const std::vector<Triangle> &values,
        uint64_t &refined, uint64_t &references);
    bool owner() const;
protected:
    static void _bind_methods();
public:
    RabbitLandsCapeBodySurface();
    bool configure_sources(const Array &descriptors, int64_t skeleton_bone_count);
    // Optional exact acceleration; invalidates prepared cache, then prepare again.
    bool set_subgrid_enabled(bool enabled);
    bool prepare_pose(const Array &body_bone_poses, const Transform3D &world,
        const Transform3D &spine_skin_frame, const Array &rigid_source_world);
    // A nonzero plane also denotes a covered point that is already clear.
    Plane body_plane_at(const Vector3 &world_point) const;
    // Unbound C++ batch entry. The caller validates ownership before its
    // immutable numeric queries run and waits for completion before returning.
    bool batch_owner_valid() const;
    Plane trusted_body_plane_at(const Vector3 &world_point) const;
    Dictionary stats() const;
    Dictionary runtime_info() const;
};
}
