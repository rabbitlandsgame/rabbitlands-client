#pragma once

#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/packed_byte_array.hpp>
#include <godot_cpp/variant/packed_int32_array.hpp>
#include <godot_cpp/variant/string_name.hpp>

#include <cstdint>
#include <cstddef>
#include <array>
#include <vector>

namespace godot {

struct NativeCrowdActorKeys {
    StringName status{"status"};
    StringName changed_ids{"changed_ids"};
    StringName x{"x"};
    StringName y{"y"};
    StringName command{"command"};
    StringName command_sequence{"command_sequence"};
    StringName facing_command{"facing_command"};
    StringName health{"health"};
    StringName sitting{"sitting"};
    StringName in_combat{"in_combat"};
    StringName alive{"alive"};
    // The written fields' names as Strings: a field a record lacks is inserted
    // under its String name, as ActorReducer (GDScript) inserts it.
    String x_text{"x"};
    String y_text{"y"};
    String command_text{"command"};
    String command_sequence_text{"command_sequence"};
    String facing_command_text{"facing_command"};
    String health_text{"health"};
    String sitting_text{"sitting"};
    String in_combat_text{"in_combat"};
    String alive_text{"alive"};
    // reduce_run results and its step-stamp argument.
    StringName consumed{"consumed"};
    StringName reason{"reason"};
    StringName facets{"facets"};
    StringName commands{"commands"};
    StringName applied{"applied"};
    StringName stamped{"stamped"};
    StringName unstamped{"unstamped"};
    StringName stamp_mode{"mode"};
    StringName step_key{"step_key"};
    StringName playout_key{"playout_key"};
    StringName pass_key{"pass_key"};
    StringName local_msec{"local_msec"};
    StringName playout_seconds{"playout_seconds"};
    StringName pass_id{"pass_id"};
};

class NativeCrowdReducer : public RefCounted {
    GDCLASS(NativeCrowdReducer, RefCounted)

    NativeCrowdActorKeys keys;

protected:
    static void _bind_methods();

public:
    Dictionary reduce_packet(Dictionary actors, const PackedByteArray &payload,
            int64_t local_actor_id) const;
    // A run of consecutive command-2 payloads, reduced in arrival order as
    // AppState's GDScript loop reduces them one packet after another, with
    // each touched actor published once (rust-batch R2). See the .cpp.
    Dictionary reduce_run(Dictionary actors, const Array &payloads,
            int64_t local_actor_id, const Dictionary &stamp) const;
};

class NativeCrowdStore : public RefCounted {
    GDCLASS(NativeCrowdStore, RefCounted)

public:
    // Public only so the shared, file-local command semantics helper can apply
    // the exact same transition to the dictionary and compact prototypes.
    struct ActorState {
        int64_t actor_id = -1;
        int64_t x = 0;
        int64_t y = 0;
        int64_t command = -1;
        int64_t command_sequence = 0;
        int64_t facing_command = -1;
        int64_t health = 0;
        bool sitting = false;
        bool in_combat = false;
        bool alive = false;
        bool has_facing_command = false;
        bool has_health = false;
        bool has_sitting = false;
        bool has_in_combat = false;
        bool has_alive = false;
        bool dirty = false;
    };

private:
    static constexpr std::size_t WIRE_ACTOR_CAPACITY = 1 << 16;
    std::vector<ActorState> actor_states;
    std::array<int32_t, WIRE_ACTOR_CAPACITY> id_to_slot{};
    std::vector<int64_t> dirty_order;
    NativeCrowdActorKeys keys;

    void mark_dirty(int64_t actor_id, ActorState &actor);
    ActorState *find_actor(int64_t actor_id);
    const ActorState *find_actor(int64_t actor_id) const;

protected:
    static void _bind_methods();

public:
    NativeCrowdStore();
    void reset(const Dictionary &actors);
    Dictionary reduce_packets(const Array &payloads, int64_t local_actor_id);
    PackedInt32Array snapshot_dirty(Dictionary actors);
    void remove(const PackedInt32Array &actor_ids);
    void clear();
    bool has(int64_t actor_id) const;
    int64_t size() const;
};

} // namespace godot
