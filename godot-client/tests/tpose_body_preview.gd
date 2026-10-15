extends SceneTree
## Candidate GLBs load from scratch; actual client actor performs appearance,
## hair attachment, animation import, wardrobe visibility and equipment binding.

var args: Dictionary = {}
var stage: Node3D
var actor: ReplicatedActor3D

func _init() -> void:
	var values := OS.get_cmdline_user_args()
	for i in range(0, values.size() - 1, 2):
		args[values[i].trim_prefix("--")] = values[i + 1]
	call_deferred("run")

func run() -> void:
	root.size = Vector2i(1500, 1100)
	stage = Node3D.new()
	root.add_child(stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color(0.13, 0.16, 0.19)
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color(0.9, 0.93, 1)
	environment.environment.ambient_light_energy = 0.65
	stage.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-35, -30, 0)
	light.light_energy = 1.2
	stage.add_child(light)
	var floor_mesh := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(12, 12)
	floor_mesh.mesh = plane
	var floor_material := StandardMaterial3D.new()
	floor_material.albedo_color = Color(0.21, 0.24, 0.25)
	floor_mesh.material_override = floor_material
	stage.add_child(floor_mesh)
	var cam := Camera3D.new()
	cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	cam.size = 2.25
	stage.add_child(cam)
	cam.position = Vector3(0, 1.05, 4)
	cam.look_at(Vector3(0, 0.9, 0))
	if args.get("angle", "front") == "gameplay":
		cam.position = Vector3(2.3, 2.7, 3.8)
		cam.look_at(Vector3(0, 0.9, 0))
	elif args.get("angle", "front") == "side":
		cam.position = Vector3(4, 1.1, 0)
		cam.look_at(Vector3(0, 0.9, 0))
	elif args.get("angle", "front") == "back":
		cam.position = Vector3(2.3, 2.7, -3.8)
		cam.look_at(Vector3(0, 0.9, 0))
	cam.current = true
	var slug: String = args.get("slug", "luminous_female")
	var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))["models"][slug].duplicate(true)
	config["scene"] = args["model"]
	if args.has("config"):
		config.merge(JSON.parse_string(FileAccess.get_file_as_string(args["config"])), true)
	if args.has("library"):
		config["animationLibrary"] = args["library"]
	if args.has("hair-fit"):
		config["hairFit"] = JSON.parse_string(FileAccess.get_file_as_string(args["hair-fit"]))
	if args.get("hair", "yes") == "no":
		config["hairStyles"] = []
	var animation: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var appearance := {"skin": 0, "eyes": 0, "hair": 0, "shirt": 0, "pants": 0, "boots": 0, "head": 0}
	if args.get("tints", "no") == "yes":
		appearance = {"skin": 3, "eyes": 4, "hair": 5, "shirt": 4, "pants": 5, "boots": 6, "head": int(args.get("head", "0"))}
	else:
		appearance["head"] = int(args.get("head", "0"))
	appearance["hair"] = int(args.get("style", str(appearance["hair"])))
	actor = ReplicatedActor3D.new()
	stage.add_child(actor)
	var errors := actor.configure({"actor_id": 9010, "x": 0, "y": 0, "rotation": 0, "kind": 1, "name": "", "appearance": appearance, "equipment_visuals": {}}, CoordinateAdapter.new({"walkingHeight": 0.0}), config, animation, equipment)
	if not errors.is_empty():
		push_error(str(errors))
		quit(1)
		return
	actor.server_target = Vector3.ZERO
	if args.get("gear", "no") == "yes":
		actor.apply_equipment_visuals({0: 114, 3: 133, 5: 208, 6: 248})
	actor.global_position = Vector3.ZERO
	# Keep the client's import adapter and face the existing gameplay camera.
	actor.rotation.y = PI
	actor.set_process(false)
	actor.set_physics_process(false)
	# Map-only marker geometry is excluded by the gameplay camera in main.tscn.
	for marker: Node in actor.find_children("MapDot*", "MeshInstance3D", true, false):
		(marker as MeshInstance3D).hide()
	var clip: String = args.get("clip", "Walk")
	if clip == "Walk":
		actor.play_action(&"walk")
	elif clip == "Run_Female":
		actor.play_action(&"run")
	elif clip == "Fighting_Idle":
		actor.play_action(&"combat_idle")
	# Physics is paused for deterministic captures; finish the runtime facing blend.
	actor._advance_facing_offset(1.0)
	actor.animation_player.play(clip)
	actor.animation_player.seek(float(args.get("time", "0.3")), true)
	actor.animation_player.pause()
	await process_frame
	await process_frame
	await create_timer(0.5).timeout
	if args.get("cycle", "no") == "yes":
		var folder: String = args["out"].get_basename() + "_frames"
		DirAccess.make_dir_recursive_absolute(folder)
		var length: float = actor.animation_player.get_animation(clip).length
		for frame in range(24):
			actor.animation_player.seek(length * float(frame) / 24.0, true)
			await process_frame
			await RenderingServer.frame_post_draw
			root.get_texture().get_image().save_png(folder.path_join("%03d.png" % frame))
		actor.animation_player.seek(float(args.get("time", "0.3")), true)
		await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(args["out"])
	var sk := actor.get_skeleton()
	var report := {"model": args["model"], "model_sha256": FileAccess.get_sha256(args["model"]), "clip": clip, "bones": sk.get_bone_count(), "rig_fit_scale": actor.rig_fit_scale(), "equipment": actor.equipment_diagnostics(), "meshes": [], "hair_attachments": []}
	report["library_sha256"] = FileAccess.get_sha256(str(config["animationLibrary"]))
	report["hair_fit"] = config.get("hairFit", {})
	report["facing_offset_degrees"] = rad_to_deg(actor._facing_offset)
	report["bone_poses"] = {}
	for bone_name: String in ["pelvis", "spine_03", "Head", "upperarm_l", "upperarm_r", "foot_l", "foot_r"]:
		var pose := sk.get_bone_global_pose(sk.find_bone(bone_name))
		report["bone_poses"][bone_name] = {"position": [pose.origin.x, pose.origin.y, pose.origin.z], "basis": [pose.basis.x.x, pose.basis.y.x, pose.basis.z.x, pose.basis.x.y, pose.basis.y.y, pose.basis.z.y, pose.basis.x.z, pose.basis.y.z, pose.basis.z.z]}
	for n: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh := n as MeshInstance3D
		var mat := mesh.material_override as StandardMaterial3D
		report.meshes.append({"name": str(mesh.name), "visible": mesh.visible, "material_override": mat != null, "tint": str(mat.albedo_color) if mat != null else "", "grow": mat.grow_amount if mat != null and mat.grow else 0.0})
	for n: Node in sk.get_children():
		if n is BoneAttachment3D:
			report.hair_attachments.append({"name": str(n.name), "bone": (n as BoneAttachment3D).bone_name, "transform": str((n as Node3D).global_transform)})
	FileAccess.open(args["out"] + ".json", FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	print("CLIENT_CAPTURE_OK ", args["out"])
	stage.queue_free()
	NativeAnimationImporter.clear()
	await process_frame
	quit()
