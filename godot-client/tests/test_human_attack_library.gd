extends SceneTree
## Actual imported Human rigs: one-shot cuts, source preservation, grip and
## opposite-arm ownership, native-axis symmetry and immutable cache sharing.
const CUTS := preload("res://src/actors/human_attack_library.gd")
const LOCOMOTION := preload("res://src/actors/human_locomotion_polish.gd")
var checks := 0
var failures := 0
var metrics: Array = []
func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)
func digest(animation: Animation) -> int:
	var values: Array = [animation.length, animation.loop_mode, animation.step]
	for track: int in animation.get_track_count():
		values.append([animation.track_get_type(track), animation.track_get_path(track),
			animation.track_get_interpolation_type(track), animation.track_is_enabled(track)])
		for key: int in animation.track_get_key_count(track):
			values.append([animation.track_get_key_time(track, key), animation.track_get_key_value(track, key)])
	return values.hash()
func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	CUTS.clear()
	for slug: String in ["luminous_male", "luminous_female"]:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		expect(actor.configure({"actor_id": 9989, "actor_type": 1, "x": 0, "y": 0,
			"rotation": 0, "appearance": {}, "equipment_visuals": {}}, CoordinateAdapter.new({"walkingHeight": 0.0}), models[slug], config, equipment).is_empty(), slug + " loads actual rig")
		actor.set_process(false)
		actor.set_physics_process(false)
		actor._weapon_carry.active = false
		var player := actor.animation_player
		player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		var source: AnimationLibrary = player.get_meta(LOCOMOTION.SOURCE_META)
		var result := player.get_animation_library(&"")
		var before: Dictionary = {}
		for name: StringName in source.get_animation_list(): before[name] = digest(source.get_animation(name))
		var existing: Dictionary = {}
		for name: StringName in result.get_animation_list():
			var animation := result.get_animation(name)
			if not animation.has_meta(&"human_single_cut") and not animation.has_meta(&"human_combat_guard"):
				existing[name] = animation
		# Actor configuration already appends these clips. Measure actual cold
		# construction separately from the shared-cache path.
		CUTS.clear()
		var started := Time.get_ticks_usec()
		CUTS.append(result, source, models[slug], actor.get_skeleton())
		var cold := Time.get_ticks_usec() - started
		started = Time.get_ticks_usec()
		CUTS.append(result, source, models[slug], actor.get_skeleton())
		metrics.append({"model": slug, "cold_usec": cold, "warm_usec": Time.get_ticks_usec() - started})
		for name: StringName in source.get_animation_list():
			expect(before[name] == digest(source.get_animation(name)), "source exact " + str(name))
		for name: StringName in existing:
			expect(result.get_animation(name) == existing[name], "existing action shared " + str(name))
		expect(result.get_animation(&"Human_Flurry_A") == source.get_animation(&"Combat_Slash_A"), "original A remains exact flurry")
		expect(result.get_animation(&"Human_Flurry_B") == source.get_animation(&"Combat_Slash_B"), "original B remains exact flurry")
		var rig := actor.get_skeleton()
		var guard := result.get_animation(CUTS.guard_clip())
		var raw_guard := source.get_animation(CUTS.GUARD)
		expect(guard != raw_guard and guard.length == raw_guard.length and guard.loop_mode == raw_guard.loop_mode, "named fitted guard preserves native timing")
		for track: int in raw_guard.get_track_count():
			var name := str(raw_guard.track_get_path(track).get_concatenated_subnames())
			for key: int in raw_guard.track_get_key_count(track):
				var original: Variant = raw_guard.track_get_key_value(track, key)
				var fitted: Variant = guard.track_get_key_value(track, key)
				if name == "upperarm_l" and raw_guard.track_get_type(track) == Animation.TYPE_ROTATION_3D:
					expect(original.angle_to(fitted) <= deg_to_rad(CUTS.SHIELD_CLEARANCE_DEGREES + 0.01), "guard clearance bounded to12degrees")
				else:
					expect(original == fitted, "guard root/feet/fingers/all other channels exact " + name)
		var base: Array[Quaternion] = []
		for bone: int in rig.get_bone_count():
			var path := NodePath(str(guard.track_get_path(0)).get_slice(":", 0) + ":" + rig.get_bone_name(bone))
			base.append(guard.rotation_track_interpolate(guard.find_track(path, Animation.TYPE_ROTATION_3D), 0.0))
		for side: String in ["r", "l"]:
			for name: StringName in CUTS.normal_clips(side):
				var clip := result.get_animation(name)
				var backhand := str(name).ends_with("Backhand")
				expect(clip.loop_mode == Animation.LOOP_NONE and is_equal_approx(clip.length, CUTS.DURATION), "one-shot bounded duration")
				expect(is_zero_approx(CUTS._transfer_weight(CUTS.CONTACT, backhand)), "shield transfer preserves exact contact")
				for sample: int in 129:
					var weight := CUTS._transfer_weight(CUTS.DURATION * sample / 128.0, backhand)
					expect(weight >= 0.0 and weight <= 1.0, "shoulder transfer bounded to 20 degrees")
				expect(clip.get_marker_names().count(&"contact") == 1, "exactly one presentation contact")
				expect(is_equal_approx(clip.get_marker_time(&"contact"), CUTS.CONTACT), "contact seconds exact")
				for track: int in clip.get_track_count():
					var type := clip.track_get_type(track)
					var bone_name := str(clip.track_get_path(track).get_concatenated_subnames())
					var bone := rig.find_bone(bone_name)
					var moving := bone_name in CUTS.TORSO or bone_name in (CUTS.ARM if side == "r" else CUTS.ARM.map(CUTS._opposite))
					if type == Animation.TYPE_ROTATION_3D and bone >= 0:
						expect(clip.rotation_track_interpolate(track, 0.0).angle_to(base[bone]) < 0.001, "starts in guard " + bone_name)
						expect(clip.rotation_track_interpolate(track, clip.length).angle_to(base[bone]) < 0.001, "recovers to same guard " + bone_name)
					for sample: int in 25:
						var t: float = clip.length * sample / 24.0
						if type == Animation.TYPE_ROTATION_3D:
							var value := clip.rotation_track_interpolate(track, t)
							expect(value.is_finite() and absf(value.length_squared() - 1.0) < 0.0001, "finite normalized rotations")
							if not moving and bone >= 0:
								expect(value.angle_to(base[bone]) < 0.001, "opposite arm/fingers/root/legs remain guard " + bone_name)
						elif type in [Animation.TYPE_POSITION_3D, Animation.TYPE_SCALE_3D]:
							var source_track := guard.find_track(clip.track_get_path(track), type)
							var value := clip.position_track_interpolate(track, t) if type == Animation.TYPE_POSITION_3D else clip.scale_track_interpolate(track, t)
							var baseline := guard.position_track_interpolate(source_track, 0.0) if type == Animation.TYPE_POSITION_3D else guard.scale_track_interpolate(source_track, 0.0)
							expect(value.is_equal_approx(baseline), "native positions/scales exact " + bone_name)
				var same := clip
				CUTS.append(result, source, models[slug], rig)
				expect(result.get_animation(name) == same, "warm actor shares immutable cut")
		# Other races must never opt in through the shared action map.
		var excluded := AnimationLibrary.new()
		for name: StringName in source.get_animation_list(): excluded.add_animation(name, source.get_animation(name))
		var old_count := excluded.get_animation_list().size()
		CUTS.append(excluded, source, {"culture": "orun", "bodyTemplate": "orun_male"}, rig)
		expect(excluded.get_animation_list().size() == old_count, "non-Human library exact")
		actor.free()
	print("human single attack tests: ", checks, " checks, ", failures, " failures; ", JSON.stringify(metrics))
	var out := OS.get_environment("RL_ATTACK_TEST_OUTPUT")
	if not out.is_empty():
		DirAccess.make_dir_recursive_absolute(out)
		FileAccess.open(out.path_join("checks.json"), FileAccess.WRITE).store_string(JSON.stringify({"checks": checks, "failures": failures, "metrics": metrics}))
	CUTS.clear()
	NativeAnimationImporter.clear()
	quit(0 if failures == 0 else 1)
