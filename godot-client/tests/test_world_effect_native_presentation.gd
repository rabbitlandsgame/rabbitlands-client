extends SceneTree
## Production opt-in, exact output, counters and failure fallback for the
## coarse native world-effect detail builder.

const Baseline = preload("res://tests/fixtures/world_effect_3d_967744_baseline.gd")
const Production = preload("res://src/world/world_effect_3d.gd")
const BASELINE_FIXTURE_SHA256 := "bd93988a1c3424c02a9ee15c93f929527dcfed66b97fc939d086b676deca33f8"

class RejectingBuilder extends RefCounted:
	func build(_effect_id: int, _power_level: int, _elapsed: float,
			_progress: float, _impact: Vector3, _palette: Color, _size: float,
			_radius: float, _area_radius: float, _has_flight: bool,
			_flight_contact: Vector3) -> Variant:
		return null

var _failures := 0
var _original_mode := ""


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_original_mode = OS.get_environment("ELORIA_NATIVE_PRESENTATION")
	_expect(FileAccess.get_sha256(
		"res://tests/fixtures/world_effect_3d_967744_baseline.gd") \
		== BASELINE_FIXTURE_SHA256, "frozen 967744 fixture bytes match")

	OS.set_environment("ELORIA_NATIVE_PRESENTATION", "world")
	var before: Dictionary = Production.native_presentation_stats()
	var baseline = Baseline.new()
	var effect = Production.new()
	root.add_child(baseline)
	root.add_child(effect)
	baseline.configure(79, Vector3(-2, 0.5, 3), null, 7)
	effect.configure(79, Vector3(-2, 0.5, 3), null, 7)
	baseline.set_process(false)
	effect.set_process(false)
	baseline.elapsed = 0.407
	effect.elapsed = 0.407
	baseline.set("_impact", Vector3(0.7, -0.2, 1.1))
	effect.set("_impact", Vector3(0.7, -0.2, 1.1))
	baseline.call("_draw_details", 0.37)
	effect.call("_draw_details", 0.37)
	_expect(effect.native_presentation_active(),
		"world mode activates native builder")
	_compare_meshes((baseline.get_node("EffectRunes") as MeshInstance3D).mesh,
		(effect.get_node("EffectRunes") as MeshInstance3D).mesh,
		"representative blessing/identity")
	var after: Dictionary = Production.native_presentation_stats()
	_expect(int(after.buildAttempts) - int(before.buildAttempts) == 1,
		"native attempt counter advances once")
	_expect(int(after.buildSuccesses) - int(before.buildSuccesses) == 1,
		"native success counter advances once")
	_expect(int(after.buildFallbacks) == int(before.buildFallbacks),
		"valid native output does not fall back")
	baseline.free()
	effect.free()

	for enabled_mode: String in ["world", "all"]:
		OS.set_environment("ELORIA_NATIVE_PRESENTATION", enabled_mode)
		var enabled = Production.new()
		_expect(enabled.native_presentation_active(),
			enabled_mode + " mode activates native world details")
		enabled.free()
	for disabled_mode: String in ["", "0", "off", "cape", "flight", "both", "1"]:
		OS.set_environment("ELORIA_NATIVE_PRESENTATION", disabled_mode)
		var disabled = Production.new()
		_expect(not disabled.native_presentation_active(),
			("empty" if disabled_mode.is_empty() else disabled_mode)
			+ " mode leaves native world details off")
		disabled.free()

	OS.set_environment("ELORIA_NATIVE_PRESENTATION", "world")
	var fallback_baseline = Baseline.new()
	var rejected = Production.new()
	root.add_child(fallback_baseline)
	root.add_child(rejected)
	fallback_baseline.configure(3, Vector3.ZERO, null, 5)
	rejected.configure(3, Vector3.ZERO, null, 5)
	fallback_baseline.set_process(false)
	rejected.set_process(false)
	fallback_baseline.elapsed = 0.63
	rejected.elapsed = 0.63
	rejected.set("_native_geometry", RejectingBuilder.new())
	var fallback_before: Dictionary = Production.native_presentation_stats()
	fallback_baseline.call("_draw_details", 0.57)
	rejected.call("_draw_details", 0.57)
	var fallback_after: Dictionary = Production.native_presentation_stats()
	_expect(not rejected.native_presentation_active(),
		"malformed output permanently selects the instance fallback")
	_expect(int(fallback_after.buildAttempts) - int(fallback_before.buildAttempts) == 1,
		"malformed output records one attempt")
	_expect(int(fallback_after.buildFallbacks) - int(fallback_before.buildFallbacks) == 1,
		"malformed output records one fallback")
	_expect(int(fallback_after.buildSuccesses) == int(fallback_before.buildSuccesses),
		"malformed output does not record success")
	var fallback_mesh: Mesh = (rejected.get_node("EffectRunes") as MeshInstance3D).mesh
	_expect(fallback_mesh is ImmediateMesh,
		"malformed output switches the instance to ImmediateMesh")
	_compare_meshes(
		(fallback_baseline.get_node("EffectRunes") as MeshInstance3D).mesh,
		fallback_mesh, "malformed native fallback")
	fallback_baseline.free()
	rejected.free()

	OS.set_environment("ELORIA_NATIVE_PRESENTATION", _original_mode)
	print("world effect native presentation: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)


func _compare_meshes(expected: Mesh, actual: Mesh, label: String) -> void:
	_expect(expected != null and actual != null, label + " meshes exist")
	if expected == null or actual == null:
		return
	_expect(expected.get_surface_count() == 1 and actual.get_surface_count() == 1,
		label + " has one triangle surface")
	if expected.get_surface_count() != 1 or actual.get_surface_count() != 1:
		return
	var before := expected.surface_get_arrays(0)
	var after := actual.surface_get_arrays(0)
	_expect(before.size() == Mesh.ARRAY_MAX and after.size() == Mesh.ARRAY_MAX,
		label + " exposes complete mesh arrays")
	if before.size() != Mesh.ARRAY_MAX or after.size() != Mesh.ARRAY_MAX:
		return
	for slot: int in Mesh.ARRAY_MAX:
		_expect(before[slot] == after[slot],
			label + " exact array%d value/order" % slot)
	_compare_materials(expected.surface_get_material(0),
		actual.surface_get_material(0), label)


func _compare_materials(expected: Material, actual: Material, label: String) -> void:
	_expect(expected is StandardMaterial3D and actual is StandardMaterial3D,
		label + " StandardMaterial3D type")
	if not expected is StandardMaterial3D or not actual is StandardMaterial3D:
		return
	var left := expected as StandardMaterial3D
	var right := actual as StandardMaterial3D
	_expect(left.shading_mode == right.shading_mode, label + " shading")
	_expect(left.transparency == right.transparency, label + " transparency")
	_expect(left.blend_mode == right.blend_mode, label + " blend")
	_expect(left.vertex_color_use_as_albedo == right.vertex_color_use_as_albedo,
		label + " vertex color")
	_expect(left.cull_mode == right.cull_mode, label + " cull")
	_expect(left.no_depth_test == right.no_depth_test, label + " depth")
	_expect(left.albedo_color == right.albedo_color, label + " albedo")


func _expect(value: bool, label: String) -> void:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
