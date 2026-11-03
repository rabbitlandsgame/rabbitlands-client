extends SceneTree
## The Low actor tier's gate wiring in Main (LAT-L6, low-actor-tier.md 2.2,
## 2.3, 2.7): at Low a remote humanoid is built on the crowd hand variant,
## Main's gate gives it finger animation back nearer the camera than 12 m and
## keeps it until 15 m, a priority actor always has it, the swaps are made one
## a frame (to-full first, nearest first), hand cues stay with full-rate and
## priority bodies, bodies past 35 m are never on the full rate, and the
## per-actor census counts hands and cues. Medium and High ask nothing of the
## actors: full hands, every cue, 45 m.
##
## main.gd is loaded at run time, not preloaded: it reads the autoload
## singletons, which a SceneTree script is compiled before.

const Options := preload("res://src/world/graphics_options.gd")
const CROWD := preload("res://src/actors/crowd_animation_library.gd")
const LOCAL := 100
const REMOTE := [101, 102, 103, 104]
const LATE := 105
const HUMANOID_KIT := {0: 114, 1: 106, 3: 117, 4: 171, 5: 184, 6: 192}
const Quality := LookProfile.Quality

var failures := 0
var checks := 0
var _main: Control
var _app_state: Node

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, label: String) -> bool:
	checks += 1
	if ok:
		print("PASS: ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)
	return ok

func _run() -> void:
	var saved_config: Variant = FileAccess.get_file_as_bytes(Options.SETTINGS_PATH) \
		if FileAccess.file_exists(Options.SETTINGS_PATH) else null
	var saved_quality := OS.get_environment(LookProfile.QUALITY_VARIABLE)
	OS.unset_environment(LookProfile.QUALITY_VARIABLE)
	var main_script := load("res://src/app/main.gd") as GDScript
	if not _expect(main_script != null and main_script.can_instantiate(), "main.gd compiles"):
		quit(1)
		return
	await _set_up()
	_set_quality(Quality.LOW)
	_check_rules(Quality.LOW)
	_put([_record(LOCAL, 500, 500)] + REMOTE.map(func(id: int) -> Dictionary:
		return _record(id, 500 + (id - 100) * 3, 502)))
	await _wait_for_nodes([LOCAL] + REMOTE)
	await _wait_for_bodies(REMOTE)
	# Nothing of Main's own frame runs between the explicit steps below.
	_main.set_process(false)
	var bodies := _bodies(REMOTE)
	if _expect(bodies.size() == REMOTE.size(), "(fixture) four remote Humans are built at Low"):
		_check_built_at_low(bodies)
		_check_hand_sweep(bodies)
		_check_cues(bodies)
		_check_census(bodies)
		_check_native_tier(bodies[3], Quality.LOW)
		_classify_cost[Quality.LOW] = _classify_us(bodies)
		await _check_frames(bodies)
		_check_preview_actor()
		_check_switch_up(bodies)
		await _check_built_high_then_low()
	_main.queue_free()
	await process_frame
	await process_frame
	if saved_config != null:
		var file := FileAccess.open(Options.SETTINGS_PATH, FileAccess.WRITE)
		file.store_buffer(saved_config)
		file.close()
	else:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(Options.SETTINGS_PATH))
	OS.set_environment(LookProfile.QUALITY_VARIABLE, saved_quality)
	print("low tier gate: %d checks, %s" % [checks, "PASS" if failures == 0 else "FAIL (%d)" % failures])
	quit(failures)

# --- Fixture -------------------------------------------------------------------

func _set_up() -> void:
	root.size = Vector2i(1280, 720)
	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(_main)
	await process_frame
	(_main.get_node("GameView") as Control).show()
	(_main.get_node("LoginPanel") as Control).hide()
	_app_state = root.get_node("/root/AppState")
	_app_state.set("authenticated", true)
	_app_state.set("local_actor_id", LOCAL)
	await process_frame

func _set_quality(level: int) -> void:
	_main.call("_on_client_setting_changed", "Graphics", "quality", level)

func _record(id: int, x: int, y: int) -> Dictionary:
	return {"actor_id": id, "x": x, "y": y, "rotation": 0, "actor_type": 1, "kind": 1,
		"name": "Gate %d" % id, "health": 50, "max_health": 50, "alive": true,
		"appearance": {}, "equipment_visuals": HUMANOID_KIT.duplicate(),
		"equipment_fallback_parts": []}

func _nodes() -> Dictionary:
	return _main.get("actor_nodes") as Dictionary

func _put(records: Array) -> void:
	var actors: Dictionary = (_app_state.get("actors") as Dictionary)
	for record: Dictionary in records:
		actors[int(record.actor_id)] = record
		_app_state.call("mark_actor_changed", int(record.actor_id))

func _sync() -> void:
	_main.call("_sync_world", _app_state.call("take_changed_actors"))
	await process_frame

func _wait_for_nodes(ids: Array) -> void:
	await _sync()
	for unused: int in range(60):
		var all := true
		for id: Variant in ids:
			all = all and _nodes().has(int(id))
		if all:
			return
		await _sync()

func _wait_for_bodies(ids: Array) -> void:
	for unused: int in range(120):
		var waiting := false
		for id: int in ids:
			var actor := _nodes().get(id) as ReplicatedActor3D
			if actor == null or actor.is_model_deferred():
				waiting = true
				break
		if not waiting:
			return
		_main.set("_animation_gate_refresh_msec", 0)
		_main.call("_update_animation_gate", 0.0)
		_main.call("_update_model_builds")
		await process_frame

func _bodies(ids: Array) -> Array[ReplicatedActor3D]:
	var found: Array[ReplicatedActor3D] = []
	for id: int in ids:
		var actor := _nodes().get(id) as ReplicatedActor3D
		if actor != null and not actor.is_model_deferred() and actor.animation_player != null:
			# The module defers a swap inside an action crossfade (tested there);
			# these checks are about Main's decisions.
			actor.action_crossfade_seconds = 0.0
			found.append(actor)
	return found

## One whole gate sweep in which each body is measured from its own camera
## point: `distances` maps a body to its camera distance in metres (straight
## above it). Bodies not named are left out of the sweep.
func _sweep(distances: Dictionary) -> void:
	_main.call("_begin_gate_sweep", Time.get_ticks_msec(), true)
	for body: ReplicatedActor3D in distances:
		_main.set("_gate_camera_at", body.global_position + Vector3(0.0, float(distances[body]), 0.0))
		_main.call("_gate_classify", body.actor_id)
	_main.call("_finish_gate_sweep")

func _queue() -> Array:
	return _main.get("_hand_swap_queue") as Array

func _drain() -> void:
	_main.call("_drain_hand_swaps")

# --- Checks --------------------------------------------------------------------

func _check_rules(level: int) -> void:
	var gate := _main.get("animation_gate") as AnimationGate
	var low := level == Quality.LOW
	_expect(is_equal_approx(gate.half_rate_metres, 35.0 if low else 45.0),
		"%s: bodies past %s m are never on the full rate" % [LookProfile.quality_name(level), "35" if low else "45"])
	_expect(is_inf(float(_main.get("_gate_hand_metres"))) != low
		and is_equal_approx(float(_main.get("_gate_hand_metres")), 12.0) == low
		and is_equal_approx(float(_main.get("_gate_hand_release_metres")), 15.0) == low,
		"%s: the gate's hand-detail distances are %s" % [LookProfile.quality_name(level),
			"12 m on, 15 m off" if low else "none"])
	_expect(bool(_main.get("_gate_cues_full_only")) == low,
		"%s: hand cues %s" % [LookProfile.quality_name(level),
			"for full-rate and priority bodies only" if low else "everywhere"])

func _check_built_at_low(bodies: Array[ReplicatedActor3D]) -> void:
	var local := _nodes().get(LOCAL) as ReplicatedActor3D
	_expect(local != null and local.hand_detail_full() and not local.hand_detail_managed(),
		"the player's own body is built with full hands and is not the gate's")
	var crowd := 0
	var held := 0
	var playing := 0
	for body: ReplicatedActor3D in bodies:
		var player := body.animation_player
		var skeleton := body.get_skeleton()
		crowd += int(not body.hand_detail_full() and body.hand_detail_managed()
			and player.get_animation_library(&"") != CROWD.full_library(player))
		held += int(not CROWD.fingers_unposed(skeleton, CROWD.finger_bones(skeleton)))
		playing += int(player.is_playing() and player.has_animation(player.assigned_animation))
	_expect(crowd == bodies.size(), "every remote Human built at Low starts on the crowd variant (%d)" % crowd)
	_expect(held == bodies.size(), "with its fingers held, not at rest (%d)" % held)
	_expect(playing == bodies.size(), "and plays its first clip from the variant (%d)" % playing)

func _check_hand_sweep(bodies: Array[ReplicatedActor3D]) -> void:
	var a := bodies[0]
	var b := bodies[1]
	var c := bodies[2]
	var d := bodies[3]
	for body: ReplicatedActor3D in bodies:
		body.set_hand_detail(false)
	_sweep({a: 10.0, b: 20.0, c: 13.0, d: 5.0})
	var queue := _queue()
	_expect(queue.size() == 2, "10 m and 5 m bodies are queued for full hands, 20 m and 13 m are not (%d)" % queue.size())
	_expect(queue.size() == 2 and queue[0].actor == d and queue[1].actor == a
		and bool(queue[0].full) and bool(queue[1].full), "the nearest to-full swap is first")
	_expect(not c.hand_detail_full(), "hysteresis: a crowd body at 13 m keeps crowd hands")
	_drain()
	_expect(d.hand_detail_full() and not a.hand_detail_full() and _queue().size() == 1,
		"one swap a frame (SWAPS_PER_FRAME = %d)" % CROWD.SWAPS_PER_FRAME)
	_drain()
	_expect(a.hand_detail_full() and _queue().is_empty(), "the next frame makes the next swap")
	# Back out: a full body at 13 m keeps its hands, one at 16 m gives them up,
	# and a selected actor gets them back at 20 m, ahead of the farther swap.
	_app_state.set("selected_actor_id", b.actor_id)
	_sweep({a: 13.0, b: 20.0, c: 30.0, d: 16.0})
	queue = _queue()
	_expect(queue.size() == 2 and queue[0].actor == b and bool(queue[0].full)
		and queue[1].actor == d and not bool(queue[1].full),
		"to-full swaps (a selected body at 20 m) come before to-crowd ones (16 m)")
	_expect(a.hand_detail_full(), "hysteresis: a full body at 13 m keeps full hands")
	_drain()
	_drain()
	_expect(b.hand_detail_full() and not d.hand_detail_full(),
		"the selected body has full hands and the 16 m one crowd hands")
	_app_state.set("selected_actor_id", -1)
	_sweep({a: 13.0, b: 20.0, c: 30.0, d: 16.0})
	_drain()
	_expect(not b.hand_detail_full(), "once deselected it gives them up again")
	# A swap queued for a body that has since become the player's own is
	# refused by the actor and costs nothing more.
	_sweep({a: 30.0})
	_expect(_queue().size() == 1, "(fixture) a far full body is queued for crowd hands")
	a.apply_render_quality(Quality.LOW, true)
	_drain()
	_expect(a.hand_detail_full() and _queue().is_empty(), "a body that has become local refuses the queued swap")
	a.apply_render_quality(Quality.LOW, false)
	# A freed, replaced or parked body is skipped.
	_sweep({c: 5.0})
	_main.get("actor_nodes").erase(c.actor_id)
	_drain()
	_expect(not c.hand_detail_full() and _queue().is_empty(), "a body no longer in the actor table is skipped")
	_main.get("actor_nodes")[c.actor_id] = c

func _check_cues(bodies: Array[ReplicatedActor3D]) -> void:
	var a := bodies[0]
	var b := bodies[1]
	var crowd: RefCounted = _main.get("crowd")
	var saved := [crowd.get("full_rate_bodies"), crowd.get("half_rate_bodies"), crowd.get("quarter")]
	crowd.set("full_rate_bodies", 1)
	crowd.set("half_rate_bodies", 0)
	crowd.set("quarter", true)
	_main.call("_apply_crowd_full_rate", [[1.0, a, AnimationGate.Tier.FULL, false],
		[2.0, b, AnimationGate.Tier.FULL, false]])
	_expect(a.animation_tier() == AnimationGate.Tier.FULL and a.combat_cues_allowed(),
		"a full-rate body keeps its hand cues")
	_expect(b.animation_tier() == AnimationGate.Tier.QUARTER and not b.combat_cues_allowed(),
		"a quarter-rate body loses them")
	_main.call("_apply_crowd_full_rate", [[1.0, a, AnimationGate.Tier.FULL, false],
		[2.0, b, AnimationGate.Tier.FULL, true]])
	_expect(b.animation_tier() == AnimationGate.Tier.QUARTER and b.combat_cues_allowed(),
		"a priority actor keeps them at any rate")
	_main.call("_apply_crowd_full_rate", [[1.0, a, AnimationGate.Tier.HALF],
		[2.0, b, AnimationGate.Tier.FULL]])
	_expect(not a.combat_cues_allowed() and not b.combat_cues_allowed(),
		"an entry without the priority flag is not a priority one")
	crowd.set("full_rate_bodies", saved[0])
	crowd.set("half_rate_bodies", saved[1])
	crowd.set("quarter", saved[2])
	# The sweep's own tier for a body it does not rank: one out of draw range
	# is paused and has no cues, unless it is a priority actor.
	_app_state.set("selected_actor_id", b.actor_id)
	_main.call("_begin_gate_sweep", Time.get_ticks_msec(), true)
	_main.set("_gate_here", a.global_position + Vector3(10000.0, 0.0, 0.0))
	a.set_combat_cues_allowed(true)
	b.set_combat_cues_allowed(false)
	_main.call("_gate_classify", a.actor_id)
	_main.call("_gate_classify", b.actor_id)
	_main.call("_finish_gate_sweep")
	_expect(a.animation_tier() == AnimationGate.Tier.PAUSED and not a.combat_cues_allowed(),
		"a paused body has no hand cues")
	_expect(b.animation_tier() == AnimationGate.Tier.PAUSED and b.combat_cues_allowed(),
		"a paused priority actor keeps them")
	_app_state.set("selected_actor_id", -1)
	# The player's own always has them.
	var local := _nodes().get(LOCAL) as ReplicatedActor3D
	local.set_combat_cues_allowed(false)
	_sweep({local: 30.0})
	_expect(local.combat_cues_allowed(), "the player's own keeps every hand cue at Low")
	# Back in range for the rest of the checks.
	_main.set("_animation_gate_refresh_msec", 0)
	_main.call("_update_animation_gate", 0.0)

func _check_census(bodies: Array[ReplicatedActor3D]) -> void:
	var a := bodies[0]
	a.set_hand_detail(false)
	a.set_combat_cues_allowed(false)
	var census := a.presentation_census()
	_expect(census.get("handDetailCrowd") == true and census.get("handDetailFull") == false
		and census.get("cuesOff") == true and census.get("cuesAllowed") == false,
		"the census counts a crowd-hands body without cues")
	a.set_hand_detail(true)
	a.set_combat_cues_allowed(true)
	census = a.presentation_census()
	_expect(census.get("handDetailFull") == true and census.get("handDetailCrowd") == false
		and census.get("cuesAllowed") == true and census.get("cuesOff") == false
		and census.has("framePresenting") and census.has("physicsPresenting"),
		"and a full-hands body with cues, beside the clock fields")
	var fields := {}
	for key: String in census:
		fields[key] = typeof(census[key])
	_expect(fields.values().all(func(kind: int) -> bool: return kind == TYPE_BOOL),
		"every census field is a counter (bool), never a distance")

## The opt-in native remote presentation classifies a slice against the 45 m
## constant; Main's sweep brings its answer to the quality's half-rate distance
## (`AnimationGate.within_half_rate`). A body the batch put on the full rate
## 40 m from the camera is stepped at half rate at Low and stays on the full
## rate at Medium and High. The batch result is injected as `classify_slice`
## would leave it, since the headless fixture runs without the native runtime.
func _check_native_tier(body: ReplicatedActor3D, level: int) -> void:
	var gate := _main.get("animation_gate") as AnimationGate
	var anchor := body.global_position + Vector3.UP
	var camera := Camera3D.new()
	root.add_child(camera)
	camera.look_at_from_position(anchor + Vector3(0.0, 0.0, 40.0), anchor, Vector3.UP)
	_main.call("_begin_gate_sweep", Time.get_ticks_msec(), true)
	gate.begin(camera)
	_main.set("_gate_slice_tiers", {body.actor_id: {"tier": AnimationGate.Tier.FULL,
		"anchor": anchor, "radius": body.view_radius()}})
	_main.call("_gate_classify", body.actor_id)
	(_main.get("_gate_slice_tiers") as Dictionary).clear()
	_main.call("_finish_gate_sweep")
	camera.free()
	# Main's own camera again, as its next frame would capture it.
	gate.begin(_main.get("gameplay_camera") as Camera3D)
	var low := level == Quality.LOW
	_expect(body.animation_tier() == (AnimationGate.Tier.HALF if low else AnimationGate.Tier.FULL),
		"%s: a native full-rate tier 40 m from the camera is %s (tier %d)" % [
			LookProfile.quality_name(level), "half rate past Low's 35 m" if low else "kept within 45 m",
			body.animation_tier()])

## Main's own per-frame gate at Low, with the real camera: sweeps, drains and
## the half-rate distance run without errors and within the swap budget.
func _check_frames(bodies: Array[ReplicatedActor3D]) -> void:
	bodies[0].set_hand_detail(false)
	_sweep({bodies[0]: 5.0})
	_main.call("_update_animation_gate", 1.0 / 30.0)
	_expect(bodies[0].hand_detail_full(), "Main's frame drains a queued swap")
	var swaps_before := _swap_count()
	for frame: int in range(24):
		_main.call("_update_animation_gate", 1.0 / 30.0)
		var made := _swap_count() - swaps_before
		swaps_before = _swap_count()
		if made > CROWD.SWAPS_PER_FRAME:
			_expect(false, "at most %d swap a frame (frame %d made %d)" % [CROWD.SWAPS_PER_FRAME, frame, made])
			return
		await process_frame
	_expect(true, "24 gate frames at Low stay within the swap budget")

## Libraries now on the four bodies, as a running count of changes.
var _last_libraries: Dictionary = {}
var _swaps := 0
func _swap_count() -> int:
	for id: int in REMOTE:
		var actor := _nodes().get(id) as ReplicatedActor3D
		if actor == null or actor.animation_player == null:
			continue
		var library := actor.animation_player.get_animation_library(&"")
		if _last_libraries.has(id) and _last_libraries[id] != library:
			_swaps += 1
		_last_libraries[id] = library
	return _swaps

## An actor built outside Main's world (a preview, a portrait, a showcase) is
## never given crowd hands, even at Low.
func _check_preview_actor() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var luminous: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var preview := ReplicatedActor3D.new()
	root.add_child(preview)
	var errors := preview.configure({"actor_id": 9701, "x": 0, "y": 0, "rotation": 0, "kind": 1,
		"name": "", "appearance": {}, "equipment_visuals": {}},
		CoordinateAdapter.new({"walkingHeight": 0.0}), models["luminous_male"], luminous, equipment)
	_expect(errors.is_empty() and LookProfile.quality() == Quality.LOW, "(fixture) a preview Human configures at Low")
	_expect(preview.hand_detail_full() and not preview.hand_detail_managed(),
		"a preview built at Low keeps full hands and is not the gate's")
	preview.free()

func _check_switch_up(bodies: Array[ReplicatedActor3D]) -> void:
	var a := bodies[0]
	a.set_hand_detail(false)
	bodies[1].set_combat_cues_allowed(false)
	bodies[2].set_hand_detail(true)
	_sweep({bodies[2]: 30.0})
	_expect(_queue().size() == 1 and not a.hand_detail_full() and not bodies[1].combat_cues_allowed(),
		"(fixture) at Low a crowd body, a body without cues and a pending swap")
	for level: int in [Quality.MEDIUM, Quality.HIGH]:
		_set_quality(level)
		_check_rules(level)
		var full := 0
		var cues := 0
		for body: ReplicatedActor3D in bodies:
			full += int(body.hand_detail_full())
			cues += int(body.combat_cues_allowed())
		_expect(full == bodies.size() and cues == bodies.size(),
			"%s gives every body full hands and every hand cue back at once (%d, %d)"
				% [LookProfile.quality_name(level), full, cues])
		_expect(_queue().is_empty(), "%s drops the swaps queued at Low" % LookProfile.quality_name(level))
		_sweep({bodies[0]: 40.0, bodies[1]: 5.0, bodies[2]: 20.0, bodies[3]: 13.0})
		_expect(_queue().is_empty() and (_main.get("_gate_hand_swaps") as Array).is_empty(),
			"%s: the gate asks no body for a hand swap" % LookProfile.quality_name(level))
		_expect(not a.set_hand_detail(false) and a.hand_detail_full(),
			"%s: a body refuses crowd hands whoever asks" % LookProfile.quality_name(level))
		bodies[1].set_combat_cues_allowed(false)
		_sweep({bodies[1]: 30.0})
		_expect(not bodies[1].combat_cues_allowed(),
			"%s: the gate leaves hand cues alone" % LookProfile.quality_name(level))
		bodies[1].set_combat_cues_allowed(true)
		_check_native_tier(bodies[3], level)
		_classify_cost[level] = _classify_us(bodies)
	print("GATE_CLASSIFY us_per_body low=%.2f medium=%.2f high=%.2f (informational: debug build, dynamic calls included)"
		% [_classify_cost.get(Quality.LOW, -1.0), _classify_cost.get(Quality.MEDIUM, -1.0),
			_classify_cost.get(Quality.HIGH, -1.0)])

## Main's per-body sweep cost at the current quality, with every body at
## rest (30 m from its camera point, crowd hands at Low, nothing to swap):
## microseconds per `_gate_classify`, the test's dynamic call included. The
## repeated classifications are never finished as a sweep (they would rank
## each body hundreds of times and release some under the body cap): the
## gathered state is dropped by starting a fresh sweep and closing it unused.
var _classify_cost: Dictionary = {}
func _classify_us(bodies: Array[ReplicatedActor3D]) -> float:
	var low := LookProfile.quality() == Quality.LOW
	for body: ReplicatedActor3D in bodies:
		body.set_hand_detail(not low)
	var rounds := 200
	var best := INF
	var queued := 0
	for repeat: int in 3:
		_main.call("_begin_gate_sweep", Time.get_ticks_msec(), true)
		var started := Time.get_ticks_usec()
		for pass_index: int in rounds:
			for body: ReplicatedActor3D in bodies:
				_main.set("_gate_camera_at", body.global_position + Vector3(0.0, 30.0, 0.0))
				_main.call("_gate_classify", body.actor_id)
		best = minf(best, float(Time.get_ticks_usec() - started) / float(rounds * bodies.size()))
		queued += (_main.get("_gate_hand_swaps") as Array).size()
	_main.call("_begin_gate_sweep", Time.get_ticks_msec(), true)
	_main.set("_gate_sweep_active", false)
	_expect(queued == 0, "(timing) bodies at rest queue no swap (%s)" % LookProfile.quality_name(LookProfile.quality()))
	return best

## A body built at High has no variant yet; the switch to Low finds it in the
## quality pass (no swap there), and the gate then gives it crowd hands.
func _check_built_high_then_low() -> void:
	_put([_record(LATE, 500 + 3 * 5, 502)])
	_main.set_process(true)
	await _wait_for_nodes([LATE])
	await _wait_for_bodies([LATE])
	_main.set_process(false)
	var late := _nodes().get(LATE) as ReplicatedActor3D
	if not _expect(late != null and not late.is_model_deferred(), "(fixture) a remote Human is built at High"):
		return
	late.action_crossfade_seconds = 0.0
	_expect(late.hand_detail_full() and not late.hand_detail_managed(),
		"built at High it has full hands and no variant")
	_set_quality(Quality.LOW)
	_check_rules(Quality.LOW)
	_expect(late.hand_detail_full() and late.hand_detail_managed(),
		"the switch to Low finds its variant without swapping")
	_sweep({late: 25.0})
	_drain()
	_expect(not late.hand_detail_full(), "and the next sweep gives it crowd hands at 25 m")
