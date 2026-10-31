extends SceneTree

## A picture-only capture at the reported Reedfall position, with both nearby
## territories resident. No network or world-package imports are needed.
func _init() -> void:
	call_deferred("run")

func run() -> void:
	if DisplayServer.get_name() == "headless":
		push_error("The seam capture requires a rendered display.")
		quit(1)
		return
	root.size = Vector2i(640, 640)
	root.content_scale_mode = Window.CONTENT_SCALE_MODE_DISABLED
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	root.get_node("Network").set_process(false)
	main.exterior_stream.set_process(false)
	var state: Node = root.get_node("AppState")
	# Start on Hearthcroft so the far pictures already exist in its frame,
	# exactly as they do before the player's reported crossing into Reedfall.
	var departure := WorldManifest.load_file("res://../eloria-assets/maps/continent-v2/hearthcroft/client/world.json")
	state.current_map = "hearthcroft"
	main.adapter = departure.coordinate_adapter()
	main.exterior_stream.active_map = "hearthcroft"
	main.exterior_stream.active_root = main.world_root
	main.exterior_stream.active_manifest = departure
	main._install_map_picture(departure)
	state.current_map = "reedfall"
	var manifest := WorldManifest.load_file("res://../eloria-assets/maps/continent-v2/reedfall/client/world.json")
	main.adapter = manifest.coordinate_adapter()
	main.exterior_stream.active_map = "reedfall"
	main.exterior_stream.active_root = main.world_root
	main.exterior_stream.active_manifest = manifest
	for map_id: String in ["hearthcroft", "twinbrook"]:
		var neighbour_manifest := WorldManifest.load_file("res://../eloria-assets/maps/continent-v2/" + map_id + "/client/world.json")
		var neighbour := Node3D.new()
		main.world_root.add_child(neighbour)
		neighbour.transform = main.exterior_stream.region_transform(map_id)
		main.exterior_stream.residents[map_id] = {"root": neighbour, "manifest": neighbour_manifest}
	var point: Vector3 = main.adapter.tile_center(305, 424)
	main.exterior_stream._last_position = point
	main.exterior_stream._refresh_views()
	for map_id: String in main.exterior_stream.residents:
		print("MINIMAP FRAME ", map_id, " ", main.exterior_stream.residents[map_id].root.transform)
	main._install_map_picture(manifest)
	main.map_viewport.size = Vector2i(512, 512)
	main.map_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	main.map_camera.position = Vector3(point.x, 220.0, point.z)
	main.map_camera.rotation = Vector3(-PI / 2, PI / 2, 0)
	main.map_camera.size = 180.0
	# Capture the real direct UI background, not an unused SubViewportTexture.
	# Place it on the root canvas at one logical pixel per captured pixel, so
	# this seam probe remains independent of the player's HUD arrangement.
	var background: Control = main.minimap_background
	background.reparent(root)
	background.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	background.position = Vector2.ZERO
	background.size = Vector2(512, 512)
	background.set_round(false)
	background.refresh(main.map_viewport.size)
	main.hide()
	main.main_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	for _frame: int in range(10):
		await process_frame
	await RenderingServer.frame_post_draw
	var out := OS.get_environment("ELORIA_MINIMAP_OUT")
	if out.is_empty():
		out = ProjectSettings.globalize_path("res://../test-artifacts/reedfall-minimap-seams.png")
	var captured: Image = root.get_texture().get_image().get_region(Rect2i(0, 0, 512, 512))
	var error: Error = captured.save_png(out)
	print("Reedfall minimap capture: ", out, " saved=", error == OK)
	main.queue_free()
	background.queue_free()
	await process_frame
	await process_frame
	quit(0 if error == OK else 1)
