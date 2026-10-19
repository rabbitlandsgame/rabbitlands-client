extends "res://tests/integration/rendered_combat_readability.gd"
## Production actors show selection, confirmation and a customized appearance.

func run() -> void:
	root.size = Vector2i(1500, 650)
	root.content_scale_size = root.size
	root.content_scale_factor = 1.0
	models = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	animations = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	equipment = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var ui := Control.new()
	root.add_child(ui)
	var bg := ColorRect.new()
	bg.size = Vector2(root.size)
	bg.color = Color("121c24")
	ui.add_child(bg)
	label(ui, "RABBIT LANDS / TARGET MARKER APPEARANCE", Vector2(18, 15), 26)
	label(ui, "Yellow = clicked tentative target. Red = confirmed active target. Settings → Banners → Target markers", Vector2(18, 54), 18)
	for panel: int in 3:
		label(ui, ["Clicked selection", "Confirmed combat target", "Player-chosen colors and sizes"][panel], Vector2(12 + panel * 500, 95), 21)
		var container := SubViewportContainer.new()
		container.position = Vector2(5 + panel * 500, 133)
		container.size = Vector2(490, 430)
		ui.add_child(container)
		var view := SubViewport.new()
		view.size = Vector2i(490, 430)
		view.own_world_3d = true
		view.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		view.msaa_3d = Viewport.MSAA_4X
		container.add_child(view)
		var stage := Node3D.new()
		view.add_child(stage)
		light_stage(stage)
		var camera := Camera3D.new()
		camera.fov = 50
		camera.cull_mask = 3
		stage.add_child(camera)
		camera.position = Vector3(2.2, 4.0, 4.2)
		camera.look_at(Vector3(0, .55, 0))
		var player := make_actor(stage, "greyhaven_male", Vector3.ZERO, -PI * .5, false, {0: 114})
		player.set_nameplate_visible(false)
		pose(player, &"combat_idle", .5)
		var wolf := make_actor(stage, "dire_wolf", Vector3(1, 0, 0), PI * .5, true, {})
		wolf.set_nameplate_visible(false)
		wolf.set_selected(true)
		pose(wolf, &"combat_idle", .5)
		if panel > 0: wolf.set_combat_target(true)
		if panel == 2:
			var style := {"circle_size": 120, "circle_thickness": 150, "circle_color": Color("32cfe6"),
				"square_size": 115, "square_thickness": 150, "square_color": Color("8eabff"),
				"triangle_size": 140, "triangle_thickness": 150, "triangle_color": Color("ef85ee")}
			wolf.set_target_marker_style(style)
			wolf.set_selected(false)
			var other := make_actor(stage, "dire_wolf", Vector3(-1, 0, 0), -PI * .5, true, {})
			other.set_target_marker_style(style)
			other.set_nameplate_visible(false)
			other.set_selected(true)
			pose(other, &"idle", .5)
		label(ui, ["Yellow circle: clicked, tentative target.", "Red circle: confirmed active target.", "Independent appearance settings for each marker."][panel], Vector2(12 + panel * 500, 585), 16)
	for frame: int in 8: await process_frame
	await RenderingServer.frame_post_draw
	var output := "res://test-artifacts/target-markers/appearance.png"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output.get_base_dir()))
	var error := root.get_texture().get_image().save_png(ProjectSettings.globalize_path(output))
	print("TARGET_MARKER_RENDER ", "PASS" if error == OK else "FAIL")
	quit(error)
