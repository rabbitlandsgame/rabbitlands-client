extends SceneTree
## Real imported Human rigs: immutable shared source, complete action/track
## preservation, cyclic male upper-body fitting and untouched lower-body contacts.
const POLISH := preload("res://src/actors/human_locomotion_polish.gd")
# Captured from the accepted v1 female arm curves, including every original
# timestamp and quaternion component. The male pass must not rewrite them.
const FEMALE_V1 := {&"Walk": "5dddc810458e7b7d590fe6b53a152d52d0456e899aa977c704581dc544f246c9",
	&"Run_Female": "ffdf688884907f72668674ca34c868554cbd45398ac8850142cee93330f2ba85"}
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

func arm_digest(animation: Animation) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	for bone: String in POLISH.ARM_BONES:
		for track: int in animation.get_track_count():
			if animation.track_get_type(track) != Animation.TYPE_ROTATION_3D or str(animation.track_get_path(track).get_concatenated_subnames()) != bone:
				continue
			context.update(bone.to_utf8_buffer())
			var values := PackedFloat64Array()
			for index: int in animation.track_get_key_count(track):
				var q: Quaternion = animation.track_get_key_value(track, index)
				values.append_array(PackedFloat64Array([animation.track_get_key_time(track, index), q.x, q.y, q.z, q.w]))
			context.update(values.to_byte_array())
	return context.finish().hex_encode()

func rotation_delta(first: Quaternion, last: Quaternion) -> float:
	# acos(dot) reports a spurious ~0.04 degrees even for the same float32
	# quaternion. The relative rotation's vector part remains well-conditioned.
	var relative := (first.inverse() * last).normalized()
	return 2.0 * atan2(Vector3(relative.x, relative.y, relative.z).length(), absf(relative.w))

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
		# one cold derivative explicitly; each sex retains its own shared pair.
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
			if slug == "luminous_female":
				expect(arm_digest(new) == FEMALE_V1[name], "female locomotion remains exactly the accepted v1 output")
			expect(old != new and new.length == old.length and new.loop_mode == old.loop_mode, "only travel animation resource is derived " + str(name))
			expect(new.get_track_count() == old.get_track_count(), "no track added or removed " + str(name))
			var modified := 0
			var worst_loop := 0.0
			var largest_arm_step := 0.0
			var copied_keys := 0
			var minimum_thumb_alignment := 1.0
			for track: int in old.get_track_count():
				copied_keys += old.track_get_key_count(track)
				var bone := str(old.track_get_path(track).get_concatenated_subnames()).get_slice(":", 0)
				var arm_rotation := old.track_get_type(track) == Animation.TYPE_ROTATION_3D and bone in POLISH.ARM_BONES
				var male_run_detail := (slug == "luminous_male" and name == &"Run_Female"
					and old.track_get_type(track) == Animation.TYPE_ROTATION_3D
					and (bone in ["spine_01", "spine_02", "neck_01"] or bone.get_slice("_", 0) in ["thumb", "index", "middle", "ring", "pinky"]))
				var permitted_rotation := arm_rotation or male_run_detail
				expect(new.track_get_path(track) == old.track_get_path(track) and new.track_get_type(track) == old.track_get_type(track), "track identity preserved")
				expect(new.track_get_key_count(track) == old.track_get_key_count(track), "source cadence preserved")
				var changed := false
				for index: int in old.track_get_key_count(track):
					expect(new.track_get_key_time(track, index) == old.track_get_key_time(track, index), "authored key time preserved")
					var before: Variant = old.track_get_key_value(track, index)
					var after: Variant = new.track_get_key_value(track, index)
					if permitted_rotation:
						var q := after as Quaternion
						expect(is_finite(q.x) and is_finite(q.y) and is_finite(q.z) and is_finite(q.w) and absf(q.length() - 1.0) < 0.00001, "finite normalized arm quaternion")
						changed = changed or not q.is_equal_approx(before)
						if index > 0:
							largest_arm_step = maxf(largest_arm_step, rotation_delta(new.track_get_key_value(track, index - 1), q))
					else:
						expect(after == before, "all protected root/leg/position/scale/other-action channels remain exact")
				if permitted_rotation:
					modified += int(changed)
					var first := new.rotation_track_interpolate(track, 0.0)
					var last := new.rotation_track_interpolate(track, new.length)
					worst_loop = maxf(worst_loop, rotation_delta(first, last))
				expect(new.track_get_interpolation_type(track) == old.track_get_interpolation_type(track), "interpolation unchanged")
			expect(modified > 0 and worst_loop < 0.0001, "arm polish is visible and loop closes " + str(name))
			expect(largest_arm_step < deg_to_rad(25), "no abrupt arm/wrist key jump " + str(name))
			if slug == "luminous_male":
				player.play(name)
				player.pause()
				var rig := actor.get_skeleton()
				for sample: int in range(49):
					player.seek(new.length * float(sample) / 48.0, true)
					rig.force_update_all_bone_transforms()
					for side: String in ["l", "r"]:
						var shoulder := rig.get_bone_global_pose(rig.find_bone("upperarm_" + side)).origin
						var elbow := rig.get_bone_global_pose(rig.find_bone("lowerarm_" + side)).origin
						var wrist := rig.get_bone_global_pose(rig.find_bone("hand_" + side)).origin
						var spread := (elbow.x - shoulder.x) * (1 if side == "l" else -1)
						expect(spread > 0.025 and spread < 0.055, "male elbow follows a stable front-view track")
						if name == &"Run_Female":
							var flex := rad_to_deg((elbow - shoulder).angle_to(wrist - elbow))
							expect(flex > 78.5 and flex < 93.5, "male rear/forward running elbows retain a natural bend")
							var middle := rig.get_bone_global_pose(rig.find_bone("middle_01_" + side)).origin
							var index := rig.get_bone_global_pose(rig.find_bone("index_01_" + side)).origin
							var pinky := rig.get_bone_global_pose(rig.find_bone("pinky_01_" + side)).origin
							var forward := (middle - wrist).normalized()
							var across := index - pinky
							across = (across - forward * across.dot(forward)).normalized()
							var up := (Vector3.UP - forward * Vector3.UP.dot(forward)).normalized()
							minimum_thumb_alignment = minf(minimum_thumb_alignment,across.dot(up))
							# The intentional ten-degree wrist flexion allows a small
							# thumb-axis tilt; palms must still remain upright.
							expect(across.dot(up) > cos(deg_to_rad(15.0)), "male run thumb-side stays upright through relaxed wrist flexion")
							for finger: String in ["index", "middle", "ring", "pinky"]:
								var knuckle := rig.get_bone_global_pose(rig.find_bone(finger+"_01_"+side)).origin
								var middle_joint := rig.get_bone_global_pose(rig.find_bone(finger+"_02_"+side)).origin
								var distal := rig.get_bone_global_pose(rig.find_bone(finger+"_03_"+side)).origin
								expect((middle_joint-knuckle).angle_to(distal-middle_joint) > deg_to_rad(55.0), "native runner grip keeps the articulated finger joints bent")
				if name == &"Run_Female":
					var widths := []
					var heights := []
					for phase: float in [0.0, 0.5]:
						player.seek(new.length * phase, true)
						rig.force_update_all_bone_transforms()
						var center := rig.get_bone_global_pose(rig.find_bone("pelvis")).origin
						var hand := rig.get_bone_global_pose(rig.find_bone("hand_l")).origin
						widths.append(absf(hand.x - center.x))
						heights.append(hand.y)
					expect(widths[0] < widths[1] - 0.06 and heights[0] > heights[1] + 0.15, "rising male hand pumps toward the chest and releases beside the hip")
			metrics.append({"model": slug, "clip": name, "duration": new.length, "modified_rotation_tracks": modified,
				"minimum_thumb_alignment":minimum_thumb_alignment,
				"max_loop_degrees": rad_to_deg(worst_loop), "first_install_usec": build_usec,
				"copied_keys": copied_keys, "tracks": old.get_track_count(), "max_rotation_key_step_degrees": rad_to_deg(largest_arm_step)})
		POLISH.install(player, models[slug])
		expect(player.get_animation_library(&"") == result, "install is idempotent")
		for quality: int in [ActorRenderQuality.Quality.LOW, ActorRenderQuality.Quality.MEDIUM, ActorRenderQuality.Quality.HIGH]:
			actor.apply_render_quality(quality, true)
			expect(player.get_animation_library(&"") == result, "quality switch retains polished locomotion")
		if human:
			expect(POLISH.derive(source, str(models[slug].gender), actor.get_skeleton()) == result, "same source and sex reuse one shared derivative")
		if human and source == previous_source:
			expect(result != previous_result, "male and female keep distinct cached locomotion")
		previous_source = source
		previous_result = result
		actor.free()
		await process_frame
	var destination := OS.get_environment("RL_HUMAN_LOCOMOTION_METRICS")
	if not destination.is_empty():
		FileAccess.open(destination, FileAccess.WRITE).store_string(JSON.stringify({"checks": checks, "failures": failures, "metrics": metrics, "action_audit": action_audit}, "  "))
	print("Human locomotion polish: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
