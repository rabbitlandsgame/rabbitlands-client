extends SceneTree
## RB-C1n (rust-batch C1, native half): the native_crowd kernels and reducer
## compiled into the verified client_runtime payload, with guarded registration
## and no default change.
##
## Loads the payload through the shared loader (src/runtime/native_library.gd)
## and checks:
## - registration: NativeCrowdReducer, NativeCrowdStore,
##   NativeCapeConstraintKernel and NativeWorldEffectGeometry (plus the existing
##   NativeSpellFlightGeometry) are registered RefCounted classes with the
##   methods their GDScript callers use, and
##   `RabbitLandsClientRuntime.runtime_info().native_crowd_providers` names the
##   library that registered each one;
## - no default change: with ELORIA_NATIVE_PRESENTATION unset, 0, off or an
##   unknown value and ELORIA_NATIVE_CROWD unset or 0, cape cloth, spell flight,
##   world effects and AppState stay on GDScript although the classes exist;
## - the existing opt-ins activate the classes from the payload without the
##   benchmark extension (`res://bin/native_crowd.gdextension`); since RB-C1g
##   (src/runtime/native_crowd.gd) classes the benchmark extension registered
##   first are used only with ELORIA_NATIVE_PROVIDER=benchmark;
## - one smoke call per class, and the reducer against ActorReducer for every
##   command byte.
## The complete kernel and reducer parity suites run unchanged against the
## payload through the `test_client_runtime_kernels_*.gd` wrappers, which use
## `load_payload()` and `skip_suite()` below.
##
## Flags (after `--`):
## - `--runtime-dir=<absolute payload directory>`: a payload built outside the
##   project (default: `NativeLibrary.default_directory()`).
## - `--expect-native=present|absent`: an unavailable or unexpected payload is
##   a failure instead of a SKIP, as in test_client_runtime.gd.
## - `--external-crowd=<absolute native_crowd.gdextension>`: also loads the
##   benchmark extension, before the payload (default; every provider must then
##   be `external`) or, with `--external-order=after`, after it (providers stay
##   `client_runtime`). Either order must load without a duplicate class; the
##   runner greps the log for `ERROR:`.

const NativeLibrary := preload("res://src/runtime/native_library.gd")
const NativeCrowd := preload("res://src/runtime/native_crowd.gd")
const Cape := preload("res://src/actors/cape_cloth.gd")
const Flight := preload("res://src/world/spell_flight_3d.gd")
const WorldEffect := preload("res://src/world/world_effect_3d.gd")
const BENCHMARK_EXTENSION := "res://bin/native_crowd.gdextension"
## Class -> {method: argument count} that the GDScript callers rely on.
const KERNELS := {
	&"NativeCrowdReducer": {"reduce_packet": 3},
	&"NativeCrowdStore": {"reset": 1, "reduce_packets": 2, "snapshot_dirty": 1, "remove": 1,
		"clear": 0, "has": 1, "size": 0},
	&"NativeCapeConstraintKernel": {"step": 17},
	&"NativeWorldEffectGeometry": {"build": 11},
	&"NativeSpellFlightGeometry": {"build": 16},
}

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> bool:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)
	return ok

static func _argument(prefix: String) -> String:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with(prefix):
			return argument.trim_prefix(prefix)
	return ""

## The payload directory named by `--runtime-dir=`, or "" for the default.
static func runtime_dir() -> String:
	return _argument("--runtime-dir=")

## Loads the payload for a wrapped suite. Call it from the wrapper's
## `_initialize` override, which runs before the autoloads' `_ready` (AppState
## decides its reducer there).
static func load_payload() -> Dictionary:
	return NativeLibrary.load_verified(runtime_dir())

## The kernel classes not registered right now.
static func missing_kernels() -> Array:
	return KERNELS.keys().filter(func(name: StringName) -> bool: return not ClassDB.class_exists(name))

## `runtime_info().native_crowd_providers`, or {} without the runtime class.
static func providers() -> Dictionary:
	if not ClassDB.class_exists(NativeLibrary.RUNTIME_CLASS):
		return {}
	var runtime: Object = ClassDB.instantiate(NativeLibrary.RUNTIME_CLASS)
	if runtime == null:
		return {}
	return (runtime.call("runtime_info") as Dictionary).get("native_crowd_providers", {})

## For the wrappers: true (after quitting) when the wrapped suite must not run
## because the payload did not load or does not provide every kernel. That is a
## SKIP, or a failure with `--expect-native=present`.
static func skip_suite(tree: SceneTree, loaded: Dictionary, suite: String) -> bool:
	var missing := missing_kernels()
	var from_payload := providers()
	var foreign := KERNELS.keys().filter(func(name: StringName) -> bool:
		return str(from_payload.get(str(name), "")) != "client_runtime")
	if bool(loaded.get("ok", false)) and missing.is_empty() and foreign.is_empty():
		print("%s: running against the client_runtime payload in %s" % [suite, loaded.directory])
		return false
	var reason := "%s: payload %s (%s), missing %s, not from client_runtime %s" % [suite,
		loaded.get("directory", ""), loaded.get("code", ""), missing, foreign]
	if OS.get_cmdline_user_args().has("--expect-native=present"):
		push_error("FAIL: requested native-present run: " + reason)
		tree.quit(1)
	else:
		print("SKIP: " + reason)
		tree.quit(0)
	return true

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var expect_present := args.has("--expect-native=present") or args.has("--expect-native")
	var expect_absent := args.has("--expect-native=absent")
	var external := _argument("--external-crowd=")
	var external_first := not external.is_empty() and _argument("--external-order=") != "after"
	var before := {}
	for name: StringName in KERNELS:
		before[name] = ClassDB.class_exists(name)
	_expect(before.values().count(true) == 0,
		"no kernel class is registered before any native library loads (%s)" % [before])
	if external_first:
		_load_external(external)
	var loaded := NativeLibrary.load_verified(runtime_dir())
	# A payload built before RB-C1n loads but reports no providers.
	var available := bool(loaded.ok) and providers().size() == KERNELS.size()
	if expect_present:
		_expect(available, "requested native-present run loads a payload with the kernels (%s, %s)" % [
			loaded.code, loaded.directory])
	elif expect_absent:
		_expect(not available, "requested native-absent run has no payload with the kernels (%s)" % loaded.code)
	if not available:
		print("SKIP: client_runtime crowd kernels; payload %s (%s), kernel providers %s" % [loaded.directory,
			loaded.code, providers()])
		print("client runtime crowd kernels: ", "PASS" if failures == 0 else "FAIL")
		quit(failures)
		return
	if not external.is_empty() and not external_first:
		_load_external(external)
	_registration(external, external_first)
	_no_default_change()
	_opt_ins(external, external_first)
	_smoke()
	_reducer_parity()
	print("client runtime crowd kernels: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _load_external(path: String) -> void:
	var status := GDExtensionManager.load_extension(path)
	_expect(status == GDExtensionManager.LOAD_STATUS_OK or status == GDExtensionManager.LOAD_STATUS_ALREADY_LOADED,
		"the benchmark extension %s loads (status %d)" % [path, status])

func _registration(external: String, external_first: bool) -> void:
	var expected := "external" if external_first else "client_runtime"
	var found := providers()
	for name: StringName in KERNELS:
		_expect(ClassDB.class_exists(name) and ClassDB.is_parent_class(name, &"RefCounted")
			and ClassDB.can_instantiate(name), "%s is a registered, instantiable RefCounted" % name)
		_expect(str(found.get(str(name), "")) == expected,
			"runtime_info names %s as the provider of %s (got %s)" % [expected, name, found.get(str(name), "")])
		var methods := {}
		for method: Dictionary in ClassDB.class_get_method_list(name, true):
			methods[str(method.name)] = (method.args as Array).size()
		var wanted: Dictionary = KERNELS[name]
		for method: String in wanted:
			_expect(int(methods.get(method, -1)) == int(wanted[method]),
				"%s.%s takes %d arguments (got %d)" % [name, method, wanted[method], methods.get(method, -1)])
	_expect(found.size() == KERNELS.size(), "runtime_info reports exactly the %d kernel providers" % KERNELS.size())
	var runtime: Object = ClassDB.instantiate(NativeLibrary.RUNTIME_CLASS)
	var info: Dictionary = runtime.call("runtime_info") if runtime != null else {}
	_expect(int(info.get("abi", 0)) == 1, "the runtime ABI stays 1")
	_expect(str(info.get("cpp_spell_flight_provider", "")) == str(found.get("NativeSpellFlightGeometry", "?")),
		"the existing flight provider key agrees with native_crowd_providers")
	var loaded_paths := Array(GDExtensionManager.get_loaded_extensions())
	_expect(external.is_empty() == loaded_paths.filter(func(path: String) -> bool:
		return path.get_file() == "native_crowd.gdextension").is_empty(),
		"the benchmark extension is loaded only when the run asked for it (%s)" % [loaded_paths])

func _active(mode: String) -> Array:
	OS.set_environment("ELORIA_NATIVE_PRESENTATION", mode)
	var cape := Cape.new()
	cape.call("_initialize_native_constraint_kernel")
	var flight := Flight.new()
	var world := WorldEffect.new()
	root.add_child(world)
	world.set_process(false)
	world.configure(2, Vector3.ZERO, null, 5)
	var result := [bool(cape.call("native_constraint_kernel_active")), flight.native_presentation_active(),
		bool(world.call("native_presentation_active"))]
	world.free()
	flight.free()
	cape.free()
	return result

func _reducer_active(mode: String) -> bool:
	var state: Node = root.get_node("AppState")
	var original: Variant = state.get("_native_crowd_reducer")
	OS.set_environment("ELORIA_NATIVE_CROWD", mode)
	state.set("_native_crowd_reducer", null)
	state.call("_initialize_native_crowd_reducer")
	var reducer: Variant = state.get("_native_crowd_reducer")
	var active := reducer != null and (reducer as Object).get_class() == "NativeCrowdReducer"
	state.set("_native_crowd_reducer", original)
	return active

func _no_default_change() -> void:
	var presentation := OS.get_environment("ELORIA_NATIVE_PRESENTATION")
	var crowd := OS.get_environment("ELORIA_NATIVE_CROWD")
	for mode: String in ["", "0", "off", "unknown"]:
		_expect(_active(mode) == [false, false, false],
			"ELORIA_NATIVE_PRESENTATION='%s' keeps cape, flight and world effects on GDScript with the classes present" % mode)
	for mode: String in ["", "0"]:
		_expect(not _reducer_active(mode),
			"ELORIA_NATIVE_CROWD='%s' keeps AppState on the GDScript reducer with the class present" % mode)
	var state: Node = root.get_node("AppState")
	if crowd != "1":
		_expect(not bool(state.call("native_crowd_reducer_active")),
			"AppState started without the native reducer (default)")
	OS.set_environment("ELORIA_NATIVE_PRESENTATION", presentation)
	OS.set_environment("ELORIA_NATIVE_CROWD", crowd)

func _opt_ins(external: String, external_first: bool) -> void:
	var presentation := OS.get_environment("ELORIA_NATIVE_PRESENTATION")
	var crowd := OS.get_environment("ELORIA_NATIVE_CROWD")
	var provider := OS.get_environment(NativeCrowd.PROVIDER_ENVIRONMENT)
	if external.is_empty() and FileAccess.file_exists(BENCHMARK_EXTENSION):
		print("NOTE: %s exists; RB-C1g loads it only with ELORIA_NATIVE_PROVIDER=benchmark" % BENCHMARK_EXTENSION)
	var cases := {"cape": [true, false, false], "flight": [false, true, false], "both": [true, true, false],
		"1": [true, true, false], "world": [false, false, true], "all": [true, true, true], " ALL ": [true, true, true]}
	if external_first:
		# RB-C1g: classes another extension registered are refused unless the
		# run names the benchmark provider.
		OS.set_environment(NativeCrowd.PROVIDER_ENVIRONMENT, "")
		_expect(_active("all") == [false, false, false],
			"the benchmark extension's classes are refused without ELORIA_NATIVE_PROVIDER=benchmark")
		OS.set_environment("ELORIA_NATIVE_CROWD", "1")
		var reducer: Dictionary = NativeCrowd.kernel("reducer")
		_expect(reducer.object == null and str(reducer.status) == "provider_untrusted",
			"the benchmark reducer is refused too (%s)" % reducer.status)
		OS.set_environment(NativeCrowd.PROVIDER_ENVIRONMENT, NativeCrowd.BENCHMARK_PROVIDER)
	for mode: String in cases:
		_expect(_active(mode) == cases[mode], "ELORIA_NATIVE_PRESENTATION='%s' activates exactly %s" % [mode, cases[mode]])
	_expect(_reducer_active("1"), "ELORIA_NATIVE_CROWD=1 activates AppState's native reducer from the loaded classes")
	var loaded_paths := Array(GDExtensionManager.get_loaded_extensions())
	if external.is_empty():
		_expect(loaded_paths.filter(func(path: String) -> bool: return path.get_file() == "native_crowd.gdextension").is_empty(),
			"no opt-in loaded the benchmark extension (%s)" % [loaded_paths])
	OS.set_environment("ELORIA_NATIVE_PRESENTATION", presentation)
	OS.set_environment("ELORIA_NATIVE_CROWD", crowd)
	OS.set_environment(NativeCrowd.PROVIDER_ENVIRONMENT, provider)

func _smoke() -> void:
	var rest := PackedVector3Array([Vector3.ZERO, Vector3.DOWN, Vector3.DOWN * 2.0, Vector3.DOWN * 3.0, Vector3.DOWN * 4.0])
	var points: Array = [PackedVector3Array([Vector3.ONE]), PackedVector3Array([Vector3.ONE]), PackedVector3Array([Vector3.ONE])]
	var previous: Array = points.duplicate(true)
	var lengths := PackedFloat32Array([1.0, 1.0, 1.0, 1.0])
	var cape: Object = ClassDB.instantiate(&"NativeCapeConstraintKernel")
	var solved := bool(cape.call("step", points, previous, [rest, rest, rest], [lengths, lengths, lengths],
		PackedVector3Array(), [], PackedVector3Array(), PackedFloat64Array(), PackedFloat64Array(), [],
		Vector3.ZERO, 0.72, Vector3.FORWARD, 0.0, 0.0, Transform3D.IDENTITY, false))
	_expect(solved and (points[1] as PackedVector3Array) == rest and (previous[2] as PackedVector3Array) == rest,
		"an unsettled cape step reseeds every chain at rest")
	_expect(not bool(cape.call("step", points, previous, [rest, rest], [lengths, lengths, lengths],
		PackedVector3Array(), [], PackedVector3Array(), PackedFloat64Array(), PackedFloat64Array(), [],
		Vector3.ZERO, 0.72, Vector3.FORWARD, 0.0, 0.0, Transform3D.IDENTITY, false)),
		"a malformed cape step is rejected")
	var world: Object = ClassDB.instantiate(&"NativeWorldEffectGeometry")
	var built: Variant = world.call("build", 79, 7, 0.407, 0.37, Vector3(0.7, -0.2, 1.1), Color(0.9, 0.8, 0.3),
		1.0, 1.0, 0.0, false, Vector3.ZERO)
	_expect(built is Array and (built as Array).size() >= 2 and ((built as Array)[0] as PackedVector3Array).size() > 0,
		"a world-effect build returns packed geometry")
	var flight: Object = ClassDB.instantiate(&"NativeSpellFlightGeometry")
	var ribbon: Variant = flight.call("build", 2, Color(0.2, 0.7, 0.9, 0.8), Vector3(-4, 2, 1), Vector3(13, 4, -8),
		Vector3.RIGHT, Vector3.UP, 0.4, 0.6, 0.35, 1.0, 0.18, Vector3.FORWARD, Vector3.RIGHT, Vector3.UP, 1.0, 5)
	_expect(ribbon is Array and not (ribbon as Array).is_empty(), "a spell-flight build returns geometry")
	_expect((flight.call("build", 2, Color(0.2, 0.7, 0.9, 0.8), Vector3.ZERO, Vector3.ONE, Vector3.RIGHT, Vector3.UP,
		0.4, 0.6, 0.35, 0.0, 0.18, Vector3.FORWARD, Vector3.RIGHT, Vector3.UP, 1.0, 5) as Array).is_empty(),
		"a spell-flight build with zero duration is rejected")
	var store: Object = ClassDB.instantiate(&"NativeCrowdStore")
	store.call("reset", {7: _actor(7), 8: _actor(8)})
	var reduced: Dictionary = store.call("reduce_packets", [_packet([[7, 18], [8, 40]])], -1)
	var actors := {7: _actor(7), 8: _actor(8)}
	var dirty: PackedInt32Array = store.call("snapshot_dirty", actors)
	_expect(str(reduced.get("status", "")) == "ok" and int(store.call("size")) == 2 and dirty.size() == 2
		and actors[7] == ActorReducer.apply_command(_actor(7), 18) and actors[8] == ActorReducer.apply_command(_actor(8), 40),
		"the compact store reduces and materialises like ActorReducer (%s)" % [reduced])

func _actor(actor_id: int) -> Dictionary:
	return {"actor_id": actor_id, "x": 10, "y": 20, "command_sequence": (1 << 40) + 9, "health": 31,
		"max_health": 47, "alive": true, "sitting": false, "in_combat": true, "map": "four_gates",
		"appearance": {"hair": 2}, "equipment_visuals": {0: 64}}

func _packet(rows: Array) -> PackedByteArray:
	var payload := PackedByteArray()
	for row: Array in rows:
		payload.append(int(row[0]) & 0xff)
		payload.append((int(row[0]) >> 8) & 0xff)
		payload.append(int(row[1]) & 0xff)
	return payload

func _reducer_parity() -> void:
	var reducer: Object = ClassDB.instantiate(&"NativeCrowdReducer")
	var mismatched: Array[int] = []
	for command: int in range(256):
		var original := _actor(7)
		var actors := {7: original}
		var result: Dictionary = reducer.call("reduce_packet", actors, _packet([[7, command]]), -1)
		if str(result.get("status", "")) != "ok" or actors[7] != ActorReducer.apply_command(original, command) \
				or result.get("changed_ids") != PackedInt32Array([7]):
			mismatched.append(command)
	_expect(mismatched.is_empty(), "the reducer equals ActorReducer for all 256 command bytes (mismatched %s)" % [mismatched])
	var local := {7: _actor(7)}
	var fallback: Dictionary = reducer.call("reduce_packet", local, _packet([[7, 19]]), 7)
	_expect(str(fallback.get("status", "")) == "fallback" and local[7] == _actor(7),
		"the local actor's command 19 still falls back before any mutation")
