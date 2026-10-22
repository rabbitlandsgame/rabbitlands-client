extends SceneTree
## The player-interest packets (protocol v2): ELORIA_PRESENCE, ELORIA_SERVER_TIME
## and ELORIA_MOUNT_DELTAS, and the capability line with the actor cap.

const InterestProtocol := preload("res://src/network/interest_protocol.gd")

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_capabilities()
	_presence()
	_server_time()
	_mount_deltas()
	_server_built()
	print("interest protocol tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _capabilities() -> void:
	for capability: String in ["player_interest_v1", "server_time_v1", "mount_deltas_v1"]:
		_expect(EloriaProtocol.CLIENT_CAPABILITIES.has(capability), "%s is declared" % capability)
	_expect(not EloriaProtocol.CLIENT_CAPABILITIES.has("actor_cap:160"),
		"the cap is not a fixed entry of the list, which load tools read as names")
	var line: String = _chat_text(EloriaProtocol.client_capabilities(90))
	_expect(line.begins_with("#clientcaps ") and line.ends_with(",actor_cap:90"),
		"the declared cap follows the names as a value token")
	_expect(_chat_text(EloriaProtocol.client_capabilities(500)).ends_with(",actor_cap:160"),
		"and never asks for more than 160")
	_expect(not _chat_text(EloriaProtocol.client_capabilities()).contains("actor_cap"),
		"without a cap the line is the list alone")
	_expect(InterestProtocol.actor_cap_command(100) == "#actorcap 100"
		and InterestProtocol.actor_cap_command(500) == "#actorcap 160"
		and InterestProtocol.actor_cap_command(3) == "#actorcap 16",
		"a cap changed in a session goes as #actorcap, within the server's range")
	for value: int in [Ids.PRESENCE, Ids.SERVER_TIME, Ids.MOUNT_DELTAS]:
		_expect(EloriaProtocol.ServerMessage.values().count(value) == 1,
			"command %d is used once in the server run" % value)

func _presence() -> void:
	var payload := _hex("01015058a000030002000200" + "5b006400c80000" + "5c00e8030a0003" + "ffff")
	var event: Dictionary = EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.ELORIA_PRESENCE, payload)
	_expect(event.type == "presence" and bool(event.active), "presence decodes")
	_expect(int(event.aoi_enter) == 80 and int(event.aoi_exit) == 88 and int(event.cap) == 160,
		"with the area's radii and the cap in force")
	_expect(int(event.nearby_hidden) == 5, "\"+N nearby\" is the hidden players and creatures together")
	var ids: PackedInt32Array = event.ids
	var tiles: PackedVector2Array = event.tiles
	var flags: PackedByteArray = event.flags
	_expect(ids == PackedInt32Array([91, 92]) and tiles[0] == Vector2(100, 200)
		and tiles[1] == Vector2(1000, 10), "each row is an actor id and a server tile")
	_expect(flags[0] == 0 and flags[1] == 3, "row flags are kept, trailing bytes ignored")
	_expect(EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.ELORIA_PRESENCE,
		_hex("01015058a00000000000")).type == "invalid", "a short header is refused")
	_expect(EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.ELORIA_PRESENCE,
		_hex("02015058a000000000000000")).type == "invalid", "another version is refused")
	_expect(EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.ELORIA_PRESENCE,
		_hex("01015058a000000000000200" + "5b006400c80000")).type == "invalid",
		"a count longer than the rows is refused")
	var empty: Dictionary = EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.ELORIA_PRESENCE,
		_hex("01015058000000000000" + "0000"))
	_expect(empty.type == "presence" and (empty.ids as PackedInt32Array).is_empty()
		and int(empty.cap) == 0, "an empty map's snapshot clears the dots")

func _server_time() -> void:
	var event: Dictionary = EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.ELORIA_SERVER_TIME,
		_hex("feffffff"))
	_expect(event.type == "server_time" and int(event.server_ms) == 4294967294,
		"a server time is an unsigned 32-bit count")
	_expect(EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.ELORIA_SERVER_TIME,
		_hex("e803")).type == "invalid", "a short stamp is refused")

func _row(actor_id: int, mode: String) -> Dictionary:
	var mounted: bool = mode == "mounted"
	return {"actor_id": actor_id, "mode": mode, "gait": "cruise" if mounted else "on_foot",
		"mount_id": "moor_pony" if mode != "on_foot" else "", "selected_mount_id": "moor_pony",
		"step_us": 133333, "can_summon": false, "blocked_reason": "", "map": "landfall",
		"owner": "Wren", "summon_due": 0, "combat_until": 0, "endurance_ms": 8000,
		"endurance_at": 1000, "endurance_rate": 0, "endurance_max_ms": 8000}

func _deltas(body: Dictionary) -> Dictionary:
	return EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.ELORIA_MOUNT_DELTAS,
		JSON.stringify(body).to_utf8_buffer())

func _mount_deltas() -> void:
	var event: Dictionary = _deltas({"schema_version": 2, "map": "landfall", "full": false,
		"states": [_row(91, "mounted"), _row(92, "summoning")], "removed": [93]})
	_expect(event.type == "mount_update" and not bool(event.full) and str(event.map) == "landfall",
		"a riding delta decodes")
	_expect((event.states as Dictionary).has(91) and (event.states as Dictionary).has(92)
		and (event.removed as Array).size() == 1 and int(event.removed[0]) == 93,
		"with its rows by actor and its removals")
	_expect(_deltas({"schema_version": 1, "map": "landfall", "full": true, "states": []}).type == "invalid",
		"a complete table's schema is not a delta")
	var broken := _row(91, "mounted")
	broken.erase("endurance_at")
	_expect(_deltas({"schema_version": 2, "map": "landfall", "full": false, "states": [broken]}).type == "invalid",
		"a row without its times is refused")
	var inconsistent := _row(91, "mounted")
	inconsistent["mount_id"] = ""
	_expect(_deltas({"schema_version": 2, "map": "landfall", "full": false, "states": [inconsistent]}).type == "invalid",
		"a row the complete tables would refuse is refused")
	_expect(_deltas({"schema_version": 2, "map": "landfall", "full": false,
		"states": [_row(91, "mounted"), _row(91, "on_foot")]}).type == "invalid", "an actor twice is refused")
	_expect(_deltas({"schema_version": 2, "map": "landfall", "full": false, "states": [],
		"removed": [-1]}).type == "invalid", "a removal that is not an actor id is refused")
	var longer := _row(94, "mounted")
	longer["endurance_max_ms"] = 12000
	longer["endurance_ms"] = 10000
	var long_gallop: Dictionary = _deltas({"schema_version": 2, "map": "landfall", "full": false,
		"states": [longer]})
	_expect(long_gallop.type == "mount_update", "a row whose own maximum is past 8 s is not refused")
	var table: Dictionary = {}
	preload("res://src/mounts/mount_delta_state.gd").new().apply(long_gallop, table, "landfall", null, 0)
	_expect(int(table[94].endurance_ms) == 10000 and int(table[94].endurance_max_ms) == 12000,
		"and keeps its endurance and maximum")

## A delta built by the server's own `_delta_payload` and `_delta_row_json`
## (eloria/live_mounts.py): one rider calling a pony, one rider gone.
const SERVER_MOUNT_DELTA := "7b22736368656d615f76657273696f6e223a322c226d6170223a226c616e6466616c6c222c2266756c6c223a66616c73652c22737461746573223a5b7b22736368656d615f76657273696f6e223a322c226163746f725f6964223a39312c226d6f6465223a2273756d6d6f6e696e67222c2267616974223a226f6e5f666f6f74222c226d6f756e745f6964223a226d6f6f725f706f6e79222c2273656c65637465645f6d6f756e745f6964223a226d6f6f725f706f6e79222c22737465705f7573223a3133333333332c2263616e5f73756d6d6f6e223a66616c73652c22626c6f636b65645f726561736f6e223a22222c226d6170223a226c616e6466616c6c222c226f776e6572223a225772656e222c2273756d6d6f6e5f647565223a3132333435362c22636f6d6261745f756e74696c223a302c22656e647572616e63655f6d73223a363030302c22656e647572616e63655f6174223a3132303030302c22656e647572616e63655f72617465223a2d313030302c22656e647572616e63655f6d61785f6d73223a383030307d5d2c2272656d6f766564223a5b39335d7d"

func _server_built() -> void:
	var event: Dictionary = EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.ELORIA_MOUNT_DELTAS,
		_hex(SERVER_MOUNT_DELTA))
	_expect(event.type == "mount_update" and (event.states as Dictionary).has(91)
		and int((event.states as Dictionary)[91].summon_due) == 123456
		and int(event.removed[0]) == 93, "a delta from the server's own builder decodes")
	var table: Dictionary = {}
	var deltas = preload("res://src/mounts/mount_delta_state.gd").new()
	deltas.apply(event, table, "landfall", null, 0)
	_expect(int(table[91].schema_version) == 1 and str(table[91].mode) == "summoning"
		and int(table[91].endurance_ms) == 6000, "and is kept in the complete tables' shape")

func _chat_text(frame: PackedByteArray) -> String:
	return frame.slice(3, frame.size() - 1).get_string_from_utf8()

func _hex(text: String) -> PackedByteArray:
	return text.hex_decode()

class Ids:
	const PRESENCE := 197
	const SERVER_TIME := 196
	const MOUNT_DELTAS := 195

func _expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)
