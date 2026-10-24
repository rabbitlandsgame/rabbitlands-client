#pragma once
#include <cstddef>
#include <cstdint>
#include <vector>
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/packed_int64_array.hpp>
#include <godot_cpp/variant/packed_float64_array.hpp>
#include <godot_cpp/variant/packed_vector3_array.hpp>
#include <godot_cpp/variant/packed_vector2_array.hpp>
#include <godot_cpp/variant/packed_color_array.hpp>

extern "C" {
struct RlFlights;
struct RlFlightSpec {
    int64_t id,generation,effect,power,priority;
    double start[3],destination[3],impact[3],tint[4],release,duration;
};
struct RlFlightAnchor {int64_t id,generation,source_valid,target_valid;double start[3],destination[3],impact[3];};
struct RlFlightCamera {double view[3],right[3],up[3];};
struct RlFlightVertex {double position[3],color[4],uv[2];};
struct RlFlightFrame {
    int64_t id,generation,epoch,phase,events;
    double elapsed,impact_progress,ring_scale,alpha;
    double start[3],destination[3],impact[3],bounds_min[3],bounds_max[3];
    const RlFlightVertex *ribbon;size_t ribbon_count;const RlFlightVertex *glow;size_t glow_count;
};
struct RlFlightView {const RlFlightFrame *frames;size_t count;};
struct RlFlightStats {uint64_t live,admitted,skipped,expired,frames,vertices,allocations,retained_geometry_bytes,state_capacity_bytes;};
uint32_t rl_flights_abi();
RlFlights *rl_flights_create();
void rl_flights_destroy(RlFlights *);
int32_t rl_flights_reset(RlFlights *,int64_t);
int32_t rl_flights_spawn(RlFlights *,const RlFlightSpec *,size_t,int64_t,size_t,int64_t *);
int32_t rl_flights_step(RlFlights *,const RlFlightAnchor *,size_t,int64_t,double,const RlFlightCamera *,RlFlightView *);
int32_t rl_flights_cancel(RlFlights *,int64_t,int64_t,int64_t);
int32_t rl_flights_stats(const RlFlights *,RlFlightStats *);
}

namespace godot {
bool client_runtime_owns_cpp_flight();
void client_runtime_mark_cpp_flight_owned();
class RabbitLandsSpellFlightRuntime : public RefCounted {
    GDCLASS(RabbitLandsSpellFlightRuntime,RefCounted);
    struct Arrays {PackedVector3Array vertices;PackedColorArray colors;PackedVector2Array uvs;};
    struct Published {Arrays ribbon,glow;};
    RlFlights *core=nullptr;
    int64_t owner_thread=0,last_status=0;
    uint64_t packed_reallocations=0;
    std::vector<RlFlightSpec> specs;
    std::vector<RlFlightAnchor> anchors;
    std::vector<int64_t> decisions;
    std::vector<Published> published;
    bool on_owner_thread() const;
    bool pack_surface(const RlFlightVertex *,size_t,Arrays &,Array &);
protected:
    static void _bind_methods();
public:
    RabbitLandsSpellFlightRuntime();
    ~RabbitLandsSpellFlightRuntime();
    Dictionary runtime_info() const;
    int64_t get_last_status() const;
    int64_t reset_epoch(int64_t);
    int64_t cancel(int64_t,int64_t,int64_t);
    PackedInt64Array spawn_batch(const PackedInt64Array &,const PackedFloat64Array &,int64_t,int64_t);
    Dictionary step_batch(const PackedInt64Array &,const PackedFloat64Array &,int64_t,double,const Vector3 &,const Vector3 &,const Vector3 &);
};
}
