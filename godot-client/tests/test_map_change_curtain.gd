extends SceneTree
## TR-01: a change of map that is not a seamless crossing happens behind the
## arrival curtain, and an arrival off a territory's cells neither re-primes
## nor waits out the curtain's limit.
##
##   * MapChangeCurtain's bookkeeping on its own, and its handoff judgement
##     against ExteriorRegionStream.take_ready's own on seam fixtures.
##   * ContinentChunkStream: a position no cell covers is off the map - no
##     re-prime, no orphaned worker, logged once per stretch - while a covered
##     position whose cell is missing still re-primes.
##   * Main's real pipeline (main.tscn, a recorded transport) on fixture maps
##     written to user://: a streamed territory, a whole map, a resident
##     neighbour reached without a crossing, a respawn's and a gauntlet exit's
##     prewarmed ground each wait until the curtain is drawn and are then
##     loaded or adopted; the prewarm survives the death state cleared while it
##     waits; the local RL head is prewarmed for a whole map only; a drawn
##     curtain, a seamless crossing and a door go ahead at once; a character
##     built behind the curtain with no ground asks for its neighbours after
##     the grace, and nothing else does.
##   * Review fixes: a curtain raised only to adopt prepared ground skips the
##     Compatibility camera warm-up (that arrival had none before TR-01); a
##     wait the server takes back before the curtain is drawn is forgotten.
##
##   Godot --headless --path godot-client --script res://tests/test_map_change_curtain.gd

const CURTAIN := preload("res://src/world/map_change_curtain.gd")
const SCRATCH := "user://map-change-curtain-test"
const LOCAL := 1
const MEDIUM := ActorRenderQuality.Quality.MEDIUM
const TRANSFORM := {"metresPerTile": 1, "serverOrigin": [0, 40], "origin": [0, 0, 0],
	"walkingHeight": 0, "invertServerY": true, "serverCells": [1400, 80]}

var checks := 0
var failures := 0
var main: Node
var app: Node
var network: Node


func _init() -> void:
	run.call_deferred()


func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("map change curtain: " + message)


func run() -> void:
	create_timer(300).timeout.connect(func() -> void:
		push_error("map change curtain timed out")
		quit(1))
	_check_bookkeeping()
	_check_handoff_judgement()
	DirAccess.make_dir_recursive_absolute(SCRATCH)
	_write_fixture()
	await _check_off_map_reprime()
	await _setup_main()
	var old_quality := LookProfile.player_quality()
	LookProfile.set_player_quality(MEDIUM)
	await _check_drawn_curtain_loads_at_once()
	await _check_streamed_waits()
	await _check_whole_map_waits()
	await _check_exterior_waits()
	await _check_respawn_prewarm_waits()
	await _check_gauntlet_prewarm_waits()
	_check_uncurtained_kinds()
	await _check_abandoned_wait()
	await _check_fading_curtain_handoff()
	_check_grounding_wait()
	LookProfile.set_player_quality(old_quality)
	await _cleanup()
	print("map change curtain: %d checks, %d failures" % [checks, failures])
	quit(1 if failures > 0 else 0)


# --- MapChangeCurtain on its own ----------------------------------------------

func _check_bookkeeping() -> void:
	var curtain = CURTAIN.new()
	expect(curtain.pending.is_empty() and not curtain.short_wait()
		and (curtain.snapshot(0).pending as Dictionary).is_empty(), "nothing waits at first")
	expect(curtain.defer("a", CURTAIN.EXTERIOR, Vector3(1, 2, 3), 100) and curtain.short_wait()
		and curtain.waiting_for(CURTAIN.EXTERIOR, "a") and not curtain.waiting_for(CURTAIN.PREWARM, "a")
		and not curtain.waiting_for(CURTAIN.EXTERIOR, "b") and not curtain.waiting_for(CURTAIN.EXTERIOR, ""),
		"a waiting exterior handoff is known by its kind and map")
	expect(not curtain.defer("a", CURTAIN.EXTERIOR, Vector3.ZERO, 120)
		and int(curtain.deferrals.get("exterior", 0)) == 1 and curtain.pending.focus == Vector3(1, 2, 3),
		"the same change asked again is not counted twice and keeps its first focus")
	expect(curtain.handoff_focus("a", Vector3.ZERO) == Vector3(1, 2, 3)
		and curtain.handoff_focus("b", Vector3(9, 9, 9)) == Vector3(9, 9, 9),
		"the exterior handoff is judged from where the camera stood at CHANGE_MAP")
	var snapshot: Dictionary = curtain.snapshot(150)
	expect(str(snapshot.pending.kind) == "exterior" and int(snapshot.pending.waited_ms) == 50,
		"the snapshot names the waiting change and how long it waited: %s" % snapshot)
	curtain.resumed(180)
	expect(curtain.pending.is_empty() and curtain.last_wait == {"map": "a", "kind": "exterior", "msec": 80},
		"the change goes ahead and its wait is recorded")
	curtain.resumed(190)
	expect(curtain.last_wait.msec == 80, "a load that did not wait records nothing")
	curtain.defer("w", CURTAIN.WHOLE_MAP, Vector3.INF, 200)
	expect(not curtain.short_wait() and curtain.handoff_focus("w", Vector3.ONE) == Vector3.ONE,
		"a whole map is a long wait (its RL head is prewarmed) and judges no handoff")
	curtain.defer("p", CURTAIN.PREWARM, Vector3.INF, 210)
	expect(curtain.short_wait() and curtain.waiting_for(CURTAIN.PREWARM, "p")
		and curtain.handoff_focus("p", Vector3.ONE) == Vector3.ONE, "a prewarm is a short wait")
	curtain.defer("s", CURTAIN.STREAMED, Vector3.INF, 220)
	expect(curtain.short_wait() and not curtain.waiting_for(CURTAIN.PREWARM, "p"),
		"a streamed territory is a short wait; a newer change replaces the older")
	curtain.clear()
	expect(curtain.pending.is_empty() and not curtain.short_wait()
		and curtain.deferrals == {"exterior": 1, "whole_map": 1, "prewarm": 1, "streamed": 1},
		"clear forgets the waiting change and keeps the counters: %s" % curtain.deferrals)
	var grace: int = CURTAIN.GROUNDING_GRACE_MSEC
	expect(not curtain.grounding_due(true, 1000) and not curtain.grounding_due(true, 1000 + grace - 1),
		"an ungrounded arrival waits out the grace first")
	expect(curtain.grounding_due(true, 1000 + grace) and curtain.grounding_first
		and curtain.grounding_waits == 1 and curtain.grounding_updates == 1, "then it asks for its neighbours")
	expect(curtain.grounding_due(true, 1000 + grace + 16) and not curtain.grounding_first
		and curtain.grounding_waits == 1 and curtain.grounding_updates == 2,
		"and keeps asking each frame, counted as one wait")
	expect(not curtain.grounding_due(false, 5000) and not curtain.grounding_due(true, 5000),
		"a grounded arrival forgets it; the next one starts its own grace")
	expect(curtain.grounding_due(true, 5000 + grace) and curtain.grounding_waits == 2,
		"the next wait is counted on its own")
	curtain.clear()
	expect(not curtain.grounding_due(true, 9000), "clear forgets a grounding wait")
	snapshot = curtain.snapshot(9000)
	expect(int(snapshot.grounding_waits) == 2 and int(snapshot.grounding_updates) == 3,
		"the snapshot counts grounding waits and updates: %s" % snapshot)
	_check_warmup_exemption()


## Review fix: a curtain raised only so that prepared ground is adopted out of
## sight skips the Compatibility camera warm-up (none ran there before TR-01);
## anything that needed the curtain before TR-01 keeps it.
func _check_warmup_exemption() -> void:
	var curtain = CURTAIN.new()
	curtain.defer("a", CURTAIN.EXTERIOR, Vector3.ONE, 0, true)
	curtain.resumed(10, "a", true)
	expect(curtain.warmup_exempt and curtain.skips_warmup() and curtain.skips_warmup()
		and curtain.warmups_skipped == 1, "a raised exterior handoff skips the warm-up, counted once")
	curtain.end_warmup_exemption()
	expect(not curtain.warmup_exempt and not curtain.skips_warmup() and curtain.warmups_skipped == 1,
		"an arrival that loads its cells, or a curtain gone, ends the exemption")
	curtain.defer("p", CURTAIN.PREWARM, Vector3.INF, 20, true)
	curtain.resumed(30, "p", true)
	expect(curtain.warmup_exempt, "a raised prewarm adoption skips the warm-up")
	curtain.defer("p", CURTAIN.PREWARM, Vector3.INF, 40, true)
	curtain.resumed(50, "p", false)
	expect(not curtain.warmup_exempt, "a prewarm wait that ends in a fresh load does not")
	curtain.defer("a", CURTAIN.EXTERIOR, Vector3.ONE, 60, false)
	curtain.resumed(70, "a", true)
	expect(not curtain.warmup_exempt, "nor a handoff behind a curtain that was already up")
	curtain.defer("s", CURTAIN.STREAMED, Vector3.INF, 80, true)
	curtain.resumed(90, "s", true)
	expect(not curtain.warmup_exempt, "nor a streamed territory (curtained before TR-01)")
	curtain.defer("a", CURTAIN.EXTERIOR, Vector3.ONE, 100, true)
	curtain.resumed(130, "b", true)
	expect(not curtain.warmup_exempt and str(curtain.last_wait.map) == "s",
		"another map going ahead neither inherits the exemption nor records the wait as its own")
	curtain.defer("a", CURTAIN.EXTERIOR, Vector3.ONE, 140, true)
	curtain.resumed(150, "a", true)
	curtain.defer("c", CURTAIN.WHOLE_MAP, Vector3.INF, 160)
	curtain.abandon()
	expect(curtain.pending.is_empty() and curtain.warmup_exempt,
		"an abandoned wait is forgotten and leaves the arrival on screen as it was")
	curtain.resumed(170, "f", false, true)
	expect(not curtain.warmup_exempt, "a fresh load never skips it")
	curtain.resumed(180, "f", true, true)
	expect(curtain.warmup_exempt and str(curtain.last_wait.map) == "a",
		"prepared ground that raised the curtain on the call that takes it (a fading curtain counts as drawn) skips it")
	curtain.resumed(190, "f", true, false)
	expect(not curtain.warmup_exempt, "behind a curtain that was already up it does not")
	curtain.clear()
	expect(not curtain.warmup_exempt and not bool(curtain.snapshot(0).warmup_exempt)
		and int(curtain.snapshot(0).warmups_skipped) == 1, "clear ends the exemption; the snapshot reports it")


## One link between "here" (the active map) and "there".
func _seam_stream(seamless: bool, edges: Array, collar: float) -> ExteriorRegionStream:
	var stream := ExteriorRegionStream.new()
	stream.active_map = "here"
	var here := {"map": "here", "position": [0, 0, 0], "frame": {"id": "here_frame",
		"anchor": [0, 0, 0], "outward": [0, -1], "viewHalfWidth": 240, "collarDepth": collar}}
	if not edges.is_empty():
		here["preloadEdges"] = edges
	var there := {"map": "there", "position": [0, 0, 0], "frame": {"id": "there_frame",
		"anchor": [0, 0, 0], "outward": [0, 1], "viewHalfWidth": 240, "collarDepth": collar}}
	stream.links = [{"seamless": seamless, "ends": [here, there]}]
	return stream


## MapChangeCurtain.handoff_continuous against what take_ready then does.
func _check_handoff_judgement() -> void:
	var border := [[[-150, 0], [150, 0]]]
	var cases := [
		[true, border, 2.0, Vector3(120, 0, 3), true, "3 m off a shipped border, far along it"],
		[true, border, 2.0, Vector3(0, 0, -5), true, "5 m on the other side of the border"],
		[true, border, 2.0, Vector3(0, 0, 20), false, "20 m from the border"],
		[true, [], 42.0, Vector3(0, 0, 30), true, "inside a legacy 42 m collar from the anchor"],
		[true, [], 2.0, Vector3(120, 0, 3), false, "a link without a border, far along its flank"],
		[false, border, 42.0, Vector3(0, 0, 1), false, "a link that is not seamless"],
	]
	for row: Array in cases:
		var stream := _seam_stream(bool(row[0]), row[1] as Array, float(row[2]))
		var arriving := Node3D.new()
		stream.residents["there"] = {"root": arriving}
		var judged := CURTAIN.handoff_continuous(stream, "there", row[3] as Vector3)
		var loader := WorldLoader.new()
		var old := Node3D.new()
		loader.add_child(old)
		loader.world_root = old
		var taken: Dictionary = stream.take_ready("there", loader, row[3] as Vector3)
		expect(not taken.is_empty() and bool(taken.continuous) == judged and judged == bool(row[4]),
			"handoff judged as take_ready does it: %s (continuous=%s)" % [row[5], judged])
		loader.free() # and `old`, its child either way (take_ready never detaches it)
		arriving.free()
		stream.free()
	var empty := _seam_stream(true, border, 2.0)
	expect(not CURTAIN.handoff_continuous(empty, "there", Vector3(0, 0, 1))
		and empty.take_ready("there", null, Vector3(0, 0, 1)).is_empty(),
		"a map that is not resident is no handoff")
	expect(not CURTAIN.handoff_continuous(null, "there", Vector3.ZERO), "no stream, no handoff")
	empty.free()


# --- Fixture maps ---------------------------------------------------------------

func _write_json(path: String, data: Dictionary) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(data))
	file.close()


func _manifest(identity: String) -> Dictionary:
	return {"schemaVersion": "1.0.0", "asset": {"id": identity, "name": identity,
		"glb": "world.glb", "units": "meters", "origin": [0, 0, 0],
		"coordinateSystem": {"upAxis": "Y", "northAxis": "-Z", "handedness": "right"},
		"bounds": {"min": [-32, 0, -32], "max": [1300, 10, 32]}, "serverCells": [1400, 80]},
		"coordinateTransform": TRANSFORM.duplicate(true),
		"spawnPoints": [{"id": "default", "position": [0, 0, 0]}],
		"collision": {"nodeNames": []}, "navigation": {"surfaceNodePrefixes": ["Terrain_"]}}


## A chunk: an independent whole-map package with one 64 m ground plane at `x`.
func _write_chunk(identity: String, x: float) -> Dictionary:
	var directory := SCRATCH.path_join(identity)
	DirAccess.make_dir_recursive_absolute(directory)
	var stage := Node3D.new()
	var ground := MeshInstance3D.new()
	ground.name = "Terrain_" + identity
	var mesh := PlaneMesh.new()
	mesh.size = Vector2(64, 64)
	ground.mesh = mesh
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(0.3, 0.55, 0.2, 1)
	mesh.material = material
	ground.position.x = x
	stage.add_child(ground)
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	expect(doc.append_from_scene(stage, state) == OK
		and doc.write_to_filesystem(state, directory.path_join("world.glb")) == OK,
		"fixture chunk %s writes" % identity)
	stage.free()
	_write_json(directory.path_join("world.json"), _manifest("fixture_" + identity))
	return {"id": identity, "manifest": identity + "/world.json",
		"bounds": {"min": [x - 32, 0, -32], "max": [x + 32, 1, 32]}, "estimatedResidentBytes": 50}


func _write_fixture() -> void:
	var chunks: Array = [_write_chunk("west", 0), _write_chunk("near", 64), _write_chunk("east", 1200)]
	var review := FileAccess.open(SCRATCH.path_join("world.glb"), FileAccess.WRITE)
	review.store_string("Review export deliberately unavailable to runtime GLB parser")
	review.close()
	for spec: Array in [["territory.json", 1000], ["reprime.json", 60]]:
		var data := _manifest("fixture_" + str(spec[0]).get_basename())
		data.streamingChunks = {"schemaVersion": "1.0", "coordinateSpace": "territory-local",
			"preloadDistance": 240, "retainDistance": 320, "maximumLoadedChunks": 8,
			"maximumResidentBytes": int(spec[1]), "chunks": chunks.duplicate(true)}
		_write_json(SCRATCH.path_join(str(spec[0])), data)


func _events(stream: ContinentChunkStream, kind: String) -> int:
	return stream.events.filter(func(row: Dictionary) -> bool: return str(row.event) == kind).size()


# --- ContinentChunkStream: off-map positions ------------------------------------

func _check_off_map_reprime() -> void:
	var loader := WorldLoader.new()
	root.add_child(loader)
	loader.load_world(SCRATCH.path_join("reprime.json"), Vector3.INF, true)
	var stream := loader.world_root as ContinentChunkStream
	expect(stream != null, "the reprime fixture is a streamed territory")
	if stream == null:
		loader.queue_free()
		return
	expect(stream.covers(Vector3.ZERO) and stream.covers(Vector3(70, 0, 0))
		and not stream.covers(Vector3(600, 0, 0)) and stream.covers(Vector3(1200, 0, 10))
		and not stream.covers(Vector3(0, 0, 45)), "covers: a position inside some cell's bounds")
	expect(loader.ensure_chunk_arrival(Vector3.ZERO) and stream.cells.has("west")
		and not stream.cells.has("near"), "the first arrival primes the cell under it, the budget keeps the next")
	stream._next_update = 0
	stream.update_focus(Vector3.ZERO)
	var worker: Thread = stream._thread
	expect(worker != null, "the framed neighbour beyond the budget imports on a worker")
	var reprimes := _events(stream, "arrival_reprime")
	expect(not loader.ensure_chunk_arrival(Vector3(600, 0, 0)), "a position no cell covers asks for no re-prime")
	expect(stream._thread == worker and _events(stream, "orphaned") == 0
		and _events(stream, "arrival_reprime") == reprimes and stream.cells.has("west")
		and stream.focus == Vector3.ZERO,
		"its ground, its focus and the worker importing for it are left alone")
	expect(not loader.ensure_chunk_arrival(Vector3(610, 0, 0)) and _events(stream, "arrival_off_map") == 1,
		"standing off the map is logged once, not on every actor update")
	expect(not loader.ensure_chunk_arrival(Vector3.ZERO) and not loader.ensure_chunk_arrival(Vector3(600, 0, 0))
		and _events(stream, "arrival_off_map") == 2, "a new stretch off the map is logged again")
	var deadline := Time.get_ticks_msec() + 30000
	while stream._thread != null and Time.get_ticks_msec() < deadline:
		await process_frame
	expect(stream._thread == null and stream.cells.has("near"), "the neighbour's import completes")
	expect(loader.ensure_chunk_arrival(Vector3(1200, 0, 0)) and stream.cells.has("east")
		and _events(stream, "arrival_reprime") == reprimes + 1,
		"a covered destination whose cell is missing still re-primes, as before")
	stream.pause_streaming()
	expect(await ContinentChunkStream.drain_workers(self, 30000), "the fixture's workers drain")
	loader.queue_free()
	await process_frame


# --- Main ---------------------------------------------------------------------

func _setup_main() -> void:
	root.size = Vector2i(1280, 720)
	app = root.get_node("AppState")
	network = root.get_node("Network")
	# Actual Network validation and Main's signal wiring; only the final
	# socket write is replaced, so this process cannot contact a service.
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
	app.authenticated = true
	app.death = {}
	app.gauntlet_loot = {}
	app.local_actor_id = LOCAL
	app.selected_actor_id = -1
	app.combat_state = {}
	app.campaign = {}
	var registry: Dictionary = main.get("map_registry")
	for map_id: String in ["tr01_land", "tr01_vale"]:
		registry[map_id] = {"manifest": SCRATCH.path_join("territory.json"), "coordinateTransform": TRANSFORM}
	registry["tr01_room"] = {"manifest": SCRATCH.path_join("west/world.json"), "coordinateTransform": TRANSFORM}


func _curtain() -> CanvasLayer:
	return main.get("arrival_curtain") as CanvasLayer


func _loader() -> WorldLoader:
	return main.get("world_loader") as WorldLoader


func _record() -> Dictionary:
	return {"actor_id": LOCAL, "actor_type": 1, "kind": 1, "name": "Traveller", "map": app.current_map,
		"x": 10, "y": 40, "rotation": 0, "health": 20, "max_health": 20, "alive": true,
		"appearance": {"skin": 2, "hair": AppearanceVariants.pack_hair(2, 0)},
		"equipment_visuals": {}, "equipment_fallback_parts": []}


func _waiting() -> Dictionary:
	return (main.get("_map_change_curtain").pending as Dictionary)


func _deferrals(kind: String) -> int:
	return int((main.get("_map_change_curtain").deferrals as Dictionary).get(kind, 0))


## Clears any arrival before the next case: the curtain down, nothing waiting.
func _settle() -> void:
	main.call("_end_arrival")
	app.actors = {}
	await process_frame


## Frames until the curtain has been drawn, then Main's arrival pass (what its
## _process would run) loads the waiting change.
func _draw_curtain_and_resume() -> void:
	var curtain := _curtain()
	for frame: int in 10:
		if bool(curtain.call("has_drawn")):
			break
		await process_frame
	expect(bool(curtain.call("has_drawn")), "the curtain is drawn within a few frames")
	main.call("_update_arrival")


## The RL head prewarm key `_sync_world` leaves while the change waits.
func _rl_prewarm_during_wait() -> int:
	main.set("_local_rl_prewarm_key", 0)
	app.actors = {LOCAL: _record()}
	main.call("_sync_world")
	app.actors = {}
	return int(main.get("_local_rl_prewarm_key"))


func _check_drawn_curtain_loads_at_once() -> void:
	var curtain := _curtain()
	curtain.call("begin", "Signing in…")
	for frame: int in 10:
		if bool(curtain.call("has_drawn")):
			break
		await process_frame
	app.current_map = "tr01_land"
	main.call("_load_server_map")
	expect(str(main.get("loaded_server_map")) == "tr01_land" and not bool(main.get("_deferred_map_load"))
		and _loader().world_root is ContinentChunkStream and _deferrals("streamed") == 0,
		"behind a curtain already drawn (signing in) a streamed territory loads at once")
	await _settle()


func _check_streamed_waits() -> void:
	app.current_map = "tr01_vale"
	var before_root: Node = _loader().world_root
	main.call("_load_server_map")
	var curtain := _curtain()
	expect(bool(main.get("_deferred_map_load")) and str(main.get("loaded_server_map")) == "tr01_land"
		and _loader().world_root == before_root and bool(curtain.call("is_showing"))
		and not bool(curtain.call("has_drawn")),
		"a streamed territory waits for the curtain: shown at once, nothing loaded yet")
	expect(str(_waiting().get("kind", "")) == "streamed" and _deferrals("streamed") == 1,
		"the wait is recorded as a streamed territory's")
	expect(_rl_prewarm_during_wait() == 0, "a short wait prewarms no RL head beside the build that follows")
	await _draw_curtain_and_resume()
	var last: Dictionary = main.get("_map_change_curtain").last_wait
	expect(str(main.get("loaded_server_map")) == "tr01_vale" and _loader().world_root != before_root
		and _loader().world_root is ContinentChunkStream and _waiting().is_empty()
		and str(last.get("kind", "")) == "streamed",
		"once the curtain is drawn the territory loads behind it: %s" % last)
	expect(not bool(main.get("_map_change_curtain").warmup_exempt),
		"a fresh territory keeps the Compatibility warm-up it always had")
	await _settle()


func _check_whole_map_waits() -> void:
	app.current_map = "tr01_room"
	main.call("_load_server_map")
	expect(bool(main.get("_deferred_map_load")) and str(main.get("loaded_server_map")) == "tr01_vale"
		and str(_waiting().get("kind", "")) == "whole_map",
		"a whole map waits for the curtain as it always did")
	expect(_rl_prewarm_during_wait() != 0, "and the player's RL head is still prewarmed during that wait")
	await _draw_curtain_and_resume()
	var manifest: WorldManifest = _loader().manifest
	expect(str(main.get("loaded_server_map")) == "tr01_room" and manifest != null
		and manifest.asset_id() == "fixture_west" and not (_loader().world_root is ContinentChunkStream),
		"then it is built behind the drawn curtain")
	await _settle()


func _check_exterior_waits() -> void:
	# A neighbour resident in the exterior stream, reached without a seamless
	# crossing (no link joins it here): a teleport or a border onto it.
	var builder := WorldLoader.new()
	builder.name = "TR01Neighbour"
	(main.get("world_root") as Node).add_child(builder)
	builder.load_world(SCRATCH.path_join("territory.json"), Vector3.INF, true)
	var resident: Dictionary = builder.release_world()
	builder.queue_free()
	var exterior: ExteriorRegionStream = main.get("exterior_stream")
	exterior.residents["tr01_land"] = resident
	app.current_map = "tr01_land"
	main.call("_load_server_map")
	expect(bool(main.get("_deferred_map_load")) and str(main.get("loaded_server_map")) == "tr01_room"
		and exterior.residents.has("tr01_land") and exterior.last_handoff.is_empty()
		and bool(_curtain().call("is_showing")),
		"a non-continuous exterior handoff waits for the curtain before the neighbour is taken")
	expect(str(_waiting().get("kind", "")) == "exterior" and _deferrals("exterior") == 1
		and (_waiting().get("focus") as Vector3).is_finite(),
		"the wait is an exterior handoff's, with the focus it is judged from")
	expect(_rl_prewarm_during_wait() == 0, "an exterior handoff's short wait prewarms no RL head")
	await _draw_curtain_and_resume()
	expect(str(main.get("loaded_server_map")) == "tr01_land" and _loader().loaded_by_adoption
		and _loader().world_root == resident.root and not exterior.residents.has("tr01_land")
		and exterior.last_handoff.get("to", "") == "tr01_land" and not bool(exterior.last_handoff.continuous)
		and not bool(main.get("_continuous_map_handoff")),
		"then the resident neighbour is adopted behind the drawn curtain, as a non-continuous handoff")
	expect(str(main.get("_map_change_curtain").last_wait.get("kind", "")) == "exterior",
		"and the wait is recorded")
	var state = main.get("_map_change_curtain")
	expect(bool(state.warmup_exempt),
		"a curtain raised only to adopt the resident skips the Compatibility warm-up (none before TR-01)")
	app.actors = {LOCAL: _record()}
	expect(bool(main.call("_hold_for_arrival")) and not bool(state.warmup_exempt),
		"an arrival that then loads its own cells was curtained before TR-01 too: the warm-up is back")
	app.actors = {}
	await _settle()


func _check_respawn_prewarm_waits() -> void:
	var prewarm: RefCounted = main.get("respawn_prewarm")
	var entry: Dictionary = MapRegistry.resolve(main.get("map_registry"), "tr01_vale")
	prewarm.call("prewarm", entry, "tr01_vale", Vector2i(10, 40), main.get("world_root"))
	expect(bool(prewarm.call("pending")) and str(prewarm.get("map_id")) == "tr01_vale",
		"the respawn's ground is prewarmed in a hidden stream while dead")
	app.death = {"kind": "death", "dead": true, "ready": true, "remaining": 0.0,
		"destination": {"map": "tr01_vale", "x": 10, "y": 40}}
	# The respawn: CHANGE_MAP, then the death state "not dead" right after it.
	app.current_map = "tr01_vale"
	main.call("_load_server_map")
	expect(bool(main.get("_deferred_map_load")) and str(main.get("loaded_server_map")) == "tr01_land"
		and str(_waiting().get("kind", "")) == "prewarm" and bool(prewarm.call("pending")),
		"a prewarmed respawn waits for the curtain before the prewarm is taken")
	app.death = {"kind": "death", "dead": false, "ready": false, "remaining": 0.0}
	main.call("_prefetch_respawn")
	expect(bool(prewarm.call("pending")) and str(prewarm.get("map_id")) == "tr01_vale",
		"the death state cleared while it waits does not discard the prewarm it is about to adopt")
	expect(_rl_prewarm_during_wait() == 0, "a prewarm's short wait prewarms no RL head")
	await _draw_curtain_and_resume()
	expect(str(main.get("loaded_server_map")) == "tr01_vale" and _loader().loaded_by_adoption
		and not bool(prewarm.call("pending")) and _loader().world_root is ContinentChunkStream,
		"then the prewarmed ground is adopted behind the drawn curtain")
	var state = main.get("_map_change_curtain")
	expect(bool(state.warmup_exempt), "a prewarmed respawn skips the Compatibility warm-up too")
	_curtain().call("cancel")
	main.call("_update_arrival")
	expect(not bool(state.warmup_exempt), "and the exemption ends with the curtain")
	await _settle()
	# Without a change waiting for it, a cleared death still lets the prewarm go.
	prewarm.call("prewarm", MapRegistry.resolve(main.get("map_registry"), "tr01_land"), "tr01_land",
		Vector2i(10, 40), main.get("world_root"))
	expect(bool(prewarm.call("pending")), "a second prewarm starts")
	main.call("_prefetch_respawn")
	expect(not bool(prewarm.call("pending")), "and with nothing waiting to adopt it, 'not dead' discards it as before")
	app.death = {}


func _check_gauntlet_prewarm_waits() -> void:
	var prewarm: RefCounted = main.get("gauntlet_prewarm")
	prewarm.call("prewarm", MapRegistry.resolve(main.get("map_registry"), "tr01_land"), "tr01_land",
		Vector2i(10, 40), main.get("world_root"))
	app.current_map = "tr01_land"
	main.call("_load_server_map")
	expect(bool(main.get("_deferred_map_load")) and str(_waiting().get("kind", "")) == "prewarm"
		and bool(prewarm.call("pending")), "a gauntlet exit onto its prewarmed ground waits for the curtain")
	app.gauntlet_loot = {"phase": "ended", "exited": true}
	main.call("_prefetch_gauntlet_exit")
	expect(bool(prewarm.call("pending")), "the loot window closing meanwhile does not discard it")
	await _draw_curtain_and_resume()
	expect(str(main.get("loaded_server_map")) == "tr01_land" and _loader().loaded_by_adoption
		and not bool(prewarm.call("pending")), "then it is adopted behind the drawn curtain")
	app.gauntlet_loot = {}
	await _settle()


func _check_uncurtained_kinds() -> void:
	var exterior: ExteriorRegionStream = main.get("exterior_stream")
	var saved_links: Array = exterior.links
	var saved_active := exterior.active_map
	var here := {"map": "tr01_land", "position": [0, 0, 0], "frame": {"id": "a", "anchor": [0, 0, 0],
		"outward": [0, -1], "viewHalfWidth": 240, "collarDepth": 2}, "preloadEdges": [[[-150, 0], [150, 0]]]}
	var there := {"map": "tr01_seam", "position": [0, 0, 0], "frame": {"id": "b", "anchor": [0, 0, 0],
		"outward": [0, 1], "viewHalfWidth": 240, "collarDepth": 2}}
	exterior.links = [{"seamless": true, "ends": [here, there]}]
	exterior.active_map = "tr01_land"
	var placeholder := Node3D.new()
	exterior.residents["tr01_seam"] = {"root": placeholder}
	expect(main.call("_map_change_curtain_kind", "tr01_seam", Vector3(40, 0, 3)) == &"",
		"a seamless crossing is never curtained")
	expect(main.call("_map_change_curtain_kind", "tr01_seam", Vector3(40, 0, 60)) == CURTAIN.EXTERIOR,
		"the same neighbour reached far from the seam is")
	exterior.residents.erase("tr01_seam")
	placeholder.free()
	exterior.links = saved_links
	exterior.active_map = saved_active
	var park: Node = main.get("world_park")
	(park.get("_parked") as Dictionary)["tr01_door"] = {"resident": {}, "at_msec": 0}
	expect(main.call("_map_change_curtain_kind", "tr01_door", Vector3.ZERO) == &"",
		"a door into a kept world keeps its uncurtained transition")
	(park.get("_parked") as Dictionary).erase("tr01_door")
	expect(main.call("_map_change_curtain_kind", "tr01_room", Vector3.ZERO) == &"",
		"a fresh load is held by the load's own branch, not here")
	var row: Dictionary = main.call("client_diagnostic_snapshot").get("map_change_curtain", {})
	expect(int((row.get("deferrals", {}) as Dictionary).get("exterior", 0)) == 1
		and int((row.get("deferrals", {}) as Dictionary).get("prewarm", 0)) == 2
		and int((row.get("deferrals", {}) as Dictionary).get("streamed", 0)) == 1
		and int((row.get("deferrals", {}) as Dictionary).get("whole_map", 0)) == 1,
		"the client snapshot counts the waits: %s" % row)


## Review fix: a change the server takes back before its curtain is drawn (the
## player sent back to the map still loaded) loads nothing, and its wait must
## not outlive it: a later change to the same map would otherwise be judged
## from the camera focus of the abandoned one and not be counted.
func _check_abandoned_wait() -> void:
	var builder := WorldLoader.new()
	builder.name = "TR01Return"
	(main.get("world_root") as Node).add_child(builder)
	builder.load_world(SCRATCH.path_join("territory.json"), Vector3.INF, true)
	var resident: Dictionary = builder.release_world()
	builder.queue_free()
	var exterior: ExteriorRegionStream = main.get("exterior_stream")
	exterior.residents["tr01_vale"] = resident
	var camera: IsometricCameraController = main.get("camera_rig")
	camera.set_focus(Vector3(5, 0, 5))
	var first_focus: Vector3 = camera.focus
	var loaded := str(main.get("loaded_server_map"))
	app.current_map = "tr01_vale"
	main.call("_load_server_map")
	expect(str(_waiting().get("kind", "")) == "exterior" and _waiting().get("focus") == first_focus,
		"a non-continuous handoff to the resident waits for its curtain")
	app.current_map = loaded
	main.call("_load_server_map")
	await _draw_curtain_and_resume()
	expect(str(main.get("loaded_server_map")) == loaded and not bool(main.get("_deferred_map_load"))
		and _waiting().is_empty() and exterior.residents.has("tr01_vale"),
		"sent back to the map still loaded, the wait is forgotten and the neighbour left alone")
	_curtain().call("cancel") # That arrival ends like any other.
	var exterior_waits := _deferrals("exterior")
	camera.set_focus(Vector3(9, 0, 9))
	var second_focus: Vector3 = camera.focus
	app.current_map = "tr01_vale"
	main.call("_load_server_map")
	expect(_deferrals("exterior") == exterior_waits + 1 and _waiting().get("focus") == second_focus
		and second_focus != first_focus,
		"a later change to that map waits on its own, judged from where the camera stands now")
	await _draw_curtain_and_resume()
	expect(str(main.get("loaded_server_map")) == "tr01_vale" and _loader().world_root == resident.root,
		"and is then adopted")
	await _settle()


## Review fix: a curtain still fading out counts as drawn, so a handoff raising
## it again goes ahead on the same call; it skips the warm-up all the same.
func _check_fading_curtain_handoff() -> void:
	var builder := WorldLoader.new()
	builder.name = "TR01Fading"
	(main.get("world_root") as Node).add_child(builder)
	builder.load_world(SCRATCH.path_join("territory.json"), Vector3.INF, true)
	var resident: Dictionary = builder.release_world()
	builder.queue_free()
	var exterior: ExteriorRegionStream = main.get("exterior_stream")
	exterior.residents["tr01_land"] = resident
	var curtain := _curtain()
	curtain.call("begin", "Entering…")
	for frame: int in 10:
		if bool(curtain.call("has_drawn")):
			break
		await process_frame
	curtain.call("finish")
	expect(not bool(curtain.call("is_showing")) and bool(curtain.call("has_drawn")), "the curtain is fading out")
	app.current_map = "tr01_land"
	main.call("_load_server_map")
	expect(str(main.get("loaded_server_map")) == "tr01_land" and _loader().world_root == resident.root
		and bool(curtain.call("is_showing")) and bool(main.get("_map_change_curtain").warmup_exempt),
		"a handoff during the fade raises it again, goes ahead at once and skips the warm-up")
	await _settle()


func _check_grounding_wait() -> void:
	var exterior: ExteriorRegionStream = main.get("exterior_stream")
	var curtain := _curtain()
	var camera: IsometricCameraController = main.get("camera_rig")
	var node := ReplicatedActor3D.new()
	node.actor_id = LOCAL
	(main.get("world_root") as Node).add_child(node)
	node.set_process(false)
	var nodes: Dictionary = main.get("actor_nodes")
	nodes[LOCAL] = node
	var grounded: Dictionary = main.get("_grounded_actors")
	grounded.erase(LOCAL)
	app.actors = {LOCAL: _record()}
	main.set("_arrival", {})
	main.set("_deferred_map_load", false)
	curtain.call("begin", "Entering…")
	expect(bool(main.call("_curtained_arrival_ungrounded")),
		"a character built behind the curtain with no ground is an ungrounded curtained arrival")
	grounded[LOCAL] = true
	expect(not bool(main.call("_curtained_arrival_ungrounded")), "a grounded one is not")
	grounded.erase(LOCAL)
	main.set("_deferred_map_load", true)
	expect(not bool(main.call("_curtained_arrival_ungrounded")), "nor one whose map still waits")
	main.set("_deferred_map_load", false)
	main.set("_arrival", {"position": Vector3.ZERO, "started": Time.get_ticks_msec(), "ready": false})
	expect(not bool(main.call("_curtained_arrival_ungrounded")), "nor one whose own cells are still loading")
	main.set("_arrival", {})
	main.set("_disconnect_console_active", true)
	expect(not bool(main.call("_curtained_arrival_ungrounded")), "nor one behind something else that blocks the world")
	main.set("_disconnect_console_active", false)
	camera.set_focus(Vector3(12, 0, 3))
	var sentinel := Vector3(-7, -7, -7)
	exterior.set("_last_position", sentinel)
	main.call("_update_exterior_focus")
	expect(exterior.get("_last_position") == sentinel,
		"within the grace the curtain still keeps the neighbours waiting")
	var curtain_state = main.get("_map_change_curtain")
	curtain_state.set("_ungrounded_since", Time.get_ticks_msec() - CURTAIN.GROUNDING_GRACE_MSEC - 5)
	var waits := int(curtain_state.grounding_waits)
	main.call("_update_exterior_focus")
	expect(exterior.get("_last_position") == camera.focus and int(curtain_state.grounding_waits) == waits + 1,
		"after the grace its neighbours are updated from where it stands")
	grounded[LOCAL] = true
	exterior.set("_last_position", sentinel)
	main.call("_update_exterior_focus")
	expect(exterior.get("_last_position") == sentinel, "once grounded the curtain keeps them waiting again")
	curtain.call("cancel")
	main.call("_update_exterior_focus")
	expect(exterior.get("_last_position") == camera.focus, "with the curtain down they follow the camera as before")
	nodes.erase(LOCAL)
	grounded.erase(LOCAL)
	node.queue_free()
	app.actors = {}


func _cleanup() -> void:
	app.authenticated = false
	main.call("_end_arrival")
	main.call("_clear_world_presentation")
	(main.get("respawn_prewarm") as RefCounted).call("discard")
	(main.get("gauntlet_prewarm") as RefCounted).call("discard")
	var exterior: ExteriorRegionStream = main.get("exterior_stream")
	exterior.clear()
	var deadline := Time.get_ticks_msec() + 30000
	while not exterior.is_idle() and Time.get_ticks_msec() < deadline:
		await process_frame
	RLHeadLibrary.cancel_warm()
	while RLHeadLibrary.warming() and Time.get_ticks_msec() < deadline:
		await process_frame
	expect(await ContinentChunkStream.drain_workers(self, 30000), "the test drains every owned resource worker")
	main.queue_free()
	await process_frame
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
