extends SceneTree
## Isolated fresh-process client-component benchmark, driven by a hash-bound job.

func _initialize() -> void: call_deferred("run")

func run() -> void:
	var job: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(OS.get_cmdline_user_args()[0]))
	assert(FileAccess.get_sha256(job.path) == job.sha256)
	var base_memory := int(Performance.get_monitor(Performance.MEMORY_STATIC))
	var base_peak := int(Performance.get_monitor(Performance.MEMORY_STATIC_MAX))
	var began := Time.get_ticks_usec()
	var packed := GlbSceneCache._build_raw(job.path)
	assert(packed != null)
	GlbSceneCache.install_prepared({str(job.path): packed})
	var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models[str(job.actor)].duplicate(true)
	var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	config.scene = job.path
	config.animationLibrary = job.path
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	assert(actor.configure({"actor_id": 1, "kind": 5, "name": "", "x": 0, "y": 0, "rotation": 0, "health": 100, "max_health": 100}, CoordinateAdapter.new({"metresPerTile": 1.0}), config, mapping).is_empty())
	actor.set_process(false)
	actor.set_physics_process(false)
	var player := actor.animation_player
	if player.animation_finished.is_connected(actor._on_animation_finished): player.animation_finished.disconnect(actor._on_animation_finished)
	for node in actor.find_children("*", "AnimationPlayer", true, false):
		(node as AnimationPlayer).callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	var load_ms := (Time.get_ticks_usec() - began) / 1000.0
	var skeleton := actor.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
	var keys := 0
	var tracks := 0
	var per_clip := {}
	for name in player.get_animation_list():
		var animation := player.get_animation(name)
		var count := 0
		for track in animation.get_track_count(): count += animation.track_get_key_count(track)
		keys += count
		tracks += animation.get_track_count()
		per_clip[str(name)] = {"keys": count, "tracks": animation.get_track_count(), "duration": animation.length}
	var retained := int(Performance.get_monitor(Performance.MEMORY_STATIC)) - base_memory
	var peak_delta := int(Performance.get_monitor(Performance.MEMORY_STATIC_MAX)) - base_peak
	var timings := {}
	for name in player.get_animation_list():
		if name == &"RESET": continue
		var duration := player.get_animation(name).length
		player.play(name, 0.0)
		player.advance(0.0)
		for frame in 240:
			player.seek(fmod(frame / 240.0, duration), false)
			player.advance(1.0 / 240.0)
			skeleton.force_update_all_bone_transforms()
		var batches := []
		for batch in 9:
			var start := Time.get_ticks_usec()
			for frame in 1200:
				if player.current_animation_position >= duration - 1.0 / 240.0: player.seek(0.0, true)
				player.advance(1.0 / 240.0)
				skeleton.force_update_all_bone_transforms()
			batches.append((Time.get_ticks_usec() - start) / 1200.0)
		batches.sort()
		timings[str(name)] = {"median_usec_per_update": batches[4], "minimum_usec_per_update": batches[0], "batch_means_usec": batches}
	var result := {"source_sha256": job.sha256, "load_ms": load_ms, "retained_static_memory_delta_bytes": retained,
		"load_peak_static_memory_increase_bytes": peak_delta, "retargeted_keys": keys, "retargeted_tracks": tracks, "clips": per_clip,
		"animation_update": timings, "bones": skeleton.get_bone_count(), "engine": Engine.get_version_info(),
		"scope": "Fresh-process real GlbSceneCache._build_raw + ReplicatedActor3D + NativeAnimationImporter, warm OS file cache. Retained Godot static CPU allocations include scene and library caches, meshes, textures and actor. AnimationPlayer advance plus forced skeleton global transforms at 240 updates/s; nine batches of 1200 updates per clip after warmup. Excludes GPU rendering/skinning, whole-game logic and frame-rate claims."}
	FileAccess.open(job.report, FileAccess.WRITE).store_string(JSON.stringify(result, "  "))
	print("CREATURE_BENCHMARK_PASS ", job.sha256, " ", load_ms, " ms, ", retained, " retained bytes")
	actor.free()
	packed = null
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit()
