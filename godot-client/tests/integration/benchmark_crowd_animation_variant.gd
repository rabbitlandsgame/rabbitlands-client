extends SceneTree
## LAT-L1 microbenchmark (headless): what the fingerless crowd variant saves per
## animation update and what a hand-detail swap costs, on real orun_male rigs
## with the runtime-imported Universal library. Ported from the wave-2 design
## bench (finger_bench.gd), now through CrowdAnimationLibrary itself.
##
## Cases, each as microseconds per AnimationPlayer.advance(1/30) per body (best
## of REPEATS x STEPS over BODIES bodies, half on Walk and half on Idle_A,
## non-deterministic like the actors):
##   full               today's library
##   crowd              the crowd variant
##   crowd_spells       the variant plus a "spell_variants" library of full
##                      clips (finger tracks then sit in the mixer's track cache
##                      even when no spell plays)
##   full_again         back on the full library
## plus derive time, swap time in each direction and the skeleton bone update,
## then the same on ACTORS configured luminous actors (their real ~90-clip
## library) with prepare() timings and a per-step swap breakdown.
##
## Run: godot --headless --log-file <log> --path godot-client
##        --script res://tests/integration/benchmark_crowd_animation_variant.gd
## Optional output file: RL_CROWD_VARIANT_BENCH=<path.json>. Timings depend on
## the machine and its load; compare cases from one run, not across machines.
const CROWD := preload("res://src/actors/crowd_animation_library.gd")
const RACE := "res://assets/actors/native/races/orun_male.glb"
const LIBRARY := "res://assets/actors/native/shared/Universal_Animation_Library.glb"
const CLIPS := ["Idle_A", "Idle_Subtle", "Walk", "Run_Female", "Fighting_Idle", "Sword_Attack"]
const LOOPS := ["Idle_A", "Idle_Subtle", "Walk", "Run_Female", "Fighting_Idle"]
const BODIES := 48
const STEPS := 120
const REPEATS := 5
const STEP := 1.0 / 30.0
const ACTORS := 16

var results := {"schemaVersion": 1, "bodies": BODIES, "steps": STEPS, "repeats": REPEATS}

func _initialize() -> void:
	# Actors build against a live tree (global transforms), so start on the
	# first frame rather than before the main loop runs.
	call_deferred("_run")

func _run() -> void:
	await process_frame
	var started := Time.get_ticks_usec()
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	if document.append_from_file(ProjectSettings.globalize_path(RACE), state) != OK:
		_finish({"error": "race parse failed"})
		return
	var template := document.generate_scene(state) as Node3D
	results["race_parse_ms"] = _ms(started)
	var bodies: Array = []
	var players: Array = []
	var skeletons: Array = []
	for index: int in BODIES:
		var body := template.duplicate() as Node3D
		body.name = "Body%d" % index
		root.add_child(body)
		var skeleton := _skeleton(body)
		started = Time.get_ticks_usec()
		var imported: Dictionary = NativeAnimationImporter.import_library(body, LIBRARY, skeleton, {},
			PackedStringArray(CLIPS), PackedStringArray(LOOPS))
		if index == 0:
			results["first_import_ms"] = _ms(started)
		var player := imported.player as AnimationPlayer
		if player == null:
			_finish({"error": "import failed", "errors": Array(imported.errors)})
			return
		player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		player.play(&"Walk" if index % 2 == 0 else &"Idle_A", 0.0)
		player.advance(STEP)
		bodies.append(body)
		players.append(player)
		skeletons.append(skeleton)
	template.free()
	var full: AnimationLibrary = players[0].get_animation_library(&"")
	CROWD.clear()
	started = Time.get_ticks_usec()
	var record := CROWD.derive(full, skeletons[0])
	results["derive_cold_ms"] = _ms(started)
	started = Time.get_ticks_usec()
	for repeat: int in 100:
		CROWD.derive(full, skeletons[0])
	results["derive_cached_us"] = snappedf(float(Time.get_ticks_usec() - started) / 100.0, 0.01)
	var crowd: AnimationLibrary = record.library
	results["tracks"] = {}
	for clip: StringName in [&"Walk", &"Idle_A", &"RESET"]:
		results.tracks[str(clip)] = {"full": full.get_animation(clip).get_track_count(),
			"crowd": crowd.get_animation(clip).get_track_count()}
	results["finger_bones"] = (record.finger_bones as PackedInt32Array).size()
	results["full"] = _advance_cost(players, skeletons)
	results["swap_to_crowd_us"] = _swap_all(players, skeletons, false)
	results["crowd"] = _advance_cost(players, skeletons)
	var spells := AnimationLibrary.new()
	for clip: StringName in [&"Fighting_Idle", &"Sword_Attack"]:
		spells.add_animation(clip, full.get_animation(clip))
	for player: AnimationPlayer in players:
		player.add_animation_library(&"spell_variants", spells)
	results["crowd_spells"] = _advance_cost(players, skeletons)
	for player: AnimationPlayer in players:
		player.remove_animation_library(&"spell_variants")
	results["swap_to_full_us"] = _swap_all(players, skeletons, true)
	results["full_again"] = _advance_cost(players, skeletons)
	var full_us: float = results.full.best_us
	var crowd_us: float = results.crowd.best_us
	results["crowd_saving_pct"] = snappedf(100.0 * (1.0 - crowd_us / maxf(full_us, 0.001)), 0.1)
	for body: Node in bodies:
		body.free()
	await process_frame
	results["actors"] = _actor_section()
	CROWD.clear()
	NativeAnimationImporter.clear()
	_finish(results)

## Configured luminous actors: the real main library (locomotion polish,
## attacks, techniques; about 90 clips), where a swap also rebuilds the
## mixer's track caches over every clip.
func _actor_section() -> Dictionary:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var out := {"actors": ACTORS}
	var actors: Array = []
	var players: Array = []
	var skeletons: Array = []
	for index: int in ACTORS:
		var slug := "luminous_male" if index % 2 == 0 else "luminous_female"
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var errors := actor.configure({"actor_id": 9800 + index, "x": 0, "y": 0, "rotation": 0, "kind": 1,
			"name": "", "appearance": {}, "equipment_visuals": {}},
			CoordinateAdapter.new({"walkingHeight": 0.0}), models[slug], animations, equipment)
		if not errors.is_empty() or actor.animation_player == null:
			out["error"] = "%s configure: %s" % [slug, errors]
			return out
		var player := actor.animation_player
		player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		player.play(&"Walk" if index % 4 < 2 else &"Idle_Subtle", 0.0)
		player.advance(STEP)
		actors.append(actor)
		players.append(player)
		skeletons.append(actor.get_skeleton())
	out["clips"] = players[0].get_animation_library(&"").get_animation_list().size()
	CROWD.clear()
	var prepare_ms: Array = []
	for index: int in players.size():
		var started := Time.get_ticks_usec()
		CROWD.prepare(players[index], skeletons[index])
		prepare_ms.append(_ms(started))
	out["prepare_ms"] = prepare_ms
	out["variants_cached"] = CROWD.cached_count()
	out["full"] = _advance_cost(players, skeletons)
	out["swap_to_crowd_us"] = _swap_all(players, skeletons, false)
	out["crowd"] = _advance_cost(players, skeletons)
	out["swap_to_full_us"] = _swap_all(players, skeletons, true)
	out["full_again"] = _advance_cost(players, skeletons)
	out["crowd_saving_pct"] = snappedf(100.0 * (1.0 - float(out.crowd.best_us) / maxf(float(out.full.best_us), 0.001)), 0.1)
	out["swap_breakdown_us"] = _swap_breakdown(players[0], skeletons[0])
	for actor: Node in actors:
		actor.free()
	return out

## One actor, the swap's steps timed separately (to the variant and back).
func _swap_breakdown(player: AnimationPlayer, skeleton: Skeleton3D) -> Dictionary:
	var full := player.get_animation_library(&"")
	var crowd: AnimationLibrary = CROWD.derive(full, skeleton).library
	var out := {}
	for direction: String in ["to_crowd", "to_full"]:
		var library := crowd if direction == "to_crowd" else full
		var position := player.current_animation_position
		var clip := player.assigned_animation
		var steps := {}
		var started := Time.get_ticks_usec()
		player.stop(true)
		steps["stop"] = Time.get_ticks_usec() - started
		started = Time.get_ticks_usec()
		player.remove_animation_library(&"")
		steps["remove"] = Time.get_ticks_usec() - started
		started = Time.get_ticks_usec()
		player.add_animation_library(&"", library)
		steps["add"] = Time.get_ticks_usec() - started
		started = Time.get_ticks_usec()
		player.play(clip, 0.0)
		steps["play"] = Time.get_ticks_usec() - started
		started = Time.get_ticks_usec()
		player.seek(position, true)
		steps["seek_update"] = Time.get_ticks_usec() - started
		started = Time.get_ticks_usec()
		player.advance(STEP)
		steps["next_advance"] = Time.get_ticks_usec() - started
		out[direction] = steps
	return out

func _advance_cost(players: Array, skeletons: Array) -> Dictionary:
	for player: AnimationPlayer in players:
		player.advance(STEP)
	var best := INF
	var samples: Array = []
	for repeat: int in REPEATS:
		var started := Time.get_ticks_usec()
		for step: int in STEPS:
			for player: AnimationPlayer in players:
				player.advance(STEP)
		var per := float(Time.get_ticks_usec() - started) / float(STEPS * players.size())
		samples.append(snappedf(per, 0.01))
		best = minf(best, per)
	var started := Time.get_ticks_usec()
	for step: int in 20:
		for skeleton: Skeleton3D in skeletons:
			skeleton.force_update_all_bone_transforms()
	var bones := float(Time.get_ticks_usec() - started) / float(20 * skeletons.size())
	return {"best_us": snappedf(best, 0.01), "samples_us": samples,
		"skeleton_update_us": snappedf(bones, 0.01)}

func _swap_all(players: Array, skeletons: Array, full: bool) -> Dictionary:
	var costs: Array = []
	for index: int in players.size():
		var started := Time.get_ticks_usec()
		var swapped := CROWD.set_hand_detail(players[index], skeletons[index], full)
		var spent := Time.get_ticks_usec() - started
		if swapped:
			costs.append(spent)
	costs.sort()
	if costs.is_empty():
		return {"swapped": 0}
	var total := 0
	for cost: int in costs:
		total += cost
	return {"swapped": costs.size(), "median_us": costs[costs.size() / 2], "max_us": costs[-1],
		"mean_us": snappedf(float(total) / costs.size(), 0.1)}

func _skeleton(node: Node) -> Skeleton3D:
	for child: Node in node.find_children("*", "Skeleton3D", true, false):
		return child as Skeleton3D
	return null

func _ms(started: int) -> float:
	return snappedf((Time.get_ticks_usec() - started) / 1000.0, 0.01)

func _finish(data: Dictionary) -> void:
	var destination := OS.get_environment("RL_CROWD_VARIANT_BENCH")
	if not destination.is_empty():
		var file := FileAccess.open(destination, FileAccess.WRITE)
		if file != null:
			file.store_string(JSON.stringify(data, "  "))
			file.close()
	print("CROWD_VARIANT_BENCH " + JSON.stringify(data))
	quit(0 if not data.has("error") else 1)
