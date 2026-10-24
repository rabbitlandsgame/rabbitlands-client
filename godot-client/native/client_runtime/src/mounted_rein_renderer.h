#pragma once
#include <godot_cpp/classes/ref.hpp>
#include <godot_cpp/classes/array_mesh.hpp>
#include <godot_cpp/classes/mesh_instance3d.hpp>
#include <godot_cpp/classes/skeleton3d.hpp>
#include <godot_cpp/variant/packed_int32_array.hpp>
#include <godot_cpp/variant/packed_float64_array.hpp>
#include <godot_cpp/variant/packed_vector3_array.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <array>
#include <functional>
#include <vector>

namespace godot {
// One existing rein MeshInstance/material and current spatial owner per rider.
// Reusable geometry state; scene links are weak ObjectIDs, never Rust pointers.
class MountedReinRenderer {
    uint64_t rein_id=0,mesh_id=0,pony_id=0,owner_id=0;
    size_t rider_bones=0;
    std::array<int,9> bones{};
    std::array<Vector3,2> sockets{};
    std::array<double,8> tuning{};
    std::vector<PackedVector3Array> paths;
    Ref<ArrayMesh> mesh;
    PackedVector3Array vertices,normals;
    std::array<PackedVector3Array,2> incoming,tails;
    std::array<double,2> lengths{};
    size_t write_at=0,vertex_count=0;
    uint64_t calls=0;
    bool resolve(Node3D *&reins,MeshInstance3D *&straps,Skeleton3D *&pony) const;
    void triangle(const Vector3 &a,const Vector3 &b,const Vector3 &c);
    void strip(const PackedVector3Array &points,const Vector3 &up);
public:
    bool configure(Skeleton3D *rider,Node3D *owner,Node3D *reins,MeshInstance3D *straps,Skeleton3D *pony,
        const PackedInt32Array &indices,const PackedFloat64Array &anchors,
        const PackedFloat64Array &parameters,const Array &bridle_paths);
    bool render(Skeleton3D *rider,const Transform3D &seat,double grip_weight,const std::function<bool()> &still_valid);
    Dictionary snapshot(bool geometry) const;
};
}
