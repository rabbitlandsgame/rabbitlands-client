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

// reduce_run facet bits. They must equal AppState's FACET_* constants
// (src/state/app_state.gd); tests/test_native_crowd_run_parity.gd checks both.
constexpr int32_t FACET_MOVE = 1;     // a step moved x/y
constexpr int32_t FACET_COMMAND = 2;  // command and command_sequence (every command)
constexpr int32_t FACET_FACING = 4;   // facing_command (walk, run, turn)
constexpr int32_t FACET_SIT = 8;      // sitting (13, 14)
constexpr int32_t FACET_COMBAT = 16;  // in_combat (18, 19)
constexpr int32_t FACET_LIFE = 32;    // alive and health (3)

// reduce_run stamp modes (AppState._command_run_stamp()).
constexpr int64_t STAMP_NONE = 0;     // leave step stamps alone
constexpr int64_t STAMP_CURRENT = 1;  // stamp remote steps, unstamp the local actor's
constexpr int64_t STAMP_CLEAR = 2;    // no current server time: unstamp every step

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

// The fields apply_dictionary_command writes, as bits of FieldState.
constexpr uint32_t FIELD_X = 1u << 0;
constexpr uint32_t FIELD_Y = 1u << 1;
constexpr uint32_t FIELD_COMMAND = 1u << 2;
constexpr uint32_t FIELD_SEQUENCE = 1u << 3;
constexpr uint32_t FIELD_FACING = 1u << 4;
constexpr uint32_t FIELD_SITTING = 1u << 5;
constexpr uint32_t FIELD_COMBAT = 1u << 6;
constexpr uint32_t FIELD_ALIVE = 1u << 7;
constexpr uint32_t FIELD_HEALTH = 1u << 8;

// Which fields a touched copy already held, learned at each field's first
// write (one `has` per written field per copy).
struct FieldState {
    uint32_t checked = 0;
    uint32_t missing = 0;
};

// Godot 4.7 keeps a StringName key's type when it inserts one, while
// ActorReducer (GDScript) inserts String keys. A field the record lacks is
// therefore inserted under its String name, so the record's keys, their order
// and var_to_bytes match the GDScript reducer; present fields are written
// through the cached StringName.
void write_field(Dictionary &record, FieldState &state, uint32_t field,
        const StringName &name, const String &text, const Variant &value) {
    if ((state.checked & field) == 0) {
        state.checked |= field;
        if (!record.has(name)) {
            state.missing |= field;
        }
    }
    if ((state.missing & field) != 0) {
        record[text] = value;
        state.missing &= ~field;
    } else {
        record[name] = value;
    }
}

void apply_dictionary_command(Dictionary &record, int command,
        const NativeCrowdActorKeys &keys, FieldState &state) {
    int64_t step_x = 0;
    int64_t step_y = 0;
    bool has_direction = false;
    command_direction(command, step_x, step_y, has_direction);
    write_field(record, state, FIELD_X, keys.x, keys.x_text,
            wrapping_add(integer_field(record, keys.x, 0), step_x));
    write_field(record, state, FIELD_Y, keys.y, keys.y_text,
            wrapping_add(integer_field(record, keys.y, 0), step_y));
    write_field(record, state, FIELD_COMMAND, keys.command, keys.command_text,
            command);
    write_field(record, state, FIELD_SEQUENCE, keys.command_sequence,
            keys.command_sequence_text,
            wrapping_add(integer_field(record, keys.command_sequence, 0), 1));
    if (has_direction) {
        write_field(record, state, FIELD_FACING, keys.facing_command,
                keys.facing_command_text, command);
    }
    if (command == COMMAND_SIT) {
        write_field(record, state, FIELD_SITTING, keys.sitting,
                keys.sitting_text, true);
    } else if (command == COMMAND_STAND) {
        write_field(record, state, FIELD_SITTING, keys.sitting,
                keys.sitting_text, false);
    } else if (command == COMMAND_ENTER_COMBAT) {
        write_field(record, state, FIELD_COMBAT, keys.in_combat,
                keys.in_combat_text, true);
    } else if (command == COMMAND_LEAVE_COMBAT) {
        write_field(record, state, FIELD_COMBAT, keys.in_combat,
                keys.in_combat_text, false);
    } else if (command == COMMAND_DEATH) {
        write_field(record, state, FIELD_ALIVE, keys.alive, keys.alive_text,
                false);
        write_field(record, state, FIELD_HEALTH, keys.health, keys.health_text,
                0);
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

// ServerTimePacing.is_step_command: walk 20-27 and run 30-37.
bool is_step_command(int command) {
    return (command >= 20 && command <= 27) || (command >= 30 && command <= 37);
}

int32_t command_facets(int command) {
    int64_t step_x = 0;
    int64_t step_y = 0;
    bool has_direction = false;
    command_direction(command, step_x, step_y, has_direction);
    int32_t mask = FACET_COMMAND;
    if (step_x != 0 || step_y != 0) {
        mask |= FACET_MOVE;
    }
    if (has_direction) {
        mask |= FACET_FACING;
    }
    if (command == COMMAND_SIT || command == COMMAND_STAND) {
        mask |= FACET_SIT;
    } else if (command == COMMAND_ENTER_COMBAT ||
            command == COMMAND_LEAVE_COMBAT) {
        mask |= FACET_COMBAT;
    } else if (command == COMMAND_DEATH) {
        mask |= FACET_LIFE;
    }
    return mask;
}

// The step-time stamp AppState._stamp_step() puts on a stepped actor, with
// the values of one flush. The key names come from ServerTimePacing.
struct RunStamp {
    int64_t mode = STAMP_NONE;
    StringName step_key;
    StringName playout_key;
    StringName pass_key;
    // The same names as Strings, for writes (see write_field).
    String step_text;
    String playout_text;
    String pass_text;
    Variant local_msec;
    Variant playout_seconds;
    int64_t pass_id = 0;
};

bool parse_stamp(const Dictionary &stamp, const NativeCrowdActorKeys &keys,
        RunStamp &out) {
    out.mode = integer_field(stamp, keys.stamp_mode, STAMP_NONE);
    if (out.mode == STAMP_NONE) {
        return true;
    }
    if (out.mode != STAMP_CURRENT && out.mode != STAMP_CLEAR) {
        return false;
    }
    const Variant step = stamp.get(keys.step_key, Variant());
    const Variant playout = stamp.get(keys.playout_key, Variant());
    const Variant pass = stamp.get(keys.pass_key, Variant());
    if (step.get_type() != Variant::STRING || playout.get_type() != Variant::STRING ||
            pass.get_type() != Variant::STRING) {
        return false;
    }
    out.step_text = step;
    out.playout_text = playout;
    out.pass_text = pass;
    if (out.step_text.is_empty() || out.playout_text.is_empty() ||
            out.pass_text.is_empty()) {
        return false;
    }
    out.step_key = StringName(out.step_text);
    out.playout_key = StringName(out.playout_text);
    out.pass_key = StringName(out.pass_text);
    if (out.mode == STAMP_CURRENT) {
        out.local_msec = stamp.get(keys.local_msec, Variant());
        out.playout_seconds = stamp.get(keys.playout_seconds, Variant());
        const Variant pass_value = stamp.get(keys.pass_id, Variant());
        if (out.local_msec.get_type() != Variant::INT ||
                out.playout_seconds.get_type() != Variant::FLOAT ||
                pass_value.get_type() != Variant::INT) {
            return false;
        }
        out.pass_id = static_cast<int64_t>(pass_value);
    }
    return true;
}

// AppState._stamp_step() for one step command, on the record the command was
// just applied to: ServerTimePacing.stamp() (first stamp of a pass wins) for a
// remote actor while the server time is current, otherwise unstamp() when the
// record holds a stamp. Same keys (written under their String names, at most
// once per actor and pass), same values, same insertion order.
void apply_step_stamp(Dictionary &record, int64_t actor_id,
        int64_t local_actor_id, const RunStamp &stamp, int64_t &stamped,
        int64_t &unstamped) {
    if (stamp.mode == STAMP_CURRENT && actor_id != local_actor_id) {
        if (integer_field(record, stamp.pass_key, -1) == stamp.pass_id &&
                record.has(stamp.step_key)) {
            return;
        }
        record[stamp.step_text] = stamp.local_msec;
        record[stamp.playout_text] = stamp.playout_seconds;
        record[stamp.pass_text] = stamp.pass_id;
        ++stamped;
    } else if (record.has(stamp.step_key)) {
        record.erase(stamp.step_key);
        record.erase(stamp.playout_key);
        record.erase(stamp.pass_key);
        ++unstamped;
    }
}

Dictionary run_result(const char *status, const char *reason,
        const NativeCrowdActorKeys &keys) {
    Dictionary result = result_with_status(status, keys);
    result[keys.reason] = String(reason);
    result[keys.consumed] = 0;
    result[keys.facets] = PackedInt32Array();
    result[keys.commands] = 0;
    result[keys.applied] = 0;
    result[keys.stamped] = 0;
    result[keys.unstamped] = 0;
    return result;
}

} // namespace

void NativeCrowdReducer::_bind_methods() {
    ClassDB::bind_method(D_METHOD("reduce_packet", "actors", "payload",
                                 "local_actor_id"),
            &NativeCrowdReducer::reduce_packet);
    ClassDB::bind_method(D_METHOD("reduce_run", "actors", "payloads",
                                 "local_actor_id", "stamp"),
            &NativeCrowdReducer::reduce_run);
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

    struct Touched {
        Dictionary record;
        FieldState fields;
    };
    std::unordered_map<int64_t, Touched> touched;
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
            Touched copy{static_cast<Dictionary>(value).duplicate(false), {}};
            found = touched.emplace(actor_id, copy).first;
            changed_order.push_back(actor_id);
        }
        apply_dictionary_command(found->second.record,
                static_cast<int>(payload[offset + 2]), keys, found->second.fields);
    }

    PackedInt32Array changed_ids;
    changed_ids.resize(static_cast<int64_t>(changed_order.size()));
    for (int64_t index = 0;
            index < static_cast<int64_t>(changed_order.size()); ++index) {
        const int64_t actor_id = changed_order[static_cast<std::size_t>(index)];
        actors[actor_id] = touched.find(actor_id)->second.record;
        changed_ids[index] = static_cast<int32_t>(actor_id);
    }

    Dictionary result = result_with_status("ok", keys);
    result[keys.changed_ids] = changed_ids;
    return result;
}

// rust-batch R2: one call for a run of consecutive ADD_ACTOR_COMMAND payloads
// that AppState buffered without decoding. The records are applied in arrival
// order exactly as AppState's GDScript loop applies them packet after packet
// (ActorReducer.apply_command, then _stamp_step), but each touched actor is
// copied once and written back once, and nothing is published per packet.
//
// `stamp` carries AppState's step-time state for this flush ({} or mode 0
// leaves the stamps alone): mode 1 stamps remote actors' steps with
// local_msec/playout_seconds/pass_id under step_key/playout_key/pass_key and
// unstamps the local actor's, mode 2 unstamps every stepped actor.
//
// The run stops before the first packet that must keep the original path, so
// AppState reduces that one in GDScript and continues with the rest:
// `invalid_payload` (not a PackedByteArray, or not 3-byte records),
// `record_not_dictionary` (a targeted record that is not a Dictionary: the
// GDScript typed assignment is the authority for corrupt containers) and
// `local_leave` (the local actor's command 19, whose synchronous combat_state
// signal must see the intermediate state). Packets before it are applied.
//
// Returns {status: "ok" | "fallback" | "invalid", reason, consumed (packets
// applied), changed_ids (first-touch order), facets (FACET_* mask per changed
// id: which kinds of command touched it), commands (records in the applied
// packets), applied (records for known actors), stamped, unstamped}. Only
// "ok" and "fallback" write to `actors`; "invalid" (a malformed `stamp`)
// writes nothing. The outer `actors` Dictionary is kept, untouched actors keep
// their record objects, and a touched record is a shallow copy (nested values
// stay shared), as with reduce_packet.
Dictionary NativeCrowdReducer::reduce_run(Dictionary actors,
        const Array &payloads, int64_t local_actor_id,
        const Dictionary &stamp) const {
    RunStamp run_stamp;
    if (!parse_stamp(stamp, keys, run_stamp)) {
        return run_result("invalid", "invalid_stamp", keys);
    }
    // Commands neither add nor remove actors, so whether the local actor is
    // present holds for the whole run (AppState's check is per command).
    const bool local_present =
            local_actor_id >= 0 && actors.has(local_actor_id);

    std::unordered_map<int64_t, std::size_t> touched;
    std::vector<int64_t> order;
    std::vector<Dictionary> records;
    std::vector<FieldState> fields;
    std::vector<int32_t> masks;
    const char *status = "ok";
    const char *reason = "";
    int64_t consumed = 0;
    int64_t commands = 0;
    int64_t applied = 0;
    int64_t stamped = 0;
    int64_t unstamped = 0;

    for (int64_t packet_index = 0; packet_index < payloads.size();
            ++packet_index) {
        const Variant value = payloads[packet_index];
        if (value.get_type() != Variant::PACKED_BYTE_ARRAY) {
            status = "fallback";
            reason = "invalid_payload";
            break;
        }
        const PackedByteArray payload = value;
        if (payload.size() % 3 != 0) {
            status = "fallback";
            reason = "invalid_payload";
            break;
        }
        // Checked against the table, which holds every record this run has
        // not written back yet; a touched record's copy is a Dictionary.
        if (!packet_records_are_dictionaries(payload, actors)) {
            status = "fallback";
            reason = "record_not_dictionary";
            break;
        }
        if (local_present &&
                packet_has_local_leave(payload, local_actor_id, actors)) {
            status = "fallback";
            reason = "local_leave";
            break;
        }
        for (int64_t offset = 0; offset < payload.size(); offset += 3) {
            const int64_t actor_id = static_cast<int64_t>(payload[offset]) |
                    (static_cast<int64_t>(payload[offset + 1]) << 8);
            const int command = static_cast<int>(payload[offset + 2]);
            std::size_t index = 0;
            auto found = touched.find(actor_id);
            if (found != touched.end()) {
                index = found->second;
            } else {
                if (!actors.has(actor_id)) {
                    continue;
                }
                const Variant record = actors[actor_id];
                if (record.get_type() != Variant::DICTIONARY) {
                    continue;
                }
                index = records.size();
                touched.emplace(actor_id, index);
                order.push_back(actor_id);
                records.push_back(static_cast<Dictionary>(record).duplicate(false));
                fields.push_back(FieldState());
                masks.push_back(0);
            }
            Dictionary &copy = records[index];
            apply_dictionary_command(copy, command, keys, fields[index]);
            if (run_stamp.mode != STAMP_NONE && is_step_command(command)) {
                apply_step_stamp(copy, actor_id, local_actor_id, run_stamp,
                        stamped, unstamped);
            }
            masks[index] |= command_facets(command);
            ++applied;
        }
        commands += payload.size() / 3;
        ++consumed;
    }

    PackedInt32Array changed_ids;
    PackedInt32Array facets;
    changed_ids.resize(static_cast<int64_t>(order.size()));
    facets.resize(static_cast<int64_t>(order.size()));
    for (std::size_t index = 0; index < order.size(); ++index) {
        actors[order[index]] = records[index];
        changed_ids[static_cast<int64_t>(index)] = static_cast<int32_t>(order[index]);
        facets[static_cast<int64_t>(index)] = masks[index];
    }

    Dictionary result = run_result(status, reason, keys);
    result[keys.consumed] = consumed;
    result[keys.changed_ids] = changed_ids;
    result[keys.facets] = facets;
    result[keys.commands] = commands;
    result[keys.applied] = applied;
    result[keys.stamped] = stamped;
    result[keys.unstamped] = unstamped;
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
