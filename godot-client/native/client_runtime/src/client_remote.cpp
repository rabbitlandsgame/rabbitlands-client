#include "client_remote.h"
#include <godot_cpp/classes/os.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/variant/packed_int64_array.hpp>
#include <chrono>
#include <cstddef>
extern "C" {
RlRemote *rl_remote_create(int64_t);
void rl_remote_destroy(RlRemote *);
int32_t rl_remote_reset(RlRemote *,int64_t);
int32_t rl_remote_map(RlRemote *,int64_t,int64_t);
int32_t rl_remote_event(RlRemote *,int64_t,int64_t,int64_t,int64_t,int64_t,int64_t,const double *,size_t);
int32_t rl_remote_tick(RlRemote *,int64_t,int64_t,int64_t,double);
int64_t rl_remote_gate(RlRemote *,int64_t,int64_t,int64_t,int64_t,bool,double);
int32_t rl_remote_outputs(const RlRemote *,const int64_t **,size_t *,const double **,size_t *);
int32_t rl_remote_classify(const double *,size_t,const double *,size_t,const double *,int64_t *);
int32_t rl_remote_stats(const RlRemote *,int64_t *,size_t);
}
using namespace godot;
namespace {
using Clock=std::chrono::steady_clock;
uint64_t elapsed(Clock::time_point start){return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(Clock::now()-start).count());}
struct Timer{uint64_t &value;Clock::time_point start=Clock::now();explicit Timer(uint64_t &v):value(v){}~Timer(){value+=elapsed(start);}};
}
RabbitLandsRemotePresentationRuntime::RabbitLandsRemotePresentationRuntime(){owner_thread=OS::get_singleton()->get_thread_caller_id();core=rl_remote_create(epoch);}
RabbitLandsRemotePresentationRuntime::~RabbitLandsRemotePresentationRuntime(){rl_remote_destroy(core);}
bool RabbitLandsRemotePresentationRuntime::owner()const{return OS::get_singleton()->get_thread_caller_id()==owner_thread;}
Dictionary RabbitLandsRemotePresentationRuntime::result(int64_t status){
    Dictionary result;result["status"]=status;
    PackedInt64Array meta;PackedFloat64Array values;
    if(status==0){
        Timer timer(conversion_us);const int64_t *m=nullptr;const double *v=nullptr;size_t nm=0,nv=0;
        if(rl_remote_outputs(core,&m,&nm,&v,&nv)!=0||nm>65536*8||nv>65536*100){result["status"]=1;}
        else {meta.resize(static_cast<int64_t>(nm));values.resize(static_cast<int64_t>(nv));
            for(size_t i=0;i<nm;++i)meta.ptrw()[i]=m[i];for(size_t i=0;i<nv;++i)values.ptrw()[i]=v[i];}
    }
    result["meta"]=meta;result["values"]=values;return result;
}
Dictionary RabbitLandsRemotePresentationRuntime::runtime_info()const{
    Dictionary d;if(!owner()){d["ready"]=false;return d;}d["ready"]=core!=nullptr&&sizeof(real_t)==4;d["remote_api"]=1;d["state_width"]=47;
    d["engine_scalar_bytes"]=static_cast<int64_t>(sizeof(real_t));d["clock_precision"]="f64";
    d["epoch"]=epoch;d["event_calls"]=static_cast<int64_t>(event_calls);d["physics_calls"]=static_cast<int64_t>(tick_calls);
    d["gate_calls"]=static_cast<int64_t>(gate_calls);d["physics_records"]=static_cast<int64_t>(records);
    d["event_total_us"]=static_cast<int64_t>(event_us);d["physics_total_us"]=static_cast<int64_t>(tick_us);
    d["gate_total_us"]=static_cast<int64_t>(gate_us);d["output_conversion_us_nested"]=static_cast<int64_t>(conversion_us);
    d["classify_calls"]=static_cast<int64_t>(classify_calls);d["classify_records"]=static_cast<int64_t>(classify_records);d["classify_total_us"]=static_cast<int64_t>(classify_us);
    int64_t stats[12]={};if(core&&rl_remote_stats(core,stats,12)==0){
        d["map_frame"]=stats[1];d["event_sequence"]=stats[2];d["active_bindings"]=stats[3];
        d["storage_rows"]=stats[4];d["row_capacity"]=stats[5];d["pace_values"]=stats[6];
        d["pace_capacity"]=stats[7];d["ordinary_gate_members"]=stats[8];d["ordinary_gate_tick"]=stats[9];
        d["state_memory_lower_bound_bytes"]=stats[10];d["awake_bindings"]=stats[11];
        d["memory_scope"]="Rust row/history/output capacity; excludes hash maps, Godot bindings, allocator and GPU";
    }
    d["timing_scope"]="adapter inclusive; conversion nested; excludes GDScript packing/application";return d;
}
int64_t RabbitLandsRemotePresentationRuntime::reset_epoch(int64_t value){if(!owner()||!core)return 1;auto status=rl_remote_reset(core,value);if(status==0)epoch=value;return status;}
int64_t RabbitLandsRemotePresentationRuntime::set_map_frame(int64_t value){if(!owner()||!core)return 1;return rl_remote_map(core,epoch,value);}
Dictionary RabbitLandsRemotePresentationRuntime::event(int64_t op,int64_t id,int64_t generation,int64_t e,int64_t seq,int64_t map,const PackedFloat64Array &values){
    if(!owner()||!core){Dictionary d;d["status"]=1;return d;}Timer timer(event_us);++event_calls;
    return result(rl_remote_event(core,op,id,generation,e,seq,map,values.ptr(),static_cast<size_t>(values.size())));
}
Dictionary RabbitLandsRemotePresentationRuntime::physics_tick(int64_t e,int64_t map,int64_t frame,double delta){
    if(!owner()||!core){Dictionary d;d["status"]=1;return d;}Timer timer(tick_us);++tick_calls;
    auto d=result(rl_remote_tick(core,e,map,frame,delta));if(static_cast<int64_t>(d["status"])==0){PackedInt64Array m=d["meta"];records+=static_cast<uint64_t>(m.size()/7);}return d;
}
int64_t RabbitLandsRemotePresentationRuntime::gate_apply(int64_t id,int64_t generation,int64_t tier,bool stagger){if(!owner()||!core)return -11;Timer timer(gate_us);++gate_calls;return rl_remote_gate(core,1,id,generation,tier,stagger,0.);}
int64_t RabbitLandsRemotePresentationRuntime::gate_discard(int64_t id,int64_t generation){if(!owner()||!core)return -11;Timer timer(gate_us);++gate_calls;return rl_remote_gate(core,2,id,generation,0,false,0.);}
int64_t RabbitLandsRemotePresentationRuntime::gate_reset(){if(!owner()||!core)return -11;return rl_remote_gate(core,4,0,0,0,false,0.);}
Dictionary RabbitLandsRemotePresentationRuntime::gate_advance(double delta){
    if(!owner()||!core){Dictionary d;d["status"]=1;return d;}Timer timer(gate_us);++gate_calls;
    auto status=rl_remote_gate(core,3,0,0,0,false,delta);return result(status<0?-status-10:0);
}
Dictionary RabbitLandsRemotePresentationRuntime::classify_batch(const PackedFloat64Array &records,const PackedFloat64Array &planes,const PackedFloat64Array &camera){
    Dictionary d;d["status"]=1;PackedInt64Array tiers;
    if(!owner()||!core||records.size()%4||records.size()/4>65536||planes.size()%4||planes.size()>24||camera.size()!=3)return d;
    Timer timer(classify_us);++classify_calls;tiers.resize(records.size()/4);
    auto status=rl_remote_classify(records.ptr(),static_cast<size_t>(records.size()/4),planes.ptr(),static_cast<size_t>(planes.size()/4),camera.ptr(),tiers.ptrw());
    if(status==0)classify_records+=static_cast<uint64_t>(tiers.size());else tiers.clear();d["status"]=status;d["tiers"]=tiers;return d;
}
void RabbitLandsRemotePresentationRuntime::_bind_methods(){
    ClassDB::bind_method(D_METHOD("runtime_info"),&RabbitLandsRemotePresentationRuntime::runtime_info);
    ClassDB::bind_method(D_METHOD("reset_epoch","epoch"),&RabbitLandsRemotePresentationRuntime::reset_epoch);
    ClassDB::bind_method(D_METHOD("set_map_frame","frame"),&RabbitLandsRemotePresentationRuntime::set_map_frame);
    ClassDB::bind_method(D_METHOD("event","operation","id","generation","epoch","sequence","map","values"),&RabbitLandsRemotePresentationRuntime::event);
    ClassDB::bind_method(D_METHOD("physics_tick","epoch","map","frame","delta"),&RabbitLandsRemotePresentationRuntime::physics_tick);
    ClassDB::bind_method(D_METHOD("gate_apply","id","generation","tier","stagger"),&RabbitLandsRemotePresentationRuntime::gate_apply);
    ClassDB::bind_method(D_METHOD("gate_discard","id","generation"),&RabbitLandsRemotePresentationRuntime::gate_discard);
    ClassDB::bind_method(D_METHOD("gate_reset"),&RabbitLandsRemotePresentationRuntime::gate_reset);
    ClassDB::bind_method(D_METHOD("gate_advance","delta"),&RabbitLandsRemotePresentationRuntime::gate_advance);
    ClassDB::bind_method(D_METHOD("classify_batch","records","planes","camera"),&RabbitLandsRemotePresentationRuntime::classify_batch);
}
