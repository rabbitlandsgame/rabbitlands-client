#include "native_crowd_reducer.h"

#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/variant/string.hpp>
#include <godot_cpp/variant/string_name.hpp>
#include <godot_cpp/variant/variant.hpp>

#include <cstring>
#include <unordered_map>

namespace godot {
namespace {

constexpr int COMMAND_DEATH = 3;
constexpr int COMMAND_SIT = 13;
constexpr int COMMAND_STAND = 14;
constexpr int COMMAND_ENTER_COMBAT = 18;
constexpr int COMMAND_LEAVE_COMBAT = 19;

int64_t integer_field(const Dictionary &record, const StringName &key,
        int64_t fallback) {
    return static_cast<int64_t>(record.get(key, fallback));
}

bool bool_field(const Dictionary &record, const StringName &key,
        bool fallback) {
    return static_cast<bool>(record.get(key, fallback));
}

int64_t wrapping_add(int64_t value, int64_t increment) {
    const uint64_t wrapped = static_cast<uint64_t>(value) +
            static_cast<uint64_t>(increment);
    int64_t result = 0;
    static_assert(sizeof(result) == sizeof(wrapped));
    std::memcpy(&result, &wrapped, sizeof(result));
    return result;
}

void command_direction(int command, int64_t &step_x, int64_t &step_y,
        bool &has_direction) {
    int direction = command;
    if (command >= 30 && command <= 37) {
        direction = command - 10;
    } else if (command >= 38 && command <= 45) {
        direction = command - 18;
    }

    has_direction = direction >= 20 && direction <= 27;
    step_x = 0;
    step_y = 0;
    if (!has_direction || command >= 38) {
        return;
    }
    static constexpr int8_t STEPS[8][2] = {
        {0, 1}, {1, 1}, {1, 0}, {1, -1},
        {0, -1}, {-1, -1}, {-1, 0}, {-1, 1},
    };
    step_x = STEPS[direction - 20][0];
    step_y = STEPS[direction - 20][1];
}

void apply_dictionary_command(Dictionary &record, int command,
        const NativeCrowdActorKeys &keys) {
    int64_t step_x = 0;
    int64_t step_y = 0;
    bool has_direction = false;
    command_direction(command, step_x, step_y, has_direction);
    record[keys.x] = wrapping_add(integer_field(record, keys.x, 0), step_x);
    record[keys.y] = wrapping_add(integer_field(record, keys.y, 0), step_y);
    record[keys.command] = command;
    record[keys.command_sequence] = wrapping_add(
            integer_field(record, keys.command_sequence, 0), 1);
    if (has_direction) {
        record[keys.facing_command] = command;
    }
    if (command == COMMAND_SIT) {
        record[keys.sitting] = true;
    } else if (command == COMMAND_STAND) {
        record[keys.sitting] = false;
    } else if (command == COMMAND_ENTER_COMBAT) {
        record[keys.in_combat] = true;
    } else if (command == COMMAND_LEAVE_COMBAT) {
        record[keys.in_combat] = false;
    } else if (command == COMMAND_DEATH) {
        record[keys.alive] = false;
        record[keys.health] = 0;
    }
}

void apply_store_command(NativeCrowdStore::ActorState &actor, int command) {
    int64_t step_x = 0;
    int64_t step_y = 0;
    bool has_direction = false;
    command_direction(command, step_x, step_y, has_direction);
    actor.x = wrapping_add(actor.x, step_x);
    actor.y = wrapping_add(actor.y, step_y);
    actor.command = command;
    actor.command_sequence = wrapping_add(actor.command_sequence, 1);
    if (has_direction) {
        actor.facing_command = command;
        actor.has_facing_command = true;
    }
    if (command == COMMAND_SIT) {
        actor.sitting = true;
        actor.has_sitting = true;
    } else if (command == COMMAND_STAND) {
        actor.sitting = false;
        actor.has_sitting = true;
    } else if (command == COMMAND_ENTER_COMBAT) {
        actor.in_combat = true;
        actor.has_in_combat = true;
    } else if (command == COMMAND_LEAVE_COMBAT) {
        actor.in_combat = false;
        actor.has_in_combat = true;
    } else if (command == COMMAND_DEATH) {
        actor.alive = false;
        actor.health = 0;
        actor.has_alive = true;
        actor.has_health = true;
    }
}

Dictionary result_with_status(const char *status,
        const NativeCrowdActorKeys &keys) {
    Dictionary result;
    result[keys.status] = String(status);
    result[keys.changed_ids] = PackedInt32Array();
    return result;
}

bool packet_records_are_dictionaries(const PackedByteArray &payload,
        const Dictionary &actors) {
    for (int64_t offset = 0; offset < payload.size(); offset += 3) {
        const int64_t actor_id = static_cast<int64_t>(payload[offset]) |
                (static_cast<int64_t>(payload[offset + 1]) << 8);
        if (actors.has(actor_id) &&
                actors[actor_id].get_type() != Variant::DICTIONARY) {
            return false;
        }
    }
    return true;
}

bool packet_has_local_leave(const PackedByteArray &payload,
        int64_t local_actor_id, const Dictionary &actors) {
    if (local_actor_id < 0 || !actors.has(local_actor_id)) {
        return false;
    }
    for (int64_t offset = 0; offset < payload.size(); offset += 3) {
        const int64_t actor_id = static_cast<int64_t>(payload[offset]) |
                (static_cast<int64_t>(payload[offset + 1]) << 8);
        if (actor_id == local_actor_id &&
                payload[offset + 2] == COMMAND_LEAVE_COMBAT) {
            return true;
        }
    }
    return false;
}

} // namespace

void NativeCrowdReducer::_bind_methods() {
    ClassDB::bind_method(D_METHOD("reduce_packet", "actors", "payload",
                                 "local_actor_id"),
            &NativeCrowdReducer::reduce_packet);
}

Dictionary NativeCrowdReducer::reduce_packet(Dictionary actors,
        const PackedByteArray &payload, int64_t local_actor_id) const {
    if (payload.size() % 3 != 0) {
        return result_with_status("invalid", keys);
    }
    // AppState's original typed assignment is the authority for corrupt
    // actor containers. Do not partly reduce the well-formed rows around one.
    if (!packet_records_are_dictionaries(payload, actors)) {
        return result_with_status("fallback", keys);
    }
    // AppState emits combat_state synchronously while reducing command 19.
    // Leave that uncommon packet on the original path so observers can inspect
    // the same intermediate state and see signals in the same order.
    if (packet_has_local_leave(payload, local_actor_id, actors)) {
        return result_with_status("fallback", keys);
    }

    std::unordered_map<int64_t, Dictionary> touched;
    std::vector<int64_t> changed_order;
    touched.reserve(static_cast<std::size_t>(payload.size() / 3));
    changed_order.reserve(static_cast<std::size_t>(payload.size() / 3));

    for (int64_t offset = 0; offset < payload.size(); offset += 3) {
        const int64_t actor_id = static_cast<int64_t>(payload[offset]) |
                (static_cast<int64_t>(payload[offset + 1]) << 8);
        if (!actors.has(actor_id)) {
            continue;
        }
        auto found = touched.find(actor_id);
        if (found == touched.end()) {
            const Variant value = actors[actor_id];
            if (value.get_type() != Variant::DICTIONARY) {
                continue;
            }
            Dictionary copy = static_cast<Dictionary>(value).duplicate(false);
            found = touched.emplace(actor_id, copy).first;
            changed_order.push_back(actor_id);
        }
        apply_dictionary_command(found->second,
                static_cast<int>(payload[offset + 2]), keys);
    }

    PackedInt32Array changed_ids;
    changed_ids.resize(static_cast<int64_t>(changed_order.size()));
    for (int64_t index = 0;
            index < static_cast<int64_t>(changed_order.size()); ++index) {
        const int64_t actor_id = changed_order[static_cast<std::size_t>(index)];
        actors[actor_id] = touched.find(actor_id)->second;
        changed_ids[index] = static_cast<int32_t>(actor_id);
    }

    Dictionary result = result_with_status("ok", keys);
    result[keys.changed_ids] = changed_ids;
    return result;
}

void NativeCrowdStore::_bind_methods() {
    ClassDB::bind_method(D_METHOD("reset", "actors"),
            &NativeCrowdStore::reset);
    ClassDB::bind_method(D_METHOD("reduce_packets", "payloads",
                                 "local_actor_id"),
            &NativeCrowdStore::reduce_packets);
    ClassDB::bind_method(D_METHOD("snapshot_dirty", "actors"),
            &NativeCrowdStore::snapshot_dirty);
    ClassDB::bind_method(D_METHOD("remove", "actor_ids"),
            &NativeCrowdStore::remove);
    ClassDB::bind_method(D_METHOD("clear"), &NativeCrowdStore::clear);
    ClassDB::bind_method(D_METHOD("has", "actor_id"),
            &NativeCrowdStore::has);
    ClassDB::bind_method(D_METHOD("size"), &NativeCrowdStore::size);
}

NativeCrowdStore::NativeCrowdStore() {
    id_to_slot.fill(-1);
}

void NativeCrowdStore::reset(const Dictionary &actors) {
    clear();
    const Array ids = actors.keys();
    actor_states.reserve(static_cast<std::size_t>(ids.size()));
    for (int64_t index = 0; index < ids.size(); ++index) {
        const int64_t actor_id = static_cast<int64_t>(ids[index]);
        if (actor_id < 0 || actor_id >= static_cast<int64_t>(WIRE_ACTOR_CAPACITY)) {
            continue;
        }
        const Variant value = actors[ids[index]];
        if (value.get_type() != Variant::DICTIONARY) {
            continue;
        }
        const Dictionary record = value;
        ActorState actor;
        actor.actor_id = actor_id;
        actor.x = integer_field(record, keys.x, 0);
        actor.y = integer_field(record, keys.y, 0);
        actor.command = integer_field(record, keys.command, -1);
        actor.command_sequence = integer_field(
                record, keys.command_sequence, 0);
        actor.has_facing_command = record.has(keys.facing_command);
        actor.facing_command = integer_field(record, keys.facing_command, -1);
        actor.has_health = record.has(keys.health);
        actor.health = integer_field(record, keys.health, 0);
        actor.has_sitting = record.has(keys.sitting);
        actor.sitting = bool_field(record, keys.sitting, false);
        actor.has_in_combat = record.has(keys.in_combat);
        actor.in_combat = bool_field(record, keys.in_combat, false);
        actor.has_alive = record.has(keys.alive);
        actor.alive = bool_field(record, keys.alive, false);
        id_to_slot[static_cast<std::size_t>(actor_id)] =
                static_cast<int32_t>(actor_states.size());
        actor_states.push_back(actor);
    }
}

void NativeCrowdStore::mark_dirty(int64_t actor_id, ActorState &actor) {
    if (!actor.dirty) {
        actor.dirty = true;
        dirty_order.push_back(actor_id);
    }
}

NativeCrowdStore::ActorState *NativeCrowdStore::find_actor(int64_t actor_id) {
    if (actor_id < 0 || actor_id >= static_cast<int64_t>(WIRE_ACTOR_CAPACITY)) {
        return nullptr;
    }
    const int32_t slot = id_to_slot[static_cast<std::size_t>(actor_id)];
    return slot >= 0 ? &actor_states[static_cast<std::size_t>(slot)] : nullptr;
}

const NativeCrowdStore::ActorState *NativeCrowdStore::find_actor(
        int64_t actor_id) const {
    if (actor_id < 0 || actor_id >= static_cast<int64_t>(WIRE_ACTOR_CAPACITY)) {
        return nullptr;
    }
    const int32_t slot = id_to_slot[static_cast<std::size_t>(actor_id)];
    return slot >= 0 ? &actor_states[static_cast<std::size_t>(slot)] : nullptr;
}

Dictionary NativeCrowdStore::reduce_packets(const Array &payloads,
        int64_t local_actor_id) {
    // Validate the entire coarse call before changing typed state. This makes
    // malformed and local-leave fallbacks safe even for a multi-packet batch.
    for (int64_t packet_index = 0; packet_index < payloads.size();
            ++packet_index) {
        const Variant value = payloads[packet_index];
        if (value.get_type() != Variant::PACKED_BYTE_ARRAY) {
            return result_with_status("invalid", keys);
        }
        const PackedByteArray payload = value;
        if (payload.size() % 3 != 0) {
            return result_with_status("invalid", keys);
        }
        if (local_actor_id >= 0 && find_actor(local_actor_id) != nullptr) {
            for (int64_t offset = 0; offset < payload.size(); offset += 3) {
                const int64_t actor_id = static_cast<int64_t>(payload[offset]) |
                        (static_cast<int64_t>(payload[offset + 1]) << 8);
                if (actor_id == local_actor_id &&
                        payload[offset + 2] == COMMAND_LEAVE_COMBAT) {
                    return result_with_status("fallback", keys);
                }
            }
        }
    }

    for (int64_t packet_index = 0; packet_index < payloads.size();
            ++packet_index) {
        const PackedByteArray payload = payloads[packet_index];
        for (int64_t offset = 0; offset < payload.size(); offset += 3) {
            const int64_t actor_id = static_cast<int64_t>(payload[offset]) |
                    (static_cast<int64_t>(payload[offset + 1]) << 8);
            ActorState *actor = find_actor(actor_id);
            if (actor == nullptr) {
                continue;
            }
            apply_store_command(*actor,
                    static_cast<int>(payload[offset + 2]));
            mark_dirty(actor_id, *actor);
        }
    }

    PackedInt32Array changed_ids;
    changed_ids.resize(static_cast<int64_t>(dirty_order.size()));
    for (int64_t index = 0;
            index < static_cast<int64_t>(dirty_order.size()); ++index) {
        changed_ids[index] = static_cast<int32_t>(
                dirty_order[static_cast<std::size_t>(index)]);
    }
    Dictionary result = result_with_status("ok", keys);
    result[keys.changed_ids] = changed_ids;
    return result;
}

PackedInt32Array NativeCrowdStore::snapshot_dirty(Dictionary actors) {
    PackedInt32Array materialized;
    std::vector<int64_t> retained_dirty;
    retained_dirty.reserve(dirty_order.size());
    for (const int64_t actor_id : dirty_order) {
        ActorState *actor = find_actor(actor_id);
        if (actor == nullptr) {
            continue;
        }
        if (!actors.has(actor_id)) {
            retained_dirty.push_back(actor_id);
            continue;
        }
        const Variant value = actors[actor_id];
        if (value.get_type() != Variant::DICTIONARY) {
            retained_dirty.push_back(actor_id);
            continue;
        }
        Dictionary record = static_cast<Dictionary>(value).duplicate(false);
        record[keys.x] = actor->x;
        record[keys.y] = actor->y;
        record[keys.command] = actor->command;
        record[keys.command_sequence] = actor->command_sequence;
        if (actor->has_facing_command) {
            record[keys.facing_command] = actor->facing_command;
        }
        if (actor->has_health) {
            record[keys.health] = actor->health;
        }
        if (actor->has_sitting) {
            record[keys.sitting] = actor->sitting;
        }
        if (actor->has_in_combat) {
            record[keys.in_combat] = actor->in_combat;
        }
        if (actor->has_alive) {
            record[keys.alive] = actor->alive;
        }
        actors[actor_id] = record;
        materialized.append(static_cast<int32_t>(actor_id));
        actor->dirty = false;
    }
    dirty_order.swap(retained_dirty);
    return materialized;
}

void NativeCrowdStore::remove(const PackedInt32Array &actor_ids) {
    for (int64_t index = 0; index < actor_ids.size(); ++index) {
        const int64_t actor_id = actor_ids[index];
        if (actor_id < 0 || actor_id >= static_cast<int64_t>(WIRE_ACTOR_CAPACITY)) {
            continue;
        }
        const int32_t slot = id_to_slot[static_cast<std::size_t>(actor_id)];
        if (slot < 0) {
            continue;
        }
        const std::size_t removed_slot = static_cast<std::size_t>(slot);
        const std::size_t last_slot = actor_states.size() - 1;
        if (removed_slot != last_slot) {
            actor_states[removed_slot] = actor_states[last_slot];
            id_to_slot[static_cast<std::size_t>(
                    actor_states[removed_slot].actor_id)] = slot;
        }
        actor_states.pop_back();
        id_to_slot[static_cast<std::size_t>(actor_id)] = -1;
    }
    std::vector<int64_t> retained_dirty;
    retained_dirty.reserve(dirty_order.size());
    for (const int64_t dirty_id : dirty_order) {
        if (find_actor(dirty_id) != nullptr) {
            retained_dirty.push_back(dirty_id);
        }
    }
    dirty_order.swap(retained_dirty);
}

void NativeCrowdStore::clear() {
    actor_states.clear();
    id_to_slot.fill(-1);
    dirty_order.clear();
}

bool NativeCrowdStore::has(int64_t actor_id) const {
    return find_actor(actor_id) != nullptr;
}

int64_t NativeCrowdStore::size() const {
    return static_cast<int64_t>(actor_states.size());
}

} // namespace godot
