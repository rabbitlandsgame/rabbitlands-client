#include "client_runtime.h"
#include "client_residency.h"
#include <godot_cpp/core/class_db.hpp>
#include <cstring>

using namespace godot;

namespace {
RlResourceKey read_key(const PackedInt64Array &array, int64_t offset) {
    RlResourceKey key{};
    for (int i=0;i<4;++i) { const int64_t value=array[offset+i]; std::memcpy(&key.words[i],&value,8); }
    return key;
}
void write_key(int64_t *target,const RlResourceKey &key) {
    for (int i=0;i<4;++i) std::memcpy(target+i,&key.words[i],8);
}
bool read_budget(const PackedInt64Array &array,RlResidencyBudget &budget) {
    if (array.size()!=4) return false;
    for (int i=0;i<4;++i) if (array[i]<0) return false;
    budget={static_cast<uint64_t>(array[0]),static_cast<uint64_t>(array[1]),
        static_cast<uint64_t>(array[2]),static_cast<uint64_t>(array[3])};
    return true;
}
}

int64_t RabbitLandsClientRuntime::residency_catalog(const PackedInt64Array &records,const PackedInt64Array &dependencies) {
    if (!can_mutate()) return 1;
    if (records.size()%9 || records.size()/9>65536
        || dependencies.size()%4 || dependencies.size()/4>262144) { last_status=1; return last_status; }
    std::vector<RlResidencyDescriptor> descriptors(static_cast<size_t>(records.size()/9));
    std::vector<RlResourceKey> deps(static_cast<size_t>(dependencies.size()/4));
    for (size_t i=0;i<descriptors.size();++i) {
        const int64_t start=static_cast<int64_t>(i*9);
        for (int j=4;j<9;++j) if (records[start+j]<0) { last_status=1; return last_status; }
        descriptors[i]={read_key(records,start),static_cast<uint64_t>(records[start+4]),
            static_cast<uint64_t>(records[start+5]),static_cast<uint64_t>(records[start+6]),
            static_cast<uint64_t>(records[start+7]),static_cast<uint64_t>(records[start+8])};
    }
    for (size_t i=0;i<deps.size();++i) deps[i]=read_key(dependencies,static_cast<int64_t>(i*4));
    last_status=rl_client_runtime_residency_catalog(core,descriptors.data(),descriptors.size(),deps.data(),deps.size());
    return last_status;
}

int64_t RabbitLandsClientRuntime::residency_reconcile(const PackedInt64Array &records,int64_t epoch) {
    if (!can_mutate()) return 1;
    if (records.size()%6 || records.size()/6>65536) { last_status=1; return last_status; }
    std::vector<RlResidencyWanted> wanted(static_cast<size_t>(records.size()/6));
    for (size_t i=0;i<wanted.size();++i) {
        const int64_t start=static_cast<int64_t>(i*6);
        wanted[i]={read_key(records,start),records[start+4],records[start+5]};
    }
    last_status=rl_client_runtime_residency_reconcile(core,wanted.data(),wanted.size(),epoch);
    return last_status;
}

int64_t RabbitLandsClientRuntime::residency_events(const PackedInt64Array &records) {
    if (!can_mutate()) return 1;
    if (records.size()%7 || records.size()/7>65536) { last_status=1; return last_status; }
    std::vector<RlResidencyEvent> events(static_cast<size_t>(records.size()/7));
    for (size_t i=0;i<events.size();++i) {
        const int64_t start=static_cast<int64_t>(i*7);
        if (records[start+4]<=0) { last_status=1; return last_status; }
        events[i]={read_key(records,start),static_cast<uint64_t>(records[start+4]),records[start+5],records[start+6]};
    }
    last_status=rl_client_runtime_residency_events(core,events.data(),events.size());
    return last_status;
}

int64_t RabbitLandsClientRuntime::residency_retry(const PackedInt64Array &keys,int64_t epoch) {
    if (!can_mutate()) return 1;
    if (keys.size()%4 || keys.size()/4>65536) { last_status=1; return last_status; }
    std::vector<RlResourceKey> rows(static_cast<size_t>(keys.size()/4));
    for (size_t i=0;i<rows.size();++i) rows[i]=read_key(keys,static_cast<int64_t>(i*4));
    last_status=rl_client_runtime_residency_retry(core,rows.data(),rows.size(),epoch);
    return last_status;
}

PackedInt64Array RabbitLandsClientRuntime::residency_step(int64_t epoch,const PackedInt64Array &limits,int64_t capacity) {
    PackedInt64Array result;
    if (!can_mutate()) return result;
    RlResidencyBudget budget{};
    if (capacity<0 || capacity>4096 || !read_budget(limits,budget)) { last_status=1; return result; }
    std::vector<RlResidencyAction> actions(static_cast<size_t>(capacity));
    size_t written=0;
    last_status=rl_client_runtime_residency_step(core,epoch,budget,actions.data(),actions.size(),&written);
    if (last_status || written>actions.size()) { if (!last_status) last_status=3; return result; }
    result.resize(static_cast<int64_t>(written*8));
    int64_t *output=result.ptrw();
    for (size_t i=0;i<written;++i) {
        const auto &action=actions[i];
        write_key(output+i*8,action.key);
        output[i*8+4]=static_cast<int64_t>(action.generation); output[i*8+5]=action.epoch;
        output[i*8+6]=action.kind; output[i*8+7]=action.pinned;
    }
    return result;
}

Dictionary RabbitLandsClientRuntime::residency_snapshot(const PackedInt64Array &limits) {
    Dictionary result;
    if (!can_mutate()) return result;
    RlResidencyBudget budget{};
    if (!read_budget(limits,budget)) { last_status=1; return result; }
    RlResidencySnapshot snapshot{};
    last_status=rl_client_runtime_residency_snapshot(core,budget,&snapshot);
    if (last_status) return result;
    result["schema"]=1; result["epoch"]=snapshot.epoch;
#define RL_FIELD(name) result[#name]=static_cast<int64_t>(snapshot.name)
    RL_FIELD(queued); RL_FIELD(loading); RL_FIELD(ready); RL_FIELD(active);
    RL_FIELD(retiring); RL_FIELD(cancel_pending); RL_FIELD(cpu_bytes); RL_FIELD(gpu_bytes);
    RL_FIELD(unknown_resources); RL_FIELD(cpu_over_budget); RL_FIELD(gpu_over_budget);
    RL_FIELD(stale_events); RL_FIELD(failed);
#undef RL_FIELD
    result["estimate_kind"]="unique-declared-resource-estimates-not-driver-allocation";
    result["execution_owner"]="godot-main-thread";
    return result;
}

void RabbitLandsClientRuntime::bind_residency_methods() {
    ClassDB::bind_method(D_METHOD("admission_begin","epoch","snapshot"),&RabbitLandsClientRuntime::admission_begin);
    ClassDB::bind_method(D_METHOD("admission_event","lease","epoch","event"),&RabbitLandsClientRuntime::admission_event);
    ClassDB::bind_method(D_METHOD("admission_snapshot"),&RabbitLandsClientRuntime::admission_snapshot);
    ClassDB::bind_method(D_METHOD("admission_dependencies","lease","epoch","records","edges"),&RabbitLandsClientRuntime::admission_dependencies);
    ClassDB::bind_method(D_METHOD("admission_release_dependencies","keys"),&RabbitLandsClientRuntime::admission_release_dependencies);
    ClassDB::bind_method(D_METHOD("admission_graph_snapshot"),&RabbitLandsClientRuntime::admission_graph_snapshot);
    ClassDB::bind_method(D_METHOD("residency_catalog","records","dependencies"),&RabbitLandsClientRuntime::residency_catalog);
    ClassDB::bind_method(D_METHOD("residency_reconcile","records","epoch"),&RabbitLandsClientRuntime::residency_reconcile);
    ClassDB::bind_method(D_METHOD("residency_events","records"),&RabbitLandsClientRuntime::residency_events);
    ClassDB::bind_method(D_METHOD("residency_retry","keys","epoch"),&RabbitLandsClientRuntime::residency_retry);
    ClassDB::bind_method(D_METHOD("residency_step","epoch","limits","capacity"),&RabbitLandsClientRuntime::residency_step);
    ClassDB::bind_method(D_METHOD("residency_snapshot","limits"),&RabbitLandsClientRuntime::residency_snapshot);
}

PackedInt64Array RabbitLandsClientRuntime::admission_begin(int64_t epoch,const PackedInt64Array &values) {
    PackedInt64Array result;
    if(!can_mutate()) return result;
    if(values.size()!=10) {last_status=1;return result;}
    for(int i=0;i<10;++i) if(values[i]<0) {last_status=1;return result;}
    RlAdmissionInput input{static_cast<uint64_t>(values[0]),static_cast<uint64_t>(values[1]),
        static_cast<uint64_t>(values[2]),static_cast<uint64_t>(values[3]),static_cast<uint64_t>(values[4]),
        static_cast<uint64_t>(values[5]),static_cast<uint64_t>(values[6]),static_cast<uint64_t>(values[7]),
        static_cast<uint64_t>(values[8]),static_cast<uint64_t>(values[9])};
    RlAdmissionDecision decision{};
    last_status=rl_client_runtime_admission_begin(core,epoch,input,&decision);
    if(last_status || decision.lease>static_cast<uint64_t>(INT64_MAX)) return result;
    result.resize(2);result.set(0,static_cast<int64_t>(decision.lease));result.set(1,static_cast<int64_t>(decision.reason));
    return result;
}
int64_t RabbitLandsClientRuntime::admission_event(int64_t lease,int64_t epoch,int64_t event) {
    if(!can_mutate()) return 1;
    if(lease<=0 || epoch<=0) {last_status=1;return last_status;}
    last_status=rl_client_runtime_admission_event(core,static_cast<uint64_t>(lease),epoch,event);return last_status;
}
Dictionary RabbitLandsClientRuntime::admission_snapshot() {
    Dictionary result;
    if(!can_mutate()) return result;
    RlAdmissionSnapshot snapshot{};
    last_status=rl_client_runtime_admission_snapshot(core,&snapshot);
    if(last_status) return result;
#define RL_ADMISSION_FIELD(name) result[#name]=static_cast<int64_t>(snapshot.name)
    RL_ADMISSION_FIELD(reserved);RL_ADMISSION_FIELD(loading);RL_ADMISSION_FIELD(ready);
    RL_ADMISSION_FIELD(active);RL_ADMISSION_FIELD(retiring);RL_ADMISSION_FIELD(cancelled);
    RL_ADMISSION_FIELD(old_epoch);RL_ADMISSION_FIELD(denials);RL_ADMISSION_FIELD(forced_sync);
#undef RL_ADMISSION_FIELD
    return result;
}

int64_t RabbitLandsClientRuntime::admission_dependencies(int64_t lease,int64_t epoch,
        const PackedInt64Array &records,const PackedInt64Array &edges) {
    if(!can_mutate()) return 1;
    if(lease<=0 || epoch<=0 || records.size()%9 || records.size()/9>65536
        || edges.size()%4 || edges.size()/4>262144) {last_status=1;return last_status;}
    std::vector<RlResidencyDescriptor> values(static_cast<size_t>(records.size()/9));
    std::vector<RlResourceKey> dependencies(static_cast<size_t>(edges.size()/4));
    for(size_t i=0;i<values.size();++i) {
        const int64_t offset=static_cast<int64_t>(i*9);
        for(int j=4;j<9;++j) if(records[offset+j]<0) {last_status=1;return last_status;}
        values[i]={read_key(records,offset),static_cast<uint64_t>(records[offset+4]),
            static_cast<uint64_t>(records[offset+5]),static_cast<uint64_t>(records[offset+6]),
            static_cast<uint64_t>(records[offset+7]),static_cast<uint64_t>(records[offset+8])};
    }
    for(size_t i=0;i<dependencies.size();++i) dependencies[i]=read_key(edges,static_cast<int64_t>(i*4));
    last_status=rl_client_runtime_admission_dependencies(core,static_cast<uint64_t>(lease),epoch,
        values.data(),values.size(),dependencies.data(),dependencies.size());
    return last_status;
}
PackedInt64Array RabbitLandsClientRuntime::admission_release_dependencies(const PackedInt64Array &keys) {
    PackedInt64Array result;
    if(!can_mutate()) return result;
    if(keys.size()%4 || keys.size()/4>65536) {last_status=1;return result;}
    std::vector<RlResourceKey> values(static_cast<size_t>(keys.size()/4)),removed(values.size());
    for(size_t i=0;i<values.size();++i) values[i]=read_key(keys,static_cast<int64_t>(i*4));
    size_t written=0;
    last_status=rl_client_runtime_admission_release_dependencies(core,values.data(),values.size(),removed.data(),removed.size(),&written);
    if(last_status || written>removed.size()) {if(!last_status) last_status=3;return result;}
    result.resize(static_cast<int64_t>(written*4));
    int64_t *output=result.ptrw();
    for(size_t i=0;i<written;++i) write_key(output+i*4,removed[i]);
    return result;
}
Dictionary RabbitLandsClientRuntime::admission_graph_snapshot() {
    Dictionary result;
    if(!can_mutate()) return result;
    RlAdmissionGraphSnapshot snapshot{};
    last_status=rl_client_runtime_admission_graph_snapshot(core,&snapshot);
    if(last_status) return result;
    result["schema"]=1;
#define RL_GRAPH_FIELD(name) result[#name]=static_cast<int64_t>(snapshot.name)
    RL_GRAPH_FIELD(resources);RL_GRAPH_FIELD(edges);RL_GRAPH_FIELD(lease_links);RL_GRAPH_FIELD(loading);
    RL_GRAPH_FIELD(ready);RL_GRAPH_FIELD(active);RL_GRAPH_FIELD(retiring);RL_GRAPH_FIELD(registrations);RL_GRAPH_FIELD(physical_releases);
#undef RL_GRAPH_FIELD
    result["allocation_kind"]="unknown_cpu_gpu_allocation";
    return result;
}
