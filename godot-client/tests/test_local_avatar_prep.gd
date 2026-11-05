extends SceneTree
## AW-04d: the player's own body waits behind the arrival curtain for its
## asset closure, parsed on the actor preparer's worker.
##
##   * LocalAvatarPrep's rules on their own: ready or no curtain builds at
##     once; a wait begins at the first not-ready ask and ends "build now" at
##     its deadline (6 s), and stays so until the body is built; another
##     player, the curtain dropping and a session's end; counters.
##   * ActorAssetClosure with `rl_head` (the player's own, in the game) also
##     names the RL head's own files at High, keeps the game hairstyle, and is
##     memoized apart; nothing changes below High.
##   * ActorResourceWarmup's local class: a PRIORITY_LOCAL file starts while
##     PUBLISH_QUEUE_LIMIT other roots await publication (one root more at
##     most) and its root is published before theirs.
##   * Main (main.tscn, a recorded transport):
##     - behind the curtain a cold local body gets no node (no stand-in) while
##       its files are parsed at PRIORITY_LOCAL, then is built with no
##       main-thread glTF parse and equals the body main's own parses build;
##     - the held world sync of a change of map asks for the closure as soon
##       as the record is known, so the body is built at its first ask;
##     - the arrival curtain stays up while the body waits and lowers once it
##       stands;
##     - a preparer that never finishes: built after the 6 s deadline (main
##       parses as before); files the worker could not prepare: built at once;
##     - curtain down, kill switch, a held body (AW-02): built at once with
##       nothing queued; the wait ends at a session's end, and a change of map
##       that overtakes it ends it so the next arrival waits afresh;
##     - High with RL loading deferred as in a window: the RL head's files are
##       asked of RLHeadLibrary and the body is built with no main parse.
##
##   Godot --headless --path godot-client --script res://tests/test_local_avatar_prep.gd

const Closure := preload("res://src/actors/actor_asset_closure.gd")
const Warmup := preload("res://src/actors/actor_resource_warmup.gd")
const Prep := preload("res://src/actors/local_avatar_prep.gd")
const MEDIUM := ActorRenderQuality.Quality.MEDIUM
const HIGH := ActorRenderQuality.Quality.HIGH
const LOCAL := 1
const CAPE_LOADOUT := {"0": 114, "1": 106, "2": 1, "3": 117, "4": 171, "5": 184, "6": 192}
const VOTARY_MALE := 3
const DEADLINE_MSEC := 90000

var checks := 0
var failures := 0
var models: Dictionary = {}
var equipment: Dictionary = {}
var main: Node
var app: Node


func _init() -> void:
	run.call_deferred()


func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("local avatar prep: " + message)


func run() -> void:
	create_timer(900).timeout.connect(func() -> void:
		push_error("local avatar prep timed out")
		quit(1))
	var previous_prepared := OS.get_environment("RABBITLANDS_PREPARED_CONTENT")
	OS.set_environment("RABBITLANDS_PREPARED_CONTENT", "raw")
	var old_quality := LookProfile.player_quality()
	LookProfile.set_player_quality(MEDIUM)
	models = (JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")) as Dictionary).models
	equipment = EquipmentRegistrySnapshotCache.prepare(
		JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json")) as Dictionary)
	_check_prep_rules()
	_check_closure_rl_head()
	await _check_local_class()
	await _setup_main()
	await _check_curtained_cold_build()
	await _check_early_request()
	await _check_curtain_waits_for_the_body()
	await _check_timeout()
	await _check_failed_files()
	await _check_built_at_once()
	await _check_held_body()
	await _check_high_rl_head()
	await _check_map_change_abandons()
	await _check_session_end()
	await _cleanup()
	LookProfile.set_player_quality(old_quality)
	if previous_prepared.is_empty():
		OS.unset_environment("RABBITLANDS_PREPARED_CONTENT")
	else:
		OS.set_environment("RABBITLANDS_PREPARED_CONTENT", previous_prepared)
	print("local avatar prep: %d checks, %d failures" % [checks, failures])
	quit(1 if failures > 0 else 0)


func _record(id: int, model_hair := 2, visuals: Dictionary = CAPE_LOADOUT, name := "Me",
		actor_type := 1, x := 0, y := 0) -> Dictionary:
	return {"actor_id": id, "actor_type": actor_type, "kind": 1, "name": name,
		"x": x, "y": y, "rotation": 0, "health": 20, "max_health": 20, "alive": true,
		"appearance": {"skin": 2, "hair": AppearanceVariants.pack_hair(model_hair, 0)},
		"equipment_visuals": visuals.duplicate(), "equipment_fallback_parts": []}


func _cold() -> void:
	RLHeadLibrary.cancel_warm()
	RLHeadLibrary.clear()
	GlbSceneCache.clear()
	ReplicatedActor3D.clear_static_caches()
	TorsoBodyCover.clear()
	preload("res://src/actors/wardrobe_shirt_fit.gd").clear()
	Closure.clear_memo()


func _misses() -> int:
	return int(GlbSceneCache.retention_snapshot().get("lookup_misses", 0))


func _pump(warmup: RefCounted, done: Callable) -> bool:
	var deadline := Time.get_ticks_msec() + DEADLINE_MSEC
	while not bool(done.call()) and Time.get_ticks_msec() < deadline:
		await process_frame
		warmup.call("poll")
	return bool(done.call())


# --- LocalAvatarPrep ----------------------------------------------------------------------

func _check_prep_rules() -> void:
	var prep = Prep.new()
	expect(prep.timeout_msec == 6000 and Prep.TIMEOUT_MSEC == 6000, "the wait is bounded at 6 s")
	expect(prep.admit(LOCAL, true, true, 0) and not prep.waiting() and prep.built(LOCAL, 1).is_empty()
		and prep.built_at_once == 1, "a ready closure builds at once: no wait, counted as built at once")
	expect(prep.admit(LOCAL, false, false, 0) and not prep.waiting() and prep.built(LOCAL, 1).is_empty()
		and prep.built_uncurtained == 1, "with the curtain down nothing waits (counted as built uncurtained)")
	expect(not prep.admit(LOCAL, false, true, 1000) and prep.waiting() and prep.waits == 1,
		"behind the curtain a closure not ready waits, from its first ask")
	expect(not prep.admit(LOCAL, false, true, 6999) and prep.waits == 1, "still waiting just before the deadline")
	expect(prep.admit(LOCAL, false, true, 7000), "at the deadline the answer is build now")
	expect(prep.admit(LOCAL, false, true, 7001) and prep.admit(LOCAL, false, true, 9000),
		"and stays so (Main asks again for the build itself) until it is built")
	var timed := prep.built(LOCAL, 7050)
	expect(str(timed.get("outcome", "")) == "timeout" and int(timed.get("wait_ms", 0)) == 6000
		and not prep.waiting() and int(prep.outcomes.get("timeout", 0)) == 1,
		"a body built after the deadline reports the timeout and the wait up to it (not the build): %s" % timed)
	prep.admit(LOCAL, false, true, 100)
	expect(prep.admit(LOCAL, true, true, 350), "a closure ready during the wait builds")
	var waited := prep.built(LOCAL, 360)
	expect(str(waited.get("outcome", "")) == "ready" and int(waited.get("wait_ms", 0)) == 250
		and prep.last_wait_msec == 250 and prep.maximum_wait_msec == 6000, "it reports the wait it had: %s" % waited)
	prep.admit(LOCAL, false, true, 0)
	expect(prep.admit(LOCAL, false, false, 50) and str(prep.built(LOCAL, 60).get("outcome", "")) == "uncurtained",
		"the curtain dropping while it waits builds at once (outcome uncurtained)")
	prep.admit(LOCAL, false, true, 0)
	expect(not prep.admit(7, false, true, 6500) and prep.waiting(),
		"another player id starts its own wait (the deadline is per player)")
	prep.clear()
	expect(not prep.waiting() and int(prep.snapshot(0).waitingForMsec) == 0, "a session's end ends the wait")
	var begun: int = prep.waits
	prep.admit(LOCAL, false, true, 1000)
	prep.abandon()
	expect(not prep.waiting() and int(prep.outcomes.get("abandoned", 0)) == 1,
		"a change of map that overtakes the wait ends it unbuilt (outcome abandoned)")
	expect(not prep.admit(LOCAL, false, true, 9000) and prep.waits == begun + 2
		and int(prep.snapshot(9000).waitingForMsec) == 0,
		"and the next arrival's wait begins at its own first ask, not at the abandoned one's")
	prep.abandon()
	prep.abandon()
	expect(int(prep.outcomes.get("abandoned", 0)) == 2, "each abandoned wait counts once; abandoning with no wait counts nothing")
	prep.clear()
	prep.note_early(LOCAL, "a")
	prep.note_early(LOCAL, "a")
	prep.note_early(LOCAL, "b")
	var row: Dictionary = prep.snapshot(0)
	expect(prep.early_requests == 2 and row.has("outcomes") and row.has("earlyRequests") and row.has("waitingForMsec")
		and row.has("timeoutMsec") and not JSON.stringify(row).contains("\"id\""),
		"early requests count once per closure; the snapshot is counts and times only: %s" % row)


# --- the closure with rl_head -------------------------------------------------------------

func _check_closure_rl_head() -> void:
	var config: Dictionary = models.luminous_male
	var record := _record(LOCAL, 7)
	var high := Closure.closure(record, "luminous_male", models, equipment, HIGH)
	var own := Closure.closure(record, "luminous_male", models, equipment, HIGH, {}, true)
	var head_files := ReplicatedActor3D.rl_head_files_for(config, record.appearance as Dictionary, HIGH)
	var hair := ReplicatedActor3D.hair_scene_for(config, 7)
	var face := RLHeadPortraitMap.face(record.appearance as Dictionary, str(config.get("gender", "female")))
	expect(not head_files.is_empty() and head_files == RLHeadLibrary.face_paths(face),
		"the RL head's own files for a portrait Human at High are its face's (head, hairstyle, beard): %s" % head_files)
	expect((high.rl_files as PackedStringArray).is_empty() and (own.rl_files as PackedStringArray) == head_files,
		"only the player's own closure (rl_head) names them; a remote's draws the classic head meanwhile")
	expect(own.scenes == high.scenes and (own.scenes as PackedStringArray).has(hair) and own.key != high.key,
		"the game hairstyle stays named (drawn where the RL head draws no module hair); the key differs")
	expect(Closure.closure(record, "luminous_male", models, equipment, MEDIUM, {}, true).rl_files
		== Closure.closure(record, "luminous_male", models, equipment, MEDIUM).rl_files
		and ReplicatedActor3D.rl_head_files_for(config, record.appearance as Dictionary, MEDIUM).is_empty(),
		"below High rl_head changes nothing (the RL hairstyle module only)")
	expect(ReplicatedActor3D.rl_head_files_for(models.votary_male, record.appearance as Dictionary, HIGH).is_empty()
		and ReplicatedActor3D.rl_head_files_for(config, {"rl_head": "lab"}, HIGH).is_empty(),
		"no RL head files for a race without portrait customization or for the lab's explicit face")
	Closure.clear_memo()
	var remote := Closure.memoized(record, "luminous_male", models, equipment, HIGH)
	var mine := Closure.memoized(record, "luminous_male", models, equipment, HIGH, {}, true)
	expect(not is_same(remote, mine) and is_same(Closure.memoized(record, "luminous_male", models, equipment,
		HIGH, {}, true), mine), "the memo keeps the player's own closure apart from a remote's")


# --- the preparer's local class -------------------------------------------------------------

func _check_local_class() -> void:
	_cold()
	var warmup = Warmup.new()
	# Remote files fill the publication queue inside one process frame (one is
	# published, the next two wait), without RL files.
	var remote := Closure.closure(_record(80), "luminous_male", models, equipment, MEDIUM)
	remote["rl_files"] = PackedStringArray()
	var own := Closure.closure(_record(LOCAL, 2, {"5": 185}, "Me", VOTARY_MALE), "votary_male",
		models, equipment, MEDIUM)
	var own_scenes: PackedStringArray = own.scenes
	var own_files := GlbSceneCache.missing(own_scenes) # canonical, as the jobs name them
	var overlap := false
	for path: String in own_scenes:
		overlap = overlap or (remote.scenes as PackedStringArray).has(path)
	expect(own_scenes.size() >= 2 and not overlap and (own.rl_files as PackedStringArray).is_empty(),
		"fixture: the player's files are not among the remote's: %s" % own_scenes)
	warmup.request_closure(remote, Warmup.PRIORITY_NEAR)
	var deadline := Time.get_ticks_msec() + DEADLINE_MSEC
	var outbox: Array = warmup.get("_outbox")
	while not (outbox.size() == Warmup.PUBLISH_QUEUE_LIMIT and warmup.get("_thread") == null) \
			and Time.get_ticks_msec() < deadline:
		OS.delay_msec(3)
		warmup.poll()
	expect(outbox.size() == Warmup.PUBLISH_QUEUE_LIMIT and warmup.get("_thread") == null,
		"fixture: %d remote roots await publication and the worker has stopped" % outbox.size())
	expect(not warmup.request_closure(own, Warmup.PRIORITY_LOCAL), "the player's closure is asked for")
	var active: Dictionary = warmup.get("_active_job")
	expect(warmup.get("_thread") != null and own_files.has(str(active.get("path", "")))
		and int(active.get("priority", -1)) == Warmup.PRIORITY_LOCAL
		and int(warmup.snapshot().localStartsPastLimit) == 1,
		"its first file starts at once, past the publication queue limit")
	while warmup.get("_thread") != null and Time.get_ticks_msec() < deadline:
		OS.delay_msec(3)
		warmup.poll()
	expect(outbox.size() == Warmup.PUBLISH_QUEUE_LIMIT + 1 and warmup.get("_thread") == null
		and int(warmup.snapshot().pendingLocalFiles) == own_scenes.size(),
		"one root more at most: with %d waiting the next local file waits too" % outbox.size())
	var first_local := str(active.get("path", ""))
	var published := int(warmup.snapshot().filesPublished)
	var remote_waiting := GlbSceneCache.missing(remote.scenes as PackedStringArray).size()
	while int(warmup.snapshot().filesPublished) == published and Time.get_ticks_msec() < deadline:
		await process_frame
		warmup.poll()
	expect(GlbSceneCache.missing(PackedStringArray([first_local])).is_empty()
		and GlbSceneCache.missing(remote.scenes as PackedStringArray).size() == remote_waiting
		and int(warmup.snapshot().localPublishedFirst) == 1,
		"the next publication is the player's root, before the remote roots that waited longer")
	var ready := await _pump(warmup, func() -> bool:
		return warmup.request_closure(own, Warmup.PRIORITY_LOCAL) and warmup.request_closure(remote) \
			and warmup.is_idle())
	var row: Dictionary = warmup.snapshot()
	expect(ready and int(row.fallbacks) == 0 and int(row.pendingLocalFiles) == 0
		and int(row.filesPublished) == own_scenes.size() + (remote.scenes as PackedStringArray).size(),
		"both closures are published in full, none left to main: %s %s" % [row, (warmup.get("_fallback") as Dictionary).keys()])


# --- Main ---------------------------------------------------------------------------------

func _setup_main() -> void:
	root.size = Vector2i(1280, 720)
	app = root.get_node("AppState")
	var network := root.get_node("Network")
	var recorder := GDScript.new()
	recorder.source_code = 'extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tsent_frames.append(frame)\n\treturn OK\n'
	expect(recorder.reload() == OK, "the isolated final-write recorder compiles")
	network.set_script(recorder)
	network.call("block_for_hud_preview")
	app.authenticated = false
	app.current_map = ""
	app.actors = {}
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	main.set_process(false)
	main.set_physics_process(false)
	await process_frame
	var floor := StaticBody3D.new()
	floor.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	var collision := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(600, 0.1, 600)
	collision.shape = box
	collision.position.y = -0.05
	floor.add_child(collision)
	main.world_root.add_child(floor)
	await physics_frame
	app.authenticated = true
	app.death = {}
	app.local_actor_id = LOCAL
	app.selected_actor_id = -1
	app.combat_state = {}
	app.campaign = {}
	app.current_map = "landfall"
	main.adapter = CoordinateAdapter.new({"walkingHeight": 0.025, "invertServerY": true})
	LookProfile.set_player_quality(MEDIUM)


func _curtain() -> CanvasLayer:
	return main.get("arrival_curtain") as CanvasLayer


func _prep() -> RefCounted:
	return main.get("_local_avatar_prep") as RefCounted


func _local() -> ReplicatedActor3D:
	var value: Variant = main.actor_nodes.get(LOCAL)
	return value as ReplicatedActor3D if is_instance_valid(value) else null


func _discard_local() -> void:
	var actor := _local()
	main.actor_nodes.erase(LOCAL)
	(main.get("_grounded_actors") as Dictionary).erase(LOCAL)
	if actor != null:
		actor.queue_free()
	await process_frame


## A fresh case: no player node, cold caches, an idle preparer, no wait.
func _fresh(curtained: bool) -> void:
	await _discard_local()
	var warmup: RefCounted = main.actor_resource_warmup
	warmup.call("clear")
	await _pump(warmup, func() -> bool: return bool(warmup.call("is_idle")))
	_cold()
	_prep().call("clear")
	main.set("_deferred_map_load", false)
	main.set("_arrival", {})
	if curtained:
		_curtain().call("begin", "Entering…")
	else:
		_curtain().call("cancel")


func _local_files_queued() -> int:
	var count := 0
	for job: Dictionary in (main.actor_resource_warmup.get("_files") as Dictionary).values():
		if int(job.priority) == Warmup.PRIORITY_LOCAL:
			count += 1
	return count


## Main's per-frame steps for the player's arrival, as `_process` runs them:
## the preparer's poll and publication, then the arrivals of the backlog.
func _arrive_until(done: Callable) -> bool:
	var deadline := Time.get_ticks_msec() + DEADLINE_MSEC
	while not bool(done.call()) and Time.get_ticks_msec() < deadline:
		main.set("_actor_creation_frame", -1)
		main.call("_update_model_builds")
		main.call("_spawn_arrivals", [LOCAL])
		if bool(done.call()):
			break
		await process_frame
	return bool(done.call())


func _mesh_signature(actor: ReplicatedActor3D) -> Dictionary:
	var out := {}
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := node as MeshInstance3D
		if mesh_node.mesh == null or not mesh_node.is_visible_in_tree():
			continue
		var surfaces: Array = []
		var mesh := mesh_node.mesh
		for surface: int in mesh.get_surface_count():
			var material := mesh_node.get_active_material(surface)
			var texture: Variant = null
			if material is BaseMaterial3D and (material as BaseMaterial3D).albedo_texture != null:
				var albedo := (material as BaseMaterial3D).albedo_texture
				texture = albedo.resource_path if not albedo.resource_path.is_empty() else albedo.get_size()
			surfaces.append([hash(mesh.surface_get_arrays(surface)) if mesh is ArrayMesh else 0,
				material.get_class() if material != null else "", texture])
		out[str(actor.get_path_to(mesh_node))] = [surfaces, mesh_node.skin.get_bind_count() if mesh_node.skin != null else 0]
	return out


func _check_curtained_cold_build() -> void:
	var me := _record(LOCAL)
	# Reference: the curtain down, main parses every file in the build (before).
	await _fresh(false)
	app.actors = {LOCAL: me}
	var misses := _misses()
	main.set("_actor_creation_frame", -1)
	var began := Time.get_ticks_usec()
	expect(bool(main.call("_spawn_actor", LOCAL, true)) and _local() != null,
		"with the curtain down the player's body is built at once, as before")
	var main_usec := Time.get_ticks_usec() - began
	var main_misses := _misses() - misses
	var main_phases := _local().configuration_timings_usec()
	await process_frame
	var reference := _mesh_signature(_local())
	expect(main_misses > 3 and _local_files_queued() == 0,
		"fixture: that build parsed its files on main (%d misses) and queued nothing for the worker" % main_misses)
	# Behind the curtain: no node while the worker parses, then the build.
	await _fresh(true)
	app.actors = {LOCAL: me}
	main.set("_actor_creation_frame", -1)
	var asked := Time.get_ticks_msec()
	main.call("_spawn_arrivals", [LOCAL])
	expect(_local() == null and bool(main.get("_spawn_backlog")),
		"behind the curtain a cold player's body is not built yet, and no stand-in is made for it")
	var closure: Dictionary = main.call("_local_closure", LOCAL, main.call("_presentation_dto", me))
	expect(_local_files_queued() > 0 and _local_files_queued() <= (closure.scenes as PackedStringArray).size()
		and bool(_prep().call("waiting")), "its files are queued at PRIORITY_LOCAL and its wait has begun")
	expect(not bool(main.call("_spawn_actor", LOCAL, true)) and _local() == null,
		"a direct build of it waits as well (the gate is in _spawn_actor)")
	var deadline := Time.get_ticks_msec() + DEADLINE_MSEC
	var ready := false
	while Time.get_ticks_msec() < deadline:
		main.call("_update_model_builds")
		ready = bool(main.call("_remote_model_ready", LOCAL))
		if ready:
			break
		await process_frame
	var waited := Time.get_ticks_msec() - asked
	expect(ready and _local() == null, "its closure becomes ready while it has no node")
	misses = _misses()
	main.set("_actor_creation_frame", -1)
	began = Time.get_ticks_usec()
	var built := bool(main.call("_spawn_actor", LOCAL, true)) and _local() != null
	var prepared_usec := Time.get_ticks_usec() - began
	expect(built and not _local().is_model_deferred(), "then the player's body is built")
	expect(_misses() - misses == 0, "its configure() found every scene cached: no main-thread glTF parse")
	var phases := _local().configuration_timings_usec()
	var row: Dictionary = main.call("client_diagnostic_snapshot")
	var prep_row: Dictionary = row.get("local_avatar_prep", {})
	expect(int((prep_row.get("outcomes", {}) as Dictionary).get("ready", 0)) == 1 and not bool(prep_row.waiting)
		and int(prep_row.lastWaitMsec) >= 0 and int((row.actor_preparer as Dictionary).filesPublished) > 0,
		"the diagnostics snapshot carries the wait (local_avatar_prep): %s" % prep_row)
	await process_frame
	var signature := _mesh_signature(_local())
	expect(not signature.is_empty() and signature == reference,
		"it equals the body main's own parses built: the same %d visible meshes, geometry, materials, textures"
		% signature.size())
	print(("TIMING local Human (Medium, 7 pieces): closure ready %d ms after the first ask behind the curtain; "
		% waited) + ("_spawn_actor %.1f ms main-parsed (model_scene %.1f, equipment %.1f, %d misses) -> %.1f ms prepared "
		% [main_usec / 1000.0, int(main_phases.get("model_scene", 0)) / 1000.0,
			int(main_phases.get("equipment", 0)) / 1000.0, main_misses, prepared_usec / 1000.0])
		+ ("(model_scene %.1f, equipment %.1f) (headless)" % [int(phases.get("model_scene", 0)) / 1000.0,
			int(phases.get("equipment", 0)) / 1000.0]))


func _check_early_request() -> void:
	var me := _record(LOCAL, 4, {"0": 165, "3": 117, "5": 184})
	await _fresh(true)
	# A change of map waiting for the curtain (TR-01); the player's ADD is in.
	main.set("_deferred_map_load", true)
	app.actors = {LOCAL: me}
	main.call("_sync_world")
	expect(_local() == null and _local_files_queued() > 0 and int(_prep().get("early_requests")) == 1,
		"the held world sync asks for the player's closure at PRIORITY_LOCAL as soon as the record is known")
	main.call("_sync_world")
	expect(int(_prep().get("early_requests")) == 1 and not bool(_prep().call("waiting")),
		"asking again is counted once, and no wait has begun: the body is not wanted yet")
	var warmup: RefCounted = main.actor_resource_warmup
	var closure: Dictionary = main.call("_local_closure", LOCAL, main.call("_presentation_dto", me))
	var ready := await _pump(warmup, func() -> bool:
		return bool(warmup.call("request_closure", closure, Warmup.PRIORITY_LOCAL)))
	expect(ready, "the worker prepares it while the world would be built")
	main.set("_deferred_map_load", false)
	var at_once := int(_prep().get("built_at_once"))
	var waits := int(_prep().get("waits"))
	var misses := _misses()
	main.set("_actor_creation_frame", -1)
	main.call("_spawn_arrivals", [LOCAL])
	expect(_local() != null and _misses() - misses == 0 and int(_prep().get("built_at_once")) == at_once + 1
		and int(_prep().get("waits")) == waits,
		"so once the map is there the body is built at its first ask: no wait, no main-thread parse")


func _check_curtain_waits_for_the_body() -> void:
	await _fresh(true)
	app.actors = {LOCAL: _record(LOCAL, 6, {"0": 114, "4": 171, "5": 185})}
	# The arrival's ground is resident (no stream), so only the body is awaited.
	main.set("_arrival", {"position": Vector3.ZERO, "started": Time.get_ticks_msec(), "ready": true})
	var lowered_early := false
	var built := false
	var deadline := Time.get_ticks_msec() + DEADLINE_MSEC
	while Time.get_ticks_msec() < deadline:
		main.set("_actor_creation_frame", -1)
		main.call("_update_model_builds")
		main.call("_spawn_arrivals", [LOCAL])
		main.call("_update_arrival")
		if _local() == null and (main.get("_arrival") as Dictionary).is_empty():
			lowered_early = true
			break
		if _local() != null:
			built = true
			break
		await process_frame
	expect(built and not lowered_early, "the curtain stays up while the player's body waits for its files")
	deadline = Time.get_ticks_msec() + 10000
	while not (main.get("_arrival") as Dictionary).is_empty() and Time.get_ticks_msec() < deadline:
		await physics_frame
		main.call("_place_actor_on_surface", _local(), true, 0.0)
		main.call("_update_arrival")
		await process_frame
	expect((main.get("_arrival") as Dictionary).is_empty() and not bool(_curtain().call("blocks_input")),
		"and lowers once the body stands on its ground")


func _check_timeout() -> void:
	await _fresh(true)
	# A preparer that never has the files (it parses nothing and never answers
	# ready): the body is built when its wait reaches the default deadline.
	var stub := GDScript.new()
	stub.source_code = 'extends "res://src/actors/actor_resource_warmup.gd"\nfunc request_closure(_closure: Dictionary, _priority := PRIORITY_NEAR) -> bool:\n\treturn false\n'
	expect(stub.reload() == OK, "the stalled preparer stub compiles")
	var previous: RefCounted = main.actor_resource_warmup
	main.actor_resource_warmup = stub.new()
	app.actors = {LOCAL: _record(LOCAL, 3, {"0": 114})}
	var asked := Time.get_ticks_msec()
	var misses := _misses()
	var built := await _arrive_until(func() -> bool: return _local() != null)
	var waited := Time.get_ticks_msec() - asked
	var reported := int(_prep().get("last_wait_msec"))
	print("TIMING stalled preparer: build released %d ms after the first ask, body built %d ms after it" % [reported, waited])
	expect(built and reported >= Prep.TIMEOUT_MSEC and reported < Prep.TIMEOUT_MSEC + 500,
		"a preparer that never finishes: the body is built at the 6 s deadline (released after %d ms)" % reported)
	expect(_misses() - misses > 0 and int((_prep().get("outcomes") as Dictionary).get("timeout", 0)) == 1,
		"by main's own parses, as before, with the timeout counted")
	main.actor_resource_warmup = previous


func _check_failed_files() -> void:
	await _fresh(true)
	# The worker could not prepare any of the player's files (error records,
	# stale stamps, a failed thread start all end in its fallback).
	var me := _record(LOCAL, 2, {"0": 114, "4": 171}, "Me", VOTARY_MALE)
	app.actors = {LOCAL: me}
	var closure: Dictionary = main.call("_local_closure", LOCAL, main.call("_presentation_dto", me))
	var fallback: Dictionary = main.actor_resource_warmup.get("_fallback")
	for path: String in (closure.scenes as PackedStringArray):
		fallback[GlbSceneCache._canonical_path(path)] = true
	expect((closure.rl_files as PackedStringArray).is_empty() and (closure.scenes as PackedStringArray).size() >= 2,
		"fixture: a votary closure without RL files")
	var misses := _misses()
	var waits := int(_prep().get("waits"))
	main.set("_actor_creation_frame", -1)
	main.call("_spawn_arrivals", [LOCAL])
	expect(_local() != null and _misses() - misses > 0 and int(_prep().get("waits")) == waits,
		"files the worker could not prepare: the body is built at once from main's parses, as before")


func _check_built_at_once() -> void:
	# The curtain down: nothing queued, built at once.
	await _fresh(false)
	app.actors = {LOCAL: _record(LOCAL, 5)}
	var requests := int(main.actor_resource_warmup.snapshot().closureRequests)
	expect(bool(main.call("_remote_model_ready", LOCAL)) and _local_files_queued() == 0
		and int(main.actor_resource_warmup.snapshot().closureRequests) == requests,
		"with the curtain down the player's body is ready at once and nothing is asked of the worker")
	# The kill switch.
	await _fresh(true)
	OS.set_environment(Warmup.SWITCH_ENVIRONMENT, "off")
	var previous: RefCounted = main.actor_resource_warmup
	main.actor_resource_warmup = Warmup.new()
	app.actors = {LOCAL: _record(LOCAL, 5)}
	main.set("_actor_creation_frame", -1)
	main.call("_spawn_arrivals", [LOCAL])
	expect(_local() != null and int(main.actor_resource_warmup.snapshot().closureRequests) == 0,
		"with ELORIA_ACTOR_PREPARER=off it is built at once behind the curtain, nothing asked of the worker")
	OS.unset_environment(Warmup.SWITCH_ENVIRONMENT)
	main.actor_resource_warmup = previous


func _check_session_end() -> void:
	await _fresh(true)
	app.actors = {LOCAL: _record(LOCAL, 8)}
	main.set("_actor_creation_frame", -1)
	main.call("_spawn_arrivals", [LOCAL])
	expect(bool(_prep().call("waiting")), "fixture: the player's body waits")
	main.call("_clear_world_presentation", true)
	expect(not bool(_prep().call("waiting")), "a session's end ends the wait")


## A change of map that overtakes the wait (KILL_ALL_ACTORS took the record
## before the body was built) must not hand the old wait's deadline to the next
## arrival: without the reset an old enough wait made the next ADD's first ask
## a timeout, and its body was built at once from main's parses.
func _check_map_change_abandons() -> void:
	await _fresh(true)
	var me := _record(LOCAL, 8, {"0": 114, "5": 185})
	app.actors = {LOCAL: me}
	main.set("_actor_creation_frame", -1)
	main.call("_spawn_arrivals", [LOCAL])
	expect(_local() == null and bool(_prep().call("waiting")), "fixture: the player's body waits behind the curtain")
	# That wait began 7 s ago (past the deadline), and was then overtaken.
	_prep().set("_since", Time.get_ticks_msec() - 7000)
	var abandoned := int((_prep().get("outcomes") as Dictionary).get("abandoned", 0))
	app.actors = {}
	main.set("_continuous_map_handoff", false)
	main.set("_retained_traveller", -1)
	main.call("_clear_actor_nodes_for_map_change")
	expect(not bool(_prep().call("waiting"))
		and int((_prep().get("outcomes") as Dictionary).get("abandoned", 0)) == abandoned + 1,
		"a change of map ends a wait whose body was never built (outcome abandoned)")
	# The next map's ADD, its files still cold: it waits from its own first ask.
	main.actor_resource_warmup.clear()
	await _pump(main.actor_resource_warmup, func() -> bool: return bool(main.actor_resource_warmup.is_idle()))
	_cold()
	app.actors = {LOCAL: me}
	main.set("_actor_creation_frame", -1)
	main.call("_spawn_arrivals", [LOCAL])
	var row: Dictionary = _prep().call("snapshot")
	expect(_local() == null and bool(row.waiting) and int(row.waitingForMsec) < Prep.TIMEOUT_MSEC,
		"the next arrival's body waits for its closure from its own first ask, not the old deadline: %s" % row)


func _check_held_body() -> void:
	# AW-02: the body held across a change of map is worn again by the ADD
	# behind the curtain without waiting, even with every cache cleared.
	await _fresh(false)
	var me := _record(LOCAL, 2, {"0": 114, "4": 171})
	app.actors = {LOCAL: me}
	main.set("_actor_creation_frame", -1)
	main.call("_spawn_actor", LOCAL, true)
	var first := _local()
	await physics_frame
	main.set("_continuous_map_handoff", false)
	main.set("_retained_traveller", -1)
	main.call("_clear_actor_nodes_for_map_change")
	expect(first != null and is_instance_valid(first) and _local() == null
		and bool((main.get("_local_avatar_hold") as RefCounted).call("holding")), "fixture: the player's body is held")
	main.actor_resource_warmup.clear()
	_cold()
	_curtain().call("begin", "Entering…")
	app.actors = {LOCAL: me}
	main.set("_actor_creation_frame", -1)
	expect(bool(main.call("_remote_model_ready", LOCAL)) and _local_files_queued() == 0,
		"the held body is ready at once: nothing is queued")
	main.call("_spawn_arrivals", [LOCAL])
	expect(_local() == first and not bool(_prep().call("waiting")), "the ADD wears the held body again at once")


func _check_high_rl_head() -> void:
	LookProfile.set_player_quality(HIGH)
	var deferral := RLHeadLibrary.deferred_loading
	# As in a window: the game defers RL loading, and the player's RL head is
	# drawn at once from files parsed ahead.
	RLHeadLibrary.deferred_loading = 1
	await _fresh(true)
	var me := _record(LOCAL, 7, {"0": 164, "4": 171, "5": 185})
	app.actors = {LOCAL: me}
	var closure: Dictionary = main.call("_local_closure", LOCAL, main.call("_presentation_dto", me))
	var head_files := ReplicatedActor3D.rl_head_files_for(models.luminous_male, me.appearance as Dictionary, HIGH)
	expect(not head_files.is_empty() and (closure.rl_files as PackedStringArray) == head_files,
		"at High the player's own closure names its RL head's files: %s" % head_files)
	var rl_waits := int(main.actor_resource_warmup.snapshot().rlWaits)
	main.set("_actor_creation_frame", -1)
	main.call("_spawn_arrivals", [LOCAL])
	expect(_local() == null and int(main.actor_resource_warmup.snapshot().rlWaits) > rl_waits,
		"it waits, its RL files asked of RLHeadLibrary's worker")
	var misses := _misses()
	var began := Time.get_ticks_msec()
	var built := await _arrive_until(func() -> bool: return _local() != null)
	print("TIMING local Human at High (RL head) behind the curtain: built %d ms after its first ask (headless)"
		% (Time.get_ticks_msec() - began))
	expect(built and _misses() - misses == 0 and GlbSceneCache.missing(head_files).is_empty(),
		"then it is built with no main-thread glTF parse, its RL head's files among the cached")
	expect(_local().get("_rl_head") != null, "and it draws its RL head")
	RLHeadLibrary.deferred_loading = deferral
	LookProfile.set_player_quality(MEDIUM)


func _cleanup() -> void:
	_curtain().call("cancel")
	RLHeadLibrary.cancel_warm()
	while RLHeadLibrary.warming():
		await process_frame
	if main != null:
		main.actor_resource_warmup.clear()
		await _pump(main.actor_resource_warmup, func() -> bool: return main.actor_resource_warmup.is_idle())
		main.call("_clear_world_presentation")
		main.queue_free()
		await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	ReplicatedActor3D.clear_static_caches()
