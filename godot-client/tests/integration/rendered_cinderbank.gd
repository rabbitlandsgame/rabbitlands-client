extends SceneTree
## Art review through the production loader, including cached restoration.
var failures := 0
var output := ""
var loader: WorldLoader
var scene: Node3D
var camera: Camera3D
var road: Node3D
var package_id := "cinderbank"

func _init() -> void: call_deferred("run")

func expect(ok: bool, text: String) -> void:
	if not ok:
		failures += 1
		push_error(text)

func load_workshop() -> void:
	loader.load_world(ProjectSettings.globalize_path("res://../eloria-assets/maps/" + package_id + "/world.json"))
	var deadline := Time.get_ticks_msec() + 60000
	while loader.world_root == null and Time.get_ticks_msec() < deadline: await process_frame
	expect(loader.world_root != null, "Workshop imports")
	if loader.world_root == null: quit(1); return
	road = load("res://src/world/road_scene.gd").new()
	scene.add_child(road)
	road.configure(loader.world_root, loader.manifest)
	for _i in range(8): await process_frame
	if package_id == "cinderbank": expect(road.workshop.machinery.size() == 2, "Flywheel and piston survive load")
	for motion: Dictionary in road.workshop.machinery:
		expect(motion.node.get_child_count() > 0, "Moving part contains geometry after load/cache")

func capture(label: String, eye: Vector3, target: Vector3) -> void:
	camera.look_at_from_position(eye, target)
	for _i in range(8): await process_frame
	await RenderingServer.frame_post_draw
	expect(root.get_texture().get_image().save_png(output.path_join(label + ".png")) == OK, "Saved " + label)

func run() -> void:
	output = OS.get_environment("ELORIA_ARTIFACT_DIR")
	DirAccess.make_dir_recursive_absolute(output)
	root.size = Vector2i(1440, 900)
	scene = Node3D.new(); root.add_child(scene)
	var environment := WorldEnvironment.new(); environment.environment = Environment.new(); scene.add_child(environment)
	var sun := DirectionalLight3D.new(); sun.shadow_enabled = true; scene.add_child(sun)
	camera = Camera3D.new(); camera.current = true; camera.fov = 48; scene.add_child(camera)
	loader = WorldLoader.new(); scene.add_child(loader)
	await load_workshop()
	WorldEnvironmentBinder.apply(loader.manifest, environment, sun)
	var flags := {"north":true, "east":false, "south":false, "west":false,
		"forge_lit":false, "sword_ready":false, "pump_repaired":false, "order_ready":false}
	road.apply_state({"flags":flags})
	expect(not road.workshop.is_processing(), "Broken pump is stopped")
	await capture("01-work-court", Vector3(83,30,-30), Vector3(60,1,-62))
	await capture("02-raw-yard", Vector3(78,26,-76), Vector3(60,1,-101))
	await capture("03-reading-room", Vector3(118,20,-38), Vector3(104,1,-65))
	await capture("04-foundry-before", Vector3(76,19,5), Vector3(60,1,-19))
	await capture("05-pump-before", Vector3(69,7,-2), Vector3(60,1.8,-12))
	for flag: String in flags: flags[flag] = true
	road.apply_state({"flags":flags})
	for flag: String in road.workshop.FLAGS:
		expect(not road.workshop.reveals[flag].is_empty(), "Authored restoration exists: " + flag)
		for node: Node3D in road.workshop.reveals[flag]: expect(node.visible, "Restored prop visible")
	for node: Node3D in road.workshop.broken.pump_repaired: expect(not node.visible, "Broken brace is replaced")
	var wheel: Node3D = road.workshop.machinery[0].node
	var angle := wheel.rotation.z
	await create_timer(.25).timeout
	expect(wheel.rotation.z != angle, "Repaired flywheel moves")
	await capture("06-pump-repaired", Vector3(69,7,-2), Vector3(60,1.8,-12))
	await capture("07-foundry-restored", Vector3(76,19,5), Vector3(60,1,-19))
	await capture("08-dispatch", Vector3(30,17,-39), Vector3(17,1,-61))
	await capture("09-overview", Vector3(127,132,67), Vector3(60,0,-60))
	road.queue_free(); await process_frame; loader.unload_world()
	await load_workshop()
	road.apply_state({"flags":flags})
	expect(road.workshop.is_processing(), "Saved repair resumes after cached reload")
	await capture("10-cached-repair", Vector3(69,7,-2), Vector3(60,1.8,-12))
	print("CINDERBANK ART PASS: ", failures, " failures")
	quit(failures)
