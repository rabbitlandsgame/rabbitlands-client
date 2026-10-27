extends SceneTree
## Real imported Human rigs: immutable shared source, complete action/track
## preservation, standing arms, free/held running hands and untouched contacts.
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
	for marker: StringName in animation.get_marker_names():
		result.append([marker,animation.get_marker_time(marker),animation.get_marker_color(marker)])
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

func idle_arm_target(walk: Animation, bone: String) -> Quaternion:
	for track: int in walk.get_track_count():
		if walk.track_get_type(track) == Animation.TYPE_ROTATION_3D and str(walk.track_get_path(track).get_concatenated_subnames()) == bone:
			return walk.rotation_track_interpolate(track,walk.length*0.25).slerp(
				walk.rotation_track_interpolate(track,walk.length*0.75),0.5).normalized()
	push_error("walk arm track missing: "+bone)
	return Quaternion.IDENTITY

func idle_shoulder_placement(baseline: Animation, candidate: Animation, rig: Skeleton3D) -> void:
	var channels := {}
	for track: int in baseline.get_track_count():
		var bone := str(baseline.track_get_path(track).get_concatenated_subnames()).get_slice(":",0)
		if not channels.has(bone): channels[bone] = {}
		channels[bone][baseline.track_get_type(track)] = track
	for sample: int in 49:
		var time := candidate.length*float(sample)/48.0
		var before := POLISH._pose_at(baseline,rig,channels,time)
		var after := POLISH._pose_at(candidate,rig,channels,time)
		for side: String in ["l","r"]:
			var upper := rig.find_bone("upperarm_"+side)
			var lower := rig.find_bone("lowerarm_"+side)
			var hand := rig.find_bone("hand_"+side)
			var shift: Vector3 = after.global[hand].origin-before.global[hand].origin
			expect(shift.z < -0.04 and shift.z > -0.085, "male idle hands move subtly posterior through the full cycle")
			expect(absf(shift.x) < 0.00001 and absf(shift.y) < 0.026, "male idle shoulder extension preserves hand width and nearly preserves height")
			var original_bend: float = (before.global[lower].origin-before.global[upper].origin).angle_to(before.global[hand].origin-before.global[lower].origin)
			var new_bend: float = (after.global[lower].origin-after.global[upper].origin).angle_to(after.global[hand].origin-after.global[lower].origin)
			expect(absf(original_bend-new_bend) < 0.00001, "idle extension carries the native arm chain without changing elbow flexion")

func held_variants(source: AnimationLibrary, result: AnimationLibrary, sex: String, rig: Skeleton3D) -> void:
	# Reconstruct the accepted travel grip before the new free-hand fist. The
	# baseline is independent of which run variant the actor currently plays.
	var baseline := POLISH._travel(source.get_animation(&"Run_Female"),true,
		POLISH._walking_hands(source.get_animation(&"Walk")))
	if sex == "male":
		POLISH._male_placement(baseline,rig,true)
		POLISH._male_running_hands(baseline,source.get_animation(&"Fighting_Idle"),rig)
	var free := result.get_animation(&"Run_Female")
	expect(POLISH.run_clip_for_hands(0) == &"Run_Female", "empty hands select the free running fist")
	for mask: int in range(1,4):
		var expected_name: StringName = [&"Human_Run_Hold_L",&"Human_Run_Hold_R",&"Human_Run_Hold_Both"][mask-1]
		expect(POLISH.run_clip_for_hands(mask) == expected_name, "held mask maps to its actual left/right hands")
		expect(result.has_animation(expected_name), "held running variant exists "+str(expected_name))
		var held := result.get_animation(expected_name)
		expect(held.length == free.length and held.loop_mode == free.loop_mode and held.step == free.step, "held run keeps the exact free run timing")
		expect(held.get_track_count() == free.get_track_count(), "held variant adds no animation channels")
		expect(held.get_marker_names() == free.get_marker_names(), "held run marker names stay exact")
		for marker: StringName in free.get_marker_names():
			expect(held.get_marker_time(marker) == free.get_marker_time(marker), "held run event time stays exact")
		var restored := {"l":0,"r":0}
		for track: int in free.get_track_count():
			var bone := str(free.track_get_path(track).get_concatenated_subnames()).get_slice(":",0)
			var finger := free.track_get_type(track) == Animation.TYPE_ROTATION_3D and bone.get_slice("_",0) in ["thumb","index","middle","ring","pinky"]
			var side := "l" if bone.ends_with("_l") else "r" if bone.ends_with("_r") else ""
			var selected := finger and ((side == "l" and mask & 1) or (side == "r" and mask & 2))
			var expected := baseline if selected else free
			expect(held.track_get_path(track) == free.track_get_path(track) and held.track_get_type(track) == free.track_get_type(track), "held run track identity stays exact")
			expect(held.track_get_key_count(track) == free.track_get_key_count(track), "held run key count stays exact")
			expect(held.track_get_interpolation_type(track) == free.track_get_interpolation_type(track) and held.track_get_interpolation_loop_wrap(track) == free.track_get_interpolation_loop_wrap(track), "held run interpolation stays exact")
			for key: int in free.track_get_key_count(track):
				expect(held.track_get_key_time(track,key) == free.track_get_key_time(track,key) and held.track_get_key_transition(track,key) == free.track_get_key_transition(track,key), "held run authored key timing stays exact")
				var value: Variant = held.track_get_key_value(track,key)
				expect(value == expected.track_get_key_value(track,key), "held fingers match their accepted grip; free fingers and all other motion stay exact")
				if selected and value != free.track_get_key_value(track,key): restored[side] += 1
		for side: String in ["l","r"]:
			var selected := (mask & (1 if side == "l" else 2)) != 0
			expect(int(restored[side]) > 0 if selected else int(restored[side]) == 0, "only the requested hand restores its pre-fist finger motion")

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
		for name: StringName in source.get_animation_list():
			expect(result.has_animation(name), "all original clip names persist "+str(name))
		if not human: expect(source.get_animation_list() == result.get_animation_list(), "other races gain no Human animation aliases")
		for action: String in animations.actions:
			expect(result.has_animation(animations.actions[action]), "all mapped actions remain available " + action)
		for name: StringName in source.get_animation_list():
			var old := source.get_animation(name)
			var new := result.get_animation(name)
			action_audit.append({"model": slug, "clip": name, "length": new.length,
				"tracks": new.get_track_count(), "loop_mode": new.loop_mode,
				"shared_original": old == new, "source_snapshot_hash": original[name].hash()})
			expect(snapshot(old) == original[name], "source remains immutable " + str(name))
			var travel := name in POLISH.CLIPS
			var idle := name in POLISH.IDLE_CLIPS
			if not human or (not travel and not idle):
				expect(old == new, "unchanged original action resources remain shared " + str(name))
				continue
			if slug == "luminous_female" and travel:
				expect(arm_digest(new) == FEMALE_V1[name], "female locomotion remains exactly the accepted v1 output")
			var idle_baseline := POLISH._idle_arms(old,result.get_animation(&"Walk")) if idle else null
			expect(old != new and new.length == old.length and new.loop_mode == old.loop_mode and new.step == old.step, "standing/travel derivatives preserve original timing " + str(name))
			expect(new.get_track_count() == old.get_track_count(), "no track added or removed " + str(name))
			expect(new.get_marker_names() == old.get_marker_names(), "original event marker names persist")
			for marker: StringName in old.get_marker_names():
				expect(new.get_marker_time(marker) == old.get_marker_time(marker), "original event marker times remain exact")
			var modified := 0
			var worst_loop := 0.0
			var largest_arm_step := 0.0
			var copied_keys := 0
			var minimum_thumb_alignment := 1.0
			var source_worst_loop := 0.0
			for track: int in old.get_track_count():
				copied_keys += old.track_get_key_count(track)
				var bone := str(old.track_get_path(track).get_concatenated_subnames()).get_slice(":", 0)
				var arm_rotation := old.track_get_type(track) == Animation.TYPE_ROTATION_3D and bone in POLISH.ARM_BONES
				var run_fingers := (name == &"Run_Female" and old.track_get_type(track) == Animation.TYPE_ROTATION_3D
					and bone.get_slice("_",0) in ["thumb","index","middle","ring","pinky"])
				var male_run_detail := (slug == "luminous_male" and name == &"Run_Female"
					and old.track_get_type(track) == Animation.TYPE_ROTATION_3D
					and bone in ["spine_01", "spine_02", "neck_01"])
				var permitted_rotation := arm_rotation or run_fingers or male_run_detail
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
						if idle and arm_rotation:
							var target := idle_arm_target(result.get_animation(&"Walk"),bone)
							var posterior_shoulder := slug == "luminous_male" and bone in ["upperarm_l","upperarm_r"]
							var allowance := deg_to_rad(7.01) if posterior_shoulder else 0.0
							expect(rotation_delta(q,target) <= rotation_delta(before,target)*0.15+allowance+0.00001, "idle arms settle close to the accepted walk midpoint with a bounded male shoulder extension")
					else:
						expect(after == before, "all protected root/leg/position/scale/other-action channels remain exact")
					if idle:
						var shoulder_extension := slug == "luminous_male" and arm_rotation and bone in ["upperarm_l","upperarm_r"]
						var baseline_value: Variant = idle_baseline.track_get_key_value(track,index)
						if shoulder_extension:
							expect(absf(rotation_delta(baseline_value,after)-deg_to_rad(7.0)) < 0.00001, "only a seven-degree shoulder extension changes the accepted male idle")
						else:
							expect(after == baseline_value, "female idle and all non-shoulder male idle channels remain exact")
				if permitted_rotation:
					modified += int(changed)
					var first := new.rotation_track_interpolate(track, 0.0)
					var last := new.rotation_track_interpolate(track, new.length)
					worst_loop = maxf(worst_loop, rotation_delta(first, last))
					source_worst_loop = maxf(source_worst_loop, rotation_delta(old.rotation_track_interpolate(track,0.0),old.rotation_track_interpolate(track,old.length)))
				expect(new.track_get_interpolation_type(track) == old.track_get_interpolation_type(track), "interpolation unchanged")
			expect(modified > 0 and worst_loop < (source_worst_loop*0.15+0.0001 if idle else 0.0001), "arm polish is visible and retains cyclic continuity " + str(name))
			expect(largest_arm_step < deg_to_rad(25), "no abrupt arm/wrist key jump " + str(name))
			if idle and slug == "luminous_male":
				idle_shoulder_placement(idle_baseline,new,actor.get_skeleton())
			if slug == "luminous_male" and travel:
				player.play(name)
				player.pause()
				var rig := actor.get_skeleton()
				var abductions: Array[float] = []
				for sample: int in range(49):
					player.seek(new.length * float(sample) / 48.0, true)
					rig.force_update_all_bone_transforms()
					for side: String in ["l", "r"]:
						var shoulder := rig.get_bone_global_pose(rig.find_bone("upperarm_" + side)).origin
						var elbow := rig.get_bone_global_pose(rig.find_bone("lowerarm_" + side)).origin
						var wrist := rig.get_bone_global_pose(rig.find_bone("hand_" + side)).origin
						var spread := (elbow.x - shoulder.x) * (1 if side == "l" else -1)
						# Frontal reference upperarms angle outward. Allow for native
						# proportions and uncertain shoulder centres under the cape.
						var frontal_angle := rad_to_deg(atan2(spread, shoulder.y-elbow.y))
						abductions.append(frontal_angle)
						expect(frontal_angle > (18.0 if name == &"Run_Female" else 12.0)
							and frontal_angle < (36.0 if name == &"Run_Female" else 30.0), "male elbow abduction follows the frontal video envelope")
						var upper_direction := (elbow-shoulder).normalized()
						var native_hinge := rig.get_bone_global_pose(rig.find_bone("upperarm_"+side)).basis*rig.get_bone_rest(rig.find_bone("lowerarm_"+side)).basis.x
						native_hinge = (native_hinge-upper_direction*native_hinge.dot(upper_direction)).normalized()
						var bend_normal := upper_direction.cross((wrist-elbow).normalized()).normalized()
						expect(native_hinge.dot(bend_normal)>cos(deg_to_rad(2.0)), "native elbow hinge aligns with the actual bend on both arms")
						if name == &"Run_Female":
							var flex := rad_to_deg((elbow - shoulder).angle_to(wrist - elbow))
							expect(flex > 78.5 and flex < 104.5, "male running bend retains rear release and the raised forward forearm")
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
				expect(float(abductions.max())-float(abductions.min()) > 2.0, "elbow abduction varies through the observed pump instead of following a fixed rail")
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
					for side: String in ["l", "r"]:
						player.seek(new.length * (0.0 if side == "l" else 0.5), true)
						rig.force_update_all_bone_transforms()
						var shoulder := rig.get_bone_global_pose(rig.find_bone("upperarm_"+side)).origin
						var wrist := rig.get_bone_global_pose(rig.find_bone("hand_"+side)).origin
						var pelvis := rig.get_bone_global_pose(rig.find_bone("pelvis")).origin
						var drop := (shoulder.y-wrist.y)/(shoulder.y-pelvis.y)
						expect(drop > 0.18 and drop < 0.37, "forward running hand stays near the observed sternum height with the wider elbow")
						expect((wrist.x-pelvis.x)*(1 if side == "l" else -1)>0.05, "running hand stays on its own side of the sternum")
			metrics.append({"model": slug, "clip": name, "duration": new.length, "modified_rotation_tracks": modified,
				"minimum_thumb_alignment":minimum_thumb_alignment,
				"max_loop_degrees": rad_to_deg(worst_loop), "first_install_usec": build_usec,
				"copied_keys": copied_keys, "tracks": old.get_track_count(), "max_rotation_key_step_degrees": rad_to_deg(largest_arm_step)})
		if human: held_variants(source,result,str(models[slug].gender),actor.get_skeleton())
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
