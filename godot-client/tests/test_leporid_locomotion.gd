extends SceneTree
## Exercise actual native actors, movement commands and the mount's hop cadence.
const Profiles := preload("res://src/mounts/mount_profiles.gd")
var failures := 0
var checks := 0

func _init() -> void:
	_run.call_deferred()

func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func _run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/models.json")).models
	var mount := Profiles.read("rabbit")
	for species: String in ["rabbit", "jackalope"]:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var config: Dictionary = models[species]
		var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
		var adapter := CoordinateAdapter.new({"metresPerTile": 1.0})
		var dto := {"actor_id": 42, "x": 0, "y": 0, "rotation": 0,
			"command": 7, "kind": 5, "name": species, "health": 10, "max_health": 10}
		var errors := actor.configure(dto, adapter, config, mapping)
		check(errors.is_empty(), species + " native actor loads: " + str(errors))
		if actor.animation_player == null:
			check(false, species + " animation player exists")
			actor.free()
			continue
		actor.set_physics_process(false)
		actor.animation_player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		for command: int in range(20, 38):
			if command in [28, 29]: continue
			dto.x += 8
			dto.command = command
			dto.buffs = 0
			actor.apply_server_state(dto, adapter)
			var action: StringName = &"run" if command >= 30 else &"walk"
			check(actor.current_action == action, species + " movement command " + str(command))
			check(actor.animation_player.current_animation == mount.clips.trot,
				species + " moves with the mount's native hop")
			var duration := actor.animation_player.current_animation_length
			var limit: float = mount.maximumCyclesPerSecond.gallop if action == &"run" else mount.maximumCyclesPerSecond.trot
			check(is_equal_approx(actor.animation_player.speed_scale / duration, limit),
				species + " uses the mounted hop cadence for " + str(action))
		# Haste arrives as a walk command with a buff, rather than a run command.
		dto.x += 8
		dto.command = 22
		dto.buffs = EloriaProtocol.ACTOR_BUFF_DOUBLE_SPEED
		actor.apply_server_state(dto, adapter)
		check(actor.current_action == &"run", species + " haste uses the faster hop")
		check(is_equal_approx(actor.animation_player.speed_scale / actor.animation_player.current_animation_length,
			float(mount.maximumCyclesPerSecond.gallop)), species + " haste cadence stays readable")
		var authority := actor.global_transform
		# Complete the movement crossfade before sampling a full source cycle.
		actor.animation_player.advance(1.0)
		var sk := actor.get_skeleton()
		var hip := sk.find_bone("hips")
		check(hip >= 0, species + " native hip exists")
		var low := INF
		var high := -INF
		for frame: int in range(61):
			actor.animation_player.seek(actor.animation_player.current_animation_length * frame / 60.0, true)
			sk.force_update_all_bone_transforms()
			var height: float = (sk.global_transform * sk.get_bone_global_pose(hip)).origin.y
			low = minf(low, height)
			high = maxf(high, height)
		check(high - low > 0.01, species + " hop visibly lifts the body")
		check(actor.global_transform.is_equal_approx(authority), species + " hopping preserves network placement")
		# Caps apply after stride/actor scaling, including giant invasion variants.
		for scale: float in [0.5, 1.0, 3.0]:
			actor.set_server_scale(scale)
			actor._segment_duration = 0.0
			actor._presentation_speed = 100.0
			actor.play_action(&"walk", true)
			check(is_equal_approx(actor.animation_player.speed_scale / actor.animation_player.current_animation_length,
				float(mount.maximumCyclesPerSecond.trot)), species + " scaled hop cadence " + str(scale))
		actor.set_server_scale(1.0)
		actor._presentation_speed = actor.resolver.stride_speed_for_action(&"walk", actor._small_creature_scale) * 0.5
		actor.play_action(&"walk", true)
		check(is_equal_approx(actor.animation_player.speed_scale, 0.5), species + " slow movement still follows stride speed")
		for action: StringName in [&"idle", &"attack_primary", &"pain", &"death"]:
			actor.play_action(action, true)
			check(actor.current_action == action and is_equal_approx(actor.animation_player.speed_scale, 1.0),
				species + " preserves " + str(action))
		actor.free()
	# A species without a cadence limit retains the existing stride calculation.
	var ordinary := ReplicatedActor3D.new()
	ordinary.resolver = AnimationResolver.new({"strideMetresPerSecond": {"walk": 2.0}})
	ordinary._presentation_speed = 3.0
	check(is_equal_approx(ordinary._playback_speed_for(&"walk"), 1.5), "other species retain stride playback")
	ordinary.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("LEPORID_LOCOMOTION ", "PASS" if failures == 0 else "FAIL", " checks=", checks, " failures=", failures)
	quit(1 if failures else 0)
