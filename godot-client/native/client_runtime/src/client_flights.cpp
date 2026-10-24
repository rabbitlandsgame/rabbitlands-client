#include "client_flights.h"
#include <godot_cpp/classes/os.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/variant/aabb.hpp>
#include <godot_cpp/variant/color.hpp>
#include <godot_cpp/variant/vector2.hpp>
#include <godot_cpp/variant/vector3.hpp>
#include <algorithm>
#include <chrono>
#include <cmath>

using namespace godot;
namespace godot {
static bool cpp_flight_owned=false;
bool client_runtime_owns_cpp_flight(){return cpp_flight_owned;}
void client_runtime_mark_cpp_flight_owned(){cpp_flight_owned=true;}
}
namespace {
using Clock=std::chrono::steady_clock;
int64_t micros(Clock::time_point start){return std::chrono::duration_cast<std::chrono::microseconds>(Clock::now()-start).count();}
Vector3 vector(const double *v){return Vector3(v[0],v[1],v[2]);}
bool finite(const double *v,size_t n){for(size_t i=0;i<n;++i)if(!std::isfinite(v[i])||std::abs(v[i])>1e12)return false;return true;}
}
RabbitLandsSpellFlightRuntime::RabbitLandsSpellFlightRuntime(){
    owner_thread=OS::get_singleton()->get_thread_caller_id();
    if(rl_flights_abi()==1)core=rl_flights_create();
}
RabbitLandsSpellFlightRuntime::~RabbitLandsSpellFlightRuntime(){rl_flights_destroy(core);}
bool RabbitLandsSpellFlightRuntime::on_owner_thread() const {
    return OS::get_singleton()->get_thread_caller_id()==owner_thread;
}
int64_t RabbitLandsSpellFlightRuntime::get_last_status() const {
    return on_owner_thread()?last_status:1;
}
Dictionary RabbitLandsSpellFlightRuntime::runtime_info()const{
    if(!on_owner_thread()){Dictionary failure;failure["ready"]=false;failure["status"]=1;failure["reason"]="wrong_thread";return failure;}
    Dictionary d;d["abi"]=rl_flights_abi();d["ready"]=core!=nullptr;d["family"]="heat_bolt";
    d["language"]="rust";d["capacity"]=512;d["packed_reallocations"]=static_cast<int64_t>(packed_reallocations);
    d["cpp_comparator_provider"]=client_runtime_owns_cpp_flight()?"client_runtime":"external";
    uint64_t packed_bytes=0;
    for(const auto &f:published)for(const auto *a:{&f.ribbon,&f.glow})
        packed_bytes+=static_cast<uint64_t>(a->vertices.size())*sizeof(Vector3)
            +static_cast<uint64_t>(a->colors.size())*sizeof(Color)+static_cast<uint64_t>(a->uvs.size())*sizeof(Vector2);
    d["retained_packed_payload_bytes"]=static_cast<int64_t>(packed_bytes);
    d["adapter_vector_capacity_bytes"]=static_cast<int64_t>(specs.capacity()*sizeof(RlFlightSpec)
        +anchors.capacity()*sizeof(RlFlightAnchor)+decisions.capacity()*sizeof(int64_t)+published.capacity()*sizeof(Published));
    d["memory_scope"]="owned Rust vector capacities and adapter payload only; excludes allocator/Godot mesh/GPU overhead";
    RlFlightStats s{};if(core&&rl_flights_stats(core,&s)==0){
        d["live"]=static_cast<int64_t>(s.live);d["admitted"]=static_cast<int64_t>(s.admitted);d["skipped"]=static_cast<int64_t>(s.skipped);
        d["expired"]=static_cast<int64_t>(s.expired);d["frames"]=static_cast<int64_t>(s.frames);d["vertices"]=static_cast<int64_t>(s.vertices);
        d["rust_geometry_allocations"]=static_cast<int64_t>(s.allocations);d["retained_geometry_capacity_bytes"]=static_cast<int64_t>(s.retained_geometry_bytes);
        d["rust_state_capacity_bytes"]=static_cast<int64_t>(s.state_capacity_bytes);
    }return d;
}
int64_t RabbitLandsSpellFlightRuntime::reset_epoch(int64_t epoch){if(!on_owner_thread())return 1;if(!core){last_status=1;return 1;}last_status=rl_flights_reset(core,epoch);return last_status;}
int64_t RabbitLandsSpellFlightRuntime::cancel(int64_t id,int64_t generation,int64_t epoch){if(!on_owner_thread())return 1;if(!core){last_status=1;return 1;}last_status=rl_flights_cancel(core,id,generation,epoch);return last_status;}
PackedInt64Array RabbitLandsSpellFlightRuntime::spawn_batch(const PackedInt64Array &records,const PackedFloat64Array &values,int64_t epoch,int64_t limit){
    PackedInt64Array result;if(!on_owner_thread())return result;if(!core||records.size()%5||records.size()/5>512||values.size()!=records.size()/5*15||limit<1||limit>512){last_status=1;return result;}
    size_t count=static_cast<size_t>(records.size()/5);specs.resize(count);decisions.resize(count);
    for(size_t i=0;i<count;++i){auto &s=specs[i];s.id=records[i*5];s.generation=records[i*5+1];s.effect=records[i*5+2];s.power=records[i*5+3];s.priority=records[i*5+4];
        const double *v=values.ptr()+i*15;std::copy_n(v,3,s.start);std::copy_n(v+3,3,s.destination);std::copy_n(v+6,3,s.impact);std::copy_n(v+9,4,s.tint);s.release=v[13];s.duration=v[14];}
    last_status=rl_flights_spawn(core,specs.data(),count,epoch,static_cast<size_t>(limit),decisions.data());
    if(last_status!=0)return result;result.resize(count);if(count)std::copy_n(decisions.data(),count,result.ptrw());return result;
}
bool RabbitLandsSpellFlightRuntime::pack_surface(const RlFlightVertex *input,size_t count,Arrays &cache,Array &out){
    if(count>840||count%6||(count&&!input))return false;
    // Validate while traversing native output, before any Godot mesh submission.
    for(size_t i=0;i<count;++i)if(!finite(input[i].position,3)||!finite(input[i].color,4)||!finite(input[i].uv,2))return false;
    const void *old_v=cache.vertices.ptr();const void *old_c=cache.colors.ptr();const void *old_u=cache.uvs.ptr();
    cache.vertices.resize(count);cache.colors.resize(count);cache.uvs.resize(count);
    Vector3 *vertices=cache.vertices.ptrw();Color *colors=cache.colors.ptrw();Vector2 *uvs=cache.uvs.ptrw();
    packed_reallocations+=(old_v!=vertices)+(old_c!=colors)+(old_u!=uvs);
    for(size_t i=0;i<count;++i){vertices[i]=vector(input[i].position);colors[i]=Color(input[i].color[0],input[i].color[1],input[i].color[2],input[i].color[3]);uvs[i]=Vector2(input[i].uv[0],input[i].uv[1]);}
    out.resize(3);out[0]=cache.vertices;out[1]=cache.colors;out[2]=cache.uvs;return true;
}
Dictionary RabbitLandsSpellFlightRuntime::step_batch(const PackedInt64Array &records,const PackedFloat64Array &values,int64_t epoch,double delta,const Vector3 &view,const Vector3 &right,const Vector3 &up){
    auto began=Clock::now();Dictionary result;
    if(!on_owner_thread())return result;
    if(!core||records.size()%4||records.size()/4>512||values.size()!=records.size()/4*9){last_status=1;return result;}
    size_t count=static_cast<size_t>(records.size()/4);anchors.resize(count);
    for(size_t i=0;i<count;++i){auto &a=anchors[i];a.id=records[i*4];a.generation=records[i*4+1];a.source_valid=records[i*4+2];a.target_valid=records[i*4+3];
        const double *v=values.ptr()+i*9;std::copy_n(v,3,a.start);std::copy_n(v+3,3,a.destination);std::copy_n(v+6,3,a.impact);}
    RlFlightCamera camera{{view.x,view.y,view.z},{right.x,right.y,right.z},{up.x,up.y,up.z}};
    RlFlightView frames{};auto core_began=Clock::now();last_status=rl_flights_step(core,anchors.data(),count,epoch,delta,&camera,&frames);
    int64_t core_us=micros(core_began);if(last_status!=0||frames.count>512||(frames.count&&!frames.frames)){last_status=last_status?last_status:1;return result;}
    auto convert_began=Clock::now();Array output;output.resize(frames.count);published.resize(frames.count);int64_t vertices=0;
    for(size_t i=0;i<frames.count;++i){const auto &f=frames.frames[i];
        if(f.id<0||f.generation<=0||f.epoch!=epoch||f.phase<0||f.phase>3||f.events<0||f.events>7
            ||!std::isfinite(f.elapsed)||!std::isfinite(f.impact_progress)||!std::isfinite(f.ring_scale)||!std::isfinite(f.alpha)
            ||!finite(f.start,3)||!finite(f.destination,3)||!finite(f.impact,3)||!finite(f.bounds_min,3)||!finite(f.bounds_max,3)) {last_status=1;return Dictionary();}
        for(int axis=0;axis<3;++axis)if(f.bounds_min[axis]>f.bounds_max[axis]){last_status=1;return Dictionary();}
        Array ribbon,glow;if(!pack_surface(f.ribbon,f.ribbon_count,published[i].ribbon,ribbon)||!pack_surface(f.glow,f.glow_count,published[i].glow,glow)){last_status=1;return Dictionary();}
        Dictionary d;d["id"]=f.id;d["generation"]=f.generation;d["epoch"]=f.epoch;d["phase"]=f.phase;d["events"]=f.events;
        d["elapsed"]=f.elapsed;d["progress"]=f.impact_progress;d["ring_scale"]=f.ring_scale;d["alpha"]=f.alpha;
        d["start"]=vector(f.start);d["destination"]=vector(f.destination);d["impact"]=vector(f.impact);
        d["bounds"]=AABB(vector(f.bounds_min),vector(f.bounds_max)-vector(f.bounds_min));d["ribbon"]=ribbon;d["glow"]=glow;output[i]=d;
        vertices+=static_cast<int64_t>(f.ribbon_count+f.glow_count);
    }
    result["abi"]=1;result["epoch"]=epoch;result["frames"]=output;result["core_us"]=core_us;
    result["conversion_us"]=micros(convert_began);result["adapter_us"]=micros(began);result["vertices"]=vertices;return result;
}
void RabbitLandsSpellFlightRuntime::_bind_methods(){
    ClassDB::bind_method(D_METHOD("runtime_info"),&RabbitLandsSpellFlightRuntime::runtime_info);
    ClassDB::bind_method(D_METHOD("get_last_status"),&RabbitLandsSpellFlightRuntime::get_last_status);
    ClassDB::bind_method(D_METHOD("reset_epoch","epoch"),&RabbitLandsSpellFlightRuntime::reset_epoch);
    ClassDB::bind_method(D_METHOD("cancel","id","generation","epoch"),&RabbitLandsSpellFlightRuntime::cancel);
    ClassDB::bind_method(D_METHOD("spawn_batch","records","values","epoch","limit"),&RabbitLandsSpellFlightRuntime::spawn_batch);
    ClassDB::bind_method(D_METHOD("step_batch","records","values","epoch","delta","view","right","up"),&RabbitLandsSpellFlightRuntime::step_batch);
}
