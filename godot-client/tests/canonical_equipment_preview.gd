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
	if args.get("back-light", "no") == "yes":
		light.rotation_degrees = Vector3(-35, 150, 0)
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
		cam.position = Vector3(0, 1.1, -4)
		cam.look_at(Vector3(0, 0.9, 0))
	elif args.get("angle", "front") == "back-quarter":
		cam.position = Vector3(-3, 2.1, -4)
		cam.look_at(Vector3(0, 1.1, 0))
	cam.current = true
	var slug: String = args.get("slug", "luminous_female")
	var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))["models"][slug].duplicate(true)
	if args.has("config"):
		config.merge(JSON.parse_string(FileAccess.get_file_as_string(args["config"])), true)
	config["scene"] = args.get("model", config["scene"])
	if args.has("library"):
		config["animationLibrary"] = args["library"]
	if args.has("hair-fit"):
		config["hairFit"] = JSON.parse_string(FileAccess.get_file_as_string(args["hair-fit"]))
	if args.get("hair", "yes") == "no":
		config["hairStyles"] = []
	# Generated import products are intentionally absent from lean worktrees.
	# Keep the authored face material for visual QA instead of applying a
	# missing region mask that would make the entire face render black.
	if config.has("faceAppearance") and not ResourceLoader.exists(
			str((config.faceAppearance as Dictionary).get("mask", ""))):
		config.erase("faceAppearance")
	var animation: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args.get("equipment", "res://data/actors/equipment.json")))
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
		var outfit := {}
		for pair: String in str(args.get("outfit", "0:114,3:133,4:219,5:208,6:248")).split(",", false):
			if pair.count(":") != 1 or not pair.get_slice(":", 0).is_valid_int() or not pair.get_slice(":", 1).is_valid_int():
				push_error("Malformed outfit pair: " + pair)
				quit(1)
				return
			outfit[int(pair.get_slice(":", 0))] = int(pair.get_slice(":", 1))
		actor.apply_equipment_visuals(outfit)
	var quality_name := str(args.get("quality", "high")).to_lower()
	var quality_level := ActorRenderQuality.QUALITY_NAMES.find(quality_name)
	if quality_level < 0:
		push_error("Unknown actor quality: " + quality_name)
		quit(1)
		return
	actor.apply_render_quality(quality_level, false)
	actor.global_position = Vector3.ZERO
	# Keep the client's import adapter and face the existing gameplay camera.
	actor.rotation.y = PI
	actor.set_process(false)
	actor.set_physics_process(false)
	# Map-only marker geometry is excluded by the gameplay camera in main.tscn.
	for marker: Node in actor.find_children("MapDot*", "MeshInstance3D", true, false):
		(marker as MeshInstance3D).hide()
	var clip: String = args.get("clip", "Walk")
	# Play the action the clip belongs to, not just the clip: how a held weapon
	# sits follows the action (WeaponCarryPose lays it in its idle grip only
	# while the actor idles, and aims it ahead only while it travels), so a
	# swing captured under the idle action would show the resting grip.
	# --action names one outright when a clip serves several.
	var action := StringName(args.get("action", ""))
	if action == &"":
		for candidate: String in (animation.get("actions", {}) as Dictionary):
			if str(animation["actions"][candidate]) == clip:
				action = StringName(candidate)
				break
	if action != &"":
		actor.play_action(action)
	# Physics is paused for deterministic captures; finish the runtime facing blend.
	actor._advance_facing_offset(1.0)
	actor.animation_player.play(clip)
	actor.animation_player.seek(float(args.get("time", "0.3")), true)
	actor.animation_player.pause()
	await process_frame
	await process_frame
	await create_timer(0.5).timeout
	if args.has("hide"):
		for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
			for suffix: String in str(args["hide"]).split(","):
				if str(node.name).ends_with(suffix):
					(node as MeshInstance3D).hide()
	if args.get("region", "full") in ["neck", "head"]:
		var skeleton := actor.get_skeleton()
		var focus := (skeleton.global_transform * skeleton.get_bone_global_pose(skeleton.find_bone("Head"))).origin - Vector3(0, .035, 0)
		var direction := Vector3(0, .08, 1)
		if args.get("angle", "front") == "side":
			direction = Vector3(1, .08, 0)
		elif args.get("angle", "front") == "back":
			direction = Vector3(0, .08, -1)
		elif args.get("angle", "front") == "back-quarter":
			direction = Vector3(-.65, .12, -.8)
		elif args.get("angle", "front") == "gameplay":
			direction = Vector3(.55, .12, 1)
		cam.size = .60 if args.get("region") == "head" else .40
		if args.get("region") == "head":
			focus += Vector3(0, .075, 0)
		cam.position = focus + direction
		cam.look_at(focus)
		await process_frame
	if args.get("region", "full") in ["shoulder", "shoulders"]:
		var skeleton := actor.get_skeleton()
		var upperarm := skeleton.find_bone("upperarm_l")
		var spine := skeleton.find_bone("spine_03")
		var upperarm_origin := (skeleton.global_transform
			* skeleton.get_bone_global_pose(upperarm)).origin
		var spine_origin := (skeleton.global_transform
			* skeleton.get_bone_global_pose(spine)).origin
		var focus := spine_origin.lerp(upperarm_origin, .72)
		var direction := Vector3(0, .06, 1)
		if args.get("angle", "front") == "side":
			direction = Vector3(1, .06, 0)
		elif args.get("angle", "front") == "back":
			direction = Vector3(0, .06, -1)
		elif args.get("angle", "front") == "back-quarter":
			direction = Vector3(-.65, .10, -.8)
		cam.size = .45
		cam.position = focus + direction
		cam.look_at(focus)
		await process_frame
	if args.get("region", "full") in ["hand", "left-hand"]:
		var skeleton := actor.get_skeleton()
		var hand_name := "hand_l" if args.get("region") == "left-hand" else "hand_r"
		var hand := skeleton.find_bone(hand_name)
		var focus := (skeleton.global_transform * skeleton.get_bone_global_pose(hand)).origin
		cam.size = .36
		var direction := Vector3(-.3 if hand_name == "hand_l" else .3, .1, .7)
		if args.get("angle", "front") == "side":
			direction = Vector3(.7, .1, 0)
		elif args.get("angle", "front") == "back":
			direction = Vector3(.3 if hand_name == "hand_l" else -.3, .1, -.7)
		elif args.get("angle", "front") == "back-quarter":
			direction = Vector3(-.55, .12, -.55)
		cam.position = focus + direction
		cam.look_at(focus)
		await process_frame
	if args.get("region", "full") in ["hips", "back"]:
		var focus := Vector3(0, .88, 0) if args["region"] == "hips" else Vector3(0, 1.35, 0)
		var direction := Vector3(0, .1, 1) if args["region"] == "hips" else Vector3(-.4, .2, -1)
		if args["region"] == "hips" and args.get("angle", "front") == "side":
			direction = Vector3(1, .1, 0)
		elif args["region"] == "hips" and args.get("angle", "front") == "back-quarter":
			direction = Vector3(-.65, .15, -.8)
		cam.size = .65
		cam.position = focus + direction
		cam.look_at(focus)
		await process_frame
	if args.get("region", "full") == "boots":
		var focus := Vector3(0, .27, 0)
		var direction := Vector3(0, .08, 1)
		if args.get("angle", "front") == "side":
			direction = Vector3(1, .08, 0)
		elif args.get("angle", "front") == "back":
			direction = Vector3(0, .08, -1)
		elif args.get("angle", "front") == "back-quarter":
			direction = Vector3(-.65, .15, -.8)
		cam.size = .55
		cam.position = focus + direction
		cam.look_at(focus)
		await process_frame
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
	var report := {"model": config["scene"], "model_sha256": FileAccess.get_sha256(config["scene"]), "clip": clip, "bones": sk.get_bone_count(), "rig_fit_scale": actor.rig_fit_scale(), "equipment": actor.equipment_diagnostics(), "meshes": [], "hair_attachments": []}
	report["runtime_sha256"] = {}
	for source: String in ["res://src/actors/replicated_actor_3d.gd", "res://src/actors/torso_body_cover.gd", "res://tests/canonical_equipment_preview.gd"]:
		report["runtime_sha256"][source] = FileAccess.get_sha256(source)
	report["equipment_config_sha256"] = FileAccess.get_sha256(args.get("equipment", "res://data/actors/equipment.json"))
	report["library_sha256"] = FileAccess.get_sha256(str(config["animationLibrary"]))
	report["quality"] = quality_name
	report["quality_lod_bias_scale"] = ActorRenderQuality.lod_bias_scale(quality_level)
	report["hair_fit"] = config.get("hairFit", {})
	report["socket_placements"] = {}
	report["socket_grip_distances"] = {}
	for piece in actor._equipment_nodes.values():
		for attachment: Node in piece:
			if attachment is BoneAttachment3D:
				var prop := attachment.get_child(0) as Node3D
				var t := prop.transform
				report["socket_placements"][str(attachment.name)] = [t.basis.x.x,t.basis.x.y,t.basis.x.z,t.basis.y.x,t.basis.y.y,t.basis.y.z,t.basis.z.x,t.basis.z.y,t.basis.z.z,t.origin.x,t.origin.y,t.origin.z]
				report["socket_grip_distances"][str(attachment.name)] = \
					prop.global_position.distance_to(attachment.global_position)
	report["facing_offset_degrees"] = rad_to_deg(actor._facing_offset)
	report["bone_poses"] = {}
	for bone_name: String in ["pelvis", "spine_03", "Head", "upperarm_l", "upperarm_r", "foot_l", "foot_r"]:
		var pose := sk.get_bone_global_pose(sk.find_bone(bone_name))
		report["bone_poses"][bone_name] = {"position": [pose.origin.x, pose.origin.y, pose.origin.z], "basis": [pose.basis.x.x, pose.basis.y.x, pose.basis.z.x, pose.basis.x.y, pose.basis.y.y, pose.basis.z.y, pose.basis.x.z, pose.basis.y.z, pose.basis.z.z]}
	for n: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh := n as MeshInstance3D
		var mat := mesh.material_override as StandardMaterial3D
		report.meshes.append({"name": str(mesh.name), "visible": mesh.visible,
			"material_override": mat != null,
			"tint": str(mat.albedo_color) if mat != null else "",
			"grow": mat.grow_amount if mat != null and mat.grow else 0.0,
			"mesh_resource_id": mesh.mesh.get_instance_id() if mesh.mesh != null else 0,
			"lod_bias": mesh.lod_bias, "cast_shadow": mesh.cast_shadow})
	if args.has("hide"):
		report["neck_diagnostic"] = []
		for n: Node in actor.find_children("*", "MeshInstance3D", true, false):
			if not n.has_meta("uncovered_body_mesh"):
				continue
			var mesh := n as MeshInstance3D
			var original := mesh.get_meta("uncovered_body_mesh") as Mesh
			var transform := sk.global_transform.affine_inverse() * mesh.global_transform
			var removed_neck: Array = []
			for surface: int in range(original.get_surface_count()):
				var before := original.surface_get_arrays(surface)
				var after := mesh.mesh.surface_get_arrays(surface)
				var kept: PackedInt32Array = after[Mesh.ARRAY_INDEX]
				var ids: PackedInt32Array = before[Mesh.ARRAY_INDEX]
				var vs: PackedVector3Array = before[Mesh.ARRAY_VERTEX]
				var keys := {}
				for i: int in range(0, kept.size(), 3):
					keys[str(kept.slice(i,i+3))] = true
				for i: int in range(0, ids.size(), 3):
					var c := transform * ((vs[ids[i]]+vs[ids[i+1]]+vs[ids[i+2]])/3.0)
					if c.y>1.40 and absf(c.x)<.11 and not keys.has(str(ids.slice(i,i+3))):
						removed_neck.append([c.x,c.y,c.z])
			report["neck_diagnostic"].append({"name":str(n.name),"transform":str(transform),"removed":removed_neck})
	for n: Node in sk.get_children():
		if n is BoneAttachment3D:
			report.hair_attachments.append({"name": str(n.name), "bone": (n as BoneAttachment3D).bone_name, "transform": str((n as Node3D).global_transform)})
	FileAccess.open(args["out"] + ".json", FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	print("CLIENT_CAPTURE_OK ", args["out"])
	stage.queue_free()
	NativeAnimationImporter.clear()
	await process_frame
	quit()
