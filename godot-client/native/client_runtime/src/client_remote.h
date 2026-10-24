#pragma once
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/packed_float64_array.hpp>
#include <cstdint>
struct RlRemote;
namespace godot {
class RabbitLandsRemotePresentationRuntime : public RefCounted {
    GDCLASS(RabbitLandsRemotePresentationRuntime, RefCounted);
    RlRemote *core=nullptr;
    int64_t owner_thread=0, epoch=1;
    uint64_t event_calls=0, tick_calls=0, gate_calls=0, records=0;
    uint64_t event_us=0, tick_us=0, conversion_us=0, gate_us=0;
    uint64_t classify_calls=0, classify_records=0, classify_us=0;
    bool owner() const;
    Dictionary result(int64_t status);
protected: static void _bind_methods();
public:
    RabbitLandsRemotePresentationRuntime();
    ~RabbitLandsRemotePresentationRuntime();
    Dictionary runtime_info() const;
    int64_t reset_epoch(int64_t value);
    int64_t set_map_frame(int64_t value);
    Dictionary event(int64_t operation,int64_t id,int64_t generation,int64_t requested_epoch,
        int64_t sequence,int64_t map,const PackedFloat64Array &values);
    Dictionary physics_tick(int64_t requested_epoch,int64_t map,int64_t frame,double delta);
    int64_t gate_apply(int64_t id,int64_t generation,int64_t tier,bool stagger);
    int64_t gate_discard(int64_t id,int64_t generation);
    int64_t gate_reset();
    Dictionary gate_advance(double delta);
    Dictionary classify_batch(const PackedFloat64Array &records,const PackedFloat64Array &planes,const PackedFloat64Array &camera);
};
}
