#include "mounted_cape_body_surface.h"
#include <godot_cpp/classes/os.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/variant/packed_float32_array.hpp>
#include <godot_cpp/variant/packed_float64_array.hpp>
#include <godot_cpp/variant/packed_int32_array.hpp>
#include <godot_cpp/variant/packed_vector3_array.hpp>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <cstring>

using namespace godot;
namespace {
using Clock=std::chrono::steady_clock;
uint64_t elapsed(Clock::time_point start) {
    return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(Clock::now()-start).count());
}
constexpr double CELL=.08, MARGIN=.008;
constexpr int SUBDIVISIONS=4, SUBGRID_MIN_CANDIDATES=32;
constexpr uint64_t MAX_FINE_REFERENCES=8000000, MAX_CELL_EXPANSION=8;
int fine_coordinate(real_t value, int32_t coarse) {
    const int64_t global=static_cast<int64_t>(std::floor(static_cast<double>(value)/(CELL/SUBDIVISIONS)));
    return static_cast<int>(std::clamp<int64_t>(global-static_cast<int64_t>(coarse)*SUBDIVISIONS,0,SUBDIVISIONS-1));
}
int32_t signed_coordinate(uint32_t bits) {
    int32_t result;std::memcpy(&result,&bits,sizeof(result));return result;
}
constexpr int64_t MAX_SOURCES=64, MAX_BONES=1024, MAX_VERTICES=1000000;
constexpr int64_t MAX_INDICES=6000000, MAX_INFLUENCES=8000000;
constexpr uint64_t MAX_GRID_REFERENCES=8000000;
bool finite(const Transform3D &t) {
    return t.origin.is_finite() && t.basis.get_column(0).is_finite() &&
        t.basis.get_column(1).is_finite() && t.basis.get_column(2).is_finite();
}
bool invertible(const Transform3D &t) {
    return finite(t) && std::isfinite(static_cast<double>(t.basis.determinant())) &&
        std::abs(static_cast<double>(t.basis.determinant()))>1e-12;
}
uint64_t cell_key(int32_t x,int32_t y) {
    return (static_cast<uint64_t>(static_cast<uint32_t>(x))<<32)|static_cast<uint32_t>(y);
}
bool cell_coordinate(real_t value,int32_t &out) {
    const double n=std::floor(static_cast<double>(value)/CELL);
    if(!std::isfinite(n)||n < -1000000 || n > 1000000)return false;
    out=static_cast<int32_t>(n);return true;
}
bool has_type(const Dictionary &d,const char *key,Variant::Type type) {
    return d.has(key) && Variant(d[key]).get_type()==type;
}
}

RabbitLandsCapeBodySurface::RabbitLandsCapeBodySurface() {
    owner_thread=OS::get_singleton()->get_thread_caller_id();
}
bool RabbitLandsCapeBodySurface::owner() const {
    return OS::get_singleton()->get_thread_caller_id()==owner_thread;
}
void RabbitLandsCapeBodySurface::_bind_methods() {
    ClassDB::bind_method(D_METHOD("configure_sources","descriptors","skeleton_bone_count"),&RabbitLandsCapeBodySurface::configure_sources);
    ClassDB::bind_method(D_METHOD("set_subgrid_enabled","enabled"),&RabbitLandsCapeBodySurface::set_subgrid_enabled);
    ClassDB::bind_method(D_METHOD("prepare_pose","body_bone_poses","world","spine_skin_frame","rigid_source_world"),&RabbitLandsCapeBodySurface::prepare_pose);
    ClassDB::bind_method(D_METHOD("body_plane_at","world_point"),&RabbitLandsCapeBodySurface::body_plane_at);
    ClassDB::bind_method(D_METHOD("stats"),&RabbitLandsCapeBodySurface::stats);
    ClassDB::bind_method(D_METHOD("runtime_info"),&RabbitLandsCapeBodySurface::runtime_info);
}
bool RabbitLandsCapeBodySurface::configure_sources(const Array &descriptors,int64_t skeleton_bone_count) {
    if(!owner())return false;
    const auto started=Clock::now();
    configured=false;prepared=false;pose_cache_hit=false;
    if(skeleton_bone_count<0||skeleton_bone_count>MAX_BONES||descriptors.is_empty()||descriptors.size()>MAX_SOURCES)return false;
    std::vector<Source> next;
    int64_t total_vertices=0,total_indices=0,total_influences=0;
    for(int64_t si=0;si<descriptors.size();++si) {
        if(Variant(descriptors[si]).get_type()!=Variant::DICTIONARY)return false;
        const Dictionary descriptor=descriptors[si];
        if(!has_type(descriptor,"bones",Variant::PACKED_INT32_ARRAY)||!has_type(descriptor,"used_binds",Variant::PACKED_INT32_ARRAY)||
            !has_type(descriptor,"surfaces",Variant::ARRAY))return false;
        const PackedInt32Array bones=descriptor["bones"],used=descriptor["used_binds"];
        const Array surfaces=descriptor["surfaces"];
        if(bones.size()>MAX_BONES||used.size()>bones.size()||surfaces.size()>256)return false;
        Source source;
        std::vector<bool> used_flags(static_cast<size_t>(bones.size()),false);
        for(int64_t b=0;b<bones.size();++b) {
            if(bones[b]<0||bones[b]>=skeleton_bone_count)return false;
            source.bones.push_back(bones[b]);
        }
        for(int64_t b=0;b<used.size();++b) {
            if(used[b]<0||used[b]>=bones.size()||used_flags[used[b]])return false;
            used_flags[used[b]]=true;source.used_binds.push_back(used[b]);
        }
        for(int64_t surface_index=0;surface_index<surfaces.size();++surface_index) {
            if(Variant(surfaces[surface_index]).get_type()!=Variant::DICTIONARY)return false;
            const Dictionary d=surfaces[surface_index];
            if(!has_type(d,"vertices",Variant::PACKED_VECTOR3_ARRAY)||!has_type(d,"indices",Variant::PACKED_INT32_ARRAY)||
                !has_type(d,"starts",Variant::PACKED_INT32_ARRAY)||!has_type(d,"slots",Variant::PACKED_INT32_ARRAY)||
                !has_type(d,"points",Variant::PACKED_VECTOR3_ARRAY)||!has_type(d,"weights",Variant::PACKED_FLOAT32_ARRAY)||
                !has_type(d,"sums",Variant::PACKED_FLOAT64_ARRAY))return false;
            const PackedVector3Array vertices=d["vertices"],points=d["points"];
            const PackedInt32Array indices=d["indices"],starts=d["starts"],slots=d["slots"];
            const PackedFloat32Array weights=d["weights"];
            const PackedFloat64Array sums=d["sums"];
            total_vertices+=vertices.size();total_indices+=indices.size();total_influences+=slots.size();
            if(total_vertices>MAX_VERTICES||total_indices>MAX_INDICES||total_influences>MAX_INFLUENCES||
                indices.size()%3!=0||starts.size()!=vertices.size()+1||sums.size()!=vertices.size()||
                slots.size()!=points.size()||slots.size()!=weights.size()||starts[0]!=0||starts[starts.size()-1]!=slots.size())return false;
            Surface surface;
            for(int64_t v=0;v<vertices.size();++v) {
                if(!vertices[v].is_finite()||!std::isfinite(sums[v])||sums[v]<0||sums[v]>8||
                    starts[v]<0||starts[v+1]<starts[v]||starts[v+1]>slots.size()||starts[v+1]-starts[v]>8)return false;
                double sum=0;
                for(int32_t at=starts[v];at<starts[v+1];++at) {
                    if(slots[at]<0||slots[at]>=bones.size()||!used_flags[slots[at]]||!points[at].is_finite()||
                        !std::isfinite(weights[at])||weights[at]<=0||weights[at]>1)return false;
                    sum+=weights[at];
                }
                if(std::abs(sum-sums[v])>1e-7)return false;
                surface.vertices.push_back(vertices[v]);surface.starts.push_back(starts[v]);surface.sums.push_back(sums[v]);
            }
            surface.starts.push_back(starts[starts.size()-1]);
            for(int64_t at=0;at<slots.size();++at) {
                surface.slots.push_back(slots[at]);surface.points.push_back(points[at]);surface.weights.push_back(weights[at]);
            }
            for(int64_t at=0;at<indices.size();++at) {
                if(indices[at]<0||indices[at]>=vertices.size())return false;
                surface.indices.push_back(indices[at]);
            }
            source.surfaces.push_back(std::move(surface));
        }
        next.push_back(std::move(source));
    }
    if(total_vertices==0)return false;
    sources=std::move(next);bone_count=skeleton_bone_count;vertex_count=total_vertices;
    triangles.clear();grid.clear();pose_context.clear();configured=true;
    coarse_references=fine_references=refined_cells=coarse_max_candidates=0;
    configure_us=elapsed(started);return true;
}

bool RabbitLandsCapeBodySurface::set_subgrid_enabled(bool enabled) {
    if(!owner())return false;
    if(subgrid_enabled==enabled)return true;
    subgrid_enabled=enabled;prepared=false;pose_cache_hit=false;pose_context.clear();
    return true;
}

void RabbitLandsCapeBodySurface::build_subgrid(Grid &cells,const std::vector<Triangle> &values,
    uint64_t &refined,uint64_t &references) {
    refined=references=0;
    // The original coarse membership/order is the authority. Subcells remove
    // only candidates whose existing padded XY box cannot contain the query.
    for(auto &item:cells) {
        GridCell &cell=item.second;
        if(cell.coarse.size()<SUBGRID_MIN_CANDIDATES)continue;
        const int32_t x=signed_coordinate(static_cast<uint32_t>(item.first>>32));
        const int32_t y=signed_coordinate(static_cast<uint32_t>(item.first));
        uint64_t required=0;
        std::array<uint32_t,16> counts{};
        for(const auto &candidate:cell.coarse) {
            const Triangle &t=values[candidate.index];
            const int x0=fine_coordinate(t.low.x,x),x1=fine_coordinate(t.high.x,x);
            const int y0=fine_coordinate(t.low.y,y),y1=fine_coordinate(t.high.y,y);
            required+=static_cast<uint64_t>(x1-x0+1)*(y1-y0+1);
            if(required>cell.coarse.size()*MAX_CELL_EXPANSION||required>MAX_FINE_REFERENCES-references)break;
            for(int sy=y0;sy<=y1;++sy)for(int sx=x0;sx<=x1;++sx)++counts[sy*SUBDIVISIONS+sx];
        }
        // Large triangles or extreme inputs can retain the exact coarse path.
        if(required>cell.coarse.size()*MAX_CELL_EXPANSION||required>MAX_FINE_REFERENCES-references)continue;
        for(size_t i=0;i<counts.size();++i)cell.offsets[i+1]=cell.offsets[i]+counts[i];
        cell.fine.resize(static_cast<size_t>(required));
        std::array<uint32_t,16> cursors{};
        std::copy(cell.offsets.begin(),cell.offsets.begin()+16,cursors.begin());
        for(const auto &candidate:cell.coarse) {
            const Triangle &t=values[candidate.index];
            const int x0=fine_coordinate(t.low.x,x),x1=fine_coordinate(t.high.x,x);
            const int y0=fine_coordinate(t.low.y,y),y1=fine_coordinate(t.high.y,y);
            for(int sy=y0;sy<=y1;++sy)for(int sx=x0;sx<=x1;++sx)
                cell.fine[cursors[sy*SUBDIVISIONS+sx]++]=candidate;
        }
        references+=required;++refined;cell.refined=true;
    }
}

bool RabbitLandsCapeBodySurface::prepare_pose(const Array &body_bone_poses,const Transform3D &world,
    const Transform3D &spine_skin_frame,const Array &rigid_source_world) {
    if(!owner())return false;
    const auto started=Clock::now();
    const bool previously_prepared=prepared;
    prepared=false;pose_cache_hit=false;
    if(!configured||body_bone_poses.size()!=bone_count||rigid_source_world.size()!=static_cast<int64_t>(sources.size())||
        !invertible(world)||!invertible(spine_skin_frame))return false;
    std::vector<Transform3D> body;
    body.reserve(static_cast<size_t>(bone_count));
    for(int64_t b=0;b<bone_count;++b) {
        if(Variant(body_bone_poses[b]).get_type()!=Variant::TRANSFORM3D)return false;
        const Transform3D pose=body_bone_poses[b];if(!finite(pose))return false;body.push_back(pose);
    }
    const Transform3D next_to_world=world*spine_skin_frame;
    if(!invertible(next_to_world))return false;
    const Transform3D next_from_world=next_to_world.affine_inverse();
    const Transform3D from_skeleton=spine_skin_frame.affine_inverse();
    const Basis next_normal_to_world=next_to_world.basis.inverse().transposed();
    if(!finite(next_from_world)||!finite(from_skeleton)||!finite(Transform3D(next_normal_to_world,Vector3())))return false;
    std::vector<std::vector<Transform3D>> poses(sources.size());
    std::vector<Transform3D> context;
    for(size_t si=0;si<sources.size();++si) {
        if(Variant(rigid_source_world[static_cast<int64_t>(si)]).get_type()!=Variant::TRANSFORM3D)return false;
        const Transform3D rigid=rigid_source_world[static_cast<int64_t>(si)];
        if(!finite(rigid))return false;
        const Source &source=sources[si];
        poses[si].resize(source.bones.size());
        for(int32_t bind:source.used_binds) {
            const Transform3D pose=from_skeleton*body[source.bones[bind]];
            if(!finite(pose))return false;
            poses[si][bind]=pose;context.push_back(pose);
        }
        if(source.bones.empty()) { poses[si].push_back(next_from_world*rigid);context.push_back(poses[si][0]); }
    }
    if(previously_prepared&&context_origin==from_skeleton.origin&&pose_context==context) {
        // World orientation may change even when the local body pose is cached.
        // The expression matches the original per-query normal exactly.
        for(auto &triangle:triangles) {
            triangle.outward=next_normal_to_world.xform(triangle.normal).normalized();
            if(!triangle.outward.is_finite())return false;
        }
        to_world=next_to_world;from_world=next_from_world;normal_to_world=next_normal_to_world;
        prepared=true;pose_cache_hit=true;++pose_cache_hits;prepare_us=elapsed(started);return true;
    }
    std::vector<Triangle> next_triangles;
    Grid next_grid;
    uint64_t references=0;
    for(size_t si=0;si<sources.size();++si) {
        const Source &source=sources[si];
        for(const Surface &surface:source.surfaces) {
            std::vector<Vector3> positions(surface.vertices.size());
            for(size_t v=0;v<positions.size();++v) {
                Vector3 point;
                if(source.bones.empty())point=poses[si][0].xform(surface.vertices[v]);
                else {
                    for(int32_t at=surface.starts[v];at<surface.starts[v+1];++at) {
                        const Transform3D &pose=poses[si][surface.slots[at]];
                        point+=pose.basis.xform(surface.points[at])+pose.origin*surface.weights[at];
                    }
                    // The raw blend weights the precomposed inverse translation;
                    // restore its remainder to match world-after-blend GPU LBS.
                    point+=from_skeleton.origin*static_cast<real_t>(1.0-surface.sums[v]);
                }
                if(!point.is_finite())return false;
                positions[v]=point;
            }
            for(size_t at=0;at<surface.indices.size();at+=3) {
                const Vector3 &a=positions[surface.indices[at]],&b=positions[surface.indices[at+1]],&c=positions[surface.indices[at+2]];
                Triangle t;t.uv=Vector2(a.x,a.y);t.ab=Vector2(b.x-a.x,b.y-a.y);t.ac=Vector2(c.x-a.x,c.y-a.y);
                const double area=t.ab.cross(t.ac);
                if(!std::isfinite(area))return false;
                if(std::abs(area)<1e-9)continue;
                t.inverse_area=1.0/area;t.normal=(b-a).cross(c-a).normalized();if(t.normal.z>0)t.normal=-t.normal;
                if(!t.normal.is_finite()||t.normal==Vector3())return false;
                t.outward=next_normal_to_world.xform(t.normal).normalized();
                if(!t.outward.is_finite())return false;
                t.heights=Vector3(a.z,b.z-a.z,c.z-a.z);
                const Vector2 low(std::min({a.x,b.x,c.x}),std::min({a.y,b.y,c.y}));
                const Vector2 high(std::max({a.x,b.x,c.x}),std::max({a.y,b.y,c.y}));
                t.low=low-Vector2(.000001f,.000001f);
                // Match Rect2(position,size).end arithmetic in the GD fallback.
                t.high=t.low+(high-low+Vector2(.000002f,.000002f));
                int32_t x0,y0,x1,y1;
                if(!cell_coordinate(low.x,x0)||!cell_coordinate(low.y,y0)||!cell_coordinate(high.x,x1)||!cell_coordinate(high.y,y1))return false;
                const uint64_t count=static_cast<uint64_t>(static_cast<int64_t>(x1)-x0+1)*static_cast<uint64_t>(static_cast<int64_t>(y1)-y0+1);
                if(count>MAX_GRID_REFERENCES||references+count>MAX_GRID_REFERENCES)return false;
                references+=count;
                const Candidate candidate{std::min({a.z,b.z,c.z}),static_cast<uint32_t>(next_triangles.size())};
                next_triangles.push_back(t);
                for(int32_t x=x0;x<=x1;++x)for(int32_t y=y0;y<=y1;++y)next_grid[cell_key(x,y)].coarse.push_back(candidate);
            }
        }
    }
    for(auto &cell:next_grid)std::sort(cell.second.coarse.begin(),cell.second.coarse.end(),[](const Candidate &a,const Candidate &b){
        return a.z<b.z||(a.z==b.z&&a.index<b.index);
    });
    uint64_t next_refined=0,next_fine_references=0,next_max_candidates=0;
    for(const auto &cell:next_grid)next_max_candidates=std::max<uint64_t>(next_max_candidates,cell.second.coarse.size());
    if(subgrid_enabled)build_subgrid(next_grid,next_triangles,next_refined,next_fine_references);
    triangles=std::move(next_triangles);grid=std::move(next_grid);pose_context=std::move(context);context_origin=from_skeleton.origin;
    coarse_references=references;fine_references=next_fine_references;refined_cells=next_refined;coarse_max_candidates=next_max_candidates;
    to_world=next_to_world;from_world=next_from_world;normal_to_world=next_normal_to_world;
    prepared=true;prepare_us=elapsed(started);return true;
}

bool RabbitLandsCapeBodySurface::batch_owner_valid() const { return owner(); }
Plane RabbitLandsCapeBodySurface::body_plane_at(const Vector3 &world_point) const {
    if(!owner())return Plane();
    return trusted_body_plane_at(world_point);
}
Plane RabbitLandsCapeBodySurface::trusted_body_plane_at(const Vector3 &world_point) const {
    if(!prepared||!world_point.is_finite())return Plane();
    const Vector3 local=from_world.xform(world_point);
    int32_t x,y;if(!cell_coordinate(local.x,x)||!cell_coordinate(local.y,y))return Plane();
    const auto found=grid.find(cell_key(x,y));if(found==grid.end())return Plane();
    const Vector2 uv(local.x,local.y);
    double minimum=std::numeric_limits<double>::infinity();
    const Triangle *best=nullptr;
    uint32_t best_index=std::numeric_limits<uint32_t>::max();
    const GridCell &cell=found->second;
    const Candidate *first=cell.coarse.data(),*end=first+cell.coarse.size();
    if(cell.refined) {
        const int at=fine_coordinate(local.y,y)*SUBDIVISIONS+fine_coordinate(local.x,x);
        first=cell.fine.data()+cell.offsets[at];end=cell.fine.data()+cell.offsets[at+1];
    }
    for(const Candidate *next=first;next!=end;++next) {
        const Candidate &candidate=*next;
        if(candidate.z>minimum+.000002)break;
        const Triangle &t=triangles[candidate.index];
        if(uv.x<t.low.x||uv.y<t.low.y||uv.x>=t.high.x||uv.y>=t.high.y)continue;
        const Vector2 q=uv-t.uv;
        const double u=q.cross(t.ac)*t.inverse_area,v=t.ab.cross(q)*t.inverse_area;
        if(u<-.000001||v<-.000001||u+v>1.000001)continue;
        const double z=t.heights.x+t.heights.y*u+t.heights.z*v;
        if(z<minimum||(z==minimum&&candidate.index<best_index)) {minimum=z;best=&t;best_index=candidate.index;}
    }
    if(!best)return Plane();
    const Vector3 outward=best->outward;
    const Vector3 surface=to_world.xform(Vector3(local.x,local.y,static_cast<real_t>(minimum)))+outward*static_cast<real_t>(MARGIN);
    if(!outward.is_finite()||!surface.is_finite())return Plane();
    return Plane(outward,outward.dot(surface));
}
Dictionary RabbitLandsCapeBodySurface::stats() const {
    Dictionary d;if(!owner())return d;
    d["meshes"]=static_cast<int64_t>(sources.size());d["vertices"]=vertex_count;d["triangles"]=static_cast<int64_t>(triangles.size());
    d["configure_usec"]=static_cast<int64_t>(configure_us);d["prepare_usec"]=static_cast<int64_t>(prepare_us);
    d["subgrid_enabled"]=subgrid_enabled;d["coarse_cells"]=static_cast<int64_t>(grid.size());
    d["coarse_references"]=static_cast<int64_t>(coarse_references);d["fine_references"]=static_cast<int64_t>(fine_references);
    d["refined_cells"]=static_cast<int64_t>(refined_cells);d["coarse_max_candidates"]=static_cast<int64_t>(coarse_max_candidates);
    d["pose_cache_hit"]=pose_cache_hit;d["pose_cache_hits"]=static_cast<int64_t>(pose_cache_hits);d["prepared"]=prepared;
    return d;
}
Dictionary RabbitLandsCapeBodySurface::runtime_info() const {
    Dictionary d;d["ready"]=owner()&&sizeof(real_t)==4;d["mounted_cape_body_surface_api"]=1;
    d["engine_scalar_bytes"]=static_cast<int64_t>(sizeof(real_t));d["world_normal_cache"]=true;d["subgrid"]=true;d["subgrid_divisions"]=SUBDIVISIONS;return d;
}
