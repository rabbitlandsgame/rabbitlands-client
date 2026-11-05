extends SceneTree
## RB-C7 (rust-batch R1/R2, group B9): actor-command reduction parity.
##
## - The reducer-mode table (`NativeCrowd.reducer_mode`) and the AppState
##   autoload's mode for this process's environment.
## - `NativeCrowdReducer.reduce_run` against the GDScript reducer
##   (`ActorReducer.apply_command` + `ServerTimePacing.stamp`/`unstamp`, as
##   `AppState._stamp_step` calls them): every command byte on full, sparse and
##   stamped records in every stamp mode, random multi-packet runs, the
##   fallback packets (the local actor's command 19, a corrupt record, a
##   malformed payload), malformed stamps, facet masks, counts, identity and
##   sharing. Records are compared with `var_to_bytes`, so key order and value
##   types count, not only `==`.
## - AppState in "run" mode against AppState in "gdscript" mode, fed the same
##   packets: turn/swing/step, death, sit/stand, combat flags, the local actor's
##   19, reused and unknown ids, malformed and empty packets, current and stale
##   server time, damage, spawns and removals, the record limit, reducer
##   switches, the connection flush, the deferred end-of-frame flush and
##   fail-closed on a broken native result; then seeded random streams. After
##   every flush point (another packet, `_network().dispatch_drained`,
##   `take_changed_actors`, a reducer switch) `var_to_bytes` of the whole actor
##   table, of the changed set (ids and order), of combat state and the
##   protocol errors are equal, the signal paths are equal once consecutive
##   `actors` repeats collapse, and combat listeners saw the same tables.
## - The random stream written as an RLREC1 session recording and replayed
##   through the recording path; `--recording=<file.rlrec>` replays a real one
##   (actor packets only; any other packet is a flush point).
##
## Flags (after `--`): `--runtime-dir=<payload>` (loaded before the autoloads,
## like the test_client_runtime_kernels_* wrappers); `--expect-native=present`
## turns a payload without `reduce_run` into a failure instead of a SKIP of the
## native parts; `--recording=<file>`, `--recording-limit=<packets>` (200000);
## `--seed=<int>`; `--frames=<int>` (400).
##
## One error line is expected: "Native reducer run failed (boom:" from the
## fail-closed case. Prints PASS/FAIL and quits with the failure count.

const NativeLibrary := preload("res://src/runtime/native_library.gd")
const NativeCrowd := preload("res://src/runtime/native_crowd.gd")
const ServerTimePacing := preload("res://src/actors/server_time_pacing.gd")
const ServerClockScript := preload("res://src/network/server_clock.gd")
const RLREC_MAGIC := "RLREC1\n"
const RLREC_RECORD_HEADER := 13
const MAX_REPORTED := 12

var failures := 0
var checks := 0
var _reported := 0
var _loaded: Dictionary = {}
var _pairs: Array[Dictionary] = []
## AppState's script and constants, taken from the autoload: a --script main
## loop cannot preload app_state.gd (it names the Network autoload, which is
## not a compile-time name before the autoloads are registered).
var _app_script: GDScript
var K: Dictionary = {}
var CMD: int = EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND
var SERVER_TIME: int = EloriaProtocol.ServerMessage.ELORIA_SERVER_TIME

## Records what one AppState announces: the paths in order, and the actor
## table each `combat_state` listener saw (and each `actors` one if asked).
class Watch:
	var state: Node
	var paths: Array[StringName] = []
	var combat_tables: Array[PackedByteArray] = []
	var actor_tables: Array[PackedByteArray] = []
	var snapshot_actors := false

	func _init(observed: Node) -> void:
		state = observed
		state.state_changed.connect(_changed)

	func _changed(path: StringName) -> void:
		paths.append(path)
		if path == &"combat_state":
			combat_tables.append(var_to_bytes(state.get("actors")))
		elif path == &"actors" and snapshot_actors:
			actor_tables.append(var_to_bytes(state.get("actors")))

	## The paths with consecutive `actors` repeats collapsed: a run publishes
	## once where the GDScript loop announced every packet.
	func collapsed() -> Array[StringName]:
		var out: Array[StringName] = []
		for path: StringName in paths:
			if path == &"actors" and not out.is_empty() and out[-1] == &"actors":
				continue
			out.append(path)
		return out

	func clear() -> void:
		paths.clear()
		combat_tables.clear()
		actor_tables.clear()

## A stand-in whose reduce_run answers nonsense, for the fail-closed case.
class BrokenReducer extends RefCounted:
	func reduce_run(_actors: Dictionary, _payloads: Array, _local: int, _stamp: Dictionary) -> Dictionary:
		return {"status": "boom", "reason": "test"}

	func reduce_packet(_actors: Dictionary, _payload: PackedByteArray, _local: int) -> Dictionary:
		return {"status": "fallback"}

func _initialize() -> void:
	_loaded = NativeLibrary.load_verified(_argument("--runtime-dir="))

func _init() -> void:
	call_deferred("_run")

## The Network autoload (not a compile-time name in a --script main loop).
func _network() -> Node:
	return root.get_node("Network")

static func _argument(prefix: String) -> String:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with(prefix):
			return argument.trim_prefix(prefix)
	return ""

func _expect(condition: bool, message: String) -> bool:
	checks += 1
	if not condition:
		_fail(message)
	return condition

func _fail(message: String) -> void:
	failures += 1
	_reported += 1
	if _reported <= MAX_REPORTED:
		push_error("FAIL: " + message)
	elif _reported == MAX_REPORTED + 1:
		push_error("FAIL: (further failures counted, not printed)")

func _run() -> void:
	_app_script = root.get_node("AppState").get_script()
	K = _app_script.get_script_constant_map()
	var expect_present := OS.get_cmdline_user_args().has("--expect-native=present")
	_mode_table()
	_autoload_mode()
	var made: Dictionary = NativeCrowd.kernel("reducer", true)
	var reducer: Object = made.object
	if str(NativeLibrary.switch_state().mode) == "off":
		_switched_off(made)
		_finish("native runtime switched off: GDScript reducer kept")
		return
	if reducer != null:
		_packet_mode_local_stamp()
	if reducer == null or not reducer.has_method(&"reduce_run"):
		var why := "reducer %s (payload %s %s)%s" % [made.status, _loaded.get("directory", ""),
			_loaded.get("code", ""), "" if reducer == null else ", no reduce_run (older payload)"]
		if expect_present:
			_fail("requested native-present run: " + why)
		else:
			print("SKIP native parts: ", why)
		_finish("native parts skipped")
		return
	print("Run parity against %s from %s (%s)" % [reducer.get_class(), made.provider, _loaded.get("directory", "")])
	_per_command(reducer)
	_sparse_order(reducer)
	_random_runs(reducer)
	_fallbacks(reducer)
	_malformed_stamps(reducer)
	_scenarios()
	await _deferred_flush()
	_fail_closed()
	var seed := int(_argument("--seed=")) if not _argument("--seed=").is_empty() else 20261104
	var frames := int(_argument("--frames=")) if not _argument("--frames=").is_empty() else 400
	var market := _stream(seed, frames, 160, {})
	_drive(_pair(_seed_actors(160), 1), market, "random market (seed %d, %d frames)" % [seed, frames])
	_drive(_pair(_seed_actors(24), 1), _stream(seed + 1, frames, 24, {"dense": true}),
		"random dense (seed %d)" % (seed + 1))
	_recording_self_test(market)
	var recording := _argument("--recording=")
	if not recording.is_empty():
		_replay_recording(recording)
	# Let the runs' deferred end-of-frame flushes fire before the states go.
	await process_frame
	_finish("")

func _finish(note: String) -> void:
	for pair: Dictionary in _pairs:
		for key: String in ["seq", "run"]:
			if is_instance_valid(pair[key]):
				(pair[key] as Node).free()
	_pairs.clear()
	print("Native crowd run parity: %s (%d checks)%s" % ["PASS" if failures == 0 else "FAIL (%d)" % failures,
		checks, "" if note.is_empty() else "; " + note])
	quit(failures)

# --- selection -------------------------------------------------------------

func _mode_table() -> void:
	var off := {"reducer": false}
	var on := {"reducer": true}
	# [RABBITLANDS_NATIVE_REDUCER, ELORIA_NATIVE_CROWD, defaults, mode, reason]
	var cases := [
		["", "", off, "gdscript", "default_off"], ["", "", on, "run", "default_on"],
		["", "1", off, "packet", "selected"], ["run", "", off, "run", "selected"],
		["packet", "", off, "packet", "selected"], [" RUN ", "1", off, "run", "selected"],
		["packet", "1", on, "packet", "selected"], ["run", "0", on, "gdscript", "script_selected"],
		["legacy", "1", on, "gdscript", "script_selected"], ["gdscript", "", on, "gdscript", "script_selected"],
		["off", "", on, "gdscript", "script_selected"], ["bogus", "1", on, "gdscript", "unknown_value"],
		["", "yes", on, "gdscript", "unknown_value"], ["", "legacy", on, "gdscript", "script_selected"],
		["", "0", on, "gdscript", "script_selected"]]
	for row: Array in cases:
		var environment := {"RABBITLANDS_NATIVE_REDUCER": row[0], "ELORIA_NATIVE_CROWD": row[1]}
		var resolved := NativeCrowd.reducer_mode(environment, row[2])
		_expect(str(resolved.mode) == row[3] and str(resolved.reason) == row[4]
			and bool(resolved.wanted) == (row[3] != "gdscript"),
			"reducer_mode(%s, defaults %s) = %s (expected %s/%s)" % [environment, row[2], resolved, row[3], row[4]])
		var selected := NativeCrowd.selection("reducer", environment, row[2])
		_expect(bool(selected.wanted) == bool(resolved.wanted) and str(selected.reason) == str(resolved.reason),
			"selection('reducer') agrees with reducer_mode for %s" % [environment])
	_expect(not bool(NativeCrowd.DEFAULTS.reducer) and NativeCrowd.DEFAULT_REDUCER_MODE == "run"
		and ",".join(NativeCrowd.REDUCER_MODES) == "gdscript,packet,run",
		"D-NATIVE: the reducer defaults off; once on, it runs coalesced")
	_expect(int(K.FACET_MOVE) == 1 and int(K.FACET_COMMAND) == 2 and int(K.FACET_FACING) == 4
		and int(K.FACET_SIT) == 8 and int(K.FACET_COMBAT) == 16 and int(K.FACET_LIFE) == 32,
		"AppState's facet bits are the ones native_crowd_reducer.cpp writes")

func _autoload_mode() -> void:
	var state: Node = root.get_node("AppState")
	var wanted := NativeCrowd.reducer_mode(NativeCrowd.reducer_environment())
	var mode := str(state.get("actor_reducer_mode"))
	if not bool(wanted.wanted) or str(NativeLibrary.switch_state().mode) == "off":
		_expect(mode == "gdscript" and not bool(state.call("native_crowd_reducer_active")),
			"AppState starts on the GDScript reducer for %s (%s)" % [NativeCrowd.reducer_environment(), mode])
		return
	print("AppState autoload reducer: %s (wanted %s)" % [mode, wanted.mode])
	_expect(mode == str(wanted.mode) or (wanted.mode == "run" and mode == "packet"),
		"AppState starts in the requested reducer mode %s (%s)" % [wanted.mode, mode])
	_expect((mode == "run") == bool(_network().dispatch_drained.is_connected(Callable(state, &"flush_actor_commands"))),
		"only the run mode listens for _network().dispatch_drained")

func _switched_off(made: Dictionary) -> void:
	_expect(made.object == null and str(made.status) == "runtime_switched_off",
		"switched off, the requested reducer is refused (%s)" % made.status)
	var state: Node = _app_script.new()
	var outcome: Dictionary = state.call("select_actor_reducer", "run")
	_expect(str(outcome.mode) == "gdscript" and str(outcome.status) == "runtime_switched_off"
		and str(state.get("actor_reducer_mode")) == "gdscript",
		"switched off, AppState keeps the GDScript reducer (%s)" % [outcome])
	state.free()

## R1 ("packet" mode, reduce_packet only) against the GDScript loop for the
## player's own actor holding a step stamp, one it was given while it was still
## a remote actor (before YOU_ARE named it): `_stamp_step` leaves the stamp on
## through a turn and takes it off at the actor's next step, whatever the server
## time, so the packet path must too. R1 stamps after the whole packet, so the
## tables are compared with ==, not var_to_bytes.
func _packet_mode_local_stamp() -> void:
	for case: String in ["current", "stale", "never seen"]:
		var states: Array[Node] = []
		for mode: String in ["gdscript", "packet"]:
			var state: Node = _app_script.new()
			var chosen: Dictionary = state.call("select_actor_reducer", mode)
			_expect(str(chosen.mode) == mode, "AppState selects the %s reducer (%s)" % [mode, chosen])
			var seed := _seed_actors(3)
			var own: Dictionary = seed[100]
			own[ServerTimePacing.STEP_KEY] = 4000
			own[ServerTimePacing.PLAYOUT_KEY] = 0.25
			own[ServerTimePacing.PASS_KEY] = 0
			state.set("actors", seed)
			state.set("local_actor_id", 100)
			state.set("server_clock", ServerClockScript.new())
			var now := Time.get_ticks_msec()
			state.set("_frame_stamps_seen", case != "never seen")
			state.set("_frame_step_local_msec", 5000)
			state.set("_frame_stamp_read_msec", now - 3600000 if case == "stale" else now + 3600000)
			states.append(state)
		var problems: Array[String] = []
		for step: Array in [[[[100, 40], [101, 22]], true], [[[101, 23], [100, 22]], false]]:
			for state: Node in states:
				state.call("_on_packet", CMD, _commands(step[0]))
			var seq_actors: Dictionary = states[0].get("actors")
			var packet_actors: Dictionary = states[1].get("actors")
			var kept: bool = (packet_actors[100] as Dictionary).has(ServerTimePacing.STEP_KEY)
			if seq_actors != packet_actors or kept != bool(step[1]):
				problems.append("after %s: own stamp kept %s (expected %s), tables equal %s" % [step[0], kept,
					step[1], seq_actors == packet_actors])
		_expect(problems.is_empty(), "packet mode, server time %s: the player's own stamp comes off at its next step, as in GDScript %s"
			% [case, problems])
		for state: Node in states:
			state.free()

# --- reduce_run against the GDScript reducer ---------------------------------

static func _commands(rows: Array) -> PackedByteArray:
	var payload := PackedByteArray()
	for row: Array in rows:
		payload.append(int(row[0]) & 0xff)
		payload.append((int(row[0]) >> 8) & 0xff)
		payload.append(int(row[1]) & 0xff)
	return payload

func _expected_facets(command: int) -> int:
	var mask := int(K.FACET_COMMAND)
	if EloriaProtocol.actor_command_step(command) != Vector2i.ZERO:
		mask |= int(K.FACET_MOVE)
	if EloriaProtocol.actor_command_direction(command) != Vector2i.ZERO:
		mask |= int(K.FACET_FACING)
	if command == 13 or command == 14:
		mask |= int(K.FACET_SIT)
	elif command == 18 or command == 19:
		mask |= int(K.FACET_COMBAT)
	elif command == 3:
		mask |= int(K.FACET_LIFE)
	return mask

func _stamp(mode: int, local_msec := 123456, playout := 0.085, pass_id := 7) -> Dictionary:
	var stamp := {"mode": mode, "step_key": ServerTimePacing.STEP_KEY, "playout_key": ServerTimePacing.PLAYOUT_KEY,
		"pass_key": ServerTimePacing.PASS_KEY}
	if mode == int(K.RUN_STAMP_CURRENT):
		stamp["local_msec"] = local_msec
		stamp["playout_seconds"] = playout
		stamp["pass_id"] = pass_id
	return stamp

## The GDScript loop over a run, with `_stamp_step`'s branches for a fixed
## stamp: what AppState's "gdscript" mode does to `actors`, plus what the
## native result should report.
func _emulate(actors: Dictionary, payloads: Array, local_id: int, stamp: Dictionary) -> Dictionary:
	var order: Array[int] = []
	var facets := {}
	var counts := {"commands": 0, "applied": 0, "stamped": 0, "unstamped": 0}
	var mode := int(stamp.get("mode", 0))
	for payload: PackedByteArray in payloads:
		counts["commands"] = int(counts["commands"]) + payload.size() / 3
		for offset: int in range(0, payload.size(), 3):
			var actor_id: int = payload[offset] | (payload[offset + 1] << 8)
			var command: int = payload[offset + 2]
			if not actors.has(actor_id):
				continue
			actors[actor_id] = ActorReducer.apply_command(actors[actor_id] as Dictionary, command)
			counts["applied"] = int(counts["applied"]) + 1
			if mode != 0 and ServerTimePacing.is_step_command(command):
				var record: Dictionary = actors[actor_id]
				if mode == int(K.RUN_STAMP_CURRENT) and actor_id != local_id:
					if not (int(record.get(ServerTimePacing.PASS_KEY, -1)) == int(stamp.pass_id)
							and record.has(ServerTimePacing.STEP_KEY)):
						counts["stamped"] = int(counts["stamped"]) + 1
					ServerTimePacing.stamp(record, int(stamp.local_msec), float(stamp.playout_seconds), int(stamp.pass_id))
				elif record.has(ServerTimePacing.STEP_KEY):
					counts["unstamped"] = int(counts["unstamped"]) + 1
					ServerTimePacing.unstamp(record)
			if not facets.has(actor_id):
				order.append(actor_id)
				facets[actor_id] = 0
			facets[actor_id] = int(facets[actor_id]) | _expected_facets(command)
	return {"order": order, "facets": facets, "counts": counts}

func _native_matches(reducer: Object, seed: Dictionary, payloads: Array, local_id: int, stamp: Dictionary,
		label: String) -> Dictionary:
	var native_actors := seed.duplicate(true)
	var script_actors := seed.duplicate(true)
	var outer := native_actors
	var result: Dictionary = reducer.call(&"reduce_run", native_actors, payloads, local_id, stamp)
	var expected := _emulate(script_actors, payloads, local_id, stamp)
	var problems: Array[String] = []
	if str(result.get("status", "")) != "ok" or int(result.get("consumed", -1)) != payloads.size():
		problems.append("status %s consumed %s" % [result.get("status"), result.get("consumed")])
	if not is_same(outer, native_actors):
		problems.append("outer table replaced")
	if var_to_bytes(native_actors) != var_to_bytes(script_actors):
		problems.append("tables differ: native %s / script %s" % [native_actors, script_actors])
	var ids: PackedInt32Array = result.get("changed_ids", PackedInt32Array())
	var masks: PackedInt32Array = result.get("facets", PackedInt32Array())
	if Array(ids) != Array(expected.order) or masks.size() != ids.size():
		problems.append("changed ids %s, expected %s" % [ids, expected.order])
	else:
		for index: int in ids.size():
			if masks[index] != int(expected.facets[ids[index]]):
				problems.append("facets of %d: %d, expected %d" % [ids[index], masks[index], expected.facets[ids[index]]])
	for key: String in ["commands", "applied", "stamped", "unstamped"]:
		if int(result.get(key, -1)) != int(expected.counts[key]):
			problems.append("%s %s, expected %s" % [key, result.get(key), expected.counts[key]])
	_expect(problems.is_empty(), "%s: %s" % [label, problems])
	return {"actors": native_actors, "result": result}

static func _full_actor(actor_id: int) -> Dictionary:
	return {"actor_id": actor_id, "x": 10 + actor_id, "y": 20, "command": 7, "command_sequence": (1 << 40) + actor_id,
		"facing_command": 24, "health": 31, "max_health": 47, "alive": true, "sitting": false, "in_combat": true,
		"map": "four_gates", "appearance": {"hair": actor_id}, "equipment_visuals": {0: 64}}

static func _stamped_actor(actor_id: int, pass_id: int) -> Dictionary:
	var actor := _full_actor(actor_id)
	actor[ServerTimePacing.STEP_KEY] = 99
	actor[ServerTimePacing.PLAYOUT_KEY] = 0.25
	actor[ServerTimePacing.PASS_KEY] = pass_id
	actor["after_stamp"] = 1
	return actor

func _per_command(reducer: Object) -> void:
	var bases := {"full": _full_actor(7), "sparse": {"actor_id": 7, "appearance": {"hair": 3}},
		"stamped this pass": _stamped_actor(7, 7), "stamped earlier": _stamped_actor(7, 3)}
	var stamps := {"none": {}, "current remote": _stamp(int(K.RUN_STAMP_CURRENT)),
		"current local": _stamp(int(K.RUN_STAMP_CURRENT)), "clear": _stamp(int(K.RUN_STAMP_CLEAR))}
	var before := failures
	for command: int in range(256):
		for base_name: String in bases:
			for stamp_name: String in stamps:
				var local_id := 7 if stamp_name == "current local" else 1
				if command == 19 and local_id == 7:
					# The local actor's 19 is the GDScript path's (see _fallbacks).
					var table := {7: bases[base_name]}
					var result: Dictionary = reducer.call(&"reduce_run", table, [_commands([[7, 19]])], 7,
						stamps[stamp_name])
					_expect(str(result.status) == "fallback" and int(result.consumed) == 0
						and is_same(table[7], bases[base_name]), "local 19 on a %s record falls back" % base_name)
					continue
				_native_matches(reducer, {7: bases[base_name], 8: _full_actor(8)}, [_commands([[7, command]])],
					local_id, stamps[stamp_name], "command %d, %s record, stamp %s" % [command, base_name, stamp_name])
	_expect(failures == before, "every command byte matches the GDScript reducer in every stamp mode")

func _sparse_order(reducer: Object) -> void:
	# New keys arrive in the order the GDScript loop inserts them: a stamp after
	# the first step, `sitting` after that, and so on.
	var sparse := {"actor_id": 11, "appearance": {"hair": 4}}
	var payloads := [_commands([[11, 20], [11, 13]]), _commands([[11, 18], [11, 31], [11, 3], [11, 14], [11, 19]])]
	var matched := _native_matches(reducer, {11: sparse}, payloads, -1, _stamp(int(K.RUN_STAMP_CURRENT)),
		"sparse record keeps the GDScript key order")
	var record: Dictionary = (matched.actors as Dictionary)[11]
	var keys := record.keys()
	_expect(keys.find(ServerTimePacing.STEP_KEY) < keys.find("sitting") and keys.all(func(key: Variant) -> bool:
		return typeof(key) == TYPE_STRING), "inserted keys are Strings in loop order (%s)" % [keys])
	# Shared nested values: the record is a shallow copy.
	var shared := {"actor_id": 12, "appearance": {"hair": 5}}
	var table := {12: shared, 13: _full_actor(13)}
	var untouched: Dictionary = table[13]
	reducer.call(&"reduce_run", table, [_commands([[12, 22]])], -1, {})
	_expect(not is_same(table[12], shared) and is_same((table[12] as Dictionary).appearance, shared.appearance)
		and is_same(table[13], untouched), "a touched record is a new shallow copy; an untouched one keeps its object")

func _random_runs(reducer: Object) -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = 7041
	var before := failures
	for trial: int in range(300):
		var seed := {}
		for actor_id: int in [3, 4, 5, 65535]:
			seed[actor_id] = _full_actor(actor_id) if rng.randf() < 0.7 else _stamped_actor(actor_id, rng.randi_range(5, 7))
		var payloads: Array = []
		for _packet: int in range(rng.randi_range(1, 8)):
			var rows: Array = []
			for _record: int in range(rng.randi_range(0, 12)):
				var actor_id: int = [3, 4, 5, 65535, 900, 0][rng.randi_range(0, 5)]
				var command := rng.randi_range(0, 255)
				if command == 19 and actor_id == 3:
					command = 18
				rows.append([actor_id, command])
			payloads.append(_commands(rows))
		var mode: int = [int(K.RUN_STAMP_NONE), int(K.RUN_STAMP_CURRENT),
			int(K.RUN_STAMP_CLEAR)][trial % 3]
		_native_matches(reducer, seed, payloads, 3, _stamp(mode, 1000 + trial, 0.05 + trial * 0.001, 6),
			"random run %d" % trial)
	_expect(failures == before, "300 random multi-packet runs match the GDScript loop")
	var empty: Dictionary = reducer.call(&"reduce_run", {1: _full_actor(1)}, [], -1, {})
	_expect(str(empty.status) == "ok" and int(empty.consumed) == 0 and (empty.changed_ids as PackedInt32Array).is_empty(),
		"an empty run is ok and changes nothing")

func _fallbacks(reducer: Object) -> void:
	# The local actor's command 19 stops the run before its packet.
	var seven := _full_actor(7)
	var eight := _full_actor(8)
	var table := {7: seven, 8: eight}
	var result: Dictionary = reducer.call(&"reduce_run", table,
		[_commands([[8, 22]]), _commands([[7, 22], [7, 19], [8, 22]]), _commands([[8, 22]])], 7, {})
	_expect(str(result.status) == "fallback" and str(result.reason) == "local_leave" and int(result.consumed) == 1
		and table[8] == ActorReducer.apply_command(eight, 22) and is_same(table[7], seven)
		and Array(result.changed_ids as PackedInt32Array) == [8],
		"local command 19: the packets before it are applied, its own is left whole (%s)" % [result])
	table = {7: seven, 8: eight}
	result = reducer.call(&"reduce_run", table, [_commands([[7, 19], [8, 22]])], 7, {})
	_expect(str(result.status) == "fallback" and int(result.consumed) == 0 and is_same(table[7], seven)
		and is_same(table[8], eight), "local command 19 in the first packet: nothing is applied")
	table = {8: eight}
	result = reducer.call(&"reduce_run", table, [_commands([[7, 19], [8, 22]])], 7, {})
	_expect(str(result.status) == "ok" and int(result.consumed) == 1, "command 19 of an absent local actor does not fall back")
	table = {7: seven, 8: eight}
	result = reducer.call(&"reduce_run", table, [_commands([[8, 19]])], 7, {})
	_expect(str(result.status) == "ok", "a remote actor's command 19 stays native")
	# A corrupt targeted record is left to the GDScript typed assignment.
	table = {7: seven, 8: "not an actor record"}
	result = reducer.call(&"reduce_run", table, [_commands([[7, 22]]), _commands([[7, 22]]), _commands([[8, 22], [7, 22]])], -1, {})
	_expect(str(result.status) == "fallback" and str(result.reason) == "record_not_dictionary" and int(result.consumed) == 2
		and table[7] == ActorReducer.apply_command(ActorReducer.apply_command(seven, 22), 22)
		and str(table[8]) == "not an actor record", "a corrupt record stops the run before its packet (%s)" % [result])
	for broken: Variant in [PackedByteArray([7, 0]), "not a payload", PackedInt32Array([1, 2, 3])]:
		table = {7: seven}
		result = reducer.call(&"reduce_run", table, [_commands([[7, 22]]), broken, _commands([[7, 22]])], -1, {})
		_expect(str(result.status) == "fallback" and str(result.reason) == "invalid_payload" and int(result.consumed) == 1
			and table[7] == ActorReducer.apply_command(seven, 22), "a malformed payload (%s) stops the run before it" % [broken])

func _malformed_stamps(reducer: Object) -> void:
	var stamped := _stamped_actor(7, 7)
	var broken := [{"mode": 5}, {"mode": int(K.RUN_STAMP_CURRENT)}, {"mode": int(K.RUN_STAMP_CLEAR)},
		{"mode": int(K.RUN_STAMP_CURRENT), "step_key": "a", "playout_key": "b", "pass_key": "c"},
		{"mode": int(K.RUN_STAMP_CURRENT), "step_key": &"a", "playout_key": "b", "pass_key": "c",
			"local_msec": 1, "playout_seconds": 0.1, "pass_id": 1},
		{"mode": int(K.RUN_STAMP_CURRENT), "step_key": "a", "playout_key": "b", "pass_key": "c",
			"local_msec": 1.5, "playout_seconds": 0.1, "pass_id": 1},
		{"mode": int(K.RUN_STAMP_CLEAR), "step_key": "", "playout_key": "b", "pass_key": "c"}]
	for stamp: Dictionary in broken:
		var table := {7: stamped}
		var result: Dictionary = reducer.call(&"reduce_run", table, [_commands([[7, 22]])], -1, stamp)
		_expect(str(result.status) == "invalid" and int(result.consumed) == 0 and is_same(table[7], stamped),
			"a malformed stamp %s writes nothing (%s)" % [stamp, result.get("status")])
	var table := {7: stamped}
	reducer.call(&"reduce_run", table, [_commands([[7, 22]])], -1, {})
	_expect(var_to_bytes(table[7]) == var_to_bytes(ActorReducer.apply_command(stamped, 22)),
		"without a stamp mode the step stamp is left alone")

# --- AppState run mode against the GDScript loop ----------------------------

static func _seed_actors(count: int) -> Dictionary:
	var actors := {}
	for index: int in range(count):
		var actor_id := 100 + index
		actors[actor_id] = {"type": "actor_spawn", "actor_id": actor_id, "x": 200 + index % 20, "y": 300 + index / 20,
			"rotation": 0, "map_handle": 0, "actor_type": 1, "scale": 1.0, "boss_rank": 0, "frame": 0,
			"max_health": 60, "health": 60, "kind": 1 if index % 3 else 2, "name": "Bot %d" % index,
			"alive": true, "map": "four_gates", "appearance": {"hair": index % 7}, "equipment_visuals": {0: 64}}
	return actors

func _pair(seed: Dictionary, local_index: int) -> Dictionary:
	var seq: Node = _app_script.new()
	var run: Node = _app_script.new()
	seq.call("select_actor_reducer", "gdscript")
	var chosen: Dictionary = run.call("select_actor_reducer", "run")
	_expect(str(chosen.mode) == "run" and str(run.get("actor_reducer_mode")) == "run",
		"AppState selects the run reducer (%s)" % [chosen])
	var ids := seed.keys()
	var local_id: int = int(ids[local_index]) if local_index >= 0 and local_index < ids.size() else -1
	for state: Node in [seq, run]:
		state.set("actors", seed.duplicate(true))
		state.set("local_actor_id", local_id)
		state.call("take_changed_actors")
	var pair := {"seq": seq, "run": run, "seq_watch": Watch.new(seq), "run_watch": Watch.new(run), "local": local_id}
	_pairs.append(pair)
	return pair

static func _protocol_errors(state: Node) -> Array:
	var out: Array = []
	for raw: Variant in state.get("recent_protocol_errors"):
		var entry := (raw as Dictionary).duplicate()
		entry.erase("msec")
		out.append(entry)
	return out

func _first_difference(left: Dictionary, right: Dictionary) -> String:
	if left.keys() != right.keys():
		return " (ids %s vs %s)" % [left.keys(), right.keys()]
	for key: Variant in left:
		if var_to_bytes(left[key]) != var_to_bytes(right[key]):
			return " (actor %s: %s vs %s)" % [key, left[key], right[key]]
	return ""

func _compare(pair: Dictionary, where: String) -> bool:
	var seq: Node = pair.seq
	var run: Node = pair.run
	var problems: Array[String] = []
	var seq_actors: Dictionary = seq.get("actors")
	var run_actors: Dictionary = run.get("actors")
	if var_to_bytes(seq_actors) != var_to_bytes(run_actors):
		problems.append("actors" + _first_difference(seq_actors, run_actors))
	if var_to_bytes(seq.get("changed_actors")) != var_to_bytes(run.get("changed_actors")):
		problems.append("changed %s vs %s" % [(seq.get("changed_actors") as Dictionary).keys(),
			(run.get("changed_actors") as Dictionary).keys()])
	if var_to_bytes(seq.get("combat_state")) != var_to_bytes(run.get("combat_state")):
		problems.append("combat_state")
	if _protocol_errors(seq) != _protocol_errors(run):
		problems.append("protocol errors %s vs %s" % [_protocol_errors(seq), _protocol_errors(run)])
	if int(seq.get("local_actor_id")) != int(run.get("local_actor_id")):
		problems.append("local actor")
	var seq_watch: Watch = pair.seq_watch
	var run_watch: Watch = pair.run_watch
	if seq_watch.collapsed() != run_watch.collapsed():
		problems.append("signals %s vs %s" % [seq_watch.collapsed(), run_watch.collapsed()])
	if seq_watch.combat_tables != run_watch.combat_tables:
		problems.append("combat listeners saw different tables")
	var facets: Dictionary = run.get("changed_facets")
	var changed: Dictionary = run.get("changed_actors")
	for actor_id: Variant in facets:
		var mask := int(facets[actor_id])
		if not changed.has(actor_id) or (mask & int(K.FACET_COMMAND)) == 0 or (mask & ~63) != 0:
			problems.append("facet entry %s=%d" % [actor_id, mask])
			break
	checks += 1
	if not problems.is_empty():
		_fail("%s: %s" % [where, problems])
		return false
	seq_watch.clear()
	run_watch.clear()
	return true

func _normalise_stamp(pair: Dictionary, current: bool, local_msec: int) -> void:
	# Both observed the same server-time packet at slightly different ticks.
	# Give both the same clock and stamp, so the comparison is about the reducer.
	var now := Time.get_ticks_msec()
	for state: Node in [pair.seq, pair.run]:
		state.set("server_clock", ServerClockScript.new())
		state.set("_frame_stamps_seen", true)
		state.set("_frame_step_local_msec", local_msec)
		state.set("_frame_stamp_read_msec", now + 3600000 if current else now - 3600000)

## Events: ["packet", command, payload(, current server time)], ["drain"],
## ["take"], ["switch", mode], ["flush"], ["disconnect"].
func _drive(pair: Dictionary, events: Array, label: String) -> void:
	var seq: Node = pair.seq
	var run: Node = pair.run
	var before := failures
	var step := 0
	for event: Array in events:
		step += 1
		match str(event[0]):
			"packet":
				var command: int = event[1]
				var payload: PackedByteArray = event[2]
				seq.call("_on_packet", command, payload)
				run.call("_on_packet", command, payload)
				if command == SERVER_TIME and payload.size() >= 4:
					_normalise_stamp(pair, bool(event[3]) if event.size() > 3 else true, payload.decode_u32(0))
				if command != CMD:
					_compare(pair, "%s, event %d (after packet %d)" % [label, step, command])
			"drain":
				_network().dispatch_drained.emit()
				_compare(pair, "%s, event %d (dispatch drained)" % [label, step])
			"flush":
				run.call("flush_actor_commands")
				_compare(pair, "%s, event %d (flush point)" % [label, step])
			"take":
				var taken_seq: Dictionary = seq.call("take_changed_actors")
				var taken_run: Dictionary = run.call("take_changed_actors")
				if not _expect(var_to_bytes(taken_seq) == var_to_bytes(taken_run),
						"%s, event %d: take_changed_actors hands over the same set (%s vs %s)" % [label, step,
							taken_seq.keys(), taken_run.keys()]):
					break
				_compare(pair, "%s, event %d (presentation pass)" % [label, step])
			"switch":
				var switched: Dictionary = run.call("select_actor_reducer", str(event[1]))
				_expect(str(switched.mode) == str(event[1]), "%s: switched to %s (%s)" % [label, event[1], switched])
				_compare(pair, "%s, event %d (switch to %s)" % [label, step, event[1]])
			"disconnect":
				seq.call("_on_connection_state_changed", "disconnected")
				run.call("_on_connection_state_changed", "disconnected")
				_compare(pair, "%s, event %d (disconnected)" % [label, step])
		if failures > before + 3:
			break
	_network().dispatch_drained.emit()
	_compare(pair, label + ", end")
	var stats: Dictionary = run.call("actor_reducer_stats")
	_expect(failures == before, "%s: run mode equals the GDScript loop at every flush point (%s)" % [label, stats])
	print("%s: %d events, run stats %s" % [label, events.size(), stats])

static func _spawn(actor_id: int, x: int, y: int, name: String) -> PackedByteArray:
	var payload := PackedByteArray()
	payload.resize(17)
	payload.encode_u16(0, actor_id)
	payload.encode_u16(2, x)
	payload.encode_u16(4, y)
	payload.encode_u16(6, 0)
	payload.encode_s16(8, 0)
	payload[10] = 2
	payload[11] = 0
	payload.encode_u16(12, 60)
	payload.encode_u16(14, 60)
	payload[16] = 2
	payload.append_array(name.to_ascii_buffer())
	payload.append(0)
	return payload

static func _u16s(values: Array) -> PackedByteArray:
	var payload := PackedByteArray()
	for value: int in values:
		payload.append(value & 0xff)
		payload.append((value >> 8) & 0xff)
	return payload

static func _u32(value: int) -> PackedByteArray:
	var payload := PackedByteArray()
	payload.resize(4)
	payload.encode_u32(0, value)
	return payload

func _packet(command: int, payload: PackedByteArray, current := true) -> Array:
	return ["packet", command, payload, current]

func _cmd(rows: Array) -> Array:
	return _packet(CMD, _commands(rows))

func _scenarios() -> void:
	var server := EloriaProtocol.ServerMessage
	# Turn, then swing, then step, folded into one run; death, sit, stand and
	# the combat flags.
	var pair := _pair(_seed_actors(6), 0)
	var local: int = pair.local
	_drive(pair, [_cmd([[101, 40]]), _cmd([[101, 46], [102, 13]]), _cmd([[101, 22], [102, 14], [103, 18]]),
		_cmd([[103, 19], [104, 3], [104, 22], [105, 255]]), ["drain"], ["take"],
		_cmd([[local, 22], [local, 40]]), _cmd([[999, 22], [local, 18]]), ["drain"], ["take"]], "turn, swing, step")
	# The local actor's command 19, mid-run, first and alone: its combat signal
	# sees the actors as the GDScript loop left them at that record.
	pair = _pair(_seed_actors(4), 0)
	local = pair.local
	_drive(pair, [_cmd([[101, 22], [local, 18]]), _cmd([[local, 22], [local, 19], [101, 22]]), _cmd([[102, 22]]),
		["drain"], ["take"], _cmd([[local, 19]]), _cmd([[101, 23]]), ["drain"],
		_cmd([[101, 24]]), _cmd([[101, 25], [local, 19]]), ["drain"], ["take"]], "local command 19")
	# Malformed, empty and unknown-id packets inside a run.
	pair = _pair(_seed_actors(3), 0)
	_drive(pair, [_cmd([[101, 22]]), _packet(CMD, PackedByteArray([101, 0])), _cmd([[101, 23]]),
		_packet(CMD, PackedByteArray()), _cmd([[4000, 22]]), ["drain"], ["take"]], "malformed and empty packets")
	# A reused id: removed, commanded while absent, spawned again, commanded.
	pair = _pair(_seed_actors(3), 0)
	_drive(pair, [_cmd([[102, 22]]), _packet(server.REMOVE_ACTOR, _u16s([102])), _cmd([[102, 22], [101, 22]]),
		_packet(server.ADD_NEW_ACTOR, _spawn(102, 50, 60, "Again")), _cmd([[102, 30], [102, 22]]),
		_packet(server.GET_ACTOR_DAMAGE, _u16s([101, 5])), _cmd([[101, 3]]), _packet(server.NEW_MINUTE, _u16s([12])),
		_cmd([[101, 22]]), ["drain"], ["take"]], "reused ids and other packets")
	# Server time: current stamps remote steps once per pass (the local actor's
	# come off), a stale one takes them off, a new pass stamps again.
	pair = _pair(_seed_actors(5), 0)
	local = pair.local
	_drive(pair, [_packet(SERVER_TIME, _u32(5000)), _cmd([[101, 22], [local, 22], [102, 40]]),
		_cmd([[101, 23], [103, 30]]), ["drain"], ["take"], _cmd([[101, 24], [104, 22]]), ["drain"],
		_packet(SERVER_TIME, _u32(5100), false), _cmd([[101, 25], [103, 31], [104, 46]]), ["drain"], ["take"],
		_packet(SERVER_TIME, _u32(5200)), _cmd([[103, 32]]), _cmd([[local, 30], [101, 26]]), ["drain"], ["take"]],
		"server-time stamps")
	# The record limit flushes inside the dispatch; a take flushes a pending
	# run; a reducer switch flushes and the GDScript loop takes over.
	pair = _pair(_seed_actors(30), 0)
	var big: Array = []
	for index: int in range(30):
		var rows: Array = []
		for slot: int in range(24):
			rows.append([100 + (index + slot) % 30, 20 + slot % 8])
		big.append(_cmd(rows))
	big.append(["drain"])
	big.append(["take"])
	_drive(pair, big, "record limit")
	var run_stats: Dictionary = (pair.run as Node).call("actor_reducer_stats")
	_expect(int(run_stats.flushes) >= 2 and int(run_stats.largest_run) * 24 >= 512,
		"a 720-record dispatch is flushed at the record limit before the drain (%s)" % [run_stats])
	pair = _pair(_seed_actors(4), 0)
	var run: Node = pair.run
	run.call("_on_packet", CMD, _commands([[101, 22]]))
	(pair.seq as Node).call("_on_packet", CMD, _commands([[101, 22]]))
	_expect((run.get("actors") as Dictionary)[101] == (_seed_actors(4) as Dictionary)[101],
		"a run is pending until a flush point")
	_drive(pair, [["take"], _cmd([[101, 23]]), ["switch", "gdscript"], _cmd([[101, 24], [102, 13]]),
		["switch", "run"], _cmd([[102, 14]]), ["drain"], ["take"]], "take and switch flushes")
	# A dropped connection: the run is reduced before the table is cleared.
	pair = _pair(_seed_actors(4), 0)
	(pair.seq_watch as Watch).snapshot_actors = true
	(pair.run_watch as Watch).snapshot_actors = true
	(pair.seq as Node).call("_on_packet", CMD, _commands([[101, 22]]))
	(pair.run as Node).call("_on_packet", CMD, _commands([[101, 22]]))
	(pair.seq as Node).call("_on_packet", CMD, _commands([[102, 22]]))
	(pair.run as Node).call("_on_packet", CMD, _commands([[102, 22]]))
	var seq_tables: Array[PackedByteArray] = (pair.seq_watch as Watch).actor_tables.duplicate()
	(pair.seq as Node).call("_on_connection_state_changed", "disconnected")
	(pair.run as Node).call("_on_connection_state_changed", "disconnected")
	var run_tables: Array[PackedByteArray] = (pair.run_watch as Watch).actor_tables
	_expect(run_tables.size() == 1 and seq_tables.size() == 2 and run_tables[0] == seq_tables[1]
		and ((pair.run as Node).get("actors") as Dictionary).is_empty(),
		"a disconnect reduces the pending run first, then clears the table")
	_compare(pair, "disconnect")
	# Facets: which kinds of command touched each actor, until another writer
	# marks it (all facets).
	pair = _pair(_seed_actors(4), 0)
	run = pair.run
	local = pair.local
	run.call("_on_packet", CMD, _commands([[101, 22], [102, 38]]))
	run.call("_on_packet", CMD, _commands([[101, 13], [103, 3], [9999, 22]]))
	_network().dispatch_drained.emit()
	var expected := {101: int(K.FACET_MOVE) | int(K.FACET_COMMAND) | int(K.FACET_FACING)
		| int(K.FACET_SIT), 102: int(K.FACET_COMMAND) | int(K.FACET_FACING),
		103: int(K.FACET_COMMAND) | int(K.FACET_LIFE)}
	_expect(run.get("changed_facets") == expected, "facets per actor (%s)" % [run.get("changed_facets")])
	run.call("_on_packet", server.GET_ACTOR_DAMAGE, _u16s([102, 5]))
	run.call("_on_packet", CMD, _commands([[local, 19], [101, 22]]))
	run.call("_on_packet", CMD, _commands([[103, 22]]))
	_network().dispatch_drained.emit()
	_expect(run.get("changed_facets") == {103: int(K.FACET_MOVE) | int(K.FACET_COMMAND)
		| int(K.FACET_FACING) | int(K.FACET_LIFE)},
		"another writer (damage, the GDScript path for local 19) marks all facets (%s)" % [run.get("changed_facets")])
	var taken: Dictionary = run.call("take_changed_actors")
	_expect(taken.keys() == [101, 102, 103, local] and run.get("taken_changed_facets") == {103: 39}
		and (run.get("changed_facets") as Dictionary).is_empty(),
		"take_changed_actors hands the facets over with the set (%s, %s)" % [taken.keys(), run.get("taken_changed_facets")])

func _deferred_flush() -> void:
	# A caller that feeds `_on_packet` itself (a replay) gets the run reduced by
	# the end of the frame without a drain or a take.
	var pair := _pair(_seed_actors(3), 0)
	(pair.seq as Node).call("_on_packet", CMD, _commands([[101, 22], [102, 40]]))
	(pair.run as Node).call("_on_packet", CMD, _commands([[101, 22], [102, 40]]))
	await process_frame
	_expect(int(((pair.run as Node).call("actor_reducer_stats") as Dictionary).pending_packets) == 0,
		"the deferred flush reduced the run by the end of the frame")
	_compare(pair, "deferred end-of-frame flush")

func _fail_closed() -> void:
	var pair := _pair(_seed_actors(3), 0)
	var run: Node = pair.run
	run.set("_native_crowd_reducer", BrokenReducer.new())
	_drive(pair, [_cmd([[101, 22]]), _cmd([[102, 40]]), ["drain"], _cmd([[101, 23]]), ["drain"], ["take"]],
		"fail closed")
	var stats: Dictionary = run.call("actor_reducer_stats")
	_expect(str(stats.mode) == "gdscript" and int(stats.native_failures) == 1 and str(stats.last_failure).begins_with("boom")
		and not bool(run.call("native_crowd_reducer_active"))
		and not _network().dispatch_drained.is_connected(Callable(run, &"flush_actor_commands")),
		"a broken native result fails closed to the GDScript reducer for the session (%s)" % [stats])

# --- random streams and recordings ------------------------------------------

func _stream(seed: int, frames: int, actor_count: int, options: Dictionary) -> Array:
	var server := EloriaProtocol.ServerMessage
	var rng := RandomNumberGenerator.new()
	rng.seed = seed
	var ids: Array[int] = []
	for index: int in range(actor_count):
		ids.append(100 + index)
	var local: int = ids[1]
	var removed: Array[int] = []
	var events: Array = []
	var dense := bool(options.get("dense", false))
	for frame: int in range(frames):
		var packets := rng.randi_range(1, 6)
		if rng.randf() < 0.04:
			packets = 30
		for _packet_index: int in range(packets):
			if rng.randf() < 0.12:
				var roll := rng.randf()
				if roll < 0.2:
					events.append(_packet(server.NEW_MINUTE, _u16s([frame % 360])))
				elif roll < 0.4:
					events.append(_packet(server.GET_ACTOR_DAMAGE, _u16s([ids[rng.randi_range(0, ids.size() - 1)],
						rng.randi_range(0, 9)])))
				elif roll < 0.55 and ids.size() > 4:
					var gone: int = ids.pop_at(rng.randi_range(2, ids.size() - 1))
					removed.append(gone)
					events.append(_packet(server.REMOVE_ACTOR, _u16s([gone])))
				elif roll < 0.7 and not removed.is_empty():
					var back: int = removed.pop_at(rng.randi_range(0, removed.size() - 1))
					ids.append(back)
					events.append(_packet(server.ADD_NEW_ACTOR, _spawn(back, rng.randi_range(0, 500),
						rng.randi_range(0, 500), "Back %d" % back)))
				elif roll < 0.85:
					events.append(_packet(SERVER_TIME, _u32(10000 + frame * 50), rng.randf() < 0.8))
				elif roll < 0.92:
					events.append(_packet(CMD, PackedByteArray([1, 2, 3, 4])))
				else:
					events.append(_packet(CMD, PackedByteArray()))
			var rows: Array = []
			for _record: int in range(rng.randi_range(1, 40 if dense else 24)):
				var pick := rng.randf()
				var actor_id: int
				if pick < 0.8:
					actor_id = ids[rng.randi_range(0, ids.size() - 1)]
				elif pick < 0.88:
					actor_id = local
				elif pick < 0.94 and not removed.is_empty():
					actor_id = removed[rng.randi_range(0, removed.size() - 1)]
				else:
					actor_id = 4000 + rng.randi_range(0, 50)
				var command := _random_command(rng)
				if actor_id == local and command == 19 and rng.randf() < 0.7:
					command = 18
				rows.append([actor_id, command])
			events.append(_cmd(rows))
		events.append(["drain"])
		if rng.randf() < 0.85:
			events.append(["take"])
		if rng.randf() < 0.01:
			events.append(["switch", "gdscript"])
		elif rng.randf() < 0.03:
			events.append(["switch", "run"])
	events.append(["switch", "run"])
	return events

static func _random_command(rng: RandomNumberGenerator) -> int:
	var roll := rng.randf()
	if roll < 0.45:
		return rng.randi_range(20, 27) if rng.randf() < 0.6 else rng.randi_range(30, 37)
	if roll < 0.6:
		return rng.randi_range(38, 45)
	if roll < 0.75:
		return rng.randi_range(46, 60)
	if roll < 0.95:
		return [13, 14, 18, 19, 3, 0, 7][rng.randi_range(0, 6)]
	return rng.randi_range(0, 255)

## The packets of `events` as an RLREC1 session recording (one server-to-client
## frame per record, a frame's gap between dispatch passes).
func _write_recording(events: Array, path: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(RLREC_MAGIC.to_ascii_buffer())
	file.store_buffer((JSON.stringify({"version": 1, "synthetic": "test_native_crowd_run_parity"}) + "\n").to_utf8_buffer())
	var nsec := 1000000000
	for event: Array in events:
		if str(event[0]) == "drain":
			nsec += 16666667
			continue
		if str(event[0]) != "packet":
			continue
		var payload: PackedByteArray = event[2]
		var frame := PackedByteArray([int(event[1])])
		frame.append_array(_u16s([payload.size() + 1]))
		frame.append_array(payload)
		var header := PackedByteArray()
		header.resize(RLREC_RECORD_HEADER)
		header[0] = "O".unicode_at(0)
		header.encode_u64(1, nsec)
		header.encode_u32(9, frame.size())
		file.store_buffer(header)
		file.store_buffer(frame)
		nsec += 100000
	file.close()

## Events from an RLREC1 recording: its actor packets in order, a dispatch
## drain and a presentation pass wherever the recording pauses 8 ms or more,
## and a flush point for every other packet (they are not fed).
func _recording_events(path: String, limit: int) -> Array:
	var server := EloriaProtocol.ServerMessage
	var fed := [server.ADD_NEW_ACTOR, server.ADD_NEW_ENHANCED_ACTOR, server.ADD_NEW_ACTOR_EXTENDED, CMD,
		server.YOU_ARE, server.REMOVE_ACTOR, server.KILL_ALL_ACTORS, server.NEW_MINUTE, server.GET_ACTOR_DAMAGE,
		server.GET_ACTOR_HEAL, SERVER_TIME]
	var events: Array = []
	var file := FileAccess.open(path, FileAccess.READ)
	if not _expect(file != null, "recording %s opens" % path):
		return events
	var magic := file.get_buffer(RLREC_MAGIC.length())
	if not _expect(magic == RLREC_MAGIC.to_ascii_buffer(), "%s is an RLREC1 recording" % path):
		return events
	file.get_line()
	var last_nsec := -1
	var pending := false
	while file.get_position() + RLREC_RECORD_HEADER <= file.get_length() and events.size() < limit:
		var header := file.get_buffer(RLREC_RECORD_HEADER)
		var kind := header[0]
		var nsec := header.decode_u64(1)
		var length := header.decode_u32(9)
		if file.get_position() + length > file.get_length() or kind == "T".unicode_at(0):
			break
		var frame := file.get_buffer(length)
		if (kind != "O".unicode_at(0) and kind != "o".unicode_at(0)) or length < 3:
			continue
		if pending and last_nsec >= 0 and nsec - last_nsec >= 8000000:
			events.append(["drain"])
			events.append(["take"])
			pending = false
		last_nsec = nsec
		var command: int = frame[0]
		if command in fed:
			events.append(["packet", command, frame.slice(3), true])
			pending = true
		else:
			events.append(["flush"])
	file.close()
	events.append(["drain"])
	events.append(["take"])
	return events

func _recording_self_test(events: Array) -> void:
	var path := OS.get_user_data_dir().path_join("rb-c7-run-parity.rlrec")
	_write_recording(events, path)
	var replayed := _recording_events(path, 1 << 30)
	var packets := events.filter(func(event: Array) -> bool: return str(event[0]) == "packet").size()
	_expect(replayed.filter(func(event: Array) -> bool: return str(event[0]) == "packet").size() == packets,
		"the RLREC1 writer and reader agree on %d packets" % packets)
	_drive(_pair(_seed_actors(160), 1), replayed, "RLREC1 replay of the random market")
	DirAccess.remove_absolute(path)

func _replay_recording(path: String) -> void:
	var limit := int(_argument("--recording-limit=")) if not _argument("--recording-limit=").is_empty() else 200000
	var events := _recording_events(path, limit)
	_expect(not events.is_empty(), "recording %s has packets" % path)
	_drive(_pair({}, -1), events, "recording " + path.get_file())
