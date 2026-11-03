extends SceneTree
## Wave 2 stage A hook commit (group A2): the thin actor and service lines the
## leaf modules asked for, run on real configured actors. The modules behind
## them have their own tests (test_crowd_animation_library, test_combat_
## presentation, test_cape_step_rate, test_frame_driven_motion); this checks
## that the actor wires them where the plans say:
## - LAT-L1 H2-H7: set_hand_detail / hand_detail_full / _restore_full_hands;
##   a Medium, High or local quality, a cinematic and mounting restore full
##   hands; spell variants are sculpted from the full clips; the session cache
##   is cleared with the wardrobe caches.
## - LAT-L1 H9: WeaponCarryPose's fist reads the full clip on a crowd body.
## - LAT-L2 H1: the combat hand-cue pass-through (and its absence on creatures).
## - LAT-L7 H1: the native remote snapshot does not mark a dead frame-clock body
##   paused before its next frame step, and is unchanged on the physics clock.
## Nothing here swaps a body by itself: until LAT-L6 wires Main's gate no
## quality draws crowd hands, so every check swaps explicitly.

const CROWD := preload("res://src/actors/crowd_animation_library.gd")
const CARRY := preload("res://src/actors/weapon_carry_pose.gd")
const Remote := preload("res://src/runtime/remote_presentation.gd")
const Quality := ActorRenderQuality.Quality

class TimedActor extends ReplicatedActor3D:
	var clock_msec := 100000

	func _movement_time_msec() -> int:
		return clock_msec

var failures := 0
var checks := 0
var models: Dictionary
var equipment: Dictionary
var luminous: Dictionary

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	checks += 1
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)

func _run() -> void:
	models = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	equipment = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	luminous = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	CROWD.clear()
	var a := _human(9801)
	await process_frame
	_check_quality_restores(a)
	_check_cinematic_restores(a)
	_check_fist(a)
	_check_cues(a)
	var c := _human(9802)
	_check_spell_variants(c)
	_check_cache_clear()
	await _check_mount()
	_check_death_snapshot()
	for actor: ReplicatedActor3D in [a, c]:
		actor.free()
	CROWD.clear()
	NativeAnimationImporter.clear()
	await process_frame
	print("stage A actor hooks: %d checks, %s" % [checks, "PASS" if failures == 0 else "FAIL (%d)" % failures])
	quit(failures)

## A remote luminous Human as Main builds one, on the manual clock, starting
## from full hands, with no crossfade hold (the module tests that).
func _human(id: int, slug := "luminous_male", animations: Dictionary = luminous) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var errors := actor.configure({"actor_id": id, "x": 0, "y": 0, "rotation": 0, "kind": 1,
		"name": "", "appearance": {}, "equipment_visuals": {}},
		CoordinateAdapter.new({"walkingHeight": 0.0}), models[slug], animations, equipment)
	_expect(errors.is_empty(), "(fixture) %s configures: %s" % [slug, errors])
	if actor.animation_player != null:
		actor.animation_player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		CROWD.restore_full(actor.animation_player)
	actor.action_crossfade_seconds = 0.0
	return actor

func _to_crowd(actor: ReplicatedActor3D) -> bool:
	actor.apply_render_quality(Quality.LOW, false)
	return actor.set_hand_detail(false) and not actor.hand_detail_full()

func _check_quality_restores(a: ReplicatedActor3D) -> void:
	var full := a.animation_player.get_animation_library(&"")
	_expect(a.hand_detail_full(), "a built body starts with full hands (no quality swaps without L6)")
	_expect(_to_crowd(a) and a.animation_player.get_animation_library(&"") != full,
		"a remote Low body takes crowd hands through the actor")
	a.apply_render_quality(Quality.LOW, false)
	_expect(not a.hand_detail_full(), "re-applying Low to a remote body keeps its crowd hands")
	a.apply_render_quality(Quality.MEDIUM, false)
	_expect(a.hand_detail_full() and a.animation_player.get_animation_library(&"") == full,
		"switching to Medium restores the full library (H6)")
	_expect(_to_crowd(a), "remote Low again")
	a.apply_render_quality(Quality.HIGH, false)
	_expect(a.hand_detail_full(), "switching to High restores full hands")
	_expect(_to_crowd(a), "remote Low again")
	a.apply_render_quality(Quality.LOW, true)
	_expect(a.hand_detail_full() and not a.set_hand_detail(false) and a.hand_detail_full(),
		"a body that becomes local is restored and refuses crowd hands")
	a.apply_render_quality(Quality.LOW, false)
	_expect(_to_crowd(a) and a.set_hand_detail(true) and a.hand_detail_full()
		and a.animation_player.get_animation_library(&"") == full, "set_hand_detail(true) restores")

func _check_cinematic_restores(a: ReplicatedActor3D) -> void:
	_expect(_to_crowd(a), "remote Low crowd body before a cinematic")
	a.set_cinematic_presentation(Vector3.ZERO, 0.0, &"idle")
	_expect(a.hand_detail_full(), "a cinematic restores full hands at once (H5)")
	_expect(not a.set_hand_detail(false) and a.hand_detail_full(), "and refuses crowd hands while it lasts")
	a.end_cinematic_presentation()

func _check_fist(a: ReplicatedActor3D) -> void:
	var skeleton := a.get_skeleton()
	var pose: Node = CARRY.new()
	pose.set("actor", a)
	a.set_hand_detail(true)
	var full_fist: Array = pose.call("_fist", skeleton, "l")
	_expect(not full_fist.is_empty(), "(fixture) the combat idle closes a full body's left hand")
	_expect(_to_crowd(a), "crowd body for the fist")
	var crowd_fist: Array = pose.call("_fist", skeleton, "l")
	_expect(crowd_fist == full_fist, "a crowd body's fist is sampled from the full clip (H9)")
	a.set_hand_detail(true)
	pose.free()

func _check_cues(a: ReplicatedActor3D) -> void:
	_expect(a.combat_presentation != null and a.combat_cues_allowed(), "(fixture) a caster Human allows hand cues")
	a.set_combat_cues_allowed(false)
	_expect(not a.combat_cues_allowed() and not a.combat_presentation.cues_allowed,
		"set_combat_cues_allowed(false) reaches the combat presentation (L2 H1)")
	a.set_combat_cues_allowed(true)
	_expect(a.combat_cues_allowed() and a.combat_presentation.cues_allowed, "and back on")
	var wolf_model: Dictionary = models.get("dire_wolf", {})
	var animation_file := str(wolf_model.get("animationMap", ""))
	if animation_file.is_empty() or not FileAccess.file_exists(animation_file):
		_expect(false, "(fixture) the dire wolf's animation map exists")
		return
	var wolf := _human(9803, "dire_wolf", JSON.parse_string(FileAccess.get_file_as_string(animation_file)))
	wolf.set_combat_cues_allowed(false)
	_expect(wolf.combat_presentation == null and not wolf.combat_cues_allowed(),
		"a creature has no hand cues to switch, and asking is harmless")
	_expect(not wolf.set_hand_detail(false) and wolf.hand_detail_full(), "a creature keeps its library")
	wolf.free()

func _finger_tracks(animation: Animation) -> int:
	var found := 0
	for track: int in animation.get_track_count():
		if CROWD.is_finger_bone(str(animation.track_get_path(track).get_concatenated_subnames())):
			found += 1
	return found

func _check_spell_variants(c: ReplicatedActor3D) -> void:
	_expect(_to_crowd(c), "crowd body before its first cast")
	c.set_spell_variant(2)
	var player := c.animation_player
	var names: PackedStringArray = player.get_animation_library(&"spell_variants").get_animation_list() \
		if player.has_animation_library(&"spell_variants") else PackedStringArray()
	var all_keep := not names.is_empty()
	for name: String in names:
		all_keep = all_keep and _finger_tracks(player.get_animation("spell_variants/" + name)) > 0
	_expect(all_keep, "a crowd body's first cast sculpts its spell variants from the full clips (H4, %d)" % names.size())
	_expect(c.set_hand_detail(true) and c.hand_detail_full() and player.has_animation_library(&"spell_variants"),
		"and returns to full hands with them installed")

func _check_cache_clear() -> void:
	_expect(CROWD.cached_count() > 0, "(fixture) the swaps above derived a variant")
	ReplicatedActor3D.clear_wardrobe_texture_cache()
	_expect(CROWD.cached_count() == 0, "the session cache clear also drops the crowd variants (H7)")

func _check_mount() -> void:
	var rider := _human(9804)
	_expect(_to_crowd(rider), "crowd body before mounting")
	rider.set_process(false)
	rider.set_physics_process(false)
	rider.set_mount_state({"mode": "mounted", "mount_id": "moor_pony", "gait": "cruise"}, models)
	var mounted := is_instance_valid(rider._mount_visual)
	_expect(mounted, "(fixture) the approved Moor Pony configures")
	if mounted:
		(rider._mount_visual as Node).set_process(false)
		_expect(rider.hand_detail_full(), "mounting restores full hands before the mounted visual is built (H3)")
		_expect(not rider.set_hand_detail(false) and rider.hand_detail_full(), "a rider refuses crowd hands")
		rider.set_mount_state({}, models)
	rider.process_mode = Node.PROCESS_MODE_DISABLED
	await process_frame
	rider.queue_free()
	await process_frame
	await process_frame

## The service's snapshot of a body it does not own (LAT-L7 H1): flag 512 means
## "already paused on its tile".
func _paused_flag(actor: ReplicatedActor3D) -> bool:
	return (int(Remote.snapshot_actor(actor)[29]) & 512) != 0

func _state(x: int, y: int, command: int) -> Dictionary:
	return {"actor_id": 7, "x": x, "y": y, "rotation": 0, "command": command, "buffs": 0,
		"health": 100, "max_health": 100, "alive": true}

func _walker(level: int) -> TimedActor:
	var actor := TimedActor.new()
	root.add_child(actor)
	actor.resolver = AnimationResolver.new({
		"actions": {"idle": "Idle", "walk": "Walk", "run": "Run", "death": "Death"},
		"serverCommands": {"3": "death", "7": "idle", "22": "walk", "32": "run"}})
	var player := AnimationPlayer.new()
	actor.add_child(player)
	player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	var library := AnimationLibrary.new()
	for clip: String in ["Idle", "Walk", "Run", "Death"]:
		var animation := Animation.new()
		animation.length = 0.1
		animation.loop_mode = Animation.LOOP_NONE if clip == "Death" else Animation.LOOP_LINEAR
		library.add_animation(clip, animation)
	player.add_animation_library("", library)
	actor.animation_player = player
	player.animation_finished.connect(actor._on_animation_finished)
	actor.apply_render_quality(level, false)
	return actor

func _check_death_snapshot() -> void:
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0})
	ReplicatedActor3D.set_frame_driven(true)
	var actor := _walker(Quality.LOW)
	actor.apply_server_state(_state(0, 0, 7), adapter, true)
	var dto := _state(1, 0, 22)
	actor.apply_server_state(dto, adapter)
	ReplicatedActor3D.advance_frame_driven(1.0 / 30.0)
	actor.apply_server_state(ActorReducer.apply_command(dto, 3), adapter)
	_expect(actor.current_action == &"death" and actor.presents_on_frame_clock() and not actor.is_physics_processing(),
		"(fixture) a dead Low body is still on the frame clock before its next frame step")
	_expect(not _paused_flag(actor), "the snapshot does not call it paused yet (is_presenting)")
	var frames := 0
	while actor.is_presenting() and frames < 60:
		ReplicatedActor3D.advance_frame_driven(1.0 / 30.0)
		frames += 1
	_expect(not actor.is_presenting() and _paused_flag(actor), "once its frame step pauses it, it is paused")
	ReplicatedActor3D.set_frame_driven(false)
	actor.free()
	# The physics clock (Medium, and every quality with the frame clock off):
	# is_presenting() is is_physics_processing(), so the flag is as before.
	var physics := _walker(Quality.MEDIUM)
	physics.apply_server_state(_state(0, 0, 7), adapter, true)
	dto = _state(1, 0, 22)
	physics.apply_server_state(dto, adapter)
	physics.apply_server_state(ActorReducer.apply_command(dto, 3), adapter)
	_expect(not physics.presents_on_frame_clock() and physics.is_presenting() == physics.is_physics_processing()
		and _paused_flag(physics) == (physics.current_action == &"death" and not physics.is_physics_processing()),
		"on the physics clock the paused flag is unchanged")
	frames = 0
	while physics.is_physics_processing() and frames < 120:
		physics._physics_process(1.0 / 60.0)
		frames += 1
	_expect(physics.current_action == &"death" and not physics.is_physics_processing() and _paused_flag(physics),
		"a settled dead body on physics is paused")
	physics.free()
