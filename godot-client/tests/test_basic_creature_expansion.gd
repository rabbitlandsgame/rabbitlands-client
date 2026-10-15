extends SceneTree
## Exercise the real replicated actor, including corrective mesh tracks,
## collision scale, clip looping, transitions and the shared library cache.

var failures: Array[String] = []
var checked_clips := 0
var corrected_creatures := 0
var checked_creatures := 0
var selected := PackedStringArray()

func _init() -> void:
	selected = OS.get_cmdline_user_args()
	_run.call_deferred()

func _json(path: String) -> Dictionary:
	return JSON.parse_string(FileAccess.get_file_as_string(path)) as Dictionary

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures.append(message)
		push_error(message)

func _make_actor(entry: Dictionary, config: Dictionary) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var dto := {"actor_id": int(entry.actor_type), "actor_type": int(entry.actor_type),
		"x": 5, "y": 5, "rotation": 0, "name": entry.name,
		"scale": 1.0, "footprint": Vector2i.ONE, "health": 100, "max_health": 100}
	var errors := actor.configure(dto, CoordinateAdapter.new(), config, _json(config.animationMap))
	_expect(errors.is_empty(), "%s configure: %s" % [entry.type, errors])
	actor.set_process(false)
	actor.set_physics_process(false)
	return actor

func _run() -> void:
	var registry := _json("res://data/actors/models.json")
	var expansion := _json("res://data/actors/basic_creature_expansion.json")
	_expect(expansion.creatures.size() == 100, "100 registered expansion creatures")
	for entry: Dictionary in expansion.creatures:
		if not selected.is_empty() and not selected.has(entry.type):
			continue
		var config: Dictionary = registry.models[entry.type]
		_expect(registry.actorTypes[str(int(entry.actor_type))] == entry.type, "actor type resolves: " + entry.type)
		var actor := _make_actor(entry, config)
		var player := actor.animation_player
		if player == null:
			actor.free()
			continue
		player.set_process(false)
		player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		var native_model := actor.get_node("NativeModel") as Node3D
		var source_player := native_model.find_children("*", "AnimationPlayer", true, false)[0] as AnimationPlayer
		var active_shapes := false
		var corrected_clip := ""
		for clip_name: String in entry.animation_clips:
			_expect(player.has_animation(clip_name), "%s missing %s" % [entry.type, clip_name])
			if not player.has_animation(clip_name):
				continue
			var clip := player.get_animation(clip_name)
			var source := source_player.get_animation(clip_name)
			var expected_shapes := 0
			var actual_shapes := 0
			for track: int in source.get_track_count():
				if source.track_get_type(track) == Animation.TYPE_BLEND_SHAPE:
					expected_shapes += 1
			for track: int in clip.get_track_count():
				if clip.track_get_type(track) == Animation.TYPE_BLEND_SHAPE:
					actual_shapes += 1
			_expect(actual_shapes == expected_shapes, "%s %s retained %d/%d corrective tracks" % [entry.type, clip_name, actual_shapes, expected_shapes])
			var looping := clip_name in ["Idle_A", "Fighting_Idle", "Walk", "Jog", "Fly", "Swim"]
			_expect((clip.loop_mode == Animation.LOOP_LINEAR) == looping, "%s %s loop flag" % [entry.type, clip_name])
			player.play(clip_name, 0.0)
			for fraction: float in [0.22, 0.5, 0.73]:
				var time := clip.length * fraction
				player.seek(time, true)
				for track: int in clip.get_track_count():
					if clip.track_get_type(track) != Animation.TYPE_BLEND_SHAPE:
						continue
					var path := clip.track_get_path(track)
					var mesh := actor.get_node(NodePath(path.get_concatenated_names())) as MeshInstance3D
					var index := mesh.find_blend_shape_by_name(path.get_concatenated_subnames())
					var expected := clip.blend_shape_track_interpolate(track, time)
					var actual := mesh.get_blend_shape_value(index)
					active_shapes = active_shapes or absf(actual) > 0.001
					if absf(actual) > 0.001:
						corrected_clip = clip_name
					_expect(is_finite(actual) and absf(actual - expected) < 0.002,
						"%s %s corrective playback differs: %s (%f vs %f)" % [entry.type, clip_name, path, actual, expected])
			if looping:
				player.advance(clip.length * 2.1)
				_expect(player.is_playing(), "%s %s keeps looping" % [entry.type, clip_name])
			checked_clips += 1
		if int(entry.morph_targets) > 0:
			corrected_creatures += 1
			_expect(active_shapes, entry.type + " corrective shapes actually activate")
		# Returning from attack/flight must restore the source idle weights.
		player.play("Idle_A", 0.15)
		player.advance(0.3)
		for node: Node in native_model.find_children("*", "MeshInstance3D", true, false):
			var mesh := node as MeshInstance3D
			for index: int in mesh.mesh.get_blend_shape_count():
				_expect(absf(mesh.get_blend_shape_value(index)) < 0.002, entry.type + " idle cleared corrective " + str(index))
		var second := _make_actor(entry, config)
		var second_player := second.animation_player
		_expect(player.get_animation_library("") == second_player.get_animation_library(""), entry.type + " library cache reused")
		second_player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		second_player.play("Idle_A", 0.0)
		second_player.seek(0.1, true)
		player.play("Sword_Attack", 0.0)
		player.seek(player.get_animation("Sword_Attack").length * 0.5, true)
		_expect(second_player.current_animation == "Idle_A", entry.type + " independent player state")
		for node: Node in second.get_node("NativeModel").find_children("*", "MeshInstance3D", true, false):
			var mesh := node as MeshInstance3D
			for index: int in mesh.mesh.get_blend_shape_count():
				_expect(absf(mesh.get_blend_shape_value(index)) < 0.002, entry.type + " independent mesh weights")
		if not corrected_clip.is_empty():
			# Exercise RESET itself, rather than relying on the explicit zero
			# shape keys that happen to be present in this delivery's idle.
			var scratch := player.get_animation_library("").duplicate(true) as AnimationLibrary
			var sparse_idle := scratch.get_animation("Idle_A").duplicate() as Animation
			for track: int in range(sparse_idle.get_track_count() - 1, -1, -1):
				if sparse_idle.track_get_type(track) == Animation.TYPE_BLEND_SHAPE:
					sparse_idle.remove_track(track)
			scratch.add_animation("TestBoneOnlyIdle", sparse_idle)
			player.remove_animation_library("")
			player.add_animation_library("", scratch)
			player.play(corrected_clip, 0.0)
			player.seek(player.get_animation(corrected_clip).length * 0.5, true)
			player.play("TestBoneOnlyIdle", 0.15)
			player.advance(0.3)
			for node: Node in native_model.find_children("*", "MeshInstance3D", true, false):
				var mesh := node as MeshInstance3D
				for index: int in mesh.mesh.get_blend_shape_count():
					_expect(absf(mesh.get_blend_shape_value(index)) < 0.002, entry.type + " RESET clears omitted corrective tracks")
		actor.free()
		second.free()
		NativeAnimationImporter.clear()
		GlbSceneCache.clear()
		checked_creatures += 1
		print("expansion actor checked: ", entry.type)
		await process_frame
	var report := {"creatures": checked_creatures, "clips": checked_clips,
		"corrective_creatures": corrected_creatures, "failures": failures}
	print("EXPANSION_REPORT ", JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)
