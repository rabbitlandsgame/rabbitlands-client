extends Node3D
## Profile-driven mount presentation on the real player and its wardrobe.
const RiderPose := preload("res://src/mounts/rider_seat_pose.gd")
const RustPose := preload("res://src/mounts/rust_rider_pose.gd")
const ReinVisual := preload("res://src/mounts/mount_reins.gd")
const CapeSurface := preload("res://src/mounts/mount_cape_surface.gd")
const UpperBody := preload("res://src/mounts/mounted_upper_body.gd")
const Profiles := preload("res://src/mounts/mount_profiles.gd")
const BorrowedTack := preload("res://src/mounts/borrowed_mount_tack.gd")
const HindLegPose := preload("res://src/mounts/mount_hind_leg_pose.gd")
var actor: ReplicatedActor3D
var pony: ReplicatedActor3D
var pose := RiderPose.new()
var rust_pose := RustPose.new()
var reins := ReinVisual.new()
var profile: Dictionary
var state: Dictionary = {}
var saddle := -1
var head := -1
var sockets: Dictionary = {}
var elapsed := 0.0
var action := ""
var modifiers: Dictionary = {}
var cape_surface := CapeSurface.new()
var upper := UpperBody.new()
var seat_rest_inverse := Transform3D.IDENTITY
var tack: Node3D
var bridle_paths: Array[PackedVector3Array] = []
var hind_legs := HindLegPose.new()
var locomotion: RefCounted
var banner_head_height := 0.0
var _requested_tier := AnimationGate.Tier.FULL
var _effective_tier := AnimationGate.Tier.FULL
var _one_shot_tier := AnimationGate.Tier.HALF
var _gating_enabled := true
var _stagger_enabled := true
var _pending_delta := 0.0
var _sample_tick := 0
var _parked := false
var _cloth_was_enabled := false
var _rider_modifier_process := Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_IDLE
var _pose_steps := 0
var _stepped_seconds := 0.0
var _presentation_view_radius := 0.0

func configure(player: ReplicatedActor3D, models: Dictionary, mount_id := "moor_pony",
		visual_profile: Dictionary = {}) -> Array[String]:
	actor = player
	profile = Profiles.read(mount_id) if visual_profile.is_empty() else visual_profile.duplicate(true)
	if profile.is_empty() or not models.has(mount_id):
		return ["Mount visual profile missing: " + mount_id]
	pony = ReplicatedActor3D.new()
	pony.name = str(profile.get("displayName", "MoorPony")).replace(" ", "")
	add_child(pony)
	var config: Dictionary = models[mount_id].duplicate(true)
	config.import.scale = float(config.import.scale) * float(profile.get("visualScale", 1.0))
	var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	# Mount gaits can use clips the unmounted creature no longer requests.
	for gait: String in profile.clips:
		mapping.actions["mount_" + gait] = profile.clips[gait]
	var errors := pony.configure({"actor_id": actor.actor_id, "x": 0, "y": 0,
		"rotation": 0, "kind": 5, "name": "", "scale": 1.0}, CoordinateAdapter.new(), config, mapping)
	if not errors.is_empty():
		return errors
	var offset: Array = profile.get("visualOffsetMetres", [0.0, 0.0, 0.0])
	pony.position = Vector3(float(offset[0]), float(offset[1]), float(offset[2]))
	pony.server_target = Vector3.ZERO
	pony.collision_layer = 0
	pony.set_physics_process(false)
	pony.set_process(false)
	pony.animation_player.pause()
	pony.animation_player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	for child: Node in pony.get_children():
		if child is Node3D and child.name != "NativeModel":
			(child as Node3D).hide()
	saddle = pony.get_skeleton().find_bone(str(profile.saddleBone))
	head = pony.get_skeleton().find_bone(str(profile.reins.headBone))
	if saddle < 0 or head < 0:
		return [mount_id + " seat/bridle attachment missing"]
	seat_rest_inverse = pony.get_skeleton().get_bone_global_rest(saddle).affine_inverse()
	var hind_errors := hind_legs.configure(pony.get_skeleton(), profile.get("hindLegPose", {}))
	if not hind_errors.is_empty():
		return hind_errors
	if profile.has("locomotionAdapter"):
		locomotion = preload("res://src/mounts/tortoise_locomotion.gd").new()
		var locomotion_errors: Array[String] = locomotion.configure(pony.get_skeleton(), profile.locomotionAdapter)
		if not locomotion_errors.is_empty(): return locomotion_errors
	var head_rest := pony.get_skeleton().get_bone_global_rest(head)
	for side: String in ["l", "r"]:
		var values: Array = profile.reins.bridleAnchorsNative[side]
		sockets[side] = head_rest.affine_inverse() * Vector3(float(values[0]), float(values[1]), float(values[2]))
	for path: Array in profile.reins.get("bridlePathsNative", []):
		var points := PackedVector3Array()
		for values: Array in path:
			points.append(head_rest.affine_inverse() * Vector3(float(values[0]), float(values[1]), float(values[2])))
		bridle_paths.append(points)
	if profile.has("borrowedTack"):
		tack = BorrowedTack.new()
		add_child(tack)
		var tack_errors: Array[String] = tack.configure(pony.get_skeleton(), profile.borrowedTack)
		if not tack_errors.is_empty():
			return tack_errors
	var player_anim := actor.animation_player
	if player_anim == null or not player_anim.has_animation("Rest_Pose") or not player_anim.has_animation("Fighting_Idle"):
		return ["Player riding reference poses missing"]
	player_anim.play("Rest_Pose")
	player_anim.seek(0.0, true)
	player_anim.pause()
	errors = pose.configure(actor, actor.get_skeleton(), profile,
		player_anim.get_animation("Fighting_Idle"), actor.get_node("NativeModel") as Node3D)
	if not errors.is_empty():
		return errors
	rust_pose.configure(pose, mount_id)
	# Anchor the banner to the neutral seat height, independent of saddle bob
	# and pitch during animation. Retain the current rider's body dimensions.
	var seat_point: Vector3
	if profile.has("seatPositionNative"):
		var point: Array = profile.seatPositionNative
		seat_point = Vector3(float(point[0]), float(point[1]), float(point[2]))
	else:
		var seat_offset: Array = profile.seatOffsetNative
		seat_point = pony.get_skeleton().get_bone_global_rest(saddle) * Vector3(
			float(seat_offset[0]), float(seat_offset[1]), float(seat_offset[2]))
	banner_head_height = actor.head_height() + actor.to_local(
		pony.get_skeleton().to_global(seat_point)).y - pose.baseline_pelvis.y
	upper.configure(actor)
	for modifier: Node in actor.get_skeleton().find_children("*", "SkeletonModifier3D", true, false):
		modifiers[modifier] = (modifier as SkeletonModifier3D).active
		(modifier as SkeletonModifier3D).active = false
	cape_surface.configure(pony.get_skeleton(), profile.get("capeContact", []), profile.get("capeMotion", {}))
	if actor._cape_cloth != null:
		actor._cape_cloth.call("set_mount_surface", cape_surface)
	actor.set_hand_props_visible(false)
	add_child(reins)
	reins.configure(profile.reins)
	_rider_modifier_process = actor.get_skeleton().modifier_callback_mode_process
	actor.get_skeleton().modifier_callback_mode_process = Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_MANUAL
	pony.get_skeleton().modifier_callback_mode_process = Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_MANUAL
	apply_render_quality(actor.render_quality(), actor.render_quality_is_local())
	_capture_presentation_view_radius()
	return []

## Main tests a sphere centred one metre above the rider's ground position.
## Capture the approved mount's imported bounds once, including its visual
## offset/scale and raised rider banner, so visible extremities do not freeze
## when a human-only sphere falls outside the frustum. No per-frame mesh walk.
func _capture_presentation_view_radius() -> void:
	_presentation_view_radius = maxf(pony.view_radius() + pony.position.length(), banner_head_height + 0.6)
	var model := pony.get_node_or_null("NativeModel") as Node3D
	if model == null:
		return
	var bounds: AABB = (pony.transform * model.transform) * pony._native_body_bounds
	for corner: int in 8:
		_presentation_view_radius = maxf(_presentation_view_radius,
			bounds.get_endpoint(corner).distance_to(Vector3.UP) + 0.5)

func presentation_view_radius() -> float:
	return _presentation_view_radius

func apply_render_quality(level: int, is_local_actor := false) -> void:
	if is_instance_valid(pony):
		pony.apply_render_quality(level, is_local_actor)
	ActorRenderQuality.apply_actor(self, level)
	refresh_cloth_permission(true)

func set_animation_tier(tier: int, one_shot_tier := AnimationGate.Tier.HALF,
		gating_enabled := true, stagger_enabled := true) -> void:
	_requested_tier = tier
	_one_shot_tier = one_shot_tier
	_gating_enabled = gating_enabled
	_stagger_enabled = stagger_enabled
	_parked = false
	_update_effective_tier(true)

func _has_one_shot() -> bool:
	if upper.action.is_empty():
		return false
	var clip := upper.clips.get(upper.action) as Animation
	return bool(upper.get("_returning")) or (clip != null and clip.loop_mode == Animation.LOOP_NONE)

func _update_effective_tier(force := false) -> void:
	var tier := _requested_tier if _gating_enabled else AnimationGate.Tier.FULL
	if _parked:
		tier = AnimationGate.Tier.PAUSED
	elif actor.mounted_presentation_priority():
		tier = AnimationGate.Tier.FULL
	elif tier == AnimationGate.Tier.PAUSED and _has_one_shot():
		tier = _one_shot_tier
	if not force and tier == _effective_tier:
		return
	var was_paused := _effective_tier == AnimationGate.Tier.PAUSED
	_effective_tier = tier
	if was_paused or tier == AnimationGate.Tier.PAUSED:
		_pending_delta = 0.0
	actor._set_mounted_animation_tier(tier)
	pony._set_model_processing(tier != AnimationGate.Tier.PAUSED)
	actor.get_skeleton().modifier_callback_mode_process = Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_MANUAL
	pony.get_skeleton().modifier_callback_mode_process = Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_MANUAL
	set_process(tier != AnimationGate.Tier.PAUSED)
	refresh_cloth_permission(true)

func pause_for_parking() -> void:
	_parked = true
	_pending_delta = 0.0
	_update_effective_tier(true)

func cape_simulation_enabled() -> bool:
	return not _parked and is_instance_valid(actor) and actor.is_drawn() \
		and is_visible_in_tree() and actor.cape_cloth_should_simulate()

func refresh_cloth_permission(reset_when_enabled := true) -> void:
	var enabled := cape_simulation_enabled()
	if enabled and reset_when_enabled and not _cloth_was_enabled:
		actor._cape_cloth.call("reset")
	_cloth_was_enabled = enabled

func scheduling_stats() -> Dictionary:
	return {"requestedTier": _requested_tier, "tier": _effective_tier,
		"poseSteps": _pose_steps, "steppedSeconds": _stepped_seconds,
		"pendingSeconds": _pending_delta, "parked": _parked, "staggered": _stagger_enabled,
		"cloth": cape_simulation_enabled()}

func _process(delta: float) -> void:
	if _parked or not is_instance_valid(actor):
		return
	_update_effective_tier()
	if _effective_tier == AnimationGate.Tier.PAUSED:
		return
	_pending_delta += maxf(0.0, delta)
	_sample_tick += 1
	var stride := 2 if _effective_tier == AnimationGate.Tier.HALF else (
		4 if _effective_tier == AnimationGate.Tier.QUARTER else 1)
	var phase := actor.actor_id if _stagger_enabled else 0
	if (_sample_tick + phase) % stride != 0:
		return
	var step := _pending_delta
	_pending_delta = 0.0
	# Offscreen one-shots finish on their clock, but an invisible arrival or
	# out-of-range body needs no mount/rein/cloth pose computation.
	var frustum_paused := _gating_enabled and _requested_tier == AnimationGate.Tier.PAUSED \
		and not actor.mounted_presentation_priority()
	if frustum_paused or not actor.is_drawn() or not is_visible_in_tree():
		if _has_one_shot():
			upper.advance(step)
		_update_effective_tier()
		return
	_step_visual(step)
	_pose_steps += 1
	_stepped_seconds += step
	_update_effective_tier()

func _step_visual(delta: float) -> void:
	upper.advance(delta)
	var moving := upper.ground_action in [&"walk", &"run"] or actor.current_action in [&"walk", &"run"] or actor._segment_duration > 0.0
	var next := "idle"
	if moving:
		next = "walk" if state.get("gait") == "walk" else ("gallop" if state.get("gait") == "burst" else "trot")
	if next != action:
		action = next
		elapsed = 0.0
	var rate := 1.0
	if action != "idle":
		var speed_key := {"walk": "walkStrideMetresPerSecond", "trot": "trotStrideMetresPerSecond", "gallop": "gallopStrideMetresPerSecond"}
		rate = actor._travel_speed() / maxf(.01, float(profile[speed_key[action]]))
		var playback_multipliers: Dictionary = profile.get("playbackRateMultipliers", {})
		rate *= float(playback_multipliers.get(action, 1.0))
	var clip: String = profile.clips[action]
	var duration := float(profile.get("cycleLengths", {}).get(action, pony.animation_player.get_animation(clip).length))
	# High travel speeds must not turn short source strides into frantic limbs.
	# This presentation limit changes the clip clock only; the server owns pace.
	var cadence: Dictionary = profile.get("maximumCyclesPerSecond", {})
	if cadence.has(action):
		rate = minf(rate, duration * float(cadence[action]))
	elapsed += delta * rate
	if locomotion != null:
		locomotion.apply(action, elapsed, duration)
	else:
		pony.animation_player.play(clip)
		pony.animation_player.seek(fposmod(elapsed, duration), true)
		pony.animation_player.pause()
	pony.get_skeleton().force_update_all_bone_transforms()
	hind_legs.apply(action)
	actor.animation_player.pause()
	var bone := pony.get_skeleton().global_transform * pony.get_skeleton().get_bone_global_pose(saddle)
	var seat: Transform3D
	if profile.has("seatPositionNative"):
		var point: Array = profile.seatPositionNative
		var frame := bone * seat_rest_inverse
		seat = Transform3D(frame.basis.orthonormalized(), frame * Vector3(float(point[0]), float(point[1]), float(point[2])))
	else:
		var offset: Array = profile.seatOffsetNative
		seat = Transform3D(bone.basis.orthonormalized(), bone * Vector3(float(offset[0]), float(offset[1]), float(offset[2])))
	if tack != null:
		tack.update_pose()
	# Gait-specific lean is optional; other mounts keep their approved pose.
	var lean_key := "gallopPelvisLeanDegrees" if action == "gallop" else "normalPelvisLeanDegrees"
	if profile.has(lean_key):
		profile.pelvisLeanDegrees = float(profile[lean_key])
	if rust_pose.try_fit(seat, action, elapsed, duration, _finish_visual.bind(delta, seat, action)):
		return
	pose.fit(seat, action, elapsed, duration)
	_finish_visual(delta, seat, action)

func _finish_visual(delta: float, seat: Transform3D, gait: String) -> void:
	var native_secondary := rust_pose.consume_native_upper_applied()
	if not native_secondary:
		upper.apply()
	refresh_cloth_permission(true)
	if actor._cape_cloth != null:
		actor._cape_cloth.call("set_native_mounted_constraint_kernel", rust_pose.mounted_constraint_backend())
	if cape_simulation_enabled():
		# Pose the body first, then cloth, once. The ordinary automatic modifier
		# remains paused so it cannot overwrite this mounted pass afterward.
		cape_surface.update(delta, gait)
		actor._cape_cloth.call("_process_modification_with_delta", delta)
		actor.get_skeleton().force_update_all_bone_transforms()
	actor._lift_overhead(actor.server_scale)
	if not native_secondary or rust_pose._mode() != "rust":
		var head_frame := pony.get_skeleton().global_transform * pony.get_skeleton().get_bone_global_pose(head)
		var bridle: Dictionary = {}
		for side: String in ["l", "r"]:
			bridle[side] = head_frame * (sockets[side] as Vector3)
		var parked := {}
		for side: String in ["l", "r"]:
			var sign_value := 1.0 if side == "l" else -1.0
			var grip := reins.grip_world(actor.get_skeleton(), side)
			var exit := reins.grip_exit_world(actor.get_skeleton(), side)
			var saddle_grip := seat.origin + seat.basis * Vector3(sign_value * .055, .12, .21)
			parked[side] = [grip.lerp(saddle_grip, upper.grip_weight), exit.lerp(saddle_grip + Vector3.DOWN * .025, upper.grip_weight)]
		var straps: Array[PackedVector3Array] = []
		for path: PackedVector3Array in bridle_paths:
			var points := PackedVector3Array()
			for point: Vector3 in path:
				points.append(head_frame * point)
			straps.append(points)
		reins.update_contact(bridle, actor.get_skeleton(), seat.basis, parked, straps)
	actor.set_hand_props_visible(false)
	if actor.combat_presentation != null:
		actor.combat_presentation.update_pose()

func play_action(next: StringName, restart := false) -> void:
	upper.request(next, restart)
	_update_effective_tier()

func restore() -> void:
	rust_pose.close()
	_parked = true
	set_process(false)
	_pending_delta = 0.0
	if actor._cape_cloth != null:
		actor._cape_cloth.call("set_mount_surface", null)
	if pose.skeleton != null:
		pose.restore()
	for modifier: Node in modifiers:
		if is_instance_valid(modifier):
			(modifier as SkeletonModifier3D).active = bool(modifiers[modifier])
	if actor.get_skeleton() != null:
		actor.get_skeleton().modifier_callback_mode_process = _rider_modifier_process
	actor.set_hand_props_visible(true)
	actor._refresh_cape_cloth_activity(true)
	actor._lift_overhead(actor.server_scale)

func _exit_tree() -> void:
	rust_pose.close()
