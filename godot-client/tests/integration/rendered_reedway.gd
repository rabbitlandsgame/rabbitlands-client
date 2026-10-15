extends "res://tests/integration/rendered_cinderbank.gd"
## Production-loader review, including each saved wagon rescue and cached reload.

func _init() -> void:
	package_id = "reedway"
	call_deferred("run")

func run() -> void:
	output = OS.get_environment("ELORIA_ARTIFACT_DIR")
	DirAccess.make_dir_recursive_absolute(output)
	root.size = Vector2i(1440,900)
	scene = Node3D.new(); root.add_child(scene)
	var environment := WorldEnvironment.new(); environment.environment = Environment.new(); scene.add_child(environment)
	var sun := DirectionalLight3D.new(); sun.shadow_enabled = true; scene.add_child(sun)
	camera = Camera3D.new(); camera.current = true; camera.fov = 48; scene.add_child(camera)
	loader = WorldLoader.new(); scene.add_child(loader)
	await load_workshop()
	WorldEnvironmentBinder.apply(loader.manifest, environment, sun)
	var flags := {"north":true,"east":false,"south":false,"west":false}
	for flag: String in road.workshop.outcome_flags: flags[flag] = false
	road.apply_state({"flags":flags})
	for direction in ["east","south","west"]:
		var flag: String = "caravan_"+direction+"_home"
		expect(not road.workshop.reveals[flag].is_empty(), "Home wagon exists: "+direction)
		expect(not road.workshop.broken[flag].is_empty(), "Stranded wagon exists: "+direction)
		for node: Node3D in road.workshop.reveals[flag]: expect(not node.visible, "Berth starts empty")
		for node: Node3D in road.workshop.broken[flag]: expect(node.visible, "Field wagon starts stranded")
	await capture("01-empty-hitching-yard",Vector3(84,31,-24),Vector3(60,1,-59))
	await capture("02-reed-pen",Vector3(80,29,-75),Vector3(60,1,-101))
	await capture("03-axle-lane",Vector3(123,24,-32),Vector3(103,1,-62))
	await capture("04-rival-yard",Vector3(78,29,13),Vector3(60,1,-21))
	await capture("05-return-road",Vector3(39,29,-29),Vector3(19,1,-61))
	for flag: String in flags: flags[flag] = true
	road.apply_state({"flags":flags})
	for flag: String in road.workshop.outcome_flags:
		for node: Node3D in road.workshop.reveals[flag]: expect(node.visible, "Rescued props visible")
		for node: Node3D in road.workshop.broken[flag]: expect(not node.visible, "Stranded wagon removed")
	await capture("06-caravan-home",Vector3(84,31,-24),Vector3(60,1,-59))
	await capture("07-wagon-detail",Vector3(57,8,-35),Vector3(48,1.9,-50))
	await capture("08-overview",Vector3(130,139,80),Vector3(60,0,-60))
	road.queue_free(); await process_frame; loader.unload_world()
	await load_workshop()
	road.apply_state({"flags":flags})
	for flag: String in road.workshop.outcome_flags:
		for node: Node3D in road.workshop.reveals[flag]: expect(node.visible, "Rescue survives cached reload")
		for node: Node3D in road.workshop.broken[flag]: expect(not node.visible, "Cache cannot duplicate a rescued wagon")
	await capture("09-cached-caravan",Vector3(84,31,-24),Vector3(60,1,-59))
	print("REEDWAY ART PASS: ",failures," failures")
	quit(failures)
