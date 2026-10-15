extends SceneTree

const TEMP_ROOT := "res://pilot"
const STYLE_PATH := TEMP_ROOT + "/.texture-rotation-test.tres"

var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_prepare_temp_root()
	_test_zero_passthrough_and_all_slots()
	_test_cache_isolation_and_source_edits()
	_test_persistence_and_choice_switches()
	_test_bridge_extra_rotation()
	_test_unsupported_shader_fails_closed()
	await _test_rendered_rotation()
	_cleanup()
	print("map authoring texture rotation: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)


func _test_rendered_rotation() -> void:
	if DisplayServer.get_name() == "headless":
		print("SKIP: rendered rotation proof requires a real graphics backend")
		return
	var viewport := SubViewport.new()
	viewport.size = Vector2i(160, 160)
	viewport.own_world_3d = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)
	var environment_node := WorldEnvironment.new()
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.03, 0.04, 0.05)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color.WHITE
	environment.ambient_light_energy = 0.8
	environment_node.environment = environment
	viewport.add_child(environment_node)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-52.0, -28.0, 0.0)
	viewport.add_child(light)
	var camera := Camera3D.new()
	camera.position = Vector3(3.2, 2.5, 4.2)
	viewport.add_child(camera)
	camera.look_at(Vector3.ZERO)
	var mesh_instance := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = Vector3(2.4, 2.0, 2.2)
	mesh_instance.mesh = box
	viewport.add_child(mesh_instance)

	var source := StandardMaterial3D.new()
	source.albedo_texture = _asymmetric_texture()
	source.uv1_scale = Vector3(0.7, 0.7, 0.7)
	source.uv1_triplanar = true
	source.uv1_world_triplanar = true
	var style := MapAuthoringVisualStyle.new()
	style.terrain_material = source
	mesh_instance.material_override = source
	await process_frame
	await process_frame
	var native_image := viewport.get_texture().get_image()
	mesh_instance.material_override = style.get_material("terrain", 0.001)
	await process_frame
	await process_frame
	var near_zero_image := viewport.get_texture().get_image()
	mesh_instance.material_override = style.get_material("terrain", 90.0)
	await process_frame
	await process_frame
	var quarter_turn_image := viewport.get_texture().get_image()

	var timber := MapAuthoringTexturePresets.create_material(
		MapAuthoringTexturePresets.TIMBER)
	style.terrain_material = timber
	mesh_instance.material_override = timber
	await process_frame
	await process_frame
	var timber_native := viewport.get_texture().get_image()
	mesh_instance.material_override = style.get_material("terrain", 0.001)
	await process_frame
	await process_frame
	var timber_near_zero := viewport.get_texture().get_image()
	mesh_instance.material_override = style.get_material("terrain", 90.0)
	await process_frame
	await process_frame
	var timber_quarter_turn := viewport.get_texture().get_image()

	var proof := Image.create(native_image.get_width() * 3,
		native_image.get_height() * 2, false, native_image.get_format())
	proof.blit_rect(native_image, Rect2i(Vector2i.ZERO, native_image.get_size()),
		Vector2i.ZERO)
	proof.blit_rect(near_zero_image,
		Rect2i(Vector2i.ZERO, near_zero_image.get_size()),
		Vector2i(native_image.get_width(), 0))
	proof.blit_rect(quarter_turn_image,
		Rect2i(Vector2i.ZERO, quarter_turn_image.get_size()),
		Vector2i(native_image.get_width() * 2, 0))
	proof.blit_rect(timber_native,
		Rect2i(Vector2i.ZERO, timber_native.get_size()),
		Vector2i(0, native_image.get_height()))
	proof.blit_rect(timber_near_zero,
		Rect2i(Vector2i.ZERO, timber_near_zero.get_size()),
		Vector2i(native_image.get_width(), native_image.get_height()))
	proof.blit_rect(timber_quarter_turn,
		Rect2i(Vector2i.ZERO, timber_quarter_turn.get_size()),
		Vector2i(native_image.get_width() * 2, native_image.get_height()))
	var proof_path := "res://test-artifacts/texture-rotation-render-proof.png"
	var proof_directory := ProjectSettings.globalize_path("res://test-artifacts")
	if not DirAccess.dir_exists_absolute(proof_directory):
		DirAccess.make_dir_recursive_absolute(proof_directory)
	_expect(proof.save_png(ProjectSettings.globalize_path(proof_path)) == OK,
		"the rendered comparison contact sheet saves")
	var near_delta := _image_delta(native_image, near_zero_image)
	var quarter_delta := _image_delta(native_image, quarter_turn_image)
	var timber_near_delta := _image_delta(timber_native, timber_near_zero)
	var timber_quarter_delta := _image_delta(timber_native, timber_quarter_turn)
	print("rendered texture rotation deltas: near-zero=%.6f quarter-turn=%.6f" % [
		near_delta, quarter_delta])
	print("rendered texture rotation proof: ", proof_path,
		" (columns native | 0.001 degrees | 90 degrees; rows albedo | timber PBR)")
	print("rendered timber PBR deltas: near-zero=%.6f quarter-turn=%.6f" % [
		timber_near_delta, timber_quarter_delta])
	_expect(near_delta < 0.012,
		"a tiny world-triplanar rotation preserves the native material look")
	_expect(quarter_delta > near_delta * 4.0 and quarter_delta > 0.015,
		"a 90-degree world-triplanar rotation visibly turns the texture")
	_expect(timber_near_delta < 0.003,
		"a tiny rotation preserves native Timber normal and ORM shading")
	_expect(timber_quarter_delta > timber_near_delta * 2.0 and
		timber_quarter_delta > 0.004,
		"a 90-degree rotation visibly turns the full Timber PBR texture set")
	viewport.queue_free()
	await process_frame


func _asymmetric_texture() -> ImageTexture:
	var image := Image.create(32, 32, false, Image.FORMAT_RGBA8)
	for y in 32:
		for x in 32:
			var color := Color(0.82, 0.18, 0.08, 1.0)
			if x >= 10 and x < 23:
				color = Color(0.12, 0.72, 0.22, 1.0)
			elif x >= 23:
				color = Color(0.10, 0.25, 0.88, 1.0)
			if (x + y * 2) % 11 < 2:
				color = color.lightened(0.16)
			image.set_pixel(x, y, color)
	return ImageTexture.create_from_image(image)


func _image_delta(left: Image, right: Image) -> float:
	if left == null or right == null or left.get_size() != right.get_size():
		return INF
	var total := 0.0
	for y in left.get_height():
		for x in left.get_width():
			var a := left.get_pixel(x, y)
			var b := right.get_pixel(x, y)
			total += absf(a.r - b.r) + absf(a.g - b.g) + absf(a.b - b.b)
	return total / float(left.get_width() * left.get_height() * 3)


func _style_with_presets() -> MapAuthoringVisualStyle:
	var style := MapAuthoringVisualStyle.new()
	style.terrain_texture = MapAuthoringTexturePresets.GRASS
	style.road_texture = MapAuthoringTexturePresets.WORN_EARTH
	style.woodwork_texture = MapAuthoringTexturePresets.TIMBER
	style.stonework_texture = MapAuthoringTexturePresets.STONE
	style.roof_texture = MapAuthoringTexturePresets.SLATE
	return style


func _test_zero_passthrough_and_all_slots() -> void:
	var style := _style_with_presets()
	for slot: String in ["terrain", "road", "woodwork", "stonework", "roof"]:
		_expect(style.get_material(slot) == _source(style, slot),
			"%s returns its exact saved source at zero degrees" % slot)
	style.terrain_texture_rotation_degrees = 11.0
	style.road_texture_rotation_degrees = 22.0
	style.woodwork_texture_rotation_degrees = 33.0
	style.stonework_texture_rotation_degrees = 44.0
	style.roof_texture_rotation_degrees = 55.0
	for slot: String in ["terrain", "road", "woodwork", "stonework", "roof"]:
		var oriented := style.get_material(slot)
		_expect(oriented is ShaderMaterial and oriented != _source(style, slot),
			"%s gets an isolated oriented derivative" % slot)
		var oriented_shader := oriented as ShaderMaterial
		_expect(is_equal_approx(rad_to_deg(float(oriented_shader.
			get_shader_parameter("texture_rotation_radians"))),
			style.call("_rotation_degrees", slot)),
			"%s derivative carries the selected angle" % slot)
	_expect(style.get_material("terrain") == style.get_material("terrain"),
		"an unchanged source and angle reuse the cached derivative")


func _test_cache_isolation_and_source_edits() -> void:
	var style := _style_with_presets()
	style.terrain_texture_rotation_degrees = 27.0
	style.road_texture_rotation_degrees = -18.0
	var terrain_source := style.terrain_material as BaseMaterial3D
	var first_terrain := style.get_material("terrain") as ShaderMaterial
	terrain_source.albedo_color = Color(0.21, 0.37, 0.48, 1.0)
	terrain_source.uv1_scale = Vector3(0.71, 0.83, 0.94)
	var second_terrain := style.get_material("terrain") as ShaderMaterial
	_expect(second_terrain != first_terrain and
		second_terrain.get_shader_parameter("albedo_tint") == terrain_source.albedo_color and
		second_terrain.get_shader_parameter("uv_scale") == terrain_source.uv1_scale,
		"BaseMaterial edits invalidate and rebuild the oriented derivative")
	_expect(terrain_source is ORMMaterial3D and terrain_source.uv1_world_triplanar,
		"building a derivative never changes the saved source material")

	var road_source := style.worn_path_material as ShaderMaterial
	var first_road := style.get_material("road") as ShaderMaterial
	road_source.set_shader_parameter("edge_feather", 0.29)
	var second_road := style.get_material("road") as ShaderMaterial
	_expect(second_road != first_road and is_equal_approx(float(
		second_road.get_shader_parameter("edge_feather")), 0.29),
		"direct road shader parameter edits invalidate the cached duplicate")


func _test_persistence_and_choice_switches() -> void:
	var style := _style_with_presets()
	style.terrain_texture_rotation_degrees = 73.0
	style.road_texture_rotation_degrees = -41.0
	style.woodwork_texture_rotation_degrees = 19.0
	style.stonework_texture_rotation_degrees = -7.0
	style.roof_texture_rotation_degrees = 90.0
	style.terrain_texture = MapAuthoringTexturePresets.CAVERN
	style.terrain_texture = MapAuthoringTexturePresets.GRASS
	_expect(is_equal_approx(style.terrain_texture_rotation_degrees, 73.0),
		"preset switching preserves the independent terrain angle")
	var undo := UndoRedo.new()
	undo.create_action("Rotate terrain texture")
	undo.add_do_property(style, "terrain_texture_rotation_degrees", -122.0)
	undo.add_undo_property(style, "terrain_texture_rotation_degrees", 73.0)
	undo.commit_action()
	undo.undo()
	_expect(is_equal_approx(style.terrain_texture_rotation_degrees, 73.0),
		"the exported angle setter participates in property undo")
	_expect(ResourceSaver.save(style, STYLE_PATH) == OK,
		"a style with five texture angles saves")
	var reopened := ResourceLoader.load(STYLE_PATH, "Resource",
		ResourceLoader.CACHE_MODE_IGNORE) as MapAuthoringVisualStyle
	_expect(reopened != null and reopened.rotation_signature().slice(0, 5) ==
		[73.0, -41.0, 19.0, -7.0, 90.0],
		"all five degree controls survive save and reopen")


func _test_bridge_extra_rotation() -> void:
	var style := _style_with_presets()
	style.woodwork_texture_rotation_degrees = 15.0
	var first_deck := style.get_material("woodwork", 20.0) as ShaderMaterial
	var second_deck := style.get_material("woodwork", -40.0) as ShaderMaterial
	_expect(first_deck != second_deck and is_equal_approx(rad_to_deg(float(
		first_deck.get_shader_parameter("texture_rotation_radians"))), 35.0) and
		is_equal_approx(rad_to_deg(float(second_deck.get_shader_parameter(
			"texture_rotation_radians"))), -25.0),
		"independent bridge extras compose with the global woodwork angle")
	_expect(style.get_material("woodwork", -15.0) == style.timber_material,
		"an extra angle that cancels the global angle returns the source")


func _test_unsupported_shader_fails_closed() -> void:
	var style := _style_with_presets()
	var custom := ShaderMaterial.new()
	custom.shader = Shader.new()
	custom.shader.code = "shader_type spatial; void fragment() { EMISSION = vec3(1.0); }"
	style.terrain_material = custom
	style.terrain_texture_rotation_degrees = 45.0
	_expect(style.get_material("terrain") == custom,
		"an unknown custom shader remains intact when rotation is unsupported")


func _source(style: MapAuthoringVisualStyle, slot: String) -> Material:
	match slot:
		"terrain":
			return style.terrain_material
		"road":
			return style.worn_path_material
		"woodwork":
			return style.timber_material
		"stonework":
			return style.stone_material
		"roof":
			return style.slate_material
	return null


func _cleanup() -> void:
	var absolute_path := ProjectSettings.globalize_path(STYLE_PATH)
	if FileAccess.file_exists(STYLE_PATH):
		DirAccess.remove_absolute(absolute_path)


func _prepare_temp_root() -> void:
	if not DirAccess.dir_exists_absolute(ProjectSettings.globalize_path(TEMP_ROOT)):
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(TEMP_ROOT))


func _expect(condition: bool, message: String) -> bool:
	if condition:
		print("PASS: ", message)
		return true
	_failures += 1
	push_error("FAIL: " + message)
	return false
