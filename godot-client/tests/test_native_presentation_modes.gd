extends SceneTree
## Independent opt-ins must activate exactly their documented components, from
## the verified client_runtime payload (RB-C1g: src/runtime/native_crowd.gd),
## and nothing else.
##
## The ELORIA_NATIVE_PRESENTATION table (cape, flight, world kernels):
## unset, 0, off, script, gdscript, legacy and unknown values keep all three on
## GDScript (DEFAULTS are off); cape, flight, both/1, world and all select
## their kernels. A selected kernel is active only when the payload is
## available: verified, not switched off, and registering the kernel classes.
## The modes that select nothing must not load the payload, and no mode loads
## the benchmark extension without ELORIA_NATIVE_PROVIDER=benchmark.
##
## Run it twice: as is (payload present) and with RABBITLANDS_NATIVE_RUNTIME=off
## (the fallback path; every kernel stays on GDScript with status
## runtime_switched_off). `--expect-native=present|absent` (user argument) turns
## an unexpected payload state into a failure.

const Cape = preload("res://src/actors/cape_cloth.gd")
const Flight = preload("res://src/world/spell_flight_3d.gd")
const WorldEffect = preload("res://src/world/world_effect_3d.gd")
const NativeLibrary = preload("res://src/runtime/native_library.gd")
const NativeCrowd = preload("res://src/runtime/native_crowd.gd")
const KERNEL_CLASSES: Array[String] = ["NativeCapeConstraintKernel", "NativeSpellFlightGeometry",
	"NativeWorldEffectGeometry"]
## Values that select nothing come first: none of them may load the payload.
const OFF_CASES := ["", "0", "off", "script", "gdscript", "legacy", "unknown"]
const ON_CASES := {"cape": [true, false, false], "flight": [false, true, false],
	"both": [true, true, false], "1": [true, true, false], "world": [false, false, true],
	"all": [true, true, true], " ALL ": [true, true, true]}

var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: ", message)
	else:
		_failures += 1
		push_error("FAIL: " + message)


func _active(mode: String) -> Array:
	OS.set_environment("ELORIA_NATIVE_PRESENTATION", mode)
	var cape := Cape.new()
	cape.call("_initialize_native_constraint_kernel")
	var flight := Flight.new()
	var world := WorldEffect.new()
	root.add_child(world)
	world.set_process(false)
	world.configure(2, Vector3.ZERO, null, 5)
	var actual := [bool(cape.call("native_constraint_kernel_active")),
		flight.native_presentation_active(),
		bool(world.call("native_presentation_active")),
		str((cape.call("native_presentation_stats") as Dictionary).get("status", ""))]
	world.free()
	flight.free()
	cape.free()
	return actual


func _run() -> void:
	var original_mode := OS.get_environment("ELORIA_NATIVE_PRESENTATION")
	var original_provider := OS.get_environment(NativeCrowd.PROVIDER_ENVIRONMENT)
	OS.set_environment(NativeCrowd.PROVIDER_ENVIRONMENT, "")
	var switched_off := str(NativeLibrary.switch_state().mode) == "off"
	# A wrapper (test_client_runtime_kernels_presentation_modes.gd) may load the
	# payload before this suite runs; the consumers then reuse it.
	var preloaded := ClassDB.class_exists(NativeLibrary.RUNTIME_CLASS)
	for mode: String in OFF_CASES:
		var actual := _active(mode)
		_expect(actual.slice(0, 3) == [false, false, false] and actual[3] == "disabled",
			"mode '%s' keeps cape/flight/world on GDScript (got %s)" % [mode, actual])
	if not preloaded:
		_expect(not ClassDB.class_exists(NativeLibrary.RUNTIME_CLASS) and not bool(NativeLibrary.stats().ensured),
			"modes that select nothing do not load the payload")
	var results := {}
	for mode: String in ON_CASES:
		results[mode] = _active(mode)
	# Availability as the loader saw it, after the consumers loaded it themselves.
	var providers := NativeCrowd.providers()
	var runtime_ready := preloaded or (bool(NativeLibrary.stats().ensured) and str(NativeLibrary.stats().code) == "loaded")
	var available := not switched_off and runtime_ready \
		and KERNEL_CLASSES.all(func(name: String) -> bool: return str(providers.get(name, "")) == "client_runtime")
	for mode: String in ON_CASES:
		var expected: Array = (ON_CASES[mode] as Array).map(func(on: bool) -> bool: return on and available)
		var actual: Array = results[mode]
		_expect(actual.slice(0, 3) == expected,
			"mode '%s': expected cape/flight/world %s, got %s (payload available: %s)" % [mode, expected,
				actual.slice(0, 3), available])
		if bool((ON_CASES[mode] as Array)[0]):
			var status := "active" if available else ("runtime_switched_off" if switched_off else "")
			if not status.is_empty():
				_expect(actual[3] == status, "mode '%s': cape status %s (got %s)" % [mode, status, actual[3]])
			else:
				_expect(str(actual[3]) != "active" and str(actual[3]) != "disabled",
					"mode '%s': an unavailable payload names its reason (%s)" % [mode, actual[3]])
	if switched_off:
		_expect(int(NativeLibrary.stats().verifications) == 0 and int(NativeLibrary.stats().loads) == 0
			and not ClassDB.class_exists(NativeLibrary.RUNTIME_CLASS),
			"the kill switch keeps the payload unread and unloaded")
	var loaded_paths := Array(GDExtensionManager.get_loaded_extensions())
	_expect(loaded_paths.filter(func(path: String) -> bool: return path.get_file() == "native_crowd.gdextension").is_empty(),
		"no mode loaded the benchmark extension (%s)" % [loaded_paths])
	var args := OS.get_cmdline_user_args()
	if args.has("--expect-native=present"):
		_expect(available, "requested native-present run: the payload provides the kernels (%s)" % [
			NativeLibrary.stats()])
	elif args.has("--expect-native=absent"):
		_expect(not available, "requested native-absent run: no payload kernels")
	print("native kernels snapshot: ", JSON.stringify(NativeCrowd.snapshot()))
	OS.set_environment("ELORIA_NATIVE_PRESENTATION", original_mode)
	OS.set_environment(NativeCrowd.PROVIDER_ENVIRONMENT, original_provider)
	print("native presentation modes: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)
