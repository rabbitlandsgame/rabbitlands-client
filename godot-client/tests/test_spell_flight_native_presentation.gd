extends SceneTree
## Production opt-in, counter, exact output, and failure fallback checks for the
## coarse native spell-flight geometry builder.

const Baseline = preload("res://tests/fixtures/spell_flight_3d_269c_baseline.gd")
const Production = preload("res://src/world/spell_flight_3d.gd")
const BASELINE_SHA256 := "0097916f9a7aca508918d088df479c5c6c7061ae0fcc02e950198faa32326d65"

class RejectingBuilder extends RefCounted:
	func build(_effect_id: int, _tint: Color, _start: Vector3,
			_destination: Vector3, _side: Vector3, _up: Vector3,
			_path_spread: float, _path_arc: float, _tail_fraction: float,
			_duration: float, _time: float, _view: Vector3,
			_camera_right: Vector3, _camera_up: Vector3, _magnitude: float,
			_particle_count: int) -> Variant:
		return null

var _failures := 0
var _original_mode := ""


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_original_mode = OS.get_environment("ELORIA_NATIVE_PRESENTATION")
	root.size = Vector2i(960, 540)
	var camera := Camera3D.new()
	root.add_child(camera)
	camera.current = true
	await process_frame
	_expect(FileAccess.get_sha256(
		"res://tests/fixtures/spell_flight_3d_269c_baseline.gd") == BASELINE_SHA256,
		"frozen baseline bytes match b90e4238b production")

	OS.set_environment("ELORIA_NATIVE_PRESENTATION", "flight")
	var before: Dictionary = Production.native_presentation_stats()
	var baseline = Baseline.new()
	var flight = Production.new()
	root.add_child(baseline)
	root.add_child(flight)
	_expect(flight.native_presentation_active(), "flight mode activates native builder")
	baseline.configure(2, Color(0.2, 0.7, 0.9, 0.8),
		Vector3(-4, 2, 1), Vector3(13, 4, -8), 5)
	flight.configure(2, Color(0.2, 0.7, 0.9, 0.8),
		Vector3(-4, 2, 1), Vector3(13, 4, -8), 5)
	baseline.draw_at(0.18)
	flight.draw_at(0.18)
	_compare_meshes((baseline.get_node("SpellEnergy") as MeshInstance3D).mesh,
		(flight.get_node("SpellEnergy") as MeshInstance3D).mesh)
	var after: Dictionary = Production.native_presentation_stats()
	_expect(int(after.buildAttempts) - int(before.buildAttempts) == 1,
		"native attempt counter advances once")
	_expect(int(after.buildSuccesses) - int(before.buildSuccesses) == 1,
		"native success counter advances once")
	_expect(int(after.buildFallbacks) == int(before.buildFallbacks),
		"valid native output does not fall back")
	baseline.free()
	flight.free()

	for enabled_mode: String in ["both", "1", "all"]:
		OS.set_environment("ELORIA_NATIVE_PRESENTATION", enabled_mode)
		var enabled = Production.new()
		_expect(enabled.native_presentation_active(),
			enabled_mode + " mode activates native flight")
		enabled.free()
	for disabled_mode: String in ["", "0", "cape", "world"]:
		OS.set_environment("ELORIA_NATIVE_PRESENTATION", disabled_mode)
		var disabled = Production.new()
		_expect(not disabled.native_presentation_active(),
			("empty" if disabled_mode.is_empty() else disabled_mode)
			+ " mode leaves native flight off")
		disabled.free()

	OS.set_environment("ELORIA_NATIVE_PRESENTATION", "flight")
	var fallback_baseline = Baseline.new()
	var rejected = Production.new()
	root.add_child(fallback_baseline)
	root.add_child(rejected)
	fallback_baseline.configure(2, Color.WHITE, Vector3.ZERO, Vector3(5, 0, 0), 1)
	rejected.configure(2, Color.WHITE, Vector3.ZERO, Vector3(5, 0, 0), 1)
	rejected.set("_native_geometry", RejectingBuilder.new())
	var fallback_before: Dictionary = Production.native_presentation_stats()
	fallback_baseline.draw_at(0.1)
	rejected.draw_at(0.1)
	var fallback_after: Dictionary = Production.native_presentation_stats()
	_expect(not rejected.native_presentation_active(),
		"rejected native output permanently selects the instance fallback")
	_expect(int(fallback_after.buildAttempts) - int(fallback_before.buildAttempts) == 1,
		"rejected output records one attempt")
	_expect(int(fallback_after.buildFallbacks) - int(fallback_before.buildFallbacks) == 1,
		"rejected output records one fallback")
	_expect(int(fallback_after.buildSuccesses) == int(fallback_before.buildSuccesses),
		"rejected output does not record success")
	var fallback_mesh: Mesh = (rejected.get_node("SpellEnergy") as MeshInstance3D).mesh
	_expect(fallback_mesh is ImmediateMesh,
		"rejected output switches the instance to ImmediateMesh")
	_compare_meshes(
		(fallback_baseline.get_node("SpellEnergy") as MeshInstance3D).mesh,
		fallback_mesh)
	fallback_baseline.free()
	rejected.free()

	OS.set_environment("ELORIA_NATIVE_PRESENTATION", _original_mode)
	print("spell flight native presentation: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)


func _compare_meshes(expected: Mesh, actual: Mesh) -> void:
	_expect(expected.get_surface_count() == 2 and actual.get_surface_count() == 2,
		"active flight has ribbon and glow surfaces")
	if expected.get_surface_count() != actual.get_surface_count():
		return
	for surface: int in expected.get_surface_count():
		var before := expected.surface_get_arrays(surface)
		var after := actual.surface_get_arrays(surface)
		_expect(before.size() == Mesh.ARRAY_MAX and after.size() == Mesh.ARRAY_MAX,
			"surface%d exposes complete arrays" % surface)
		if before.size() != Mesh.ARRAY_MAX or after.size() != Mesh.ARRAY_MAX:
			continue
		for slot: int in Mesh.ARRAY_MAX:
			_expect(before[slot] == after[slot],
				"surface%d array%d exact value/order" % [surface, slot])
		_compare_materials(expected.surface_get_material(surface),
			actual.surface_get_material(surface), surface)


func _compare_materials(expected: Material, actual: Material, surface: int) -> void:
	_expect(expected != null and actual != null,
		"surface%d material exists" % surface)
	if expected == null or actual == null:
		return
	_expect(expected.get_class() == actual.get_class(),
		"surface%d material type" % surface)
	if expected is ShaderMaterial and actual is ShaderMaterial:
		var left := expected as ShaderMaterial
		var right := actual as ShaderMaterial
		_expect(left.shader == right.shader, "surface%d shader" % surface)
		for parameter: String in ["radial", "intensity"]:
			_expect(left.get_shader_parameter(parameter)
				== right.get_shader_parameter(parameter),
				"surface%d %s" % [surface, parameter])
	_expect(expected.render_priority == actual.render_priority,
		"surface%d render priority" % surface)
	_expect(expected.next_pass == actual.next_pass,
		"surface%d next pass" % surface)


func _expect(value: bool, label: String) -> void:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
