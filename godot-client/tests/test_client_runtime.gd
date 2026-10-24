extends SceneTree

const Controller := preload("res://src/runtime/client_runtime.gd")
var failures := 0
var _old_mode := ""

class MalformedRuntime extends RefCounted:
	var fault := "short"
	func runtime_info() -> Dictionary:
		return {"ready": true, "abi": 1}
	func get_last_status() -> Variant:
		return "invalid-status" if fault == "status-type" else (1 if fault == "status" else 0)
	func plan_batch(records: PackedInt64Array, epoch: int, tick: int) -> Variant:
		if fault == "type":
			return ["not-a-packed-integer-result"]
		var output := PackedInt64Array()
		for index: int in records.size() / 5:
			var tier: int = records[index * 5 + 3]
			var phase: int = records[index * 5 + 4]
			var stride := 2 if tier == 1 else 4
			output.append_array(PackedInt64Array([records[index * 5], records[index * 5 + 1], epoch,
				1 if (tick + phase) % stride == 0 else 0]))
		if output.size() > 0:
			match fault:
				"short": output.resize(output.size() - 1)
				"id": output[0] += 1
				"generation": output[1] += 1
				"epoch": output[2] += 1
				"due": output[3] = 2
		return output

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> bool:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)
	return ok

func _write(path: String, text: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file != null:
		file.store_string(text)
		file.close()
	else:
		_expect(false, "test fixture file is writable")

func _preflight() -> void:
	var directory := "user://client-runtime-preflight-%d" % OS.get_process_id()
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory))
	var controller := Controller.new()
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", "compare")
	controller.initialize(directory.path_join("absent"))
	_expect(controller.snapshot().reason == "optional_runtime_absent" and not controller.snapshot().native_available,
		"missing optional runtime falls back before extension loading")
	var path := directory.path_join("runtime-manifest.json")
	_write(path, "{ invalid manifest")
	controller.initialize(directory)
	_expect(controller.snapshot().reason == "manifest_invalid", "malformed optional manifest falls back without engine errors")
	var version := Engine.get_version_info()
	var platform: String = {"Windows": "windows", "Linux": "linux", "macOS": "macos"}.get(OS.get_name(), "unsupported")
	var library: String = {"windows": "client_runtime.dll", "linux": "client_runtime.so", "macos": "client_runtime.dylib"}.get(platform, "unsupported")
	var manifest := {"abi": 99, "engine_major": version.major, "engine_minor": version.minor,
		"platform": platform, "architecture": "x86_64", "library": library}
	_write(path, JSON.stringify(manifest))
	controller.initialize(directory)
	_expect(controller.snapshot().reason == "api_mismatch", "ABI mismatch is rejected before loading")
	manifest.abi = 1
	manifest.engine_minor = int(version.minor) + 1
	_write(path, JSON.stringify(manifest))
	controller.initialize(directory)
	_expect(controller.snapshot().reason == "api_mismatch", "engine API mismatch is rejected before loading")
	manifest.engine_minor = version.minor
	manifest.platform = "unsupported-fixture-platform"
	_write(path, JSON.stringify(manifest))
	controller.initialize(directory)
	_expect(controller.snapshot().reason == "unsupported_platform", "platform mismatch is rejected before loading")
	manifest.platform = platform
	manifest.architecture = "unsupported-fixture-architecture"
	_write(path, JSON.stringify(manifest))
	controller.initialize(directory)
	_expect(controller.snapshot().reason == "unsupported_platform", "architecture mismatch is rejected before loading")
	manifest.architecture = "x86_64"
	_write(path, JSON.stringify(manifest))
	controller.initialize(directory)
	_expect(controller.snapshot().reason == "optional_runtime_incomplete", "incomplete optional payload stays on legacy")
	_write(directory.path_join(library), "deliberately-not-a-native-library")
	_write(directory.path_join("client_runtime.gdextension"), "deliberately-not-a-descriptor")
	manifest.library_sha256 = "incorrect"
	manifest.descriptor_sha256 = "incorrect"
	_write(path, JSON.stringify(manifest))
	controller.initialize(directory)
	_expect(controller.snapshot().reason == "runtime_checksum_mismatch" and controller.native_runtime() == null,
		"wrong checksums reject fake native files before the loader can report engine errors")
	controller.close()
	for name: String in [library, "client_runtime.gdextension", "runtime-manifest.json"]:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(directory.path_join(name)))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(directory))
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", "legacy")
	controller.initialize()
	_expect(controller.snapshot().mode == "legacy" and controller.snapshot().reason == "legacy_selected", "explicit legacy requires no native payload")
	controller.close()
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", "unsupported-mode")
	controller.initialize()
	_expect(controller.snapshot().reason == "unsupported_mode", "unknown modes retain legacy presentation")
	controller.close()

func _gate_state(gate: AnimationGate, players: Array[AnimationPlayer]) -> Dictionary:
	var groups: Array = []
	for group: Dictionary in gate._groups:
		var ids: Array[int] = []
		for player: AnimationPlayer in group.members:
			ids.append(player.get_instance_id())
		groups.append([group.tier, group.phase, group.stride, group.delta, ids])
	var states: Array = []
	for player: AnimationPlayer in players:
		states.append([player.active, player.callback_mode_process])
	return {"tick": gate._tick, "groups": groups, "players": states}

func _groups() -> Dictionary:
	var gate := AnimationGate.new()
	var players: Array[AnimationPlayer] = []
	for tier: int in [AnimationGate.Tier.FULL, AnimationGate.Tier.PAUSED,
		AnimationGate.Tier.HALF, AnimationGate.Tier.HALF,
		AnimationGate.Tier.QUARTER, AnimationGate.Tier.QUARTER,
		AnimationGate.Tier.QUARTER, AnimationGate.Tier.QUARTER]:
		var player := AnimationPlayer.new()
		players.append(player)
		gate.apply(player, tier)
	return {"gate": gate, "players": players}

func _bad_outputs() -> void:
	for fault: String in ["short", "id", "generation", "epoch", "due", "status", "type", "status-type"]:
		var fixture := _groups()
		var gate := fixture.gate as AnimationGate
		var players: Array[AnimationPlayer] = fixture.players
		gate.advance(0.016)
		var before := _gate_state(gate, players)
		var native := MalformedRuntime.new()
		native.fault = fault
		var controller := Controller.new()
		controller._native = native
		controller._mode = "compare"
		controller._frames = Controller.COMPARE_INTERVAL - 1
		controller.observe_gate(gate)
		var snapshot := controller.snapshot()
		_expect(snapshot.mode == "legacy" and snapshot.reason == "comparison_mismatch"
			and snapshot.mismatches == 1 and not snapshot.native_available,
			"malformed %s output fails the complete comparison closed" % fault)
		_expect(_gate_state(gate, players) == before and snapshot.presentation_backend == "legacy",
			"malformed %s output leaves legacy groups, clocks and players untouched" % fault)
		controller.close()
		gate.reset(false)
		for player: AnimationPlayer in players:
			player.free()

func _rests() -> PackedFloat64Array:
	return PackedFloat64Array([1,0,0, 0,1,0, 0,0,1, 0,0,0, 1,0,0, 0,1,0, 0,0,1, 0,0,0])

func _poses() -> PackedFloat64Array:
	return PackedFloat64Array([0,0,0, 0,0,0,1, 1,1,1, 0,0,0, 0,0,0,1, 1,1,1])

func _native_contract(native: RefCounted) -> void:
	var info: Dictionary = native.call("runtime_info")
	_expect(info.abi == 1 and info.language == "rust" and info.ready and info.precision == "f64", "actual adapter reports the Rust core and ABI")
	var records := PackedInt64Array()
	var tiers: Array[int] = []
	var phases: Array[int] = []
	for tier: int in [0, 1, 2, 3]:
		var stride := 2 if tier == 1 else (4 if tier == 3 else 1)
		for phase: int in stride:
			tiers.append(tier)
			phases.append(phase)
			records.append_array(PackedInt64Array([100 + tiers.size(), 7, 0, tier, phase]))
	for tick: int in [0, 1, 2, 3, 4, 17, 9223372036854775807]:
		var output: PackedInt64Array = native.call("plan_batch", records, 1, tick)
		var valid := output.size() == tiers.size() * 4 and int(native.call("get_last_status")) == 0
		for index: int in tiers.size():
			var tier: int = tiers[index]
			var stride := 2 if tier == 1 else 4
			var due := 1 if tier == 0 else (0 if tier == 2 else (1 if (tick % stride + phases[index]) % stride == 0 else 0))
			if output.size() == tiers.size() * 4:
				valid = valid and output[index * 4] == records[index * 5] and output[index * 4 + 1] == 7 \
					and output[index * 4 + 2] == 1 and output[index * 4 + 3] == due
		_expect(valid, "Rust cadence matches every tier/phase at tick%d, including overflow boundary" % tick)
	var parents := PackedInt32Array([-1, 0])
	var rest := _rests()
	var pose := _poses()
	var original_rest := rest.duplicate()
	var handle: int = native.call("register_rig", parents, rest, pose)
	_expect(handle > 0 and rest == original_rest, "valid identity rig registers without changing caller buffers")
	parents.clear()
	rest.clear()
	pose.clear()
	var rig_record := PackedInt64Array([50, 8, handle, 0, 0])
	_expect((native.call("plan_batch", rig_record, 1, 0) as PackedInt64Array).size() == 4,
		"registered rig handle survives caller buffer release")
	_expect(int(native.call("register_rig", PackedInt32Array([1, 0]), _rests(), _poses())) == 0,
		"cyclic hierarchy is rejected")
	var invalid_pose := _poses()
	invalid_pose[3] = NAN
	_expect(int(native.call("register_rig", PackedInt32Array([-1, 0]), _rests(), invalid_pose)) == 0,
		"nonfinite rig input is rejected")
	for bad: PackedInt64Array in [PackedInt64Array([1,1,0,0]), PackedInt64Array([1,1,-1,0,0]),
		PackedInt64Array([1,1,0,0,0, 2,0,0,1,0]), PackedInt64Array([1,1,0,0,0, 2,1,0,3,4])]:
		var calls_before: int = int((native.call("runtime_info") as Dictionary).plan_calls)
		var rejected: PackedInt64Array = native.call("plan_batch", bad, 1, 0)
		_expect(rejected.is_empty() and int(native.call("get_last_status")) == 1
			and int((native.call("runtime_info") as Dictionary).plan_calls) == calls_before,
			"invalid complete batch returns no partial result or successful publication")
	_expect(int(native.call("reset_epoch", 2)) == 0 and int(native.call("reset_epoch", 2)) == 2,
		"session reset is monotonic and rejects stale reset")
	_expect((native.call("plan_batch", rig_record, 1, 0) as PackedInt64Array).is_empty()
		and int(native.call("get_last_status")) == 2, "old epoch is rejected")
	_expect((native.call("plan_batch", rig_record, 2, 0) as PackedInt64Array).is_empty()
		and int(native.call("get_last_status")) == 2, "reset invalidates old rig handles")
	var fresh: int = native.call("register_rig", PackedInt32Array([-1, 0]), _rests(), _poses())
	_expect(fresh > handle and bool(native.call("unregister_rig", fresh))
		and not bool(native.call("unregister_rig", fresh)), "rig handles are not reused and stale unregister fails")

func _run() -> void:
	_old_mode = OS.get_environment("RABBITLANDS_CLIENT_RUNTIME")
	_preflight()
	_bad_outputs()
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", "compare")
	var controller := Controller.new()
	controller.initialize()
	var snapshot := controller.snapshot()
	var args := OS.get_cmdline_user_args()
	if args.has("--expect-native") or args.has("--expect-native=present"):
		_expect(snapshot.native_available and snapshot.mode == "compare", "requested native-present profile actually loads the verified payload")
	elif args.has("--expect-native=absent"):
		_expect(not snapshot.native_available and snapshot.mode == "legacy", "requested native-absent profile stays playable on legacy")
	if snapshot.native_available:
		var fixture := _groups()
		var gate := fixture.gate as AnimationGate
		var players: Array[AnimationPlayer] = fixture.players
		for index: int in Controller.COMPARE_INTERVAL - 1:
			gate.advance(0.016)
			controller.observe_gate(gate)
		_expect(controller.snapshot().comparisons == 0, "comparison observes only its bounded cadence")
		gate.advance(0.016)
		var before := _gate_state(gate, players)
		controller.observe_gate(gate)
		_expect(controller.snapshot().comparisons == 1 and controller.snapshot().records_checked == 6
			and controller.snapshot().mismatches == 0 and _gate_state(gate, players) == before,
			"actual Rust comparison covers all stepped groups without changing legacy presentation")
		gate.reset(false)
		for player: AnimationPlayer in players:
			player.free()
		_native_contract(controller.native_runtime())
	else:
		print("SKIP: actual Rust API checks; optional native payload is unavailable (", snapshot.reason, ")")
	controller.close()
	_expect(Controller.current() == null, "close removes the weak current controller")
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", _old_mode)
	print("client runtime tests: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
