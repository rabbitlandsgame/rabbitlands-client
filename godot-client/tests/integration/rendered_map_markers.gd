extends SceneTree
## Rendered evidence for server-placed map markers.
##
## The "before" frame is the full map with the marker packet already reduced
## into state but the map named as somewhere else - which is exactly what the
## shipped client did with every marker, because nothing decoded command 90 at
## all. The "after" frame is the same map once the marker belongs to it.
##
## The gameplay capture verifies the separate green effect and floating label.

const SCREEN_SIZE := Vector2i(1280, 720)

var _artifacts := ""
var _failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/phase2")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE

	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	(main.get_node("LoginPanel") as Control).hide()
	var app_state: Node = root.get_node("/root/AppState")
	app_state.set("authenticated", true)
	# Use the fixture ground and a known transform, without asynchronously
	# loading a region whose real tile origin differs from this little stage.
	app_state.set("current_map", "four_gates")
	main.set("loaded_server_map", "four_gates")
	var adapter := CoordinateAdapter.new()
	main.set("adapter", adapter)
	(main.get("console_commands") as ConsoleCommands).marks.clear()
	(main.get("map_marker_overlay") as Control).configure(
		main.get("full_map_camera"), adapter, (main.get("full_map_viewport") as SubViewport).size)

	# A plain lit ground so the top-down cameras have something to render.
	var stage: Node3D = main.get_node(
		"GameView/ViewportContainer/Viewport/WorldRoot") as Node3D
	var ground_mesh := PlaneMesh.new()
	ground_mesh.size = Vector2(120.0, 120.0)
	var ground_material := StandardMaterial3D.new()
	ground_material.albedo_color = Color(0.29, 0.35, 0.24)
	ground_mesh.material = ground_material
	var ground := MeshInstance3D.new()
	ground.mesh = ground_mesh
	ground.position.y = -0.02
	stage.add_child(ground)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-52.0, 38.0, 0.0)
	stage.add_child(sun)
	for _settle: int in range(4):
		await process_frame

	# A marker the server placed on another map: held, and drawn nowhere.
	# Tile (6, 4): a marker beside the player, where a top-down map can show it.
	var elsewhere := PackedByteArray([0xea, 0x01, 0x06, 0x00, 0x04, 0x00])
	elsewhere.append_array(_nul("./maps/somewhere_else.elm"))
	elsewhere.append_array(_nul("Reed bank"))
	app_state.call("_on_packet", 90, elsewhere)
	main.call("_on_map_button_pressed")
	for _settle: int in range(8):
		await process_frame
	var markers: Dictionary = main.get("map_marker_nodes") as Dictionary
	_expect(markers.is_empty(),
		"a marker for another map is drawn nowhere")
	await _capture("map-marker-before.png",
		"the full map with the marker packet reduced but belonging elsewhere -"
			+ " which is what every marker looked like before command 90 decoded")

	var here := PackedByteArray([0xea, 0x01, 0x06, 0x00, 0x04, 0x00])
	here.append_array(_nul("./maps/four_gates.elm"))
	here.append_array(_nul("Reed bank"))
	app_state.call("_on_packet", 90, here)
	for _settle: int in range(8):
		await process_frame
	markers = main.get("map_marker_nodes") as Dictionary
	_expect(markers.size() == 1, "the marker is drawn on the map it belongs to")
	await _capture("map-marker-full-map.png",
		"the same map with the server's waypoint marker and its label")

	main.call("_on_map_button_pressed")
	for _settle: int in range(6):
		await process_frame
	var pin: MapMarker3D = markers[490]
	_expect((pin.get_node("WorldLabel") as Label3D).text == "Reed bank",
		"the gameplay marker names the destination")
	RenderingServer.force_draw(false)
	var viewport: SubViewport = main.get("main_viewport") as SubViewport
	var world_image: Image = viewport.get_texture().get_image()
	_expect(_green_pixels(world_image) > 20,
		"green marker light is actually rendered by the gameplay camera")
	await _capture("map-marker-gameplay-view.png",
		"the gameplay view shows a green ground glow, rising sparks and the label")

	# Observe several particle lifetimes, including refreshes whose REMOVE
	# and ADD land on different rendered frames. The glow alone must not
	# conceal an empty/reset particle stream.
	var glow: MeshInstance3D = pin.get_node("GroundGlow")
	glow.hide()
	var sparks: GPUParticles3D = pin.get_node("RisingSparks")
	var spark_id: int = sparks.get_instance_id()
	var minimum_sparks := 1000000
	var samples := 0
	var started: int = Time.get_ticks_msec()
	while Time.get_ticks_msec() - started < int(sparks.lifetime * 3000.0):
		if samples % 8 == 0:
			app_state.call("_on_packet", 91, PackedByteArray([0xea, 0x01]))
		await create_timer(0.06).timeout
		RenderingServer.force_draw(false)
		var spark_pixels: int = _green_pixels(viewport.get_texture().get_image())
		minimum_sparks = mini(minimum_sparks, spark_pixels)
		_expect(spark_pixels > 0, "sparks remain visible at loop sample %d" % samples)
		if samples % 8 == 0:
			app_state.call("_on_packet", 90, here)
			var refreshed: MapMarker3D = markers[490]
			if not _expect(refreshed == pin
				and refreshed.get_node("RisingSparks").get_instance_id() == spark_id,
				"a rendered refresh preserves the running particle stream"):
				quit(_failures)
				return
		samples += 1
	_expect(samples >= 12, "continuity sampled throughout three particle lifetimes")
	print("marker continuity: samples=%d minimum_spark_pixels=%d" % [samples, minimum_sparks])
	glow.show()

	app_state.call("_on_packet", 91, PackedByteArray([0xea, 0x01]))
	await create_timer(0.3).timeout
	for _settle: int in range(4):
		await process_frame
	_expect((main.get("map_marker_nodes") as Dictionary).is_empty(),
		"the server takes the marker away again")
	RenderingServer.force_draw(false)
	_expect(_green_pixels(viewport.get_texture().get_image()) == 0,
		"the gameplay effect disappears when the server removes its marker")

	var lesson := PackedByteArray([255, 133])
	lesson.append_array(_nul("The Gate Warden\n\n"
		+ "Ilyon has held this gate long enough to stop being impressed by arrivals. "
		+ "Walk close and click him to talk.\n\n"
		+ "Anything a person asks of you is written into your quest log, so you "
		+ "never have to remember an errand exactly as it was worded.\n\n"
		+ "While you are here: what you type reaches everyone standing near you. "
		+ "Use #jc to join a numbered channel, then put @ in front of a message "
		+ "to send it there instead."))
	app_state.call("_on_packet", 0, lesson)
	for _settle: int in range(4):
		await process_frame
	var panel: Control = main.get("popup_panel") as Control
	_expect(panel.visible and Rect2(Vector2.ZERO, Vector2(SCREEN_SIZE)).encloses(
		panel.get_global_rect()), "the next tutorial lesson is visible and fits the screen")
	await _capture("tutorial-plaza-next-instructions.png", "the next lesson after reaching the plaza")

	app_state.set("authenticated", false)
	main.queue_free()
	await process_frame
	print("rendered map markers: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)

func _nul(value: String) -> PackedByteArray:
	var bytes: PackedByteArray = value.to_utf8_buffer()
	bytes.append(0)
	return bytes

func _capture(name: String, description: String) -> void:
	await process_frame
	RenderingServer.force_draw(false)
	var image: Image = root.get_texture().get_image()
	_expect(image != null and image.get_size() == SCREEN_SIZE,
		"%s is a full %dx%d frame" % [name, SCREEN_SIZE.x, SCREEN_SIZE.y])
	if image == null:
		return
	_expect(_has_colour_variation(image),
		"%s contains rendered colour variation rather than a dummy frame" % name)
	_expect(image.save_png(_artifacts.path_join(name)) == OK,
		"%s is written" % name)
	print("capture ", name, ": ", description)

func _has_colour_variation(image: Image) -> bool:
	var lowest := 2.0
	var highest := -1.0
	for y: int in range(0, image.get_height(), 8):
		for x: int in range(0, image.get_width(), 8):
			var luminance: float = image.get_pixel(x, y).get_luminance()
			lowest = minf(lowest, luminance)
			highest = maxf(highest, luminance)
	return highest - lowest > 0.02

func _green_pixels(image: Image) -> int:
	var found := 0
	for y: int in image.get_height():
		for x: int in image.get_width():
			var colour: Color = image.get_pixel(x, y)
			if colour.g > 0.6 and colour.g > colour.r * 1.35 and colour.g > colour.b * 1.5:
				found += 1
	return found

func _expect(value: bool, label: String) -> bool:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
	return value
