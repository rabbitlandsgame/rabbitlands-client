extends SceneTree
## World text must retain its entire outline over transparent scene geometry.
## Compare the same marker with and without a transparent quad in front of it.
const SCREEN_SIZE := Vector2i(1280, 720)
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = SCREEN_SIZE
	var stage := Node3D.new()
	root.add_child(stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color(0.4, 0.5, 0.3)
	stage.add_child(environment)
	var camera := Camera3D.new()
	camera.position = Vector3(0, 3.7, 12)
	camera.fov = 50
	camera.current = true
	camera.cull_mask = 3
	stage.add_child(camera)
	var marker := MapMarker3D.new()
	stage.add_child(marker)
	marker.configure({"marker_id": 1, "x": 0, "y": 0,
		"label": "Follow Nesh's lantern"}, CoordinateAdapter.new())
	# Centre the real marker's label, independent of the adapter's tile origin.
	marker.position = Vector3.ZERO
	var label := marker.get_node("WorldLabel") as Label3D
	var front := MeshInstance3D.new()
	var quad := QuadMesh.new()
	quad.size = Vector2(10, 2)
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.albedo_color = Color(0.4, 0.5, 0.3, 1)
	material.render_priority = 0
	quad.material = material
	front.mesh = quad
	front.position = Vector3(0, 3.7, 1)
	stage.add_child(front)
	front.hide()
	var baseline := await _capture()
	front.show()
	var obstructed := await _capture()
	var center := camera.unproject_position(label.global_position)
	var baseline_outline := _black_pixels(baseline, center)
	var obstructed_outline := _black_pixels(obstructed, center)
	print("outline pixels: clear=", baseline_outline, " transparent=", obstructed_outline)
	_expect(baseline_outline > 100, "the reference text has a visible outline")
	_expect(obstructed_outline >= baseline_outline * 0.95,
		"transparent world geometry preserves the whole outline")
	var artifacts := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if not artifacts.is_empty():
		DirAccess.make_dir_recursive_absolute(artifacts)
		baseline.save_png(artifacts.path_join("outline-clear.png"))
		obstructed.save_png(artifacts.path_join("outline-transparent.png"))
	stage.queue_free()
	await process_frame
	print("rendered world label outline: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _capture() -> Image:
	for frame: int in range(8):
		await process_frame
	await RenderingServer.frame_post_draw
	return root.get_texture().get_image()

func _black_pixels(picture: Image, center: Vector2) -> int:
	var count := 0
	for y: int in range(int(center.y) - 20, int(center.y) + 20):
		for x: int in range(int(center.x) - 170, int(center.x) + 170):
			var colour := picture.get_pixel(x, y)
			if maxf(colour.r, maxf(colour.g, colour.b)) < 0.12:
				count += 1
	return count

func _expect(ok: bool, description: String) -> void:
	if not ok:
		failures += 1
		push_error(description)
