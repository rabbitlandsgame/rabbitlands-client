extends SceneTree
## Cost of the RL head prototype against today's head, on the real client
## actor, per actor-quality tier. Windowed (the counters are the renderer's);
## serialise with gpu_lock.sh.
##
##   Godot --path godot-client --script res://tests/integration/rl_head_metrics.gd -- [--frames 120]
##
## Per quality (LOW, MEDIUM, HIGH):
##   * one actor framed near (bust), mid (12 m) and far (30 m): the frame's
##     primitives and draw calls over the empty stage, RL head and baseline;
##   * 1 and 40 actors walking: primitives, draw calls, texture, buffer and
##     video memory, and the mean and 95th-percentile frame and process times,
##     for the baseline head, the RL head with every face animating (talking
##     and blinking, updated every frame), the RL head with faces at rest
##     (auto-blink on its distance schedule only), and the RL head with secondary hair
##     motion on and off (a synthetic 8-chain, 4-joint spring rig per actor
##     while no RL hairstyle with springs exists). "process" is the main
##     loop's processing - scripts, animation, skeletons, springs - up to the
##     frame being drawn; render CPU and GPU times are the viewport's own.
## Every cache is warmed first (one actor of each kind and sex), so spawn
## times are steady-state. Also the static triangle counts of each head part
## and the video memory of the RL textures. Writes
## .local/rl-heads/evidence/metrics/rl_head_metrics_<renderer>.json.

const Stage := preload("res://prototypes/rl_heads/rl_head_stage.gd")
const CROWD := 40

var stage: Node3D
var camera: Camera3D
var frames := 120
var results: Dictionary = {}
var _process_began := 0
var _process_us := PackedFloat64Array()
var _sampling := false


func _init() -> void:
	var values := OS.get_cmdline_user_args()
	for index in range(0, values.size() - 1, 2):
		if values[index] == "--frames":
			frames = int(values[index + 1])
	call_deferred("_run")


func _run() -> void:
	root.size = Vector2i(960, 540)
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	Engine.max_fps = 0
	stage = Node3D.new()
	root.add_child(stage)
	Stage.build(stage)
	camera = Camera3D.new()
	camera.cull_mask = 1
	camera.fov = 40.0
	stage.add_child(camera)
	camera.current = true
	results["renderer"] = RenderingServer.get_current_rendering_method()
	results["gpu"] = RenderingServer.get_video_adapter_name()
	results["window"] = [root.size.x, root.size.y]
	results["frames_per_sample"] = frames
	RenderingServer.viewport_set_measure_render_time(root.get_viewport_rid(), true)
	process_frame.connect(func() -> void: _process_began = Time.get_ticks_usec())
	RenderingServer.frame_pre_draw.connect(func() -> void:
		if _sampling and _process_began > 0:
			_process_us.append(float(Time.get_ticks_usec() - _process_began)))
	_place_camera(Vector3(0.0, 1.4, 3.0), Vector3(0.0, 1.2, 0.0))
	results["empty_stage"] = await _info()
	# Warm every cache: animation import, head pieces, materials, textures.
	var warm_began := Time.get_ticks_usec()
	for kind: String in ["baseline", "rl"]:
		for sex: String in ["female", "male"]:
			var warm := _spawn(kind, sex, ActorRenderQuality.Quality.HIGH, Vector3.ZERO, 9390)
			await process_frame
			warm.queue_free()
			await process_frame
	results["cold_warmup_ms"] = (Time.get_ticks_usec() - warm_began) / 1000.0
	results["static_triangles"] = _static_triangles()
	results["rl_texture_mb"] = _rl_texture_megabytes()
	var tiers := {}
	for quality: int in [ActorRenderQuality.Quality.LOW, ActorRenderQuality.Quality.MEDIUM,
			ActorRenderQuality.Quality.HIGH]:
		var tier := {}
		for kind: String in ["baseline", "rl"]:
			tier["single_" + kind] = await _single(kind, quality)
		for kind: String in ["baseline", "rl", "rl_still", "rl_hair_motion"]:
			for count: int in [1, CROWD]:
				tier["%s_x%d" % [kind, count]] = await _crowd(kind, quality, count)
		tiers[ActorRenderQuality.quality_name(quality)] = tier
		print("RL_HEAD_METRICS tier ", ActorRenderQuality.quality_name(quality), " done")
	results["tiers"] = tiers
	var folder := ProjectSettings.globalize_path("res://").path_join(
		"../.local/rl-heads/evidence/metrics").simplify_path()
	DirAccess.make_dir_recursive_absolute(folder)
	var path := folder.path_join("rl_head_metrics_%s.json" % results["renderer"])
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(results, "\t"))
	file.close()
	print("RL_HEAD_METRICS_DONE ", path)
	quit()


func _place_camera(at: Vector3, look: Vector3) -> void:
	camera.global_position = at
	camera.look_at(look, Vector3.UP)


func _spawn(kind: String, sex: String, quality: int, at: Vector3, id: int) -> ReplicatedActor3D:
	# Hair 200 is the shipped bob (AppearanceVariants.pack_hair(5, 0)), the
	# same fitted hairstyle the RL head wears below as `legacy:bob`.
	var appearance := {"skin": 1, "eyes": 2, "hair": 200}
	if kind != "baseline":
		var preset := "mira" if sex == "female" else "rowan"
		var face := RLHeadAppearance.from_preset(preset)
		# Like for like: the baseline wears a shipped hairstyle, so does this.
		face.hair = "legacy:bob"
		appearance = {"rl_head": face.to_dict()}
	var actor := Stage.spawn(stage, sex, appearance, {}, quality, id)
	actor.global_position = at
	return actor


func _info() -> Dictionary:
	for frame in 4:
		await process_frame
	await RenderingServer.frame_post_draw
	return {
		"primitives": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME),
		"draw_calls": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME),
		"objects": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_OBJECTS_IN_FRAME),
		"texture_mem_mb": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TEXTURE_MEM_USED) / 1048576.0,
		"buffer_mem_mb": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_BUFFER_MEM_USED) / 1048576.0,
		"video_mem_mb": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_VIDEO_MEM_USED) / 1048576.0,
	}


func _single(kind: String, quality: int) -> Dictionary:
	var began := Time.get_ticks_usec()
	var actor := _spawn(kind, "female", quality, Vector3.ZERO, 9400)
	var record := {"spawn_ms": (Time.get_ticks_usec() - began) / 1000.0}
	Stage.pose(actor, "Idle", 0.5)
	var empty: Dictionary = results["empty_stage"]
	for framing: Array in [["near", 1.6], ["mid", 12.0], ["far", 30.0]]:
		var distance: float = framing[1]
		_place_camera(Vector3(0.0, 1.5, distance), Vector3(0.0, 1.45, 0.0))
		var info := await _info()
		record[framing[0]] = {"primitives_over_empty": int(info["primitives"]) - int(empty["primitives"]),
			"draw_calls_over_empty": int(info["draw_calls"]) - int(empty["draw_calls"])}
	actor.queue_free()
	await process_frame
	return record


func _crowd(kind: String, quality: int, count: int) -> Dictionary:
	var actors: Array[ReplicatedActor3D] = []
	var began := Time.get_ticks_usec()
	for index: int in count:
		var at := Vector3(float(index % 8) * 1.3 - 4.55, 0.0, -float(index / 8) * 1.6)
		actors.append(_spawn(kind, "female" if index % 2 == 0 else "male", quality, at, 9500 + index))
	var spawn_ms := (Time.get_ticks_usec() - began) / 1000.0
	for actor: ReplicatedActor3D in actors:
		actor.animation_player.play("Walk")
		actor.animation_player.seek(randf() * 1.0, true)
		var rig := actor.rl_head()
		if rig != null and kind == "rl_still":
			# Faces at rest: blinking on its own, distance-throttled schedule.
			rig.set_hair_motion_allowed(false)
		elif rig != null:
			rig.expression().always_update = true
			rig.expression().set_talking(true)
			if kind == "rl_hair_motion":
				_add_synthetic_springs(actor)
			else:
				rig.set_hair_motion_allowed(false)
	_place_camera(Vector3(0.0, 4.0, 9.0), Vector3(0.0, 1.0, -2.5))
	var info := await _info()
	var frame_times := PackedFloat64Array()
	var render_cpu := PackedFloat64Array()
	var render_gpu := PackedFloat64Array()
	_process_us.clear()
	_sampling = true
	var last := Time.get_ticks_usec()
	for frame: int in frames:
		await process_frame
		var now := Time.get_ticks_usec()
		frame_times.append((now - last) / 1000.0)
		render_cpu.append(RenderingServer.viewport_get_measured_render_time_cpu(root.get_viewport_rid()))
		render_gpu.append(RenderingServer.viewport_get_measured_render_time_gpu(root.get_viewport_rid()))
		last = now
	_sampling = false
	var process_times := PackedFloat64Array()
	for value: float in _process_us:
		process_times.append(value / 1000.0)
	var running := 0
	for motion: Node in stage.find_children("*", "RLHairMotion", true, false):
		if (motion as RLHairMotion).is_running():
			running += 1
	info["spawn_ms"] = spawn_ms
	info["frame_ms"] = _stats(frame_times)
	info["process_ms"] = _stats(process_times)
	info["render_cpu_ms"] = _stats(render_cpu)
	info["render_gpu_ms"] = _stats(render_gpu)
	info["hair_chains_running"] = running
	for actor: ReplicatedActor3D in actors:
		actor.queue_free()
	await process_frame
	await process_frame
	return info


## A stand-in for an RL hairstyle's springs, for the cost of the simulator:
## eight four-joint locks round the head with a sphere and a capsule collider,
## driven by RLHairMotion exactly as a real style would be.
func _add_synthetic_springs(actor: ReplicatedActor3D) -> void:
	var skeleton := actor.get_skeleton()
	var attachment := BoneAttachment3D.new()
	attachment.name = "MetricsHairSprings"
	attachment.bone_name = "Head"
	skeleton.add_child(attachment)
	var hair := Skeleton3D.new()
	attachment.add_child(hair)
	var root_bone := hair.add_bone("hair_root")
	var springs: Array = []
	for lock: int in 8:
		var angle := TAU * float(lock) / 8.0
		var previous := root_bone
		var bones: Array = []
		for joint: int in 4:
			var bone := hair.add_bone("lock_%d_%d" % [lock, joint])
			hair.set_bone_parent(bone, previous)
			var offset := Vector3(cos(angle) * 0.09, 0.1, sin(angle) * 0.09) if joint == 0 \
				else Vector3(0.0, -0.05, 0.0)
			hair.set_bone_rest(bone, Transform3D(Basis.IDENTITY, offset))
			hair.reset_bone_pose(bone)
			bones.append("lock_%d_%d" % [lock, joint])
			previous = bone
		springs.append({"bones": bones, "stiffness": 1.0, "drag": 0.4, "gravity": 0.6, "radius": 0.012})
	var motion := RLHairMotion.new()
	attachment.add_child(motion)
	motion.configure(hair, {"springs": springs, "collisions": [
		{"shape": "sphere", "offset": [0, 0.08, 0.01], "radius": 0.095},
		{"shape": "capsule", "offset": [0, -0.08, -0.02], "radius": 0.06, "height": 0.2}]})
	motion.enabled = true


func _stats(values: PackedFloat64Array) -> Dictionary:
	if values.is_empty():
		return {}
	var sorted := values.duplicate()
	sorted.sort()
	var total := 0.0
	for value: float in values:
		total += value
	return {"mean": total / values.size(), "p95": sorted[int(floor(0.95 * (sorted.size() - 1)))],
		"max": sorted[sorted.size() - 1]}


## What the RL textures hold in video memory, as uploaded (after the
## library's mip chain and block compression), by file.
func _rl_texture_megabytes() -> Dictionary:
	var result := {}
	var total := 0.0
	for path: Variant in RLHeadLibrary._textures:
		var texture := RLHeadLibrary._textures[path] as Texture2D
		if texture == null:
			continue
		var image := texture.get_image()
		var megabytes := image.get_data_size() / 1048576.0 if image != null else 0.0
		result[str(path).get_file()] = {"size": [texture.get_width(), texture.get_height()],
			"format": image.get_format() if image != null else -1, "mb": megabytes}
		total += megabytes
	result["total_mb"] = total
	return result


func _static_triangles() -> Dictionary:
	var result := {}
	for sex: String in ["female", "male"]:
		var info := RLHeadLibrary.head(sex)
		var levels: Array = []
		for level: Array in info.get("lods", []) as Array:
			var total := 0
			var by_material := {}
			for piece: Dictionary in level:
				var mesh := piece["mesh"] as Mesh
				for surface: int in mesh.get_surface_count():
					var arrays := mesh.surface_get_arrays(surface)
					var count := (arrays[Mesh.ARRAY_INDEX] as PackedInt32Array).size() / 3
					var material := mesh.surface_get_material(surface)
					var key := material.resource_name if material != null else "?"
					by_material[key] = int(by_material.get(key, 0)) + count
					total += count
			levels.append({"triangles": total, "by_material": by_material})
		var cut: Dictionary = info.get("body_cut", {})
		var hidden := 0
		for run: Array in cut.get("hiddenBodyTriangles", []) as Array:
			hidden += int(run[1])
		var legacy := {"body_head_triangles_cut": hidden}
		var source := GlbSceneCache.instantiate(ProjectSettings.globalize_path(
			"res://assets/actors/native/races/luminous_%s.glb" % sex))
		if source != null:
			for part: String in ["eyes", "eyebrows", "scalp"]:
				var node := source.find_child(part, true, false) as MeshInstance3D
				if node != null:
					legacy[part] = RLHeadRig.mesh_triangles(node.mesh)
			source.free()
		result[sex] = {"rl_head_levels": levels, "legacy_head": legacy}
	return result
