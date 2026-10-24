extends "res://tests/test_spell_flight_native_presentation.gd"
## Current C++/Script committed-mesh parity. Historical baseline checks remain
## in their original test; this override intentionally never calls that _run.
const CurrentReference = preload("res://tests/fixtures/spell_flight_current_script_reference.gd")
const CurrentMaterials = preload("res://src/world/spell_visual_material.gd")


func _run() -> void:
	_original_mode = OS.get_environment("ELORIA_NATIVE_PRESENTATION")
	root.size = Vector2i(960, 540)
	var camera := Camera3D.new()
	root.add_child(camera)
	camera.current = true
	await process_frame
	if not ClassDB.class_exists("NativeSpellFlightGeometry"):
		_expect(false, "current C++ comparator is loaded before this fixture")
		_finish_current(camera)
		return

	OS.set_environment("ELORIA_NATIVE_PRESENTATION", "flight")
	var before: Dictionary = Production.native_presentation_stats()
	var reference := CurrentReference.new()
	var flight := Production.new()
	root.add_child(reference)
	root.add_child(flight)
	_expect(not reference.native_presentation_active(), "current Script reference never initializes native")
	_expect(flight.native_presentation_active(), "flight mode activates current C++ builder")
	var palette := Color(0.2, 0.7, 0.9, 0.8)
	reference.configure(2, palette, Vector3(-4, 2, 1), Vector3(13, 4, -8), 5)
	flight.configure(2, palette, Vector3(-4, 2, 1), Vector3(13, 4, -8), 5)
	reference.draw_at(0.18)
	flight.draw_at(0.18)
	# Both are committed mesh readbacks, including the engine's RGBA8 storage.
	# Inherited helpers compare every array slot/order exactly, without an EPS.
	_compare_meshes(reference._mesh_node.mesh, flight._mesh_node.mesh)
	_current_materials(reference._mesh_node.mesh, flight._mesh_node.mesh, palette, 5)
	var after: Dictionary = Production.native_presentation_stats()
	_expect(int(after.buildAttempts) - int(before.buildAttempts) == 1, "current native attempt advances once")
	_expect(int(after.buildSuccesses) - int(before.buildSuccesses) == 1, "current native success advances once")
	_expect(int(after.buildFallbacks) == int(before.buildFallbacks), "valid current C++ output has no fallback")
	reference.free()
	flight.free()

	for enabled_mode: String in ["both", "1", "all"]:
		OS.set_environment("ELORIA_NATIVE_PRESENTATION", enabled_mode)
		var enabled := Production.new()
		_expect(enabled.native_presentation_active(), enabled_mode + " activates current C++ flight")
		enabled.free()
	for disabled_mode: String in ["", "0", "cape", "world"]:
		OS.set_environment("ELORIA_NATIVE_PRESENTATION", disabled_mode)
		var disabled := Production.new()
		_expect(not disabled.native_presentation_active(),
			("empty" if disabled_mode.is_empty() else disabled_mode) + " keeps C++ flight off")
		disabled.free()

	OS.set_environment("ELORIA_NATIVE_PRESENTATION", "flight")
	var fallback_reference := CurrentReference.new()
	var rejected := Production.new()
	root.add_child(fallback_reference)
	root.add_child(rejected)
	fallback_reference.configure(2, Color.WHITE, Vector3.ZERO, Vector3(5, 0, 0), 1)
	rejected.configure(2, Color.WHITE, Vector3.ZERO, Vector3(5, 0, 0), 1)
	rejected.set("_native_geometry", RejectingBuilder.new())
	var fallback_before: Dictionary = Production.native_presentation_stats()
	fallback_reference.draw_at(0.1)
	rejected.draw_at(0.1)
	var fallback_after: Dictionary = Production.native_presentation_stats()
	_expect(not rejected.native_presentation_active(), "rejected current C++ output permanently selects Script fallback")
	_expect(int(fallback_after.buildAttempts) - int(fallback_before.buildAttempts) == 1, "rejection records one attempt")
	_expect(int(fallback_after.buildFallbacks) - int(fallback_before.buildFallbacks) == 1, "rejection records one fallback")
	_expect(int(fallback_after.buildSuccesses) == int(fallback_before.buildSuccesses), "rejection records no success")
	_expect(rejected._mesh_node.mesh is ImmediateMesh, "rejection switches to current ImmediateMesh")
	_compare_meshes(fallback_reference._mesh_node.mesh, rejected._mesh_node.mesh)
	_current_materials(fallback_reference._mesh_node.mesh, rejected._mesh_node.mesh, Color.WHITE, 1)
	var settled: Dictionary = Production.native_presentation_stats()
	rejected.draw_at(0.12)
	fallback_reference.draw_at(0.12)
	_expect(Production.native_presentation_stats() == settled, "permanent fallback makes no later native attempt")
	_compare_meshes(fallback_reference._mesh_node.mesh, rejected._mesh_node.mesh)
	fallback_reference.free()
	rejected.free()
	_finish_current(camera)


func _current_materials(expected: Mesh, actual: Mesh, palette: Color, power: int) -> void:
	if expected.get_surface_count() != 2 or actual.get_surface_count() != 2:
		_expect(false, "current material policy requires both surfaces")
		return
	var intensity := SpellPresentation.power_intensity(power) / SpellPresentation.power_intensity(5)
	for surface: int in 2:
		var radial := surface == 1
		var desired := CurrentMaterials.energy(palette, power, radial)
		var material := actual.surface_get_material(surface) as ShaderMaterial
		_expect(expected.surface_get_material(surface) == desired and material == desired,
			"current surface%d retains the current shared material reference" % surface)
		if material == null:
			continue
		_expect(material.shader == CurrentMaterials.BODY_SHADER, "current body shader reference")
		_expect(material.get_shader_parameter("radial") == radial, "current radial body policy")
		_expect(material.get_shader_parameter("soft_edges") == true, "current soft edge body policy")
		_expect(material.get_shader_parameter("tint") == CurrentMaterials.body_tint(palette), "current palette tint policy")
		_expect(material.get_shader_parameter("intensity") == intensity, "current body intensity")
		_expect(material.render_priority == desired.render_priority, "current body render priority")
		var glow := material.next_pass as ShaderMaterial
		_expect(glow != null and glow == desired.next_pass, "current next-pass reference")
		if glow != null:
			_expect(glow.shader == CurrentMaterials.GLOW_SHADER, "current glow shader reference")
			_expect(glow.get_shader_parameter("radial") == radial, "current radial glow policy")
			_expect(glow.get_shader_parameter("intensity") == intensity * 0.40, "current glow intensity")
			_expect(glow.render_priority == 1, "current glow render priority")
			_expect(glow.next_pass == null, "current glow has no extra pass")


func _finish_current(camera: Camera3D) -> void:
	camera.free()
	OS.set_environment("ELORIA_NATIVE_PRESENTATION", _original_mode)
	print("spell flight native current: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)
