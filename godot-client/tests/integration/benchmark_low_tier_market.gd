extends SceneTree
## Wave 2 stage B, FIX-CPU: where the Low actor tier's per-body savings land in
## a market-like crowd, measured in ONE process so the cases share the build,
## the scripts and the host state.
##
## ACTORS configured luminous Humans (equipped, both sexes) stand in the tree as
## remote bodies at Low. With `--tiers=market` (the default) an AnimationGate
## steps them as Main's gate leaves a Performance-preset market (s3-market-160:
## 9 full / 8 half / 32 quarter / 20 paused of 69 built): 8 on the full rate
## (the engine's idle processing), 8 at half and the rest but a sixth at
## quarter rate, staggered, with their skeletons on the same clock, and a sixth
## paused; `--tiers=full` puts every body on the full rate. Two in five walk a
## tile every WALK_FRAMES frames, staggered (27 of 69 in the market). The frame
## clock is Engine.max_fps = FPS with 60 Hz physics, as the Performance preset
## runs. Four cases are run in interleaved blocks (A B C D, then D C B A, ...):
##   crowd/frame     the Low tier as built: crowd hands, frame-driven motion
##   full/frame      full hands (the finger tracks back), frame-driven motion
##   crowd/physics   crowd hands, remote motion on the 60 Hz physics ticks
##   full/physics    both off: what the Low tier had before LAT-L1 and LAT-L7
## and per frame the main thread's work is recorded: from the frame's first
## physics tick (or its idle step when it has none) to a zero-time SceneTree
## timer the last node queues, which fires after the idle step's deferred flush
## (skeleton updates, their modifiers and listeners) and its transform
## notifications; also the physics part alone, the frame-clock step, the
## presentation steps' own bodies and the gate's stepping of the half- and
## quarter-rate bodies. Hands are swapped with CrowdAnimationLibrary directly
## (no crossfade deferral), the clock with ReplicatedActor3D.set_frame_driven
## and the actors' quality pass, the way Main does both.
##
## Run: godot --headless --log-file <log> --path godot-client
##        --script res://tests/integration/benchmark_low_tier_market.gd
## User arguments (after --): --actors=N --blocks=N --block-frames=N --fps=N
## --tiers=market|full --explore (where the frame-clock step runs: EXPLORE_CASES).
## Optional output file: RL_LOW_TIER_BENCH=<path.json>. Headless draws nothing:
## RenderingServer calls are the dummy server's, so a rendered client pays more
## for each moved body's transform notifications than this shows.
const CROWD := preload("res://src/actors/crowd_animation_library.gd")
const Quality := LookProfile.Quality
const HUMANOID_KIT := {0: 114, 1: 106, 3: 117, 4: 171, 5: 184, 6: 192}
const CASES := ["crowd/frame", "full/frame", "crowd/physics", "full/physics"]
## `--explore`: where in the frame the frame clock's step runs (diagnostic).
## "frame" first in the idle step (Main's place), "framelast" last in it,
## "framephysics" in the frame's first physics tick (the frame's delta).
const EXPLORE_CASES := ["crowd/frame", "crowd/framelast", "crowd/framephysics", "crowd/physics"]
const WALK_FRAMES := 12

var actor_count := 48
var cases: Array = CASES
var blocks := 6
var block_frames := 90
var fps := 30
var tiers := "market"
var results := {"schemaVersion": 1}
var _gate := AnimationGate.new()
var _gate_usec := 0
var _actors: Array[ReplicatedActor3D] = []
## The presentation steps the actors took this frame and their own time (the
## step's body, without how it was dispatched).
class TimedActor extends ReplicatedActor3D:
	static var step_calls := 0
	static var step_usec := 0

	func advance_presentation(delta: float) -> void:
		var started := Time.get_ticks_usec()
		super.advance_presentation(delta)
		step_usec += Time.get_ticks_usec() - started
		step_calls += 1
var _tiles := PackedInt32Array()
var _adapter := CoordinateAdapter.new({"walkingHeight": 0.0})
var _driver: Node
var _closer: Node
var _frame_step_usec := 0
var _iteration_started := -1
var _process_started := -1
var _process_ended := -1
var _last_work_usec := -1
var _last_physics_usec := -1
var _last_process_usec := -1
var _last_step_usec := 0
var _last_step_calls := 0

func _initialize() -> void:
	for argument: String in OS.get_cmdline_user_args():
		var pair := argument.trim_prefix("--").split("=")
		if pair.size() == 2 and pair[0] == "tiers" and pair[1] in ["market", "full"]:
			tiers = pair[1]
		if pair.size() != 2 or not pair[1].is_valid_int():
			continue
		match pair[0]:
			"actors": actor_count = maxi(2, int(pair[1]))
			"blocks": blocks = maxi(1, int(pair[1]))
			"block-frames": block_frames = maxi(10, int(pair[1]))
			"fps": fps = maxi(10, int(pair[1]))
	if "--explore" in OS.get_cmdline_user_args():
		cases = EXPLORE_CASES
	call_deferred("_run")

## Main's `_advance_remote_motion`: the frame clock's one step, first in the
## idle step.
class FrameClockDriver:
	extends Node
	var owner_bench: Object
	var in_physics := false
	func _process(delta: float) -> void:
		if not in_physics:
			var started := Time.get_ticks_usec()
			ReplicatedActor3D.advance_frame_driven(delta)
			owner_bench.set("_frame_step_usec", Time.get_ticks_usec() - started)
		# Main's _update_animation_gate: the stepped tiers, after the frame step.
		var gate_started := Time.get_ticks_usec()
		(owner_bench.get("_gate") as AnimationGate).advance(delta)
		owner_bench.set("_gate_usec", Time.get_ticks_usec() - gate_started)

## The last node to process: queues the timer that closes the frame's work.
class FrameCloser:
	extends Node
	var owner_bench: Object
	func _process(_delta: float) -> void:
		owner_bench.set("_process_ended", Time.get_ticks_usec())
		get_tree().create_timer(0.0, true, false, true).timeout.connect(
			Callable(owner_bench, "_on_iteration_closed"))

func _on_iteration_started() -> void:
	if _iteration_started < 0:
		_iteration_started = Time.get_ticks_usec()
		if _driver != null and _driver.in_physics and Engine.is_in_physics_frame():
			var started := Time.get_ticks_usec()
			ReplicatedActor3D.advance_frame_driven(1.0 / float(fps))
			_frame_step_usec = Time.get_ticks_usec() - started

func _on_process_started() -> void:
	_on_iteration_started()
	if _process_started < 0:
		_process_started = Time.get_ticks_usec()

func _on_iteration_closed() -> void:
	if _iteration_started >= 0:
		var now := Time.get_ticks_usec()
		_last_work_usec = now - _iteration_started
		_last_physics_usec = maxi(0, _process_started - _iteration_started)
		_last_process_usec = maxi(0, _process_ended - _process_started)
		_last_step_usec = TimedActor.step_usec
		_last_step_calls = TimedActor.step_calls
	TimedActor.step_usec = 0
	TimedActor.step_calls = 0
	_iteration_started = -1
	_process_started = -1
	_process_ended = -1

func _run() -> void:
	await process_frame
	Engine.max_fps = fps
	Engine.physics_ticks_per_second = 60
	results["actors"] = actor_count
	results["blocks"] = blocks
	results["blockFrames"] = block_frames
	results["fps"] = fps
	results["tiers"] = tiers
	_gate.gate_skeletons = true
	_gate.stagger = true
	var error := _build()
	if not error.is_empty():
		_finish({"error": error})
		return
	_driver = FrameClockDriver.new()
	_driver.owner_bench = self
	_driver.process_priority = -(1 << 30)
	root.add_child(_driver)
	_closer = FrameCloser.new()
	_closer.owner_bench = self
	_closer.process_priority = 1 << 30
	root.add_child(_closer)
	physics_frame.connect(_on_iteration_started)
	process_frame.connect(_on_process_started)
	var per_case := {}
	for name: String in cases:
		per_case[name] = {"work_ms": [], "physics_ms": [], "process_ms": [], "frame_step_ms": [],
			"step_body_ms": [], "steps": [], "gate_step_ms": [], "walkers_presenting": []}
	for block: int in blocks:
		var order: Array = cases.duplicate()
		if block % 2 == 1:
			order.reverse()
		for name: String in order:
			await _apply_case(name)
			# Two frames for the case to settle (swaps' cache rebuild, rehoming).
			for unused: int in 2:
				await _frame()
			for frame: int in block_frames:
				await _frame()
				var row: Dictionary = per_case[name]
				if _last_work_usec >= 0:
					(row.work_ms as Array).append(float(_last_work_usec) / 1000.0)
					(row.physics_ms as Array).append(float(_last_physics_usec) / 1000.0)
					(row.process_ms as Array).append(float(_last_process_usec) / 1000.0)
					(row.step_body_ms as Array).append(float(_last_step_usec) / 1000.0)
					(row.steps as Array).append(float(_last_step_calls))
				(row.frame_step_ms as Array).append(float(_frame_step_usec) / 1000.0)
				(row.gate_step_ms as Array).append(float(_gate_usec) / 1000.0)
				if frame == 0:
					(row.walkers_presenting as Array).append(_presenting())
	var summary := {}
	for name: String in cases:
		var row: Dictionary = per_case[name]
		summary[name] = {"work_ms": _stats(row.work_ms), "physics_ms": _stats(row.physics_ms),
			"process_ms": _stats(row.process_ms), "step_body_ms": _stats(row.step_body_ms),
			"steps_per_frame": snappedf(_mean(row.steps), 0.01),
			"flush_ms": snappedf(_mean(row.work_ms) - _mean(row.physics_ms) - _mean(row.process_ms), 0.001),
			"frame_step_ms": _stats(row.frame_step_ms), "gate_step_ms": _stats(row.gate_step_ms),
			"presenting": row.walkers_presenting,
			"total_ms": snappedf(_mean(row.work_ms), 0.001)}
	results["cases"] = summary
	if cases == CASES:
		results["fingers_full_minus_crowd_ms"] = {
			"frame": _difference(summary, "full/frame", "crowd/frame"),
			"physics": _difference(summary, "full/physics", "crowd/physics")}
		results["clock_physics_minus_frame_ms"] = {
			"crowd": _difference(summary, "crowd/physics", "crowd/frame"),
			"full": _difference(summary, "full/physics", "full/frame")}
		results["tier_saving_ms"] = _difference(summary, "full/physics", "crowd/frame")
	ReplicatedActor3D.set_frame_driven(false)
	_gate.reset(false)
	physics_frame.disconnect(_on_iteration_started)
	process_frame.disconnect(_on_process_started)
	for actor: ReplicatedActor3D in _actors:
		actor.free()
	_driver.free()
	_closer.free()
	CROWD.clear()
	NativeAnimationImporter.clear()
	_finish(results)

func _build() -> String:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var started := Time.get_ticks_usec()
	for index: int in actor_count:
		var slug := "luminous_male" if index % 2 == 0 else "luminous_female"
		var actor := TimedActor.new()
		root.add_child(actor)
		var errors := actor.configure({"actor_id": 9700 + index, "x": 0, "y": index * 2, "rotation": 0,
			"kind": 1, "name": "Market %d" % index, "appearance": {},
			"equipment_visuals": HUMANOID_KIT.duplicate(), "equipment_fallback_parts": []},
			_adapter, models[slug], animations, equipment)
		if not errors.is_empty() or actor.animation_player == null:
			return "%s configure: %s" % [slug, errors]
		actor.apply_render_quality(Quality.LOW, false)
		actor.apply_server_state(_state(index, 0, index * 2, 7), _adapter, true)
		_actors.append(actor)
		_tiles.append(0)
	results["build_ms"] = snappedf(float(Time.get_ticks_usec() - started) / 1000.0, 0.1)
	results["clips"] = _actors[0].animation_player.get_animation_library(&"").get_animation_list().size() \
		if CROWD.hand_detail_full(_actors[0].animation_player) else -1
	return ""

func _state(index: int, x: int, y: int, command: int) -> Dictionary:
	return {"actor_id": 9700 + index, "x": x, "y": y, "rotation": 0, "command": command, "buffs": 0,
		"health": 100, "max_health": 100, "alive": true}

func _apply_case(name: String) -> void:
	var parts := name.split("/")
	var crowd_hands := parts[0] == "crowd"
	var frame_clock := parts[1].begins_with("frame")
	_driver.in_physics = parts[1] == "framephysics"
	_driver.process_priority = (1 << 30) - 1 if parts[1] == "framelast" else -(1 << 30)
	ReplicatedActor3D.set_frame_driven(frame_clock)
	for index: int in _actors.size():
		var actor := _actors[index]
		# The quality pass puts an awake body on the clock now in force.
		actor.apply_render_quality(Quality.LOW, false)
		CROWD.set_hand_detail(actor.animation_player, actor.get_skeleton(), not crowd_hands)
		_gate.apply(actor.animation_player, _tier_of(index), actor.get_skeleton())
	await process_frame

## The gate tier a body has in the market mix: 8 full, 8 half, the last sixth
## paused, the rest quarter; every body full with `--tiers=full`.
func _tier_of(index: int) -> AnimationGate.Tier:
	if tiers == "full" or index < 8:
		return AnimationGate.Tier.FULL
	if index < 16:
		return AnimationGate.Tier.HALF
	if index >= _actors.size() - _actors.size() / 6:
		return AnimationGate.Tier.PAUSED
	return AnimationGate.Tier.QUARTER

## One drawn frame, and the walkers' next steps (a tile every WALK_FRAMES
## frames, staggered), as packets between frames.
func _frame() -> void:
	await process_frame
	var frame := Engine.get_process_frames()
	for index: int in _actors.size():
		if index % 5 < 2 and (frame + index) % WALK_FRAMES == 0:
			_tiles[index] = (_tiles[index] + 1) % 40
			_actors[index].apply_server_state(_state(index, _tiles[index], index * 2, 22), _adapter)

func _presenting() -> Dictionary:
	var frame_driven := 0
	var physics := 0
	var crowd := 0
	for actor: ReplicatedActor3D in _actors:
		frame_driven += int(actor.presents_on_frame_clock())
		physics += int(actor.is_physics_processing())
		crowd += int(not CROWD.hand_detail_full(actor.animation_player))
	return {"frame": frame_driven, "physics": physics, "crowdHands": crowd}

func _difference(summary: Dictionary, minuend: String, subtrahend: String) -> float:
	return snappedf(float(summary[minuend].total_ms) - float(summary[subtrahend].total_ms), 0.001)

func _mean(values: Array) -> float:
	if values.is_empty():
		return 0.0
	var total := 0.0
	for value: float in values:
		total += value
	return total / float(values.size())

func _stats(values: Array) -> Dictionary:
	var sorted := values.duplicate()
	sorted.sort()
	return {"mean": snappedf(_mean(values), 0.001),
		"p50": snappedf(float(sorted[sorted.size() / 2]), 0.001) if not sorted.is_empty() else 0.0,
		"n": values.size()}

func _finish(data: Dictionary) -> void:
	var destination := OS.get_environment("RL_LOW_TIER_BENCH")
	if not destination.is_empty():
		var file := FileAccess.open(destination, FileAccess.WRITE)
		if file != null:
			file.store_string(JSON.stringify(data, "  "))
			file.close()
	print("LOW_TIER_MARKET_BENCH " + JSON.stringify(data))
	quit(0 if not data.has("error") else 1)
