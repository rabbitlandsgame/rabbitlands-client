#include "mounted_rein_renderer.h"
#include <godot_cpp/core/object.hpp>
#include <cmath>
#include <algorithm>

using namespace godot;
namespace {
bool finite_buffer(const double *v,size_t count) {for(size_t i=0;i<count;++i)if(!std::isfinite(v[i]))return false;return true;}
}
bool MountedReinRenderer::resolve(Node3D *&reins,MeshInstance3D *&straps,Skeleton3D *&pony) const {
    reins=Object::cast_to<Node3D>(ObjectDB::get_instance(rein_id));
    straps=Object::cast_to<MeshInstance3D>(ObjectDB::get_instance(mesh_id));
    pony=Object::cast_to<Skeleton3D>(ObjectDB::get_instance(pony_id));
    auto *owner=Object::cast_to<Node3D>(ObjectDB::get_instance(owner_id));
    return reins && straps && pony && owner && reins->is_inside_tree() && straps->is_inside_tree()
        && pony->is_inside_tree() && owner->is_inside_tree() && !reins->is_queued_for_deletion()
        && !straps->is_queued_for_deletion() && !pony->is_queued_for_deletion() && !owner->is_queued_for_deletion()
        && owner->is_ancestor_of(reins) && reins->is_ancestor_of(straps) && owner->is_ancestor_of(pony)
        && bones[8]<pony->get_bone_count();
}
bool MountedReinRenderer::configure(Skeleton3D *rider,Node3D *owner,Node3D *reins,MeshInstance3D *straps,Skeleton3D *pony,
    const PackedInt32Array &indices,const PackedFloat64Array &anchors,const PackedFloat64Array &parameters,const Array &bridle_paths) {
    if(!rider || !owner || !reins || !straps || !pony || indices.size()!=9 || anchors.size()!=6 || parameters.size()!=8
        || !finite_buffer(anchors.ptr(),6) || !finite_buffer(parameters.ptr(),8) || bridle_paths.size()>16)return false;
    for(int i=0;i<9;++i) {
        if(indices[i]<0 || indices[i]>=(i==8?pony->get_bone_count():rider->get_bone_count()))return false;
        bones[i]=indices[i];
    }
    for(int i=0;i<8;++i)tuning[i]=parameters[i];
    if(tuning[0]!=std::floor(tuning[0]) || tuning[0]<1. || tuning[0]>128. || tuning[5]<=0. || tuning[6]<=0.)return false;
    for(int side=0;side<2;++side)sockets[side]=Vector3(anchors[side*3],anchors[side*3+1],anchors[side*3+2]);
    paths.clear();vertex_count=(2*(static_cast<size_t>(tuning[0])+9))*24;
    for(int64_t i=0;i<bridle_paths.size();++i) {
        if(bridle_paths[i].get_type()!=Variant::PACKED_VECTOR3_ARRAY)return false;
        PackedVector3Array path=bridle_paths[i];
        if(path.size()<2 || path.size()>64)return false;
        for(int64_t j=0;j<path.size();++j)if(!path[j].is_finite())return false;
        vertex_count+=static_cast<size_t>(path.size()-1)*24;paths.push_back(path);
    }
    rein_id=reins->get_instance_id();mesh_id=straps->get_instance_id();pony_id=pony->get_instance_id();owner_id=owner->get_instance_id();
    rider_bones=static_cast<size_t>(rider->get_bone_count());
    Node3D *r=nullptr;MeshInstance3D *m=nullptr;Skeleton3D *p=nullptr;
    if(!resolve(r,m,p))return false;
    mesh.instantiate();vertices.resize(vertex_count);normals.resize(vertex_count);
    return true;
}
void MountedReinRenderer::triangle(const Vector3 &a,const Vector3 &b,const Vector3 &c) {
    const Vector3 normal=(b-a).cross(c-a).normalized();
    for(const Vector3 &p:{a,b,c}) {vertices.set(write_at,p);normals.set(write_at,normal);++write_at;}
}
void MountedReinRenderer::strip(const PackedVector3Array &points,const Vector3 &up) {
    for(int64_t i=0;i<points.size()-1;++i) {
        const Vector3 direction=(points[i+1]-points[i]).normalized();
        Vector3 across=(up-direction*up.dot(direction)).normalized();
        across=across.rotated(direction,static_cast<real_t>(tuning[7]*3.14159265358979323846/180.));
        const Vector3 wide=across*static_cast<real_t>(tuning[5])*.5f;
        const Vector3 thin=direction.cross(across)*static_cast<real_t>(tuning[6])*.5f;
        const Vector3 a[4]={points[i]+wide+thin,points[i]-wide+thin,points[i]-wide-thin,points[i]+wide-thin};
        const Vector3 b[4]={points[i+1]+wide+thin,points[i+1]-wide+thin,points[i+1]-wide-thin,points[i+1]+wide-thin};
        for(int face=0;face<4;++face) {const int next=(face+1)%4;triangle(a[face],a[next],b[next]);triangle(a[face],b[next],b[face]);}
    }
}
bool MountedReinRenderer::render(Skeleton3D *rider,const Transform3D &seat,double grip_weight,const std::function<bool()> &still_valid) {
    if(!rider || static_cast<size_t>(rider->get_bone_count())!=rider_bones || !std::isfinite(grip_weight) || grip_weight<0. || grip_weight>1.)return false;
    Node3D *reins=nullptr;MeshInstance3D *straps=nullptr;Skeleton3D *pony=nullptr;
    auto valid=[&]() {return still_valid() && resolve(reins,straps,pony);};
    if(!valid())return false;
    const Transform3D local_to_world=reins->get_global_transform();if(!valid())return false;
    if(std::abs(local_to_world.basis.determinant())<1e-12)return false;
    const Transform3D to_local=local_to_world.affine_inverse();
    const Vector3 up=local_to_world.basis.inverse().xform(Vector3(0,1,0));
    const Transform3D rider_world=rider->get_global_transform();if(!valid())return false;
    const Transform3D pony_world=pony->get_global_transform();if(!valid())return false;
    const Transform3D head_pose=pony->get_bone_global_pose(bones[8]);if(!valid())return false;
    const Transform3D head=pony_world*head_pose;
    write_at=0;
    for(int side=0;side<2;++side) {
        std::array<Vector3,4> fingers;
        for(int i=0;i<4;++i) {fingers[i]=rider->get_bone_global_pose(bones[side*4+i]).origin;if(!valid())return false;}
        const Vector3 grip=rider_world.xform((fingers[0]+fingers[1])*.5f);
        const Vector3 exit=rider_world.xform((fingers[2]+fingers[3])*.5f);
        const double sign=side==0?1.:-1.;
        const Vector3 parked=seat.origin+seat.basis.xform(Vector3(sign*.055,.12,.21));
        const Vector3 finish=grip.lerp(parked,static_cast<real_t>(grip_weight));
        const Vector3 leave=exit.lerp(parked+Vector3(0,-.025,0),static_cast<real_t>(grip_weight));
        const Vector3 start=head.xform(sockets[side]);
        PackedVector3Array &points=incoming[side];points.resize(static_cast<int64_t>(tuning[0])+1);lengths[side]=0.;
        for(int index=0;index<=static_cast<int>(tuning[0]);++index) {
            const double u=static_cast<double>(index)/tuning[0],slack=std::sin(3.14159265358979323846*u);
            Vector3 point=start.lerp(finish,static_cast<real_t>(u));
            point+=seat.basis.get_column(0)*static_cast<real_t>(sign)*static_cast<real_t>(tuning[2])*static_cast<real_t>(slack);
            point+=Vector3(0,-1,0)*static_cast<real_t>(tuning[1])*static_cast<real_t>(slack);
            if(index>0)lengths[side]+=static_cast<double>(point.distance_to(local_to_world.xform(points[index-1])));
            points.set(index,to_local.xform(point));
        }
        strip(points,up);
        Vector3 tail=leave+Vector3(0,-1,0)*static_cast<real_t>(tuning[3]);
        tail+=seat.basis.get_column(0)*static_cast<real_t>(sign)*static_cast<real_t>(tuning[4])-seat.basis.get_column(2)*.025f;
        PackedVector3Array &grip_points=tails[side];grip_points.resize(10);
        grip_points.set(0,to_local.xform(finish));grip_points.set(1,to_local.xform(leave));
        for(int index=1;index<=8;++index) {
            const double u=static_cast<double>(index)/8.;
            Vector3 point=leave.lerp(tail,static_cast<real_t>(u));
            point+=seat.basis.get_column(0)*static_cast<real_t>(sign)*.015f*static_cast<real_t>(std::sin(3.14159265358979323846*u));
            grip_points.set(index+1,to_local.xform(point));
        }
        strip(grip_points,up);
    }
    for(const PackedVector3Array &path:paths) {
        PackedVector3Array points;points.resize(path.size());
        for(int64_t i=0;i<path.size();++i)points.set(i,to_local.xform(head.xform(path[i])));
        strip(points,up);
    }
    if(write_at!=vertex_count || !valid())return false;
    for(int64_t i=0;i<vertices.size();++i)if(!vertices[i].is_finite() || !normals[i].is_finite())return false;
    // Resources remain strongly held across changed callbacks; every following
    // scene access rechecks weak ownership and the enclosing mutation guard.
    if(straps->get_mesh()!=mesh) {straps->set_mesh(mesh);if(!valid())return false;}
    mesh->clear_surfaces();if(!valid())return false;
    Array arrays;arrays.resize(Mesh::ARRAY_MAX);arrays[Mesh::ARRAY_VERTEX]=vertices;arrays[Mesh::ARRAY_NORMAL]=normals;
    mesh->add_surface_from_arrays(Mesh::PRIMITIVE_TRIANGLES,arrays);if(!valid())return false;
    reins->show();if(!valid())return false;
    ++calls;return true;
}
Dictionary MountedReinRenderer::snapshot(bool geometry) const {
    Dictionary result;
    result["backend"]="native-array-mesh";result["calls"]=static_cast<int64_t>(calls);
    result["vertices"]=static_cast<int64_t>(vertex_count);result["surfaces"]=mesh.is_valid()?mesh->get_surface_count():0;
    if(geometry) {
        Dictionary p,g,l;
        for(int side=0;side<2;++side) {const StringName key=side==0?StringName("l"):StringName("r");p[key]=incoming[side];g[key]=tails[side];l[key]=lengths[side];}
        result["points"]=p;result["gripPoints"]=g;result["lengths"]=l;
        result["meshVertices"]=vertices;result["meshNormals"]=normals;
    }
    return result;
}
