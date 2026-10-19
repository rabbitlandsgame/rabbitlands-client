extends Node3D
## Profile-driven mount presentation on the real player and its wardrobe.
const RiderPose := preload("res://src/mounts/rider_seat_pose.gd")
const ReinVisual := preload("res://src/mounts/mount_reins.gd")
const CapeSurface := preload("res://src/mounts/mount_cape_surface.gd")
const UpperBody := preload("res://src/mounts/mounted_upper_body.gd")
const Profiles := preload("res://src/mounts/mount_profiles.gd")
const BorrowedTack := preload("res://src/mounts/borrowed_mount_tack.gd")
const HindLegPose := preload("res://src/mounts/mount_hind_leg_pose.gd")
var actor: ReplicatedActor3D
var pony: ReplicatedActor3D
var pose := RiderPose.new()
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
	var errors := pony.configure({"actor_id": actor.actor_id, "x": 0, "y": 0,
		"rotation": 0, "kind": 5, "name": "", "scale": 1.0}, CoordinateAdapter.new(), config, mapping)
	if not errors.is_empty():
		return errors
	pony.position = Vector3.ZERO
	pony.server_target = Vector3.ZERO
	pony.collision_layer = 0
	pony.set_physics_process(false)
	pony.set_process(false)
	pony.animation_player.pause()
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
	return []

func _process(delta: float) -> void:
	if not actor.is_drawn() or not visible:
		return
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
	elapsed += delta * rate
	var clip: String = profile.clips[action]
	var duration := float(profile.get("cycleLengths", {}).get(action, pony.animation_player.get_animation(clip).length))
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
	pose.fit(seat, action, elapsed, duration)
	upper.apply()
	if actor._cape_cloth != null and actor._cape_cloth_worn:
		# Pose the body first, then cloth, once. The ordinary automatic modifier
		# remains paused so it cannot overwrite this mounted pass afterward.
		cape_surface.update(delta, action)
		actor._cape_cloth.call("_process_modification_with_delta", delta)
		actor.get_skeleton().force_update_all_bone_transforms()
	actor._lift_overhead(actor.server_scale)
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

func restore() -> void:
	if actor._cape_cloth != null:
		actor._cape_cloth.call("set_mount_surface", null)
	if pose.skeleton != null:
		pose.restore()
	for modifier: Node in modifiers:
		if is_instance_valid(modifier):
			(modifier as SkeletonModifier3D).active = bool(modifiers[modifier])
	actor.set_hand_props_visible(true)
	actor._refresh_cape_cloth_activity(true)
	actor._lift_overhead(actor.server_scale)
