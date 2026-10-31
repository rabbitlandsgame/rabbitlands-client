extends SceneTree
## Rendered color/crop/mask regression with deliberately visible model traps.
## Run on a real display with ELORIA_ARTIFACT_DIR naming an owned output folder.
const Background := preload("res://src/ui/map_background_2d.gd")
func _init() -> void:
	_run.call_deferred()
func _run() -> void:
	var output := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if DisplayServer.get_name() == "headless" or output.is_empty():
		push_error("Use a real display and an owned ELORIA_ARTIFACT_DIR.")
		quit(1)
		return
	if DirAccess.make_dir_recursive_absolute(output) != OK:
		push_error("Cannot create the owned render output directory.")
		quit(1)
		return
	root.min_size = Vector2i(800, 340)
	var ground := ColorRect.new()
	ground.color = Color(0.1, 0.1, 0.1)
	ground.size = Vector2(1800, 1800)
	root.add_child(ground)
	var image := Image.create(64, 64, false, Image.FORMAT_RGBA8)
	image.fill(Color.RED)
	image.fill_rect(Rect2i(32, 0, 32, 32), Color.GREEN)
	image.fill_rect(Rect2i(0, 32, 32, 32), Color.BLUE)
	image.fill_rect(Rect2i(32, 32, 32, 32), Color.YELLOW)
	image.generate_mipmaps()
	var texture := ImageTexture.create_from_image(image)
	var viewports: Array[SubViewport] = []
	for side: int in 2:
		var viewport := SubViewport.new()
		viewport.size = Vector2i(800, 600)
		viewport.own_world_3d = true
		viewport.disable_3d = true
		viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
		root.add_child(viewport)
		viewports.append(viewport)
		var camera := Camera3D.new()
		camera.projection = Camera3D.PROJECTION_ORTHOGONAL
		camera.size = 100.0
		viewport.add_child(camera)
		camera.position = Vector3(0, 200, 0)
		camera.rotation_degrees = Vector3(-90, 0, 0)
		var trap := MeshInstance3D.new()
		var mesh := BoxMesh.new()
		mesh.size = Vector3(1000, 1, 1000)
		trap.mesh = mesh
		var material := StandardMaterial3D.new()
		material.albedo_color = Color.MAGENTA
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		trap.material_override = material
		viewport.add_child(trap)
		var canvas := Background.new()
		root.add_child(canvas)
		canvas.position = Vector2(20 + side * 390, 50)
		canvas.size = Vector2(360, 240)
		canvas.configure(camera, viewport.size)
		var picture: Texture2D = texture
		if side == 1:
			var atlas := AtlasTexture.new()
			atlas.atlas = texture
			atlas.region = Rect2(32, 0, 32, 32)
			picture = atlas
		canvas.set_pictures([{"texture": picture, "extent": Rect2(-200.0/3.0, -50, 400.0/3.0, 100)}])
		canvas.set_round(side == 1)
	for frame: int in 8:
		await process_frame
	await RenderingServer.frame_post_draw
	var capture := root.get_texture().get_image()
	var saved := capture.save_png(output.path_join("direct-2d.png"))
	var tests := [{"at": Vector2i(120, 110), "want": Color.RED},
		{"at": Vector2i(280, 110), "want": Color.GREEN},
		{"at": Vector2i(120, 230), "want": Color.BLUE},
		{"at": Vector2i(280, 230), "want": Color.YELLOW},
		{"at": Vector2i(590, 170), "want": Color.GREEN}]
	var failures := int(saved != OK)
	for test: Dictionary in tests:
		var pixel := Vector2i(root.get_final_transform() * Vector2(test.at))
		var got := capture.get_pixelv(pixel)
		var wanted: Color = test.want
		if Vector3(got.r, got.g, got.b).distance_to(Vector3(wanted.r, wanted.g, wanted.b)) > 0.05:
			failures += 1
			print("PIXEL_MISMATCH ", test.at, " got ", got, " wanted ", test.want)
	var corner := capture.get_pixelv(Vector2i(root.get_final_transform() * Vector2(440, 60)))
	if corner.r > 0.4 or corner.g > 0.4 or corner.b > 0.4:
		failures += 1
	for viewport: SubViewport in viewports:
		if viewport.get_render_info(Viewport.RENDER_INFO_TYPE_VISIBLE,
				Viewport.RENDER_INFO_PRIMITIVES_IN_FRAME) != 0:
			failures += 1
	print("DIRECT_2D_RENDER failures=", failures)
	quit(1 if failures else 0)
