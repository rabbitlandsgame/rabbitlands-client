extends SceneTree
## Locks the effect geometry contract while its hot loops are optimized.
## Frozen helpers are the pre-optimization implementation; production remains
## the other side of the comparison after the candidate is copied in.

const BaselineMesh = preload("res://tests/fixtures/combat_effect_mesh_baseline.gd")
const BaselineFlight = preload("res://tests/fixtures/spell_flight_3d_baseline.gd")
const ProductionFlight = preload("res://src/world/spell_flight_3d.gd")
const BASELINE_MESH_PATH := "res://tests/fixtures/combat_effect_mesh_baseline.gd"
const BASELINE_FLIGHT_PATH := "res://tests/fixtures/spell_flight_3d_baseline.gd"
const BASELINE_MESH_SHA256 := "71628e85617c03a6949a74fe500ef29c0cd1860191f0f4fe83c740f33112d3a6"
const BASELINE_FLIGHT_SHA256 := "c333f8afe62e6387cfcf286fba0a275951abc790cc780c9d3702cc594f930f5e"

var _failures := 0
var _cases := 0
var _camera: Camera3D


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	root.size = Vector2i(960, 540)
	_camera = Camera3D.new()
	root.add_child(_camera)
	_camera.current = true
	await process_frame
	_check_baseline_provenance(BASELINE_MESH_PATH, "extends RefCounted",
		BASELINE_MESH_SHA256)
	_check_baseline_provenance(BASELINE_FLIGHT_PATH, "extends Node3D",
		BASELINE_FLIGHT_SHA256)
	_compare_primitive_helpers()
	await _compare_spell_flights()
	print("effect geometry parity: ",
		"PASS (%d cases)" % _cases if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)


func _compare_primitive_helpers() -> void:
	var line_cases: Array[Dictionary] = [
		{"a": Vector3(1.2, -0.4, 2.1), "b": Vector3(-3.0, 1.5, 0.2),
			"width": 0.13, "color": Color(0.2, 0.7, 1.0, 0.43),
			"normal": Vector3.UP},
		{"a": Vector3.ONE, "b": Vector3.ONE, "width": 0.2,
			"color": Color.WHITE, "normal": Vector3.UP},
		{"a": Vector3.ZERO, "b": Vector3.UP * 4.0, "width": 0.0,
			"color": Color(0.4, 0.3, 0.2, 0.1), "normal": Vector3.UP},
		{"a": Vector3(-2, 3, 1), "b": Vector3(4, -1, 5), "width": -0.07,
			"color": Color(3.0, 0.2, 0.1, 1.7),
			"normal": Vector3(0.2, 0.9, -0.3).normalized()},
	]
	for index: int in line_cases.size():
		_compare_primitive("line-%d" % index, "line", line_cases[index])
	var arc_cases: Array[Dictionary] = [
		{"centre": Vector3.ZERO, "radius": 0.72, "width": 0.02,
			"color": Color(0.6, 0.8, 1.0, 0.7), "start": 0.0,
			"sweep": TAU, "basis": Basis.IDENTITY},
		{"centre": Vector3(2, 1, -3), "radius": 1.6, "width": 0.08,
			"color": Color(1.0, 0.4, 0.1, 0.5), "start": 1.37,
			"sweep": -TAU * 0.85,
			"basis": Basis(Vector3(1, 2, -1).normalized(), 0.73)},
		{"centre": Vector3(-1, 4, 2), "radius": 0.0, "width": 0.0,
			"color": Color.TRANSPARENT, "start": -4.2,
			"sweep": 0.0, "basis": Basis(Vector3.RIGHT, PI * 0.5)},
		{"centre": Vector3(0.1, -0.2, 0.3), "radius": -0.45, "width": -0.01,
			"color": Color(0.1, 0.2, 0.3, 0.4), "start": 700.0,
			"sweep": 0.0001, "basis": Basis(Vector3.FORWARD, -1.2)},
	]
	for index: int in arc_cases.size():
		_compare_primitive("arc-%d" % index, "arc", arc_cases[index])
	for size: float in [0.19, 0.0, -0.35]:
		_compare_primitive("spark-%s" % size, "spark", {
			"centre": Vector3(0.7, -1.1, 2.4), "size": size,
			"color": Color(0.9, 0.6, 0.2, 0.37)})


func _compare_primitive(label: String, kind: String, values: Dictionary) -> void:
	var baseline := _primitive_mesh(BaselineMesh, kind, values)
	var production := _primitive_mesh(CombatEffectMesh, kind, values)
	_compare_meshes(baseline, production, label, true)
	_cases += 1


func _primitive_mesh(helper: Variant, kind: String, values: Dictionary) -> ImmediateMesh:
	var mesh := ImmediateMesh.new()
	mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES, helper.material())
	match kind:
		"line":
			helper.line(mesh, values.a, values.b, values.width,
				values.color, values.normal)
		"arc":
			helper.arc(mesh, values.centre, values.radius, values.width,
				values.color, values.start, values.sweep, values.basis)
		"spark":
			helper.spark(mesh, values.centre, values.size, values.color)
	mesh.surface_end()
	return mesh


func _compare_spell_flights() -> void:
	var effects := [0, 1, 2, 10, 73, 83, 84, 85, 86, 999]
	var powers := [1, 5, 10]
	var paths: Array[Dictionary] = [
		{"from": Vector3.ZERO, "to": Vector3(5, 0, 0)},
		{"from": Vector3(2, -1, 3), "to": Vector3(2, 6, 3)},
		{"from": Vector3(-4, 2, 1), "to": Vector3(-3.99, 2, 1)},
		{"from": Vector3(12, -5, 9), "to": Vector3(-58, 3, 29)},
		{"from": Vector3(-2, 4, 7), "to": Vector3(-2, 4, 7)},
	]
	var camera_rotations := [
		Vector3(-22.0, 15.0, 0.0),
		Vector3(-67.0, -128.0, 0.0),
		Vector3(5.0, 179.0, 31.0),
	]
	for effect_index: int in effects.size():
		var effect: int = effects[effect_index]
		var power: int = powers[effect_index % powers.size()]
		var path: Dictionary = paths[effect_index % paths.size()]
		for rotation: Vector3 in camera_rotations:
			_camera.rotation_degrees = rotation
			var baseline = BaselineFlight.new()
			var production = ProductionFlight.new()
			root.add_child(baseline)
			root.add_child(production)
			var tint := Color(0.17 + effect_index * 0.03, 0.82, 0.41, 0.93)
			baseline.configure(effect, tint, path.from, path.to, power)
			production.configure(effect, tint, path.from, path.to, power)
			_expect(baseline.duration == production.duration,
				"effect%d-power%d duration" % [effect, power])
			if effect_index % 2 == 1:
				var moved_from: Vector3 = path.from + Vector3(0.37, -0.11, 0.29)
				var moved_to: Vector3 = path.to + Vector3(-1.7, 0.43, 2.1)
				baseline.set_endpoints(moved_from, moved_to)
				production.set_endpoints(moved_from, moved_to)
			_compare_flight_points(baseline, production,
				"effect%d-power%d-rotation%s" % [effect, power, rotation])
			var duration: float = baseline.duration
			for time: float in [-0.13, 0.0, duration * 0.17, duration * 0.51,
					duration, duration + 0.12,
					duration + BaselineFlight.AFTERGLOW - 0.00001,
					duration + BaselineFlight.AFTERGLOW,
					duration + 0.25]:
				baseline.draw_at(time)
				production.draw_at(time)
				var baseline_mesh := (baseline.get_node("SpellEnergy") as MeshInstance3D).mesh
				var production_mesh := (production.get_node("SpellEnergy") as MeshInstance3D).mesh
				_compare_meshes(baseline_mesh, production_mesh,
					"flight-effect%d-power%d-time%.5f-camera%s" % [
						effect, power, time, rotation],
					time < duration + BaselineFlight.AFTERGLOW)
				_cases += 1
			baseline.free()
			production.free()


func _compare_flight_points(baseline: Node, production: Node, label: String) -> void:
	for strand: int in 3:
		var progress_values: Array[float] = [-0.3, 0.0]
		for step: int in 17:
			progress_values.append(float(step) / 16.0)
		progress_values.append(1.4)
		for progress: float in progress_values:
			_expect(baseline.point_at(progress, strand) == production.point_at(progress, strand),
				label + " point order/value strand%d progress%.5f" % [strand, progress])


func _compare_meshes(baseline: Mesh, production: Mesh, label: String,
		expect_nonempty: bool) -> void:
	_expect(baseline.get_surface_count() == production.get_surface_count(),
		label + " surface count")
	if expect_nonempty:
		_expect(baseline.get_surface_count() > 0,
			label + " baseline has a real rendered surface")
	else:
		_expect(baseline.get_surface_count() == 0,
			label + " expired baseline has no rendered surface")
	if baseline.get_surface_count() != production.get_surface_count():
		return
	for surface: int in baseline.get_surface_count():
		var expected := baseline.surface_get_arrays(surface)
		var actual := production.surface_get_arrays(surface)
		_expect(expected.size() == Mesh.ARRAY_MAX and actual.size() == Mesh.ARRAY_MAX,
			label + " surface%d exposes every mesh array slot" % surface)
		if expected.size() != Mesh.ARRAY_MAX or actual.size() != Mesh.ARRAY_MAX:
			continue
		if expect_nonempty:
			_expect((expected[Mesh.ARRAY_VERTEX] as PackedVector3Array).size() > 0,
				label + " surface%d has nonzero baseline vertices" % surface)
			_expect((actual[Mesh.ARRAY_VERTEX] as PackedVector3Array).size() > 0,
				label + " surface%d has nonzero production vertices" % surface)
		for slot: int in Mesh.ARRAY_MAX:
			_expect(expected[slot] == actual[slot],
				label + " surface%d array%d exact order/value" % [surface, slot])
		_compare_materials(baseline.surface_get_material(surface),
			production.surface_get_material(surface),
			label + " surface%d material" % surface)


func _compare_materials(expected: Material, actual: Material, label: String) -> void:
	_expect(expected != null and actual != null, label + " exists")
	if expected == null or actual == null:
		return
	_expect(expected.get_class() == actual.get_class(), label + " resource type")
	if expected is StandardMaterial3D and actual is StandardMaterial3D:
		var left := expected as StandardMaterial3D
		var right := actual as StandardMaterial3D
		_expect(left.shading_mode == right.shading_mode, label + " shading")
		_expect(left.transparency == right.transparency, label + " transparency")
		_expect(left.blend_mode == right.blend_mode, label + " blend")
		_expect(left.vertex_color_use_as_albedo == right.vertex_color_use_as_albedo,
			label + " vertex color")
		_expect(left.cull_mode == right.cull_mode, label + " culling")
		_expect(left.no_depth_test == right.no_depth_test, label + " depth")
		_expect(left.albedo_color == right.albedo_color, label + " albedo")
	elif expected is ShaderMaterial and actual is ShaderMaterial:
		var left := expected as ShaderMaterial
		var right := actual as ShaderMaterial
		_expect(left.shader == right.shader, label + " shader")
		for parameter: String in ["radial", "intensity"]:
			_expect(left.get_shader_parameter(parameter)
				== right.get_shader_parameter(parameter),
				label + " shader parameter " + parameter)
	_expect(expected.render_priority == actual.render_priority, label + " render priority")
	_expect(expected.next_pass == actual.next_pass, label + " next pass")


func _check_baseline_provenance(path: String, marker: String,
		expected_sha256: String) -> void:
	var source := FileAccess.get_file_as_string(path)
	var body_at := source.find(marker)
	_expect(body_at >= 0, path + " contains the frozen source body")
	if body_at < 0:
		return
	var normalized := source.substr(body_at).replace("\r\n", "\n")
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(normalized.to_utf8_buffer())
	_expect(context.finish().hex_encode() == expected_sha256,
		path + " matches the reviewed baseline SHA-256")


func _expect(value: bool, label: String) -> void:
	if value:
		return
	_failures += 1
	push_error("FAIL: " + label)
