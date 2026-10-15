extends Node3D

## Renders the occluded-actor silhouette in a real region, with and without,
## from the game's own isometric rig. One-off illustration, not a test.
##
##     Godot --path godot-client --rendering-driver opengl3 \
##         src/dev/silhouette_demo.tscn -- --package=<dir> --out=<dir>

func _ready() -> void:
	var opts: Dictionary = {}
	for arg: String in OS.get_cmdline_user_args():
		var bare: String = arg.lstrip("-")
		if "=" in bare:
			opts[bare.get_slice("=", 0)] = bare.substr(bare.find("=") + 1)
	var package: String = str(opts.get("package", ""))
	var out_dir: String = str(opts.get("out", ""))
	DirAccess.make_dir_recursive_absolute(out_dir)

	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	state.set_handle_binary_image(GLTFState.HANDLE_BINARY_EMBED_AS_BASISU)
	var err := doc.append_from_buffer(
		FileAccess.get_file_as_bytes(package.path_join("world.glb")), package, state)
	if err != OK:
		print("[demo] load failed: ", err)
		get_tree().quit(2)
		return
	var scene: Node3D = doc.generate_scene(state)
	add_child(scene)

	var env := Environment.new()
	var sky := Sky.new()
	var sky_mat := ProceduralSkyMaterial.new()
	sky_mat.sky_top_color = Color(0.36, 0.52, 0.74)
	sky_mat.sky_horizon_color = Color(0.72, 0.78, 0.84)
	sky.sky_material = sky_mat
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.5
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)
	var sun := DirectionalLight3D.new()
	sun.light_energy = 1.15
	sun.rotation = Vector3(deg_to_rad(-32.0), deg_to_rad(148.0), 0.0)
	add_child(sun)

	# A canopy near the middle of the forest, and the actor placed so that the
	# camera's line of sight runs straight through it.
	var canopies: Array[Vector3] = []
	# Ordinary forest trees only. The Great Tree is a landmark platform, and
	# standing under it photographs the underside of a deck, not a canopy.
	var nodes: Array[Node] = scene.find_children("Tree_*_Canopy", "MeshInstance3D", true, false)
	for node: Node in nodes:
		canopies.append((node as Node3D).global_position)
	# The camera has to stand in open air or the frame is just leaves. Pick a
	# tree whose 26 m camera position has nothing else growing near it.
	var pitch0 := deg_to_rad(-60.0)
	var back := Vector3(0.0, -sin(pitch0), cos(pitch0)) * 26.0
	var canopy: Node3D = null
	var best := -1.0
	for i in nodes.size():
		var origin: Vector3 = canopies[i]
		var eye: Vector3 = origin - Vector3(0.0, 0.0, 6.0) + Vector3.UP + back
		var nearest := INF
		for j in canopies.size():
			if j == i:
				continue
			nearest = minf(nearest, eye.distance_to(canopies[j]))
		# The tree overhead still has to be a real canopy, not a sapling on the
		# barrens: only count a candidate whose own crown is wide and near.
		if nearest > best and origin.distance_to(Vector3(0, origin.y, 0)) < 320.0:
			best = nearest
			canopy = nodes[i] as Node3D
	print("[demo] clearest camera position has %.1f m to the next tree" % best)
	if canopy == null:
		print("[demo] no canopy found")
		get_tree().quit(2)
		return
	var stand: Vector3 = canopy.global_position - Vector3(0.0, 0.0, 6.0)
	print("[demo] canopy=%s at %s, actor at %s" % [canopy.name, canopy.global_position, stand])

	var registry: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string("res://data/actors/models.json"))
	var model_config: Dictionary = (registry.get("models", {}) as Dictionary).get(
		"luminous_female", {}) as Dictionary
	var animation_config: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string(str(model_config.get("animationMap", ""))))
	var equipment_config: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var actor := ReplicatedActor3D.new()
	add_child(actor)
	actor.configure({"actor_id": 1, "x": 0, "y": 0, "rotation": 0,
		"appearance": {"skin": 1, "hair": 2, "eyes": 3,
			"shirt": 1, "pants": 2, "boots": 3, "head": 1},
		"equipment_visuals": {0: 100, 1: 100, 2: 100, 3: 100,
			4: 100, 5: 100, 6: 100, 7: 100}},
		CoordinateAdapter.new({"walkingHeight": 0.0, "invertServerY": true}),
		model_config, animation_config, equipment_config)
	actor.set_physics_process(false)
	actor.global_position = stand

	# The game's rig: pitch -60, yaw 0, 26 m back, as IsometricCameraController
	# sets it up by default.
	var pitch := deg_to_rad(-60.0)
	var camera := Camera3D.new()
	camera.fov = 26.0
	camera.current = true
	add_child(camera)
	var focus: Vector3 = stand + Vector3.UP * 1.0
	camera.global_position = focus + Vector3(0.0, -sin(pitch), cos(pitch)) * 26.0
	camera.look_at(focus, Vector3.UP)

	for i in 8:
		await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(
		out_dir.path_join("silhouette-off.png"))
	actor.set_occlusion_silhouette_enabled(true)
	for i in 8:
		await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(
		out_dir.path_join("silhouette-on.png"))
	print("[demo] wrote both frames to ", out_dir)
	get_tree().quit()
