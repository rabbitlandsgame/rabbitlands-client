extends SceneTree
## Pixel evidence: ground changes independently of the subject; overhead text
## retains identical pixels through scene grading, resizing and camera moves.
const LabelStyle := preload("res://src/ui/world_label_style.gd")
const Overlay := preload("res://src/ui/world_text_overlay.gd")
var failures := 0
var artifacts := ""
var view: SubViewport

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if artifacts.is_empty():
		artifacts = ProjectSettings.globalize_path("res://test-artifacts/appearance-modes")
	DirAccess.make_dir_recursive_absolute(artifacts)
	root.size = Vector2i(960, 640)
	var canvas := Control.new()
	root.add_child(canvas)
	canvas.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var display := TextureRect.new()
	canvas.add_child(display)
	display.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	display.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	view = SubViewport.new()
	view.size = root.size
	view.own_world_3d = true
	view.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	display.add_child(view)
	display.texture = view.get_texture()
	var stage := Node3D.new()
	view.add_child(stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("323b46")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color.WHITE
	environment.environment.ambient_light_energy = 0.65
	stage.add_child(environment)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55, -20, 0)
	stage.add_child(sun)
	var camera := Camera3D.new()
	stage.add_child(camera)
	camera.position = Vector3(0, 7, 11)
	camera.look_at(Vector3(0, 0.8, 0))
	camera.cull_mask = 3
	camera.current = true
	var terrain := MeshInstance3D.new()
	terrain.name = "Terrain_fixture"
	var plane := PlaneMesh.new()
	plane.size = Vector2(24, 24)
	var ground_mesh := ArrayMesh.new()
	ground_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, plane.get_mesh_arrays())
	var ground := StandardMaterial3D.new()
	ground.albedo_color = Color("6e9354")
	ground_mesh.surface_set_material(0, ground)
	terrain.mesh = ground_mesh
	stage.add_child(terrain)
	var subject := MeshInstance3D.new()
	subject.name = "Subject_fixture"
	subject.mesh = BoxMesh.new()
	(subject.mesh as BoxMesh).size = Vector3(2.8, 2.5, 1.8)
	var material := StandardMaterial3D.new()
	material.albedo_color = Color("c36d37")
	material.roughness = 0.7
	subject.mesh.surface_set_material(0, material)
	subject.position.y = 1.25
	stage.add_child(subject)
	var label := Label3D.new()
	label.text = "Moss Hound  120/120"
	label.position.y = 3.1
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.no_depth_test = true
	label.fixed_size = true
	label.modulate = Color("fff25a")
	LabelStyle.apply(label, 20, 0.0012953, 1)
	stage.add_child(label)
	var overlay := Overlay.new()
	canvas.add_child(overlay)
	overlay.configure(view)
	var manifest := WorldManifest.new()
	manifest.data = {"asset": {"id": "fixture"},
		"continentGeography": {"geometryMode": "continent-chunks-v1"},
		"environment": {"sun": {"enabled": true}}}
	LookProfile.set_player_mode(LookProfile.Mode.ORIGINAL)
	var original := await _capture()
	original.save_png(artifacts.path_join("original.png"))
	var original_text := overlay.text_viewport.get_texture().get_image()
	var center := camera.unproject_position(subject.position + Vector3(0, 0.3, 0))
	LookProfile.set_player_mode(LookProfile.Mode.PAINTED_GROUND)
	LookSwitch.sync(stage, manifest)
	var painted := await _capture()
	painted.save_png(artifacts.path_join("painted-ground.png"))
	_expect(original.get_data() != painted.get_data(), "painted terrain changes visible pixels")
	_expect(_crop(original, center) == _crop(painted, center),
		"the subject retains exactly the Original pixels")
	_expect(original_text.get_data() == overlay.text_viewport.get_texture().get_image().get_data(),
		"overhead text pixels are identical in Original and Painted ground")
	LookProfile.set_player_mode(LookProfile.Mode.FULL_PAINTED)
	LookSwitch.sync(stage, manifest)
	LookGrade.apply(manifest, environment, sun)
	var full := await _capture()
	full.save_png(artifacts.path_join("full-painted.png"))
	_expect(_crop(original, center) != _crop(full, center),
		"Full painted still changes the subject through global lighting and grade")
	var text := overlay.text_viewport.get_texture().get_image()
	_expect(original_text.get_data() == text.get_data(),
		"Full painted grade and glow leave overhead text pixels unchanged")
	var ink := 0
	for y: int in text.get_height():
		for x: int in text.get_width():
			if text.get_pixel(x, y).a > 0.5:
				ink += 1
	_expect(ink > 100, "the clean pass contains legible, opaque text")
	view.size = Vector2i(1280, 720)
	root.size = view.size
	camera.fov = 62
	camera.position += Vector3(1, 0.5, 0)
	await _capture()
	_expect(overlay.text_viewport.size == view.size
		and overlay.text_camera.global_transform == camera.global_transform
		and overlay.text_camera.fov == camera.fov,
		"overlay follows native resolution and camera projection changes")
	label.hide()
	await _capture()
	text = overlay.text_viewport.get_texture().get_image()
	_expect(text.get_pixel(text.get_width() / 2, text.get_height() / 2).a == 0.0,
		"the pass background stays transparent")
	canvas.queue_free()
	await process_frame
	print("rendered appearance modes: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _capture() -> Image:
	for frame: int in 5:
		await process_frame
	await RenderingServer.frame_post_draw
	return root.get_texture().get_image()

func _crop(picture: Image, center: Vector2) -> PackedByteArray:
	return picture.get_region(Rect2i(Vector2i(center) - Vector2i(16, 16), Vector2i(32, 32))).get_data()

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
	else:
		print("PASS " + message)
