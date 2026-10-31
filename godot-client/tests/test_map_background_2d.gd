extends SceneTree
## CPU/headless checks for direct cartography drawing. Existing marker and
## camera picking APIs are the independent alignment references; no world
## geometry, imported assets, game session or rendered benchmark is needed.
const Background := preload("res://src/ui/map_background_2d.gd")
const Markers := preload("res://src/ui/minimap_marker_overlay.gd")
var checks := 0
var failures := 0

func _init() -> void:
	_run.call_deferred()

func _expect(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error("Map background 2D: " + message)

func _run() -> void:
	var viewport := SubViewport.new()
	viewport.size = Vector2i(800, 600)
	viewport.own_world_3d = true
	viewport.disable_3d = true
	viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	root.add_child(viewport)
	var camera := Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.keep_aspect = Camera3D.KEEP_HEIGHT
	camera.size = 100.0
	viewport.add_child(camera)
	camera.position = Vector3(0, 200, 0)
	camera.look_at(Vector3.ZERO, Vector3.FORWARD)
	var background := Background.new()
	root.add_child(background)
	background.size = Vector2(700, 300)
	background.configure(camera, viewport.size)
	var image := Image.create(8, 8, false, Image.FORMAT_RGBA8)
	image.fill(Color.RED)
	image.fill_rect(Rect2i(4, 0, 4, 4), Color.GREEN)
	image.fill_rect(Rect2i(0, 4, 4, 4), Color.BLUE)
	image.fill_rect(Rect2i(4, 4, 4, 4), Color.YELLOW)
	var texture := ImageTexture.create_from_image(image)
	var extent := Rect2(-40, -30, 80, 60)
	background.set_pictures([{"texture": texture, "extent": extent}])
	var quads: Array[Dictionary] = background.projected_pictures()
	_expect(quads.size() == 1, "visible picture retained with its corners outside/inside the view")
	_expect(background.image_rect().is_equal_approx(Rect2(150, 0, 400, 300)),
		"wide control letterboxes the logical camera image")
	_expect(quads[0].points[0].is_equal_approx(Vector2(230, 60))
		and quads[0].points[2].is_equal_approx(Vector2(470, 240)),
		"known north-up world corners land at the expected screen pixels")
	_expect(quads[0].uvs == PackedVector2Array([Vector2.ZERO, Vector2.RIGHT, Vector2.ONE, Vector2.DOWN]),
		"north-up image corners keep their authored orientation")

	var markers := Markers.new()
	root.add_child(markers)
	var frame := Transform3D(Basis(Vector3.UP, deg_to_rad(17.0)), Vector3(4, 7, -3))
	for logical: Vector2i in [Vector2i(640, 480), Vector2i(480, 900), Vector2i(1024, 256)]:
		viewport.size = logical
		for yaw: float in [0.0, 30.0, 90.0, -137.0]:
			for zoom: float in [50.0, 200.0]:
				camera.transform = Transform3D(Basis(Vector3.UP, deg_to_rad(yaw))
					* Basis.from_euler(Vector3(-PI * 0.5, 0, 0)), Vector3(4, 200, -3))
				camera.size = zoom
				background.size = Vector2(711, 389)
				background.configure(camera, logical)
				markers.size = background.size
				markers.configure(camera, logical)
				background.set_pictures([{"texture": texture, "extent": Rect2(-20, -10, 40, 20),
					"transform": frame}])
				quads = background.projected_pictures()
				_expect(quads.size() == 1, "transformed region remains present across aspect/rotation/zoom")
				if quads.is_empty():
					continue
				var world := frame * Vector3(0, 0, 0)
				var centre: Vector2 = (quads[0].points[0] + quads[0].points[2]) * 0.5
				var mark: Variant = markers.mark_point({"position": world})
				_expect(mark is Vector2 and (mark as Vector2).distance_to(centre) < 0.002,
					"existing actor marker lands on its background world position")
				var rect: Rect2 = background.image_rect()
				var pixel := (centre - rect.position) / rect.size * Vector2(logical)
				var ray := camera.project_ray_origin(pixel)
				var direction := camera.project_ray_normal(pixel)
				var picked := ray + direction * ((world.y - ray.y) / direction.y)
				_expect(picked.distance_to(world) < 0.002,
					"existing camera picking round-trips the background position")

	# A region covering the whole view cannot be dropped merely because every
	# one of its four corners lies off screen. A remote region may be skipped.
	background.set_pictures([{"texture": texture, "extent": Rect2(-10000, -10000, 20000, 20000)},
		{"texture": texture, "extent": Rect2(100000, 100000, 40, 40)}])
	_expect(background.projected_pictures().size() == 1, "large covering quad retained and remote quad culled")
	camera.transform = Transform3D(Basis.from_euler(Vector3(-PI * 0.5, 0, 0)), Vector3(0, 200, 0))
	camera.size = 100.0
	viewport.size = Vector2i(800, 600)
	background.configure(camera, viewport.size)
	background.set_pictures([{"texture": texture, "extent": extent}])
	var full: PackedVector2Array = background.projected_pictures()[0].points
	var cropped := AtlasTexture.new()
	cropped.atlas = texture
	cropped.region = Rect2(4, 0, 4, 4)
	background.set_pictures([{"texture": cropped, "extent": extent}])
	quads = background.projected_pictures()
	_expect(quads[0].texture == texture and quads[0].points == full,
		"cropped region uses underlying texture without changing its world rectangle")
	_expect(quads[0].uvs[0] == Vector2(0.5, 0) and quads[0].uvs[2] == Vector2(1, 0.5),
		"cropped map selects only its authored quadrant")
	var uv: Vector2 = (quads[0].uvs[0] + quads[0].uvs[2]) * 0.5
	_expect(image.get_pixel(int(uv.x * 8), int(uv.y * 8)) == Color.GREEN,
		"cropped texture samples green rather than the complete four-colour image")

	var margined := AtlasTexture.new()
	margined.atlas = texture
	margined.region = Rect2(4, 0, 4, 4)
	margined.margin = Rect2(2, 2, 4, 4)
	background.set_pictures([{"texture": margined, "extent": extent}])
	quads = background.projected_pictures()
	_expect(quads[0].points[0].distance_to(full[0] + (full[2] - full[0]) * 0.25) < 0.002
		and quads[0].points[2].distance_to(full[0] + (full[2] - full[0]) * 0.75) < 0.002,
		"atlas transparent margins preserve their logical empty space")
	var nested := AtlasTexture.new()
	nested.atlas = margined
	nested.region = Rect2(2, 2, 4, 4)
	background.set_pictures([{"texture": nested, "extent": extent}])
	quads = background.projected_pictures()
	_expect(quads[0].points == full and quads[0].texture == texture
		and quads[0].uvs[0] == Vector2(0.5, 0) and quads[0].uvs[2] == Vector2(1, 0.5),
		"nested crop of a margined atlas resolves its exact visible source region")
	background.set_pictures([{"texture": texture, "extent": extent},
		{"texture": cropped, "extent": extent}])
	quads = background.projected_pictures()
	_expect(quads.size() == 2 and quads[1].uvs[0] == Vector2(0.5, 0),
		"current picture supplied last remains above neighbors")
	viewport.size = Vector2i(500, 1000)
	background.refresh(viewport.size)
	_expect(background.image_rect().size.is_equal_approx(Vector2(194.5, 389)),
		"refresh accepts logical viewport resizing before a map redraw")
	background.refresh()
	_expect(background.image_rect().size.is_equal_approx(Vector2(194.5, 389)),
		"resize signal refresh preserves the last positive logical viewport size")
	background.set_round(true)
	background.refresh()
	_expect(background.material is ShaderMaterial
		and (background.material as ShaderMaterial).shader.get_mode() == Shader.MODE_CANVAS_ITEM,
		"only a 2D mask material is created")
	_expect((background.material as ShaderMaterial).get_shader_parameter("rounded") == true,
		"round clipping is selected without changing polygon UVs")
	var fitted: Rect2 = background.image_rect()
	_expect((background.material as ShaderMaterial).get_shader_parameter("image_rect")
		== Vector4(fitted.position.x, fitted.position.y, fitted.size.x, fitted.size.y),
		"mask uses the displayed image rectangle, including letterboxing")
	_expect(background.clip_contents and background.mouse_filter == Control.MOUSE_FILTER_IGNORE,
		"background clips to its control and leaves all map interactions to its parent")
	_expect(background.get_child_count() == 0 and background.find_children("*", "Node3D").is_empty(),
		"background creates no scene nodes or 3D geometry")
	_expect(viewport.own_world_3d and viewport.disable_3d
		and viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED,
		"picture/round/refresh calls never reactivate the 3D viewport")
	background.clear()
	_expect(background.projected_pictures().is_empty(), "clear releases all retained map pictures")
	markers.queue_free()
	background.queue_free()
	viewport.queue_free()
	await process_frame
	print("Map background 2D: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
