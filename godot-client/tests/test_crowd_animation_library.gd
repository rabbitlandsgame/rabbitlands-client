extends SceneTree
## LAT-L1: the fingerless crowd animation variant and the per-player hand
## swap. Real imported rigs (orun_male + Universal library, and configured
## luminous/creature actors): the variant keeps every clip and every non-finger
## channel exactly, body poses match the full library, fingers hold, the swap
## keeps the playing clip, and every refusal keeps the full library.
## The actor-level checks run only once group A2 has added the thin hooks
## (ReplicatedActor3D.set_hand_detail and friends); they are reported as
## skipped otherwise.
const CROWD := preload("res://src/actors/crowd_animation_library.gd")
const POLISH := preload("res://src/actors/human_locomotion_polish.gd")
const RACE := "res://assets/actors/native/races/orun_male.glb"
const LIBRARY := "res://assets/actors/native/shared/Universal_Animation_Library.glb"
const CLIPS := ["Idle_A", "Walk", "Run_Female", "Fighting_Idle", "Sword_Attack"]
const LOOPS := ["Idle_A", "Walk", "Run_Female", "Fighting_Idle"]
const STEP := 1.0 / 30.0
const BONE_TYPES := [Animation.TYPE_POSITION_3D, Animation.TYPE_ROTATION_3D, Animation.TYPE_SCALE_3D]

var failures := 0
var checks := 0
var skipped: Array = []
var finished_signals := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func run() -> void:
	CROWD.clear()
	_pure_helpers()
	var rig_a := _rig()
	var rig_b := _rig()
	if rig_a.is_empty() or rig_b.is_empty():
		expect(false, "orun_male rig and Universal library import")
		_finish()
		return
	var full: AnimationLibrary = rig_a.player.get_animation_library(&"")
	_variant_contents(full, rig_a.skeleton)
	_synthetic_libraries(rig_a.skeleton)
	_pose_equivalence(rig_a, rig_b, full)
	_swap_mechanics(rig_a, full)
	_refusals(rig_b)
	await _actor_checks()
	CROWD.clear()
	expect(CROWD.cached_count() == 0, "clear() empties the variant cache")
	(rig_a.body as Node).free()
	(rig_b.body as Node).free()
	POLISH.clear()
	NativeAnimationImporter.clear()
	_finish()

func _finish() -> void:
	for note: String in skipped:
		print("SKIPPED: " + note)
	print("Crowd animation library: %d checks, %d failures, %d skipped" % [checks, failures, skipped.size()])
	quit(1 if failures else 0)

# --- Fixtures ------------------------------------------------------------------

func _rig() -> Dictionary:
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	if document.append_from_file(ProjectSettings.globalize_path(RACE), state) != OK:
		return {}
	var body := document.generate_scene(state) as Node3D
	root.add_child(body)
	var skeleton: Skeleton3D
	for node: Node in body.find_children("*", "Skeleton3D", true, false):
		skeleton = node as Skeleton3D
		break
	if skeleton == null:
		return {}
	var imported: Dictionary = NativeAnimationImporter.import_library(body, LIBRARY, skeleton, {},
		PackedStringArray(CLIPS), PackedStringArray(LOOPS))
	var player := imported.player as AnimationPlayer
	if player == null:
		return {}
	player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	if not player.animation_finished.is_connected(_on_finished):
		player.animation_finished.connect(_on_finished)
	return {"body": body, "skeleton": skeleton, "player": player}

func _on_finished(_name: StringName) -> void:
	finished_signals += 1

func _finger_names(skeleton: Skeleton3D) -> Dictionary:
	var names := {}
	for bone: int in CROWD.finger_bones(skeleton):
		names[skeleton.get_bone_name(bone)] = true
	return names

func _bone(animation: Animation, track: int) -> String:
	return str(animation.track_get_path(track).get_concatenated_subnames())

func _track_snapshot(animation: Animation, track: int) -> Array:
	var values: Array = [animation.track_get_path(track), animation.track_get_type(track),
		animation.track_get_interpolation_type(track), animation.track_get_interpolation_loop_wrap(track),
		animation.track_is_enabled(track)]
	for key: int in animation.track_get_key_count(track):
		values.append([animation.track_get_key_time(track, key), animation.track_get_key_value(track, key),
			animation.track_get_key_transition(track, key)])
	return values

func _rotation_delta(first: Quaternion, second: Quaternion) -> float:
	var relative := (first.inverse() * second).normalized()
	return 2.0 * atan2(Vector3(relative.x, relative.y, relative.z).length(), absf(relative.w))

func _finger_rotations(skeleton: Skeleton3D) -> Array:
	var result: Array = []
	for bone: int in CROWD.finger_bones(skeleton):
		result.append(skeleton.get_bone_pose_rotation(bone))
	return result

func _same_rotations(first: Array, second: Array, tolerance := 1e-5) -> bool:
	if first.size() != second.size():
		return false
	for index: int in first.size():
		if _rotation_delta(first[index], second[index]) > tolerance:
			return false
	return true

func _hold_rotations(record: Dictionary) -> Array:
	var hold: PackedFloat32Array = record.hold
	var result: Array = []
	for index: int in hold.size() / 4:
		result.append(Quaternion(hold[index * 4], hold[index * 4 + 1], hold[index * 4 + 2], hold[index * 4 + 3]))
	return result

# --- Pure helpers ------------------------------------------------------------------

func _pure_helpers() -> void:
	expect(CROWD.want_full(10.0 * 10.0, false, 12.0, 15.0), "10 m: full hands")
	expect(not CROWD.want_full(20.0 * 20.0, true, 12.0, 15.0), "20 m: crowd hands even when full")
	expect(CROWD.want_full(13.0 * 13.0, true, 12.0, 15.0), "13 m hysteresis keeps full hands")
	expect(not CROWD.want_full(13.0 * 13.0, false, 12.0, 15.0), "13 m hysteresis keeps crowd hands")
	expect(CROWD.want_full(1.0e9, false, INF, INF), "INF detail (Medium/High): always full")
	var queue: Array = [{"full": false, "d2": 4.0}, {"full": true, "d2": 100.0},
		{"full": false, "d2": 1.0}, {"full": true, "d2": 9.0}]
	queue.sort_custom(CROWD.swap_before)
	expect(queue.map(func(entry: Dictionary) -> float: return entry.d2) == [9.0, 100.0, 1.0, 4.0],
		"swap drain order: to-full first, nearest first")
	expect(CROWD.SWAPS_PER_FRAME == 1, "one swap per frame (measured actor swap cost)")
	for name: String in ["thumb_01_l", "index_04_leaf_r", "pinky_03_r", "middle_02_l", "ring_01_r"]:
		expect(CROWD.is_finger_bone(name), "finger bone " + name)
	for name: String in ["hand_l", "lowerarm_r", "ball_leaf_l", "cape_l_01", "thumbnail", "index_l", "Index_01_l"]:
		expect(not CROWD.is_finger_bone(name), "not a finger bone " + name)

# --- The variant ----------------------------------------------------------------------

func _variant_contents(full: AnimationLibrary, skeleton: Skeleton3D) -> void:
	var started := Time.get_ticks_usec()
	var record := CROWD.derive(full, skeleton)
	var derive_ms := (Time.get_ticks_usec() - started) / 1000.0
	var crowd: AnimationLibrary = record.library
	var fingers := _finger_names(skeleton)
	expect(fingers.size() == 40, "orun_male rig has 40 finger bones (%d)" % fingers.size())
	expect((record.finger_bones as PackedInt32Array).size() == 40 and (record.hold as PackedFloat32Array).size() == 160,
		"record carries 40 finger bones and 40 held quaternions")
	expect(crowd != full, "a hand rig gets a distinct variant")
	expect(crowd.get_animation_list() == full.get_animation_list(), "variant keeps the clip list and its order")
	expect(CROWD.derive(full, skeleton).library == crowd, "same source and rig reuse the cached variant")
	for name: StringName in full.get_animation_list():
		var old := full.get_animation(name)
		var new := crowd.get_animation(name)
		expect(new.length == old.length and new.loop_mode == old.loop_mode and new.step == old.step,
			"timing kept " + str(name))
		expect(new.get_marker_names() == old.get_marker_names(), "markers kept " + str(name))
		var kept: Array = []
		var finger_tracks := 0
		var other_old := 0
		for track: int in old.get_track_count():
			var finger: bool = old.track_get_type(track) in BONE_TYPES and fingers.has(_bone(old, track))
			if finger:
				finger_tracks += 1
			else:
				kept.append(_track_snapshot(old, track))
				other_old += 1
		expect(new.get_track_count() == other_old, "only finger tracks removed " + str(name))
		var new_snapshots: Array = []
		for track: int in new.get_track_count():
			expect(not (new.track_get_type(track) in BONE_TYPES and fingers.has(_bone(new, track))),
				"no finger bone track left " + str(name))
			new_snapshots.append(_track_snapshot(new, track))
		expect(new_snapshots == kept, "non-finger tracks identical and in order " + str(name))
		expect(finger_tracks > 0, "Universal clip carries finger channels " + str(name))
	var walk_full := full.get_animation(&"Walk")
	var walk_crowd := crowd.get_animation(&"Walk")
	var bone_tracks := func(animation: Animation) -> int:
		var count := 0
		for track: int in animation.get_track_count():
			if animation.track_get_type(track) in BONE_TYPES:
				count += 1
		return count
	var shape_tracks := func(animation: Animation) -> int:
		var count := 0
		for track: int in animation.get_track_count():
			if animation.track_get_type(track) == Animation.TYPE_BLEND_SHAPE:
				count += 1
		return count
	expect(bone_tracks.call(walk_full) == 195 and bone_tracks.call(walk_crowd) == 75,
		"Walk: 195 -> 75 bone tracks (%d -> %d)" % [bone_tracks.call(walk_full), bone_tracks.call(walk_crowd)])
	expect(shape_tracks.call(walk_crowd) == shape_tracks.call(walk_full), "Walk keeps its blend-shape tracks")
	# The hold is the idle grip at t=0.
	var idle := full.get_animation(&"Idle_A")
	var tracks := {}
	for track: int in idle.get_track_count():
		if idle.track_get_type(track) == Animation.TYPE_ROTATION_3D:
			tracks[_bone(idle, track)] = track
	var expected: Array = []
	for bone: int in record.finger_bones:
		expected.append(idle.rotation_track_interpolate(int(tracks[skeleton.get_bone_name(bone)]), 0.0))
	expect(_same_rotations(_hold_rotations(record), expected), "hold = Idle_A finger rotations at t=0")
	var rest_differs := false
	for index: int in expected.size():
		var bone: int = record.finger_bones[index]
		if _rotation_delta(expected[index], skeleton.get_bone_rest(bone).basis.get_rotation_quaternion()) > 0.1:
			rest_differs = true
	expect(rest_differs, "the idle grip differs from the rig's rest fingers (the hold is needed)")
	print("CROWD_VARIANT derive_ms=%.2f clips=%d" % [derive_ms, crowd.get_animation_list().size()])

func _synthetic_libraries(skeleton: Skeleton3D) -> void:
	var path := "Skeleton3D"
	var make := func(index: int, with_finger: bool) -> AnimationLibrary:
		var library := AnimationLibrary.new()
		var clip := Animation.new()
		clip.length = 1.0 + index
		var body := clip.add_track(Animation.TYPE_ROTATION_3D)
		clip.track_set_path(body, NodePath(path + ":pelvis"))
		clip.track_insert_key(body, 0.0, Quaternion.IDENTITY)
		if with_finger:
			var finger := clip.add_track(Animation.TYPE_ROTATION_3D)
			clip.track_set_path(finger, NodePath(path + ":index_01_l"))
			clip.track_insert_key(finger, 0.0, Quaternion(Vector3.UP, 0.5))
		library.add_animation(&"Clip", clip)
		return library
	var plain: AnimationLibrary = make.call(0, false)
	var plain_record := CROWD.derive(plain, skeleton)
	expect(plain_record.library != plain and plain_record.library.get_animation(&"Clip") == plain.get_animation(&"Clip"),
		"a clip without finger tracks is shared, not copied")
	CROWD.clear()
	for index: int in CROWD.CACHE_LIMIT + 1:
		CROWD.derive(make.call(index, true), skeleton)
	expect(CROWD.cached_count() == CROWD.CACHE_LIMIT, "variant cache is FIFO-limited to %d" % CROWD.CACHE_LIMIT)
	# Rigs without hands never get a variant.
	var creature := Skeleton3D.new()
	for name: String in ["root", "spine", "head", "front_leg_l", "front_leg_r", "tail_01"]:
		creature.add_bone(name)
	var none := CROWD.derive(plain, creature)
	expect(none.library == plain and (none.finger_bones as PackedInt32Array).is_empty(), "a creature rig returns the source")
	var one_hand := Skeleton3D.new()
	for finger: String in ["thumb", "index", "middle", "ring", "pinky"]:
		for joint: int in 4:
			one_hand.add_bone("%s_0%d_l" % [finger, joint + 1])
	expect(CROWD.derive(plain, one_hand).library == plain, "fewer than %d finger bones returns the source" % CROWD.MIN_FINGER_BONES)
	creature.free()
	one_hand.free()
	CROWD.clear()

# --- Body poses ------------------------------------------------------------------------

func _pose_equivalence(rig_a: Dictionary, rig_b: Dictionary, full: AnimationLibrary) -> void:
	var pa: AnimationPlayer = rig_a.player
	var pb: AnimationPlayer = rig_b.player
	var sa: Skeleton3D = rig_a.skeleton
	var sb: Skeleton3D = rig_b.skeleton
	sb.reset_bone_poses()
	expect(CROWD.fingers_unposed(sb, CROWD.finger_bones(sb)), "a never-animated rig has unposed fingers")
	# A far build: the variant is installed before the first play.
	expect(CROWD.set_hand_detail(pb, sb, false), "never-played body takes the crowd variant")
	var record := CROWD.derive(full, sb)
	var hold := _hold_rotations(record)
	expect(_same_rotations(_finger_rotations(sb), hold), "fingers equal the hold after a far build")
	expect(not pb.is_playing(), "installing before the first play starts nothing")
	var worst_body := 0.0
	var worst_origin := 0.0
	var worst_bone := ""
	var animated := 0.0
	var fingers_held := true
	var full_moves_fingers := false
	for clip: String in CLIPS:
		pa.play(clip, 0.0)
		pb.play(clip, 0.0)
		for step: int in 30:
			pa.advance(STEP)
			pb.advance(STEP)
			sa.force_update_all_bone_transforms()
			sb.force_update_all_bone_transforms()
			for bone: int in sa.get_bone_count():
				var name := sa.get_bone_name(bone)
				if name.begins_with("cape_"):
					continue
				if CROWD.is_finger_bone(name):
					continue
				var delta := _rotation_delta(sa.get_bone_pose_rotation(bone), sb.get_bone_pose_rotation(bone))
				var origin := (sa.get_bone_global_pose(bone).origin - sb.get_bone_global_pose(bone).origin).length()
				if delta > worst_body:
					worst_body = delta
					worst_bone = name
				worst_origin = maxf(worst_origin, origin)
				animated = maxf(animated, _rotation_delta(sa.get_bone_pose_rotation(bone),
					sa.get_bone_rest(bone).basis.get_rotation_quaternion()))
			fingers_held = fingers_held and _same_rotations(_finger_rotations(sb), hold)
			full_moves_fingers = full_moves_fingers or not _same_rotations(_finger_rotations(sa), hold, 1e-3)
	expect(worst_body <= 1e-3, "non-finger local rotations match the full library (%.6f rad, %s)" % [worst_body, worst_bone])
	expect(worst_origin <= 1e-4, "non-finger global origins match the full library (%.7f m)" % worst_origin)
	expect(animated > 1.0, "the compared clips really animate the body (%.2f rad)" % animated)
	expect(fingers_held, "the variant never writes a finger: the hold stays through 5 clips")
	expect(full_moves_fingers, "the full library does write fingers (the comparison is meaningful)")
	print("CROWD_POSE worst_rotation_rad=%.7f bone=%s worst_origin_m=%.8f animated_rad=%.3f" % [worst_body, worst_bone, worst_origin, animated])
	expect(CROWD.set_hand_detail(pb, sb, true), "back to full")
	pb.stop()

# --- Swap mechanics ------------------------------------------------------------------

func _swap_mechanics(rig: Dictionary, full: AnimationLibrary) -> void:
	var player: AnimationPlayer = rig.player
	var skeleton: Skeleton3D = rig.skeleton
	finished_signals = 0
	player.speed_scale = 1.37
	player.play(&"Walk", 0.0)
	for step: int in 12:
		player.advance(STEP)
	var posed := _finger_rotations(skeleton)
	var position := player.current_animation_position
	var started := Time.get_ticks_usec()
	expect(CROWD.set_hand_detail(player, skeleton, false), "playing body swaps to the crowd variant")
	var to_crowd_us := Time.get_ticks_usec() - started
	expect(player.get_animation_library(&"") == CROWD.derive(full, skeleton).library, "library \"\" is the variant")
	expect(not CROWD.hand_detail_full(player) and CROWD.full_library(player) == full, "state: crowd, full library held aside")
	expect(player.is_playing() and player.assigned_animation == &"Walk", "the assigned clip keeps playing")
	expect(absf(player.current_animation_position - position) < 1e-4, "clip position kept (%.4f vs %.4f)" % [player.current_animation_position, position])
	expect(is_equal_approx(player.speed_scale, 1.37), "speed_scale kept")
	expect(_same_rotations(_finger_rotations(skeleton), posed), "a posed body keeps its last full-library grip")
	expect(not CROWD.set_hand_detail(player, skeleton, false), "a second crowd request changes nothing")
	expect(CROWD.full_animation(player, &"Fighting_Idle") == full.get_animation(&"Fighting_Idle")
		and player.get_animation(&"Fighting_Idle") != full.get_animation(&"Fighting_Idle"),
		"full_animation reads the held full clip (WeaponCarryPose fist) while the variant plays")
	expect(CROWD.full_animation(player, &"NoSuchClip") == null and CROWD.full_animation(null, &"Walk") == null,
		"full_animation: unknown clip or player is null")
	for step: int in 10:
		player.advance(STEP)
	expect(_same_rotations(_finger_rotations(skeleton), posed), "the grip holds while the variant plays")
	position = player.current_animation_position
	started = Time.get_ticks_usec()
	expect(CROWD.set_hand_detail(player, skeleton, true), "swap back to full")
	var to_full_us := Time.get_ticks_usec() - started
	expect(player.get_animation_library(&"") == full and CROWD.hand_detail_full(player)
		and not player.has_meta(CROWD.FULL_META), "full library restored, state cleared")
	expect(player.is_playing() and player.assigned_animation == &"Walk"
		and absf(player.current_animation_position - position) < 1e-4, "clip and position kept on the way back")
	# The restoring seek poses the fingers from the full clip at once.
	var walk := full.get_animation(&"Walk")
	var rotation_track := {}
	for track: int in walk.get_track_count():
		if walk.track_get_type(track) == Animation.TYPE_ROTATION_3D:
			rotation_track[_bone(walk, track)] = track
	var reposed := true
	for bone: int in CROWD.finger_bones(skeleton):
		var expected := walk.rotation_track_interpolate(int(rotation_track[skeleton.get_bone_name(bone)]), position)
		reposed = reposed and _rotation_delta(expected, skeleton.get_bone_pose_rotation(bone)) < 1e-3
	expect(reposed, "fingers follow the full clip again right after the restore")
	expect(not CROWD.set_hand_detail(player, skeleton, true), "a second full request changes nothing")
	expect(CROWD.full_animation(player, &"Walk") == player.get_animation(&"Walk"),
		"on a full-hands player full_animation is the player's own clip")
	# Crossfade deferral (not for pinned restores).
	player.play(&"Idle_A", 0.0)
	for step: int in 30:
		player.advance(STEP)
	player.play(&"Walk", 0.15)
	player.advance(STEP)
	expect(not CROWD.set_hand_detail(player, skeleton, false, false, 0.15 / 1.37), "a body inside its crossfade is left for later")
	expect(CROWD.hand_detail_full(player), "deferred: still full")
	for step: int in 8:
		player.advance(STEP)
	expect(CROWD.set_hand_detail(player, skeleton, false, false, 0.15 / 1.37), "after the crossfade the swap goes through")
	player.play(&"Idle_A", 0.15)
	player.advance(STEP)
	expect(CROWD.set_hand_detail(player, skeleton, false, true, 0.15 / 1.37), "pinned restores at once, even mid-crossfade")
	expect(CROWD.hand_detail_full(player), "pinned: full")
	expect(not CROWD.set_hand_detail(player, skeleton, false, true), "pinned never takes the variant")
	expect(CROWD.restore_full(player) == false, "restore_full on a full body is a no-op")
	# Restart alias (play_action's per-actor "action_restarts" library).
	var aliases := AnimationLibrary.new()
	aliases.add_animation(&"clip_walk", player.get_animation(&"Walk"))
	player.add_animation_library(&"action_restarts", aliases)
	player.play(&"action_restarts/clip_walk", 0.0)
	for step: int in 5:
		player.advance(STEP)
	position = player.current_animation_position
	expect(CROWD.set_hand_detail(player, skeleton, false), "a body playing a restart alias swaps")
	expect(not player.has_animation_library(&"action_restarts"), "the alias library leaves with the outgoing library")
	expect(player.assigned_animation == &"Walk" and player.is_playing()
		and absf(player.current_animation_position - position) < 1e-4, "the alias continues as its base clip")
	expect(CROWD.set_hand_detail(player, skeleton, true), "and back")
	# A stopped or finished player still assigned to a restart alias (a remote
	# body whose restarted strike ended) keeps the alias library both ways, so
	# assigned_animation never names a clip that is gone.
	var finished_aliases := AnimationLibrary.new()
	finished_aliases.add_animation(&"clip_walk", player.get_animation(&"Walk"))
	player.add_animation_library(&"action_restarts", finished_aliases)
	player.play(&"action_restarts/clip_walk", 0.0)
	player.advance(STEP)
	player.stop()
	expect(CROWD.set_hand_detail(player, skeleton, false) and not player.is_playing()
		and player.has_animation(player.assigned_animation),
		"a stopped player keeps the restart alias it is assigned (to crowd)")
	expect(CROWD.set_hand_detail(player, skeleton, true) and not player.is_playing()
		and player.has_animation(player.assigned_animation),
		"a stopped player keeps the restart alias it is assigned (back to full)")
	player.play(&"Walk", 0.0)
	player.advance(STEP)
	player.remove_animation_library(&"action_restarts")
	# A stopped body swaps without starting anything.
	player.stop()
	expect(CROWD.set_hand_detail(player, skeleton, false) and not player.is_playing(), "a stopped body swaps and stays stopped")
	expect(CROWD.set_hand_detail(player, skeleton, true) and not player.is_playing(), "and back, still stopped")
	# Spell variants are a managed library and stay installed.
	player.add_animation_library(&"spell_variants", AnimationLibrary.new())
	expect(CROWD.set_hand_detail(player, skeleton, false) and player.has_animation_library(&"spell_variants"),
		"spell variants do not block the swap and stay installed")
	expect(CROWD.set_hand_detail(player, skeleton, true), "and back with spell variants")
	player.remove_animation_library(&"spell_variants")
	expect(finished_signals == 0, "swaps never emit animation_finished (%d)" % finished_signals)
	player.speed_scale = 1.0
	print("CROWD_SWAP to_crowd_us=%d to_full_us=%d" % [to_crowd_us, to_full_us])

func _refusals(rig: Dictionary) -> void:
	var player: AnimationPlayer = rig.player
	var skeleton: Skeleton3D = rig.skeleton
	player.play(&"Idle_A", 0.0)
	player.advance(STEP)
	player.add_animation_library(&"rescue", AnimationLibrary.new())
	expect(not CROWD.set_hand_detail(player, skeleton, false) and CROWD.hand_detail_full(player),
		"a foreign library (cinematic, campaign) keeps full hands")
	player.remove_animation_library(&"rescue")
	player.deterministic = true
	expect(not CROWD.set_hand_detail(player, skeleton, false), "a deterministic player keeps full hands")
	player.deterministic = false
	expect(not CROWD.set_hand_detail(null, skeleton, false) and CROWD.hand_detail_full(null)
		and CROWD.full_library(null) == null, "null player is harmless")

# --- Configured actors ---------------------------------------------------------------

func _actor(models: Dictionary, slug: String, animations: Dictionary, equipment: Dictionary, id: int) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var errors := actor.configure({"actor_id": id, "x": 0, "y": 0, "rotation": 0, "kind": 1,
		"name": "", "appearance": {}, "equipment_visuals": {}},
		CoordinateAdapter.new({"walkingHeight": 0.0}), models[slug], animations, equipment)
	expect(errors.is_empty(), slug + " configures: " + str(errors))
	return actor

func _actor_checks() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var a := _actor(models, "luminous_male", animations, equipment, 9901)
	var b := _actor(models, "luminous_male", animations, equipment, 9902)
	var c := _actor(models, "luminous_male", animations, equipment, 9903)
	for actor: ReplicatedActor3D in [a, b, c]:
		actor.animation_player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		# Under a forced Low look quality A2's optional build-time install (H8)
		# starts remote bodies on crowd hands; these checks start from full.
		CROWD.restore_full(actor.animation_player)
	await process_frame
	# Locomotion polish installs at build time, before any swap: the full
	# library held aside is exactly the polished result.
	var polished: AnimationLibrary = a.animation_player.get_meta(POLISH.RESULT_META) if a.animation_player.has_meta(POLISH.RESULT_META) else null
	expect(polished != null and a.animation_player.get_animation_library(&"") == polished, "luminous actor plays the polished library")
	CROWD.clear()
	var started := Time.get_ticks_usec()
	expect(CROWD.prepare(a.animation_player, a.get_skeleton()), "prepare derives a configured actor's variant")
	var prepare_ms := (Time.get_ticks_usec() - started) / 1000.0
	expect(CROWD.hand_detail_full(a.animation_player) and a.animation_player.get_animation_library(&"") == polished,
		"prepare does not swap")
	started = Time.get_ticks_usec()
	expect(CROWD.set_hand_detail(a.animation_player, a.get_skeleton(), false), "configured luminous actor swaps")
	var swap_us := Time.get_ticks_usec() - started
	print("CROWD_ACTOR clips=%d prepare_ms=%.2f swap_after_prepare_us=%d" % [polished.get_animation_list().size(), prepare_ms, swap_us])
	var crowd := a.animation_player.get_animation_library(&"")
	expect(CROWD.full_library(a.animation_player) == polished, "full library = polished locomotion result")
	expect(crowd.has_animation(POLISH.run_clip_for_hands(1)) and crowd.has_animation(POLISH.ATTACKS.guard_clip()),
		"variant derived from the polished library (held runs and guard kept)")
	for action: String in animations.actions:
		var clip: String = a.resolver.clip_for_action(action)
		if a.animation_player.has_animation(clip) or not polished.has_animation(clip):
			continue
		expect(false, "mapped action still resolves on the variant " + action)
	expect(CROWD.set_hand_detail(a.animation_player, a.get_skeleton(), true)
		and a.animation_player.get_animation_library(&"") == polished, "restored to the polished library")
	# Spell variants read the full library through source_library.
	var reference := SpellAnimationLibrary.install(b.animation_player, b.resolver)
	var with_source := SpellAnimationLibrary.install(c.animation_player, c.resolver, CROWD.full_library(c.animation_player))
	expect(not reference.is_empty() and reference == with_source, "same variant names with or without source_library")
	var same := true
	for effect: int in reference:
		var first := b.animation_player.get_animation(reference[effect])
		var second := c.animation_player.get_animation(with_source[effect])
		same = same and first.get_track_count() == second.get_track_count()
		for track: int in first.get_track_count():
			same = same and _track_snapshot(first, track) == _track_snapshot(second, track)
	expect(same, "an unswapped body's spell variants are unchanged by source_library")
	c.animation_player.remove_animation_library(&"spell_variants")
	expect(CROWD.set_hand_detail(c.animation_player, c.get_skeleton(), false), "spell test body swaps to crowd")
	var crowd_spells := SpellAnimationLibrary.install(c.animation_player, c.resolver, CROWD.full_library(c.animation_player))
	var fingers := _finger_names(c.get_skeleton())
	var keeps_fingers := not crowd_spells.is_empty()
	for effect: int in crowd_spells:
		var clip := c.animation_player.get_animation(crowd_spells[effect])
		var found := false
		for track: int in clip.get_track_count():
			found = found or fingers.has(_bone(clip, track))
		keeps_fingers = keeps_fingers and found
	expect(keeps_fingers, "a crowd body's spell variants are sculpted from the full clips (finger tracks kept)")
	CROWD.set_hand_detail(c.animation_player, c.get_skeleton(), true)
	# A creature never takes a variant.
	var creature_animations := {}
	var creature_model: Dictionary = models.get("dire_wolf", {})
	var animation_file := str(creature_model.get("animationMap", ""))
	if not animation_file.is_empty() and FileAccess.file_exists(animation_file):
		creature_animations = JSON.parse_string(FileAccess.get_file_as_string(animation_file))
	if creature_animations.is_empty():
		skipped.append("creature actor check (dire_wolf animation map not found)")
	else:
		var wolf := _actor(models, "dire_wolf", creature_animations, equipment, 9904)
		var before := wolf.animation_player.get_animation_library(&"") if wolf.animation_player != null else null
		expect(wolf.animation_player != null and not CROWD.prepare(wolf.animation_player, wolf.get_skeleton())
			and not CROWD.set_hand_detail(wolf.animation_player, wolf.get_skeleton(), false)
			and wolf.animation_player.get_animation_library(&"") == before, "a creature keeps its library")
		wolf.free()
	# Actor hooks (group A2). Skipped until they exist.
	if not a.has_method("set_hand_detail"):
		skipped.append("actor hooks set_hand_detail / hand_detail_full / _restore_full_hands not applied yet (A2)")
	else:
		a.apply_render_quality(ActorRenderQuality.Quality.LOW, false)
		expect(a.call("set_hand_detail", false) and not a.call("hand_detail_full"), "remote Low actor takes crowd hands")
		expect(a.call("set_hand_detail", true) and a.call("hand_detail_full"), "and full again")
		a.apply_render_quality(ActorRenderQuality.Quality.LOW, true)
		expect(not a.call("set_hand_detail", false) and a.call("hand_detail_full"), "the local actor refuses crowd hands")
		a.apply_render_quality(ActorRenderQuality.Quality.LOW, false)
		expect(a.call("set_hand_detail", false), "remote again")
		a.call("_restore_full_hands")
		expect(a.call("hand_detail_full"), "_restore_full_hands restores")
		a.set_cinematic_presentation(Vector3.ZERO, 0.0, &"idle")
		expect(not a.call("set_hand_detail", false) and a.call("hand_detail_full"), "a cinematic actor refuses crowd hands")
		a.end_cinematic_presentation()
	for actor: ReplicatedActor3D in [a, b, c]:
		actor.free()
	await process_frame
