extends SceneTree
## The visible exit text must use the door, including when lifted above the HUD.
var failures := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func run() -> void:
	create_timer(90).timeout.connect(func(): push_error("Shop exit test timed out"); quit(1))
	var network := root.get_node("Network")
	network.block_for_hud_preview()
	var recorder := GDScript.new()
	recorder.source_code = 'extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tsent_frames.append(frame)\n\treturn OK\n'
	expect(recorder.reload() == OK, "the isolated transport recorder compiles")
	network.set_script(recorder)
	network.block_for_hud_preview()
	var app := root.get_node("AppState")
	app.authenticated = false
	var main = load("res://src/app/main.tscn").instantiate()
	main.set_script(load("res://tests/fixtures/offline_ui_main.gd"))
	root.add_child(main)
	for frame in range(8): await process_frame
	main.set_process(false)
	main.set_physics_process(false)
	main.camera_rig.set_process(false)
	main.camera_rig.set_physics_process(false)
	main.main_viewport.size = Vector2i(1600, 900)
	app.authenticated = true
	app.local_actor_id = 1
	app.current_map = "landfall_town"
	app.campaign = {}
	app.actors = {1:{"x":175,"y":26,"health":40,"sitting":false}}
	app.map_objects = {59204:{"object_id":59204,"x":175,"y":21}}
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/world/objects.json"))
	var exit := MapObject3D.new()
	exit.configure({"object_id":59204,"kind":EloriaProtocol.MAP_OBJECT_INTERACTIVE,
		"x":175,"y":21,"label":"Portal","detail":"The avenue."}, main.adapter, catalog)
	main.world_root.add_child(exit)
	main.map_object_nodes[59204] = exit
	var title := exit.get_node("EntranceLabel") as Label3D
	var door := exit.global_position + Vector3(0,0,1)
	var player := door + Vector3(0,0,-5.5)
	exit.update_label_focus(player, false)
	var camera: Camera3D = main.gameplay_camera
	camera.fov = 50.0
	var pitch := deg_to_rad(-50.0)
	camera.global_position = player + Vector3(0,-sin(pitch),cos(pitch)) * 12.0
	camera.look_at(player + Vector3.UP * 1.2, Vector3.UP)
	await physics_frame
	await process_frame
	var lift := exit.keep_label_above(camera, 650.0)
	var per_unit := MapObject3D.screen_pixels_per_unit(camera)
	var center := camera.unproject_position(title.global_position) \
		+ Vector2(title.offset.x, -title.offset.y) * title.pixel_size * per_unit
	var half_width := MapObject3D.label_half_width(title) * per_unit
	var click := center + Vector2(half_width * 0.8, 0)
	expect(exit.building_exit and title.visible and lift > 0, "Ilka's visible exit label is lifted above the HUD")
	var query := PhysicsRayQueryParameters3D.create(camera.project_ray_origin(click),
		camera.project_ray_origin(click) + camera.project_ray_normal(click) * 2000, MapObject3D.PICK_LAYER)
	expect(main.gameplay_world.direct_space_state.intersect_ray(query).is_empty(),
		"the label click lies outside the physical doorway pick")
	expect(main._pick_map_object(click) == exit, "the visible exit text selects Ilka's door")
	var sent: Array = network.get("sent_frames")
	sent.clear()
	var event := InputEventMouseButton.new()
	event.button_index = MOUSE_BUTTON_LEFT
	event.pressed = true
	main._handle_world_click(event, click)
	expect(sent.size() == 1 and sent[0] == EloriaProtocol.use_map_object(59204),
		"clicking Click to leave sends USE_MAP_OBJECT instead of a ground walk")
	title.visible = false
	expect(main._pick_map_object(click) == null, "hidden labels do not intercept world clicks")
	title.visible = true
	expect(main._pick_map_object(center + Vector2(half_width + 20,0)) == null,
		"clicks beside the label remain world clicks")
	main.map_object_nodes.clear()
	exit.free()
	app.current_map = "landfall"
	app.actors[1].x = 166
	app.actors[1].y = 263
	app.map_objects = {59204:{"object_id":59204,"x":166,"y":265}}
	var entrance := MapObject3D.new()
	entrance.configure({"object_id":59204,"kind":EloriaProtocol.MAP_OBJECT_INTERACTIVE,
		"x":166,"y":265,"label":"Portal","detail":"The True Note. Open to all."}, main.adapter, catalog)
	main.world_root.add_child(entrance)
	main.map_object_nodes[59204] = entrance
	title = entrance.get_node("EntranceLabel") as Label3D
	entrance.update_label_focus(entrance.global_position, false)
	camera.global_position = entrance.global_position + Vector3(0,3,10)
	camera.look_at(entrance.global_position + Vector3.UP * 1.2, Vector3.UP)
	await physics_frame
	await process_frame
	per_unit = MapObject3D.screen_pixels_per_unit(camera)
	half_width = MapObject3D.label_half_width(title) * per_unit
	click = camera.unproject_position(title.global_position) + Vector2(half_width * 0.8, 0)
	expect(entrance.building_door and main._pick_map_object(click) == entrance,
		"the exterior Click to enter label selects The True Note")
	sent.clear()
	main._handle_world_click(event, click)
	expect(sent.size() == 1 and sent[0] == EloriaProtocol.use_map_object(59204),
		"a character in front of the shop enters immediately through its label")
	sent.clear()
	event.alt_pressed = true
	main._handle_world_click(event, click)
	expect(sent.size() == 1 and sent[0] == EloriaProtocol.look_at_map_object(59204),
		"Alt on a door label still inspects the door")
	camera.look_at(camera.global_position + Vector3.BACK, Vector3.UP)
	expect(entrance.door_label_rect(camera).size == Vector2.ZERO,
		"door labels behind the camera cannot capture a click")
	app.authenticated = false
	main.free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("shop exit click: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
