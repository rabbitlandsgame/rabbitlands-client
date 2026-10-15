extends SceneTree
## Independent opt-ins must activate exactly their documented components.

const Cape = preload("res://src/actors/cape_cloth.gd")
const Flight = preload("res://src/world/spell_flight_3d.gd")
const WorldEffect = preload("res://src/world/world_effect_3d.gd")

var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var original_mode := OS.get_environment("ELORIA_NATIVE_PRESENTATION")
	var cases := {
		"": [false, false, false], "0": [false, false, false],
		"off": [false, false, false], "cape": [true, false, false],
		"flight": [false, true, false], "both": [true, true, false],
		"1": [true, true, false], "world": [false, false, true],
		"all": [true, true, true], " ALL ": [true, true, true],
		"unknown": [false, false, false],
	}
	for mode: String in cases:
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
			bool(world.call("native_presentation_active"))]
		if actual != cases[mode]:
			_failures += 1
			push_error("mode '%s': expected cape/flight/world %s, got %s" % [
				mode, cases[mode], actual])
		world.free()
		flight.free()
		cape.free()
	OS.set_environment("ELORIA_NATIVE_PRESENTATION", original_mode)
	print("native presentation modes: ", "PASS" if _failures == 0 else "FAIL")
	quit(_failures)
