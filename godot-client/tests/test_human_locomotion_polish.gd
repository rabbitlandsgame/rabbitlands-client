extends SceneTree
## Real imported Human rigs: immutable shared source, complete action/track
## preservation, cyclic arm corrections and untouched lower-body contacts.
const POLISH := preload("res://src/actors/human_locomotion_polish.gd")
var failures := 0
var checks := 0
var metrics: Array = []
var action_audit: Array = []

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func snapshot(animation: Animation) -> Array:
	var result: Array = [animation.length, animation.loop_mode, animation.step]
	for track: int in animation.get_track_count():
		var values: Array = [animation.track_get_path(track), animation.track_get_type(track),
			animation.track_get_interpolation_type(track), animation.track_get_interpolation_loop_wrap(track), animation.track_is_enabled(track)]
		for index: int in animation.track_get_key_count(track):
			values.append([animation.track_get_key_time(track, index), animation.track_get_key_value(track, index), animation.track_get_key_transition(track, index)])
		result.append(values)
	return result

func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	POLISH.clear()
	var previous_source: AnimationLibrary
	var previous_result: AnimationLibrary
	for slug: String in ["luminous_male", "luminous_female", "orun_male"]:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var errors := actor.configure({"actor_id": 9900, "x": 0, "y": 0, "rotation": 0, "kind": 1,
			"name": "", "appearance": {}, "equipment_visuals": {}},
			CoordinateAdapter.new({"walkingHeight": 0.0}), models[slug], animations, equipment)
		expect(errors.is_empty(), slug + " loads current native actor")
		var player := actor.animation_player
		var source: AnimationLibrary = player.get_meta(POLISH.SOURCE_META) if player.has_meta(POLISH.SOURCE_META) else player.get_animation_library(&"")
		var original := {}
		for name: StringName in source.get_animation_list(): original[name] = snapshot(source.get_animation(name))
		# Configure may already have installed the integration hook. Benchmark
		# one cold derivative explicitly; the second Human must reuse that one.
		if slug == "luminous_male": POLISH.clear()
		var began := Time.get_ticks_usec()
		POLISH.install(player, models[slug])
		var build_usec := Time.get_ticks_usec() - began
		var result := player.get_animation_library(&"")
		var human := slug.begins_with("luminous_")
		expect((result != source) == human, slug + " opt-in keeps other races original")
		expect(source.get_animation_list() == result.get_animation_list(), "all clip names remain exact")
		for action: String in animations.actions:
			expect(result.has_animation(animations.actions[action]), "all mapped actions remain available " + action)
		for name: StringName in source.get_animation_list():
			var old := source.get_animation(name)
			var new := result.get_animation(name)
			action_audit.append({"model": slug, "clip": name, "length": new.length,
				"tracks": new.get_track_count(), "loop_mode": new.loop_mode,
				"shared_original": old == new, "source_snapshot_hash": original[name].hash()})
			expect(snapshot(old) == original[name], "source remains immutable " + str(name))
			if not human or name not in POLISH.CLIPS:
				expect(old == new, "non-locomotion resources remain shared " + str(name))
				continue
			expect(old != new and new.length == old.length and new.loop_mode == old.loop_mode, "only travel animation resource is derived " + str(name))
			expect(new.get_track_count() == old.get_track_count(), "no track added or removed " + str(name))
			var modified := 0
			var worst_loop := 0.0
			var copied_keys := 0
			for track: int in old.get_track_count():
				copied_keys += old.track_get_key_count(track)
				var bone := str(old.track_get_path(track).get_concatenated_subnames()).get_slice(":", 0)
				var arm_rotation := old.track_get_type(track) == Animation.TYPE_ROTATION_3D and bone in POLISH.ARM_BONES
				expect(new.track_get_path(track) == old.track_get_path(track) and new.track_get_type(track) == old.track_get_type(track), "track identity preserved")
				expect(new.track_get_key_count(track) == old.track_get_key_count(track), "source cadence preserved")
				var changed := false
				for index: int in old.track_get_key_count(track):
					expect(new.track_get_key_time(track, index) == old.track_get_key_time(track, index), "authored key time preserved")
					var before: Variant = old.track_get_key_value(track, index)
					var after: Variant = new.track_get_key_value(track, index)
					if arm_rotation:
						var q := after as Quaternion
						expect(is_finite(q.x) and is_finite(q.y) and is_finite(q.z) and is_finite(q.w) and absf(q.length() - 1.0) < 0.00001, "finite normalized arm quaternion")
						changed = changed or not q.is_equal_approx(before)
					else:
						expect(after == before, "all torso/root/leg/translation/scale/finger keys remain exact")
				if arm_rotation:
					modified += int(changed)
					var first := new.rotation_track_interpolate(track, 0.0)
					var last := new.rotation_track_interpolate(track, new.length)
					worst_loop = maxf(worst_loop, first.angle_to(last))
				expect(new.track_get_interpolation_type(track) == old.track_get_interpolation_type(track), "interpolation unchanged")
			expect(modified > 0 and worst_loop < 0.0001, "arm polish is visible and loop closes " + str(name))
			metrics.append({"model": slug, "clip": name, "duration": new.length, "modified_arm_tracks": modified,
				"max_loop_degrees": rad_to_deg(worst_loop), "first_install_usec": build_usec,
				"copied_keys": copied_keys, "tracks": old.get_track_count()})
		POLISH.install(player, models[slug])
		expect(player.get_animation_library(&"") == result, "install is idempotent")
		for quality: int in [ActorRenderQuality.Quality.LOW, ActorRenderQuality.Quality.MEDIUM, ActorRenderQuality.Quality.HIGH]:
			actor.apply_render_quality(quality, true)
			expect(player.get_animation_library(&"") == result, "quality switch retains polished locomotion")
		if human and source == previous_source:
			expect(result == previous_result, "same rig/source shares Human derivative across sexes")
		previous_source = source
		previous_result = result
		actor.free()
		await process_frame
	var destination := OS.get_environment("RL_HUMAN_LOCOMOTION_METRICS")
	if not destination.is_empty():
		FileAccess.open(destination, FileAccess.WRITE).store_string(JSON.stringify({"checks": checks, "failures": failures, "metrics": metrics, "action_audit": action_audit}, "  "))
	print("Human locomotion polish: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
