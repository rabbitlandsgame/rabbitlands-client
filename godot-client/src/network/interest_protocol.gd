extends RefCounted
## Area of interest, presence, server-time frames and mount deltas: the
## capabilities a crowded shard needs from the client, how this client says
## how many actors it wants, and the three packets that carry them.
##
## The server keeps every player to an area of interest around them (80 tiles
## to come into view, 88 to leave it) and to a cap on the actors it sends at
## once. Players beyond the area are sent once a second as presence dots. The
## client states its own cap, which may be lower than the server's on a slower
## machine. Each part is a separate capability and needs a server setting as
## well; until the first packet of a part arrives the client behaves exactly
## as a client without it, so a server that never sends one changes nothing.

## Accepts the area of interest, the actor cap and "+N nearby", and decodes
## ELORIA_PRESENCE.
const PLAYER_INTEREST_CAPABILITY := "player_interest_v1"
## Decodes ELORIA_SERVER_TIME and paces remote actors by it.
const SERVER_TIME_CAPABILITY := "server_time_v1"
## Decodes ELORIA_MOUNT_DELTAS instead of complete riding tables.
const MOUNT_DELTAS_CAPABILITY := "mount_deltas_v1"
## The cap travels as a value token in the same capability list.
const ACTOR_CAP_TOKEN := "actor_cap:%d"

## The range the server takes a declared cap in, players and creatures
## together. NPCs, the player's target, attackers, party and trade partner are
## sent whatever the cap. A client that declares none gets the maximum.
const ACTOR_CAP_MAXIMUM := 160
const ACTOR_CAP_MINIMUM := 16
const ACTOR_CAP_DEFAULT := ACTOR_CAP_MAXIMUM

const PRESENCE_VERSION := 1
const PRESENCE_HEADER_BYTES := 12
const PRESENCE_ROW_BYTES := 7
## Presence row flags.
const PRESENCE_HIDDEN_BY_CAP := 1
const PRESENCE_PK := 2
const MOUNT_DELTAS_SCHEMA := 2
## Riders one mount packet may carry, as the complete tables allow.
const MOUNT_DELTAS_MAXIMUM_ROWS := 256

const MountDeltaState := preload("res://src/mounts/mount_delta_state.gd")
const MountState := preload("res://src/mounts/mount_preview_state.gd")

## A cap within the range the server takes; anything not a number is the
## default.
static func clamp_actor_cap(value: Variant) -> int:
	var number: int = int(value) if typeof(value) in [TYPE_INT, TYPE_FLOAT] else ACTOR_CAP_DEFAULT
	return clampi(number, ACTOR_CAP_MINIMUM, ACTOR_CAP_MAXIMUM)

## The cap this client declares for the player's "Characters drawn in a
## crowd" setting: no more actors asked of the server than are drawn with a
## body, within the protocol's range. The setting's default (160) declares
## 160, the same as declaring nothing. The one place the rule lives, so it can
## change in one line if the cap should stop following the setting.
static func declared_actor_cap(crowd_bodies: int) -> int:
	return clamp_actor_cap(crowd_bodies)

## The capability token that states `cap`.
static func actor_cap_token(cap: int) -> String:
	return ACTOR_CAP_TOKEN % clamp_actor_cap(cap)

## ELORIA_PRESENCE: the map's players this client is not shown as actors, and
## how many near ones the cap holds back. Bytes after the known fields, and
## flag bits this client does not know, are ignored.
static func decode_presence(payload: PackedByteArray) -> Dictionary:
	if payload.size() < PRESENCE_HEADER_BYTES:
		return {"type": "invalid", "error": "presence_length"}
	if payload[0] != PRESENCE_VERSION:
		return {"type": "invalid", "error": "presence_version"}
	var count: int = payload.decode_u16(10)
	if payload.size() < PRESENCE_HEADER_BYTES + count * PRESENCE_ROW_BYTES:
		return {"type": "invalid", "error": "presence_rows"}
	var ids := PackedInt32Array()
	var tiles := PackedVector2Array()
	var flags := PackedByteArray()
	ids.resize(count)
	tiles.resize(count)
	flags.resize(count)
	for index: int in range(count):
		var at: int = PRESENCE_HEADER_BYTES + index * PRESENCE_ROW_BYTES
		ids[index] = payload.decode_u16(at)
		tiles[index] = Vector2(payload.decode_u16(at + 2), payload.decode_u16(at + 4))
		flags[index] = payload[at + 6]
	return {"type": "presence", "active": (payload[1] & 1) != 0,
		"aoi_enter": int(payload[2]), "aoi_exit": int(payload[3]),
		"cap": payload.decode_u16(4),
		"nearby_hidden": payload.decode_u16(6) + payload.decode_u16(8),
		"ids": ids, "tiles": tiles, "flags": flags}

## ELORIA_SERVER_TIME: the server's clock in milliseconds (u32, wrapping) at
## which the packets after it, up to the next stamp, happened.
static func decode_server_time(payload: PackedByteArray) -> Dictionary:
	if payload.size() < 4:
		return {"type": "invalid", "error": "server_time_length"}
	return {"type": "server_time", "server_ms": int(payload.decode_u32(0))}

## ELORIA_MOUNT_DELTAS: the riding table, whole (`full`) or as the riders whose
## row changed and the actors whose row went away. Rows are returned as the
## server sent them, keyed by actor id; each is checked here the way the
## complete tables are, in the shape `MountDeltaState.v1_row` gives it.
static func decode_mount_deltas(payload: PackedByteArray) -> Dictionary:
	var decoded: Variant = JSON.parse_string(payload.get_string_from_utf8())
	if not decoded is Dictionary:
		return {"type": "invalid", "error": "mount_deltas_json"}
	var data: Dictionary = decoded
	if (data.get("schema_version") != MOUNT_DELTAS_SCHEMA or not data.get("map") is String
			or not data.get("full") is bool or not data.get("states") is Array
			or not data.get("removed", []) is Array
			or (data.states as Array).size() > MOUNT_DELTAS_MAXIMUM_ROWS):
		return {"type": "invalid", "error": "mount_deltas_header"}
	var states: Dictionary = {}
	for value: Variant in data.states:
		if not value is Dictionary:
			return {"type": "invalid", "error": "mount_deltas_row"}
		var row: Dictionary = value
		if not MountState._integer(row.get("actor_id"), 0, 65535) or states.has(int(row.actor_id)):
			return {"type": "invalid", "error": "mount_deltas_actor"}
		var shaped: Dictionary = MountDeltaState.v1_row(row)
		if shaped.is_empty():
			return {"type": "invalid", "error": "mount_deltas_timing"}
		shaped["kind"] = "mount_preview"
		shaped["schema_version"] = 1
		shaped["epoch"] = 0
		shaped["revision"] = 1
		var checker := MountState.new()
		checker.reset(int(row.actor_id), 0)
		if not checker.apply_snapshot(shaped):
			return {"type": "invalid", "error": "mount_deltas_state"}
		states[int(row.actor_id)] = row
	var removed: Array[int] = []
	for value: Variant in data.get("removed", []):
		if not MountState._integer(value, 0, 65535):
			return {"type": "invalid", "error": "mount_deltas_removed"}
		removed.append(int(value))
	return {"type": "mount_update", "map": data.map, "full": data.full,
		"states": states, "removed": removed}
