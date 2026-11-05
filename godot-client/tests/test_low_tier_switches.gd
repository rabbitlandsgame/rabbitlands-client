extends SceneTree
## FIX-CPU (wave 2 stage B): the Low actor tier's measurement switches and the
## gate's precomputed Low rules.
##
## - RABBITLANDS_CROWD_PRESENTATION `-hands`, `-frameclock` and `-cues` drop one
##   part of the Low tier (CrowdPresentation.TIER_PARTS) under any policy, and
##   nothing else; without them every part is on, `legacy` included.
## - Main reads them where the quality is applied: `-hands` leaves remote
##   Humans built at Low on full hands and the gate asking nothing of them,
##   `-frameclock` keeps remote motion on physics at Low, `-cues` leaves hand
##   cues alone. Medium and High are as before whichever is set.
## - The gate's precomputed rules (`_gate_low_rules`, `_gate_hands_on`, the
##   squared hand distances) follow the quality: 12/15 m at Low, nothing at
##   Medium and High; the frame clock is off there, so Main's frame does not
##   step it.
## - The rules the gate inlines give what the library rules they copy give:
##   the hand decision CrowdAnimationLibrary.want_full's (with the priority
##   and pinned clauses) around both hand distances, the hand cues
##   CombatPresentation3D.cues_wanted's at Low.
##
## main.gd is loaded at run time, not preloaded: it reads the autoload
## singletons, which a SceneTree script is compiled before.

const Options := preload("res://src/world/graphics_options.gd")
const CrowdPresentationScript := preload("res://src/world/crowd_presentation.gd")
const CrowdLibrary := preload("res://src/actors/crowd_animation_library.gd")
const LOCAL := 100
const REMOTE := [101, 102]
## The parity check's own body, so no body it leaves parked is revived for
## the switch checks.
const PARITY := 103
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
	_check_parsing()
	var saved_config: Variant = FileAccess.get_file_as_bytes(Options.SETTINGS_PATH) \
		if FileAccess.file_exists(Options.SETTINGS_PATH) else null
	var saved_quality := OS.get_environment(LookProfile.QUALITY_VARIABLE)
	OS.unset_environment(LookProfile.QUALITY_VARIABLE)
	var main_script := load("res://src/app/main.gd") as GDScript
	if _expect(main_script != null and main_script.can_instantiate(), "main.gd compiles"):
		await _set_up()
		_check_gate_rules()
		await _check_rule_parity()
		await _check_hands_switch()
		_check_frame_clock_switch()
		_check_cues_switch()
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
	ReplicatedActor3D.set_frame_driven(false)
	print("low tier switches: %d checks, %s" % [checks, "PASS" if failures == 0 else "FAIL (%d)" % failures])
	quit(failures)

# --- CrowdPresentation.configure ---------------------------------------------------

func _tier(crowd: RefCounted) -> Array:
	return [crowd.get("tier_hands"), crowd.get("tier_frame_clock"), crowd.get("tier_cues")]

func _features(crowd: RefCounted) -> Array:
	return ["lazy", "gate", "effects", "park", "stagger", "quarter"].map(
		func(name: String) -> bool: return bool(crowd.get(name)))

func _check_parsing() -> void:
	var crowd: RefCounted = CrowdPresentationScript.new()
	for policy: String in ["", "all", "legacy", "lazy,gate", "-quarter", "hands"]:
		crowd.call("configure", policy)
		_expect(_tier(crowd) == [true, true, true], "policy '%s' keeps every Low tier part" % policy)
	crowd.call("configure", "")
	var everything := _features(crowd)
	crowd.call("configure", "hands")
	_expect(_features(crowd) == everything, "naming a tier part is not a feature list (every feature stays on)")
	crowd.call("configure", "-hands")
	_expect(_tier(crowd) == [false, true, true] and _features(crowd) == everything,
		"-hands drops the crowd hand variant and nothing else")
	crowd.call("configure", "-frameclock,-cues")
	_expect(_tier(crowd) == [true, false, false] and _features(crowd) == everything,
		"-frameclock,-cues drop the frame clock and the cue rule and nothing else")
	crowd.call("configure", "lazy,-hands")
	_expect(_tier(crowd) == [false, true, true] and bool(crowd.get("lazy")) and not bool(crowd.get("gate")),
		"a feature list keeps its meaning beside a dropped tier part")
	crowd.call("configure", "legacy")
	_expect(not _features(crowd).has(true), "legacy still turns every crowd feature off")
	crowd.call("configure", "-hands,-frameclock,-cues")
	var described: Dictionary = crowd.call("describe")
	_expect(described.get("tierHands") == false and described.get("tierFrameClock") == false
		and described.get("tierCues") == false, "describe() reports the tier parts")

# --- Main fixture --------------------------------------------------------------------

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

func _crowd() -> RefCounted:
	return _main.get("crowd") as RefCounted

## The quality applied again, as Main's quality pass does, so a policy set
## after startup is read even when the level does not change.
func _set_quality(level: int) -> void:
	_main.call("_on_client_setting_changed", "Graphics", "quality", level)
	_main.call("_apply_graphics_quality")

func _record(id: int, x: int, y: int) -> Dictionary:
	return {"actor_id": id, "x": x, "y": y, "rotation": 0, "actor_type": 1, "kind": 1,
		"name": "Switch %d" % id, "health": 50, "max_health": 50, "alive": true,
		"appearance": {}, "equipment_visuals": HUMANOID_KIT.duplicate(),
		"equipment_fallback_parts": []}

func _nodes() -> Dictionary:
	return _main.get("actor_nodes") as Dictionary

func _sync() -> void:
	_main.call("_sync_world", _app_state.call("take_changed_actors"))
	await process_frame

func _spawn(records: Array) -> void:
	var actors: Dictionary = (_app_state.get("actors") as Dictionary)
	for record: Dictionary in records:
		actors[int(record.actor_id)] = record
		_app_state.call("mark_actor_changed", int(record.actor_id))
	for unused: int in range(120):
		await _sync()
		var waiting := false
		for record: Dictionary in records:
			var actor := _nodes().get(int(record.actor_id)) as ReplicatedActor3D
			waiting = waiting or actor == null or actor.is_model_deferred()
		if not waiting:
			return
		_main.set("_animation_gate_refresh_msec", 0)
		_main.call("_update_animation_gate", 0.0)
		_main.call("_update_model_builds")

func _despawn(ids: Array) -> void:
	var actors: Dictionary = (_app_state.get("actors") as Dictionary)
	for id: int in ids:
		actors.erase(id)
		_app_state.call("mark_actor_changed", id)
	await _sync()

func _rules() -> Array:
	return [_main.get("_gate_low_rules"), _main.get("_gate_hands_on"),
		float(_main.get("_gate_hand_d2")), float(_main.get("_gate_hand_release_d2"))]

func _check_gate_rules() -> void:
	_crowd().call("configure", "")
	_set_quality(Quality.LOW)
	var rules := _rules()
	_expect(rules[0] == true and rules[1] == true and is_equal_approx(rules[2], 144.0)
		and is_equal_approx(rules[3], 225.0), "Low: the gate's rules are on, hands at 12 m / 15 m squared (%s)" % [rules])
	_expect(ReplicatedActor3D.frame_driven(), "Low: remote motion is on the frame clock")
	for level: int in [Quality.MEDIUM, Quality.HIGH]:
		_set_quality(level)
		rules = _rules()
		_expect(rules[0] == false and rules[1] == false and is_inf(rules[2]) and is_inf(rules[3]),
			"%s: no Low rule, no hand distance (%s)" % [LookProfile.quality_name(level), rules])
		_expect(not ReplicatedActor3D.frame_driven() and ReplicatedActor3D.frame_driven_count() == 0,
			"%s: no frame clock, so Main's frame has nothing to step" % LookProfile.quality_name(level))
		_expect(not bool(_main.get("_gate_cues_full_only")) and is_equal_approx(
			(_main.get("animation_gate") as AnimationGate).half_rate_metres, 45.0),
			"%s: every hand cue, 45 m half-rate distance" % LookProfile.quality_name(level))

## What the gate's sweep asks of `body` with the camera `metres` above it:
## whether it wants full hands (the body's own state when nothing is queued)
## and how many swaps one classify queued.
func _gate_hand_decision(body: ReplicatedActor3D, metres: float) -> Array:
	_main.call("_begin_gate_sweep", Time.get_ticks_msec(), true)
	_main.set("_gate_camera_at", body.global_position + Vector3(0.0, metres, 0.0))
	_main.call("_gate_classify", body.actor_id)
	var swaps: Array = _main.get("_gate_hand_swaps")
	_main.set("_gate_hand_swaps", [])
	_main.call("_finish_gate_sweep")
	return [body.hand_detail_full() if swaps.is_empty() else bool(swaps[0].full), swaps.size()]

## Every (distance, hands now, selected) case around both hand distances whose
## gate decision differs from the library rule it inlines.
func _hand_parity_mismatches(body: ReplicatedActor3D) -> Array:
	var near := ActorRenderQuality.hand_detail_metres(Quality.LOW)
	var release := ActorRenderQuality.hand_detail_release_metres(Quality.LOW)
	var mismatches: Array = []
	for metres: float in [1.0, near - 0.25, near + 0.25, release - 0.25, release + 0.25, 40.0]:
		for full_now: bool in [true, false]:
			for selected: bool in [false, true]:
				CrowdLibrary.set_hand_detail(body.animation_player, body.get_skeleton(), full_now)
				_app_state.set("selected_actor_id", body.actor_id if selected else -1)
				var decision := _gate_hand_decision(body, metres)
				var want: bool = selected or CrowdLibrary.want_full(metres * metres, full_now, near, release) \
					or (full_now and body.hand_detail_pinned())
				if body.hand_detail_full() != full_now or decision[0] != want or decision[1] > 1:
					mismatches.append([metres, full_now, selected, decision, want])
	_app_state.set("selected_actor_id", -1)
	return mismatches

func _check_rule_parity() -> void:
	_crowd().call("configure", "")
	_set_quality(Quality.LOW)
	await _spawn([_record(LOCAL, 500, 500), _record(PARITY, 504, 500)])
	var body := _nodes().get(PARITY) as ReplicatedActor3D
	if _expect(body != null and body.hand_detail_managed() and not body.hand_detail_pinned(),
			"(fixture) a remote Human at Low whose hands the gate manages"):
		var mismatches := _hand_parity_mismatches(body)
		_expect(mismatches.is_empty(),
			"the gate's hand decision is CrowdAnimationLibrary.want_full's, priority and hysteresis included (%s)"
			% [mismatches])
		# The check notices an inlined rule that drifts: a release distance
		# equal to the near one (no hysteresis) is caught.
		_main.set("_gate_hand_release_d2", float(_main.get("_gate_hand_d2")))
		_expect(not _hand_parity_mismatches(body).is_empty(),
			"(sensitivity) a gate without the 15 m hysteresis fails the parity check")
		_set_quality(Quality.LOW)
	if _expect(body != null and body.combat_presentation != null,
			"(fixture) the remote Human has a combat presentation"):
		var cue_mismatches: Array = []
		for before: bool in [true, false]:
			for full_rate: bool in [true, false]:
				for priority: bool in [true, false]:
					body.set_combat_cues_allowed(before)
					_main.call("_gate_set_cues", body, full_rate, priority)
					if body.combat_cues_allowed() != CombatPresentation3D.cues_wanted(Quality.LOW, full_rate, priority):
						cue_mismatches.append([before, full_rate, priority])
		_expect(cue_mismatches.is_empty(),
			"the gate's hand cues are CombatPresentation3D.cues_wanted's at Low (%s)" % [cue_mismatches])
	await _despawn([PARITY])

func _check_hands_switch() -> void:
	# Default at Low first: a remote Human is built on the crowd variant.
	_crowd().call("configure", "")
	_set_quality(Quality.LOW)
	await _spawn([_record(LOCAL, 500, 500), _record(REMOTE[0], 503, 502)])
	var built := _nodes().get(REMOTE[0]) as ReplicatedActor3D
	_expect(built != null and not built.hand_detail_full(),
		"(fixture) without a switch a remote Human built at Low starts on crowd hands")
	await _despawn([REMOTE[0]])
	# -hands: the next one is built on full hands, and the gate never asks.
	_crowd().call("configure", "-hands")
	_set_quality(Quality.LOW)
	var rules := _rules()
	_expect(rules[0] == true and rules[1] == false and is_inf(rules[2]),
		"-hands at Low: hands are not managed, the cue rule still is (%s)" % [rules])
	_expect(bool(_main.get("_gate_cues_full_only")), "-hands at Low keeps the hand-cue rule")
	await _spawn([_record(LOCAL, 500, 500), _record(REMOTE[1], 506, 502)])
	var body := _nodes().get(REMOTE[1]) as ReplicatedActor3D
	_expect(body != null and body.hand_detail_full() and not body.crowd_hands_at_build,
		"-hands: a remote Human built at Low keeps full hands")
	if body != null:
		_main.call("_begin_gate_sweep", Time.get_ticks_msec(), true)
		_main.set("_gate_camera_at", body.global_position + Vector3(0.0, 40.0, 0.0))
		_main.call("_gate_classify", body.actor_id)
		_main.call("_finish_gate_sweep")
		_expect((_main.get("_hand_swap_queue") as Array).is_empty() and body.hand_detail_full(),
			"-hands: a body 40 m from the camera is not queued for crowd hands")
	await _despawn([REMOTE[1]])
	_crowd().call("configure", "")
	_set_quality(Quality.LOW)

func _check_frame_clock_switch() -> void:
	_crowd().call("configure", "-frameclock")
	_set_quality(Quality.LOW)
	_expect(not ReplicatedActor3D.frame_driven(), "-frameclock at Low: remote motion stays on physics")
	_expect(bool(_main.get("_gate_hands_on")) and bool(_main.get("_gate_cues_full_only")),
		"-frameclock at Low keeps the hand and cue rules")
	_crowd().call("configure", "")
	_set_quality(Quality.LOW)
	_expect(ReplicatedActor3D.frame_driven(), "without it Low is back on the frame clock")

func _check_cues_switch() -> void:
	_crowd().call("configure", "-cues")
	_set_quality(Quality.LOW)
	_expect(not bool(_main.get("_gate_cues_full_only")) and bool(_main.get("_gate_hands_on"))
		and bool(_main.get("_gate_low_rules")), "-cues at Low: the gate leaves hand cues alone, hands still managed")
	_crowd().call("configure", "-hands,-cues")
	_set_quality(Quality.LOW)
	_expect(not bool(_main.get("_gate_low_rules")), "-hands,-cues at Low: no per-body Low rule is left")
	_crowd().call("configure", "")
	_set_quality(Quality.HIGH)
