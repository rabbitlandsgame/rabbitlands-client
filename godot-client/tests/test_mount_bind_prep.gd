extends SceneTree
## AW-07: mount visuals outside the packet handler.
##
##   * MountProfiles.read and MountedPlayerVisual.animation_map read and parse
##     each file once per process and hand out deep copies.
##   * ActorAssetClosure.mount_closure names the files a bind reads: the
##     mount's scene (its own animation library) and the borrowed tack's
##     source; nothing for an unknown mount; memoized.
##   * ReplicatedActor3D.mount_bind_needed: only a built body riding a mount
##     it does not show yet needs a bind.
##   * MountBindQueue's rules: one wait per reason, oldest first, overdue,
##     one bind a frame, counters without ids.
##   * Main (main.tscn, a recorded transport, the game view shown):
##     - a remote rider's first mount-up on a cold species binds nothing in
##       the packet handler: the rider stays as drawn while the mount's files
##       are parsed at PRIORITY_MOUNT and the mount visual's script loads on a
##       ResourceLoader thread (this is the process's first bind), then Main's
##       per-frame actor work binds it with no main-thread glTF parse or script
##       compile, and the visual equals the one main's own parse builds;
##     - ready binds of a burst of riders are made one a frame, outside the
##       handler;
##     - the player's own: the selected mount is asked for ahead; a mount-up
##       on it binds at once; a cold species waits at PRIORITY_LOCAL; behind
##       the arrival curtain the body waits for the ridden mount's files and is
##       built on its mount;
##     - a first-seen remote rider's body waits for its mount's files too and
##       is built on its mount (never on foot first);
##     - a species change keeps the shown mount until the new one is ready;
##     - dismount, removal and a session's end drop a waiting bind;
##     - at Low a remote rider's body stays unfinished (no refit; schedule
##       1.1 #11 is AW-06b's rule, this only shows AW-07 adds none);
##     - as before (bound at once): ELORIA_ACTOR_PREPARER=off, a hidden game
##       view, and the player's own body built with the curtain down;
##     - the diagnostics row `mount_binds`, and one profile read per species.
##
##   Godot --headless --path godot-client --script res://tests/test_mount_bind_prep.gd

const Closure := preload("res://src/actors/actor_asset_closure.gd")
const Warmup := preload("res://src/actors/actor_resource_warmup.gd")
const Profiles := preload("res://src/mounts/mount_profiles.gd")
## Loaded lazily: the first bind of this process must find it unloaded (the
## threaded script load is under test). `Visual` is set once it is loaded.
const VISUAL_PATH := "res://src/mounts/mounted_player_visual.gd"
const Queue := preload("res://src/mounts/mount_bind_queue.gd")
const MEDIUM := ActorRenderQuality.Quality.MEDIUM
const LOCAL := 1
const RIDERS := [101, 102, 103]
const DEADLINE_MSEC := 90000

var checks := 0
var failures := 0
var models: Dictionary = {}
var main: Node
var app: Node
var profile_reads_at_start := 0
var Visual = null


func _init() -> void:
	run.call_deferred()


func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("mount bind prep: " + message)


func run() -> void:
	create_timer(900).timeout.connect(func() -> void:
		push_error("mount bind prep timed out")
		quit(1))
	var previous_prepared := OS.get_environment("RABBITLANDS_PREPARED_CONTENT")
	OS.set_environment("RABBITLANDS_PREPARED_CONTENT", "raw")
	var old_quality := LookProfile.player_quality()
	LookProfile.set_player_quality(MEDIUM)
	models = (JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")) as Dictionary).models
	_check_profile_cache()
	_check_mount_closure()
	_check_queue_rules()
	await _setup_main()
	await _check_remote_cold_mount_up()
	Visual = load(VISUAL_PATH) as Script
	_check_animation_map_cache()
	await _check_bind_needed()
	await _check_burst_one_a_frame()
	await _check_species_change()
	await _check_local_mount_up()
	await _check_local_arrival_on_mount()
	await _check_first_seen_rider()
	await _check_dropped()
	await _measure_three_species()
	await _check_low_remote_rider()
	await _check_as_before()
	_check_diagnostics()
	await _cleanup()
	LookProfile.set_player_quality(old_quality)
	if previous_prepared.is_empty():
		OS.unset_environment("RABBITLANDS_PREPARED_CONTENT")
	else:
		OS.set_environment("RABBITLANDS_PREPARED_CONTENT", previous_prepared)
	print("mount bind prep: %d checks, %d failures" % [checks, failures])
	quit(1 if failures > 0 else 0)


# --- Files read once -------------------------------------------------------------------

func _check_profile_cache() -> void:
	Profiles.clear_cache()
	var reads := Profiles.file_reads
	profile_reads_at_start = reads
	var first := Profiles.read("golden_plains_horse")
	var second := Profiles.read("golden_plains_horse")
	expect(Profiles.file_reads == reads + 1 and not first.is_empty() and first == second,
		"a profile is read from disk once and the same each time")
	expect(first == JSON.parse_string(FileAccess.get_file_as_string(Profiles.PATHS.golden_plains_horse)),
		"it equals the file as parsed")
	first.clips["walk"] = "Changed"
	(first.reins as Dictionary).clear()
	var third := Profiles.read("golden_plains_horse")
	expect(third == second and str(third.clips.walk) != "Changed" and not (third.reins as Dictionary).is_empty(),
		"a caller changing its copy changes no later read (deep copies)")
	expect(Profiles.read("no_such_mount").is_empty() and Profiles.file_reads == reads + 1,
		"an unknown mount reads nothing")
	for id: String in Profiles.PATHS:
		Profiles.read(id)
		Profiles.read(id)
	expect(Profiles.file_reads == reads + Profiles.PATHS.size(), "one read per species: %d" % Profiles.PATHS.size())


func _check_animation_map_cache() -> void:
	Visual.clear_animation_maps()
	var reads: int = Visual.animation_map_reads
	var path := str(models.golden_plains_horse.animationMap)
	var first: Dictionary = Visual.animation_map(path)
	var second: Dictionary = Visual.animation_map(path)
	expect(Visual.animation_map_reads == reads + 1 and first == second
		and first == JSON.parse_string(FileAccess.get_file_as_string(path)),
		"an animation map is read once and equals the file as parsed")
	(first.actions as Dictionary)["mount_walk"] = "Walk"
	expect(not (Visual.animation_map(path).actions as Dictionary).has("mount_walk"),
		"configure's gait clips go into its own copy only")


func _check_mount_closure() -> void:
	Closure.clear_memo()
	var shapes := true
	for id: String in Profiles.PATHS:
		var closure: Dictionary = Closure.mount_closure(id, models)
		var scenes: PackedStringArray = closure.scenes
		var tack := str((Profiles.read(id).get("borrowedTack", {}) as Dictionary).get("source", ""))
		var wanted := PackedStringArray([str(models[id].scene)])
		if not tack.is_empty() and tack != str(models[id].scene):
			wanted.append(tack)
		var ok: bool = scenes == wanted and (closure.pieces as PackedStringArray).is_empty() \
			and (closure.rl_files as PackedStringArray).is_empty() and str(closure.mount) == id \
			and (closure.libraries as PackedStringArray) == PackedStringArray([str(models[id].animationLibrary)]) \
			and not str(closure.key).is_empty() and is_same(Closure.mount_closure(id, models), closure)
		if not ok:
			print("closure of ", id, ": ", closure)
		shapes = shapes and ok
	expect(shapes, "every mount's closure is its scene and the borrowed tack's source, memoized")
	var pony: Dictionary = Closure.mount_closure("moor_pony", models)
	expect((pony.scenes as PackedStringArray).size() == 1, "the Moor Pony needs only its own scene")
	var rat: Dictionary = Closure.mount_closure("giant_rat", models)
	expect(str((rat.scenes as PackedStringArray)[0]).begins_with("res://assets/actors/native/mounts/"),
		"the giant rat's scene outside the creatures folder is named too (a file job, not the creature job)")
	var unknown: Dictionary = Closure.mount_closure("no_such_mount", models)
	expect((unknown.scenes as PackedStringArray).is_empty() and str(unknown.key).is_empty(),
		"an unknown mount needs nothing")
	var other_models: Dictionary = models.duplicate()
	expect(not is_same(Closure.mount_closure("moor_pony", other_models), pony),
		"another models dictionary starts the memo again")


func _check_queue_rules() -> void:
	var queue = Queue.new()
	queue.keep(5, "files", 100)
	queue.keep(5, "files", 150)
	queue.keep(6, "turn", 120)
	queue.keep(4, "turn", 120)
	expect(queue.has(5) and queue.reason(5) == "files" and queue.file_waits == 1 and queue.turn_waits == 2,
		"a wait is counted once per reason")
	queue.keep(5, "turn", 200)
	expect(queue.reason(5) == "turn" and queue.turn_waits == 3, "its reason changes and is counted")
	expect(queue.ids() == [5, 4, 6], "oldest first (ties by id): %s" % [queue.ids()])
	expect(not queue.overdue(5, 100 + Queue.OVERDUE_MSEC - 1) and queue.overdue(5, 100 + Queue.OVERDUE_MSEC),
		"overdue after OVERDUE_MSEC")
	expect(queue.may_bind(10), "a frame may bind")
	queue.note_bound(5, 1500, 10, 400)
	expect(not queue.may_bind(10) and queue.may_bind(11) and Queue.BINDS_PER_FRAME == 1,
		"one bind a frame")
	expect(queue.bound == 1 and queue.last_wait_msec == 300 and queue.maximum_bind_usec == 1500 and not queue.has(5),
		"a bind is counted with its wait and time")
	queue.release(4)
	queue.drop(6)
	queue.drop(77)
	expect(queue.is_empty() and queue.dropped == 1, "release is no drop; a drop counts once")
	queue.keep(9, "files", 0)
	var row: Dictionary = queue.snapshot(50)
	expect(int(row.pending) == 1 and int(row.waitingForFiles) == 1 and int(row.oldestMsec) == 50
		and not str(row).contains("\"9\""), "the snapshot counts, without ids: %s" % row)
	queue.clear()
	expect(queue.is_empty() and queue.dropped == 2, "clear drops what waits")


# --- Main -------------------------------------------------------------------------------

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
	main.game_view.show()
	LookProfile.set_player_quality(MEDIUM)
	models = main.get("models")


func _record(id: int, hair := 2, visuals: Dictionary = {"0": 114, "4": 171}) -> Dictionary:
	return {"actor_id": id, "actor_type": 1, "kind": 1, "name": "Rider%d" % id,
		"x": id % 7, "y": 0, "rotation": 0, "health": 20, "max_health": 20, "alive": true,
		"appearance": {"skin": 2, "hair": AppearanceVariants.pack_hair(hair, 0)},
		"equipment_visuals": visuals.duplicate(), "equipment_fallback_parts": []}


func _row(id: int, mount: String, selected := "", mode := "mounted") -> Dictionary:
	return {"schema_version": 1, "actor_id": id, "mode": mode, "gait": "cruise" if mode == "mounted" else "on_foot",
		"mount_id": mount if mode == "mounted" else "", "selected_mount_id": selected if not selected.is_empty() else mount,
		"step_us": 133333, "endurance_ms": 5000, "summon_remaining_ms": 0, "combat_remaining_ms": 0,
		"can_summon": false, "blocked_reason": "", "map": "", "owner": "Rider%d" % id}


func _curtain() -> CanvasLayer:
	return main.get("arrival_curtain") as CanvasLayer


func _binds() -> RefCounted:
	return main.get("_mount_binds") as RefCounted


func _warmup() -> RefCounted:
	return main.actor_resource_warmup as RefCounted


func _node(id: int) -> ReplicatedActor3D:
	var value: Variant = main.actor_nodes.get(id)
	return value as ReplicatedActor3D if is_instance_valid(value) else null


func _misses() -> int:
	return int(GlbSceneCache.retention_snapshot().get("lookup_misses", 0))


func _visual(id: int) -> Node3D:
	var node := _node(id)
	if node == null:
		return null
	var visual: Variant = node.get("_mount_visual")
	return visual as Node3D if is_instance_valid(visual) else null


func _shows(id: int, mount: String) -> bool:
	return _visual(id) != null and str(_node(id).mount_state.get("mount_id", "")) == mount


func _queued(path: String) -> int:
	var job: Dictionary = (_warmup().get("_files") as Dictionary).get(GlbSceneCache._canonical_path(path), {})
	return int(job.get("priority", -1)) if not job.is_empty() else -1


## A fresh case: no actor nodes, cold caches, an idle preparer, nothing kept.
func _fresh() -> void:
	for raw_id: Variant in main.actor_nodes.keys():
		var node := _node(int(raw_id))
		if node != null:
			node.queue_free()
	main.actor_nodes.clear()
	(main.get("_grounded_actors") as Dictionary).clear()
	await process_frame
	_warmup().call("clear")
	await _pump(func() -> bool: return bool(_warmup().call("is_idle")))
	RLHeadLibrary.cancel_warm()
	RLHeadLibrary.clear()
	GlbSceneCache.clear()
	NativeAnimationImporter.clear()
	ReplicatedActor3D.clear_static_caches()
	Closure.clear_memo()
	_binds().call("clear")
	main.set("_selected_mount_asked", "")
	(main.get("_local_avatar_prep") as RefCounted).call("clear")
	_curtain().call("cancel")
	main.set("_arrival", {})
	main.set("_deferred_map_load", false)
	app.actors = {}
	app.actor_mounts = {}
	main.game_view.show()


func _pump(done: Callable) -> bool:
	var deadline := Time.get_ticks_msec() + DEADLINE_MSEC
	while not bool(done.call()) and Time.get_ticks_msec() < deadline:
		await process_frame
		_warmup().call("poll")
	return bool(done.call())


## Main's per-frame actor work (`_update_model_builds`: the preparer's poll and
## publication, the kept mount binds, the body builds), a frame at a time.
func _frames_until(done: Callable) -> bool:
	var deadline := Time.get_ticks_msec() + DEADLINE_MSEC
	while not bool(done.call()) and Time.get_ticks_msec() < deadline:
		await process_frame
		main.set("_actor_creation_frame", -1)
		main.call("_update_model_builds")
	return bool(done.call())


## A built remote body (main parses its files: the fixture, not under test).
func _built_rider(id: int) -> ReplicatedActor3D:
	var actors: Dictionary = app.actors
	actors[id] = _record(id)
	app.actors = actors
	main.set("_actor_creation_frame", -1)
	main.call("_spawn_actor", id, true)
	return _node(id)


func _mount_rows(rows: Dictionary) -> void:
	app.actor_mounts = rows


func _handler_usec() -> int:
	var began := Time.get_ticks_usec()
	main.call("_on_state_changed", &"mount_states")
	return Time.get_ticks_usec() - began


func _mount_signature(id: int) -> Dictionary:
	var out := {}
	var visual := _visual(id)
	if visual == null:
		return out
	# Unnamed nodes take generated names (@Node3D@1234): compare by structure.
	var generated := RegEx.create_from_string("@[A-Za-z0-9_]+@[0-9]+")
	for node: Node in visual.find_children("*", "MeshInstance3D", true, false):
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
		out[generated.sub(str(visual.get_path_to(mesh_node)), "@", true)] = [surfaces,
			mesh_node.skin.get_bind_count() if mesh_node.skin != null else 0]
	return out


func _check_bind_needed() -> void:
	await _fresh()
	var rider := _built_rider(101)
	expect(rider != null and not rider.is_model_deferred(), "fixture: a built remote body")
	var horse := _row(101, "golden_plains_horse")
	expect(rider.mount_bind_needed(horse), "a built body riding a mount it does not show needs a bind")
	expect(not rider.mount_bind_needed(_row(101, "", "", "on_foot")) and not rider.mount_bind_needed({})
		and not rider.mount_bind_needed(_row(101, "no_such_mount")), "on foot, no row or an unknown mount: none")
	main.game_view.hide()
	_mount_rows({101: horse})
	main.call("_apply_actor_mount", 101)
	main.game_view.show()
	expect(_shows(101, "golden_plains_horse") and not rider.mount_bind_needed(horse)
		and rider.mount_bind_needed(_row(101, "giant_rat")),
		"the mount shown needs none (a new gait or coat is cheap); another species does")
	var stand_in := ReplicatedActor3D.new()
	root.add_child(stand_in)
	stand_in.configure(_record(150), main.adapter, models.luminous_male, {}, {}, false)
	expect(stand_in.is_model_deferred() and not stand_in.mount_bind_needed(horse),
		"a deferred body keeps the record only: no bind")
	stand_in.free()


func _check_remote_cold_mount_up() -> void:
	await _fresh()
	var rider := _built_rider(101)
	var horse_scene := str(models.golden_plains_horse.scene)
	var pony_scene := str(models.moor_pony.scene)
	expect(not GlbSceneCache.missing(PackedStringArray([horse_scene, pony_scene])).is_empty(),
		"fixture: the horse and the borrowed saddle's source are cold")
	expect(not ResourceLoader.has_cached(VISUAL_PATH), "fixture: no mount has been bound in this process yet")
	_mount_rows({101: _row(101, "golden_plains_horse")})
	var handler := _handler_usec()
	expect(_visual(101) == null and bool(_binds().call("has", 101)) and _binds().call("reason", 101) == "files",
		"a cold mount-up binds nothing in the packet handler: the rider waits, drawn as it is")
	expect(_queued(horse_scene) == Warmup.PRIORITY_MOUNT and _queued(pony_scene) == Warmup.PRIORITY_MOUNT,
		"its mount's scene and the borrowed tack's source are queued at PRIORITY_MOUNT")
	main.call("_present_actor", 101)
	expect(_visual(101) == null and bool(_binds().call("has", 101)), "a presentation pass keeps it waiting")
	var misses := _misses()
	var bound_before := int(_binds().get("bound"))
	var asked := Time.get_ticks_msec()
	var bound := await _frames_until(func() -> bool: return _shows(101, "golden_plains_horse"))
	var waited := Time.get_ticks_msec() - asked
	expect(bound and int(_binds().get("bound")) == bound_before + 1 and not bool(_binds().call("has", 101)),
		"once its files are in, Main's per-frame actor work binds it")
	expect(_misses() - misses == 0, "the bind parsed no glTF on the main thread (no GlbSceneCache miss)")
	var bind_usec := int(_binds().get("last_bind_usec"))
	expect(main.get("_mount_visual_script") != null and bool(main.get("_mount_visual_script_threaded"))
		and ResourceLoader.has_cached(VISUAL_PATH),
		"the mount visual's script was loaded on a ResourceLoader thread ahead of the bind, and is held")
	expect(bind_usec < 50000, "so the process's first bind costs %.1f ms on main (headless), not the script compile"
		% (bind_usec / 1000.0))
	var prepared := _mount_signature(101)
	# Reference: the same mount-up bound in the handler from main's own parses.
	_mount_rows({101: _row(101, "", "", "on_foot")})
	main.call("_on_state_changed", &"mount_states")
	expect(_visual(101) == null, "fixture: on foot again")
	GlbSceneCache.clear()
	NativeAnimationImporter.clear()
	main.game_view.hide()
	misses = _misses()
	_mount_rows({101: _row(101, "golden_plains_horse")})
	var reference_handler := _handler_usec()
	main.game_view.show()
	expect(_shows(101, "golden_plains_horse") and _misses() - misses > 0,
		"fixture: with the game view hidden it binds in the handler from main's parses (%d misses)" % (_misses() - misses))
	var reference := _mount_signature(101)
	if prepared != reference:
		for path: String in reference:
			if prepared.get(path) != reference[path]:
				print("differs: ", path, "\n prepared ", prepared.get(path), "\n main     ", reference[path])
		for path: String in prepared:
			if not reference.has(path):
				print("only prepared: ", path)
	expect(not prepared.is_empty() and prepared == reference,
		"the bound mount equals the one main's own parse builds: the same %d visible meshes, geometry, materials"
		% prepared.size())
	print(("TIMING remote cold mount-up (golden_plains_horse, headless): handler %.1f ms before -> %.1f ms; "
		% [reference_handler / 1000.0, handler / 1000.0]) + ("files ready and bound %d ms after the row; "
		% waited) + ("bind %.1f ms on main from prepared files" % (bind_usec / 1000.0)))


func _check_burst_one_a_frame() -> void:
	await _fresh()
	for id: int in RIDERS:
		_built_rider(id)
	# The mounts' files are in already (another rider's earlier bind).
	var rows := {}
	for id: int in RIDERS:
		rows[id] = _row(id, "jadefeather_raptor")
	var closure: Dictionary = Closure.mount_closure("jadefeather_raptor", models)
	var ready := await _pump(func() -> bool:
		return bool(_warmup().call("request_closure", closure, Warmup.PRIORITY_MOUNT)))
	expect(ready, "fixture: the raptor's files are prepared")
	_mount_rows(rows)
	var handler := _handler_usec()
	var waiting := 0
	for id: int in RIDERS:
		waiting += int(_binds().call("reason", id) == "turn" and _visual(id) == null)
	expect(waiting == RIDERS.size(), "three ready mount-ups bind nothing in the handler (%.1f ms): they take turns"
		% (handler / 1000.0))
	var per_frame: Array = []
	# The fixture's publication time is not these frames' actor work.
	_warmup().call("take_publish_usec")
	for _frame: int in RIDERS.size() + 1:
		await process_frame
		main.set("_actor_creation_frame", -1)
		main.call("_update_model_builds")
		var shown := 0
		for id: int in RIDERS:
			shown += int(_shows(id, "jadefeather_raptor"))
		per_frame.append(shown)
	expect(per_frame == [1, 2, 3, 3], "one bind a frame: riders shown per frame %s" % [per_frame])
	expect(_binds().call("is_empty") and int(_binds().get("maximum_bind_usec")) > 0,
		"none waits afterwards; bind times are recorded")
	# The frame's actor work spent: a ready bind waits, until it is overdue.
	for id: int in RIDERS:
		rows[id] = _row(id, "", "", "on_foot")
	_mount_rows(rows)
	main.call("_on_state_changed", &"mount_states")
	rows[101] = _row(101, "jadefeather_raptor")
	_mount_rows(rows)
	main.call("_on_state_changed", &"mount_states")
	await process_frame
	main.call("_actor_work_available", false)
	main.set("_actor_work_usec", 1000000)
	main.call("_bind_pending_mounts")
	expect(_visual(101) == null and _binds().call("reason", 101) == "turn",
		"with the frame's actor work spent a ready bind waits")
	((_binds().get("_pending") as Dictionary)[101] as Dictionary)["since"] = Time.get_ticks_msec() - Queue.OVERDUE_MSEC
	var overdue := int(_binds().get("overdue_binds"))
	main.call("_bind_pending_mounts")
	expect(_shows(101, "jadefeather_raptor") and int(_binds().get("overdue_binds")) == overdue + 1,
		"one kept for OVERDUE_MSEC is made regardless")


func _check_species_change() -> void:
	await _fresh()
	_built_rider(101)
	main.game_view.hide()
	_mount_rows({101: _row(101, "moor_pony")})
	main.call("_apply_actor_mount", 101)
	main.game_view.show()
	var pony := _visual(101)
	expect(_shows(101, "moor_pony"), "fixture: the rider shows the Moor Pony")
	_mount_rows({101: _row(101, "giant_rat")})
	main.call("_on_state_changed", &"mount_states")
	expect(_visual(101) == pony and _binds().call("reason", 101) == "files",
		"a change to a cold species keeps the mount shown while the new one's files are parsed")
	var bound := await _frames_until(func() -> bool: return _shows(101, "giant_rat"))
	expect(bound and not is_instance_valid(pony), "then the new mount replaces it")


func _check_local_mount_up() -> void:
	await _fresh()
	var me := _record(LOCAL)
	me.name = "Rider%d" % LOCAL
	app.actors = {LOCAL: me}
	main.set("_actor_creation_frame", -1)
	main.call("_spawn_actor", LOCAL, true)
	expect(_node(LOCAL) != null, "fixture: the player's own body (curtain down)")
	var rabbit_scene := str(models.rabbit.scene)
	_mount_rows({LOCAL: _row(LOCAL, "", "rabbit", "on_foot")})
	main.call("_on_state_changed", &"mount_states")
	expect(_queued(rabbit_scene) == Warmup.PRIORITY_MOUNT, "the selected mount is asked for ahead, at PRIORITY_MOUNT")
	var closure: Dictionary = Closure.mount_closure("rabbit", models)
	expect(await _pump(func() -> bool: return bool(_warmup().call("request_closure", closure))),
		"its files are prepared while the player is on foot")
	# The creature memory budget may evict that idle prefetch (MEM-M5): later
	# changes of the mount table do not parse it again while it stays idle...
	GlbSceneCache.forget(rabbit_scene)
	_mount_rows({LOCAL: _row(LOCAL, "", "rabbit", "on_foot")})
	main.call("_on_state_changed", &"mount_states")
	main.call("_on_state_changed", &"mount_deltas")
	expect(_queued(rabbit_scene) == -1,
		"an evicted idle prefetch of the same selection is not asked for again on each table change")
	# ...and a call of it asks at PRIORITY_LOCAL, so its countdown covers the parse.
	var calling := _row(LOCAL, "", "rabbit", "on_foot")
	calling.mode = "summoning"
	calling.mount_id = "rabbit"
	calling.summon_remaining_ms = 1200
	_mount_rows({LOCAL: calling})
	main.call("_on_state_changed", &"mount_states")
	expect(_queued(rabbit_scene) == Warmup.PRIORITY_LOCAL and _visual(LOCAL) == null,
		"a mount being summoned is asked for at PRIORITY_LOCAL while the call counts down")
	expect(await _pump(func() -> bool: return bool(_warmup().call("request_closure", closure))),
		"its files are prepared again during the call")
	var misses := _misses()
	_mount_rows({LOCAL: _row(LOCAL, "rabbit")})
	var handler := _handler_usec()
	expect(_shows(LOCAL, "rabbit") and _misses() - misses == 0 and not bool(_binds().call("has", LOCAL)),
		"the mount-up on it binds at once, with no main-thread parse (%.1f ms)" % (handler / 1000.0))
	# A cold species, never selected: the player's mount-up waits for its files.
	var stag_scene := str(models.lantern_stag.scene)
	_mount_rows({LOCAL: _row(LOCAL, "", "rabbit", "on_foot")})
	main.call("_on_state_changed", &"mount_states")
	expect(_visual(LOCAL) == null and not GlbSceneCache.missing(PackedStringArray([stag_scene])).is_empty(),
		"fixture: on foot, the stag cold")
	_mount_rows({LOCAL: _row(LOCAL, "lantern_stag")})
	main.call("_on_state_changed", &"mount_states")
	expect(_visual(LOCAL) == null and _binds().call("reason", LOCAL) == "files"
		and _queued(stag_scene) == Warmup.PRIORITY_LOCAL,
		"a mount-up on a cold species waits for its files, asked at PRIORITY_LOCAL")
	misses = _misses()
	var bound := await _frames_until(func() -> bool: return _shows(LOCAL, "lantern_stag"))
	expect(bound and _misses() - misses == 0, "then it is bound with no main-thread parse")


func _check_local_arrival_on_mount() -> void:
	await _fresh()
	var me := _record(LOCAL, 4, {"0": 114})
	me.name = "Rider%d" % LOCAL
	_curtain().call("begin", "Entering…")
	app.actors = {LOCAL: me}
	_mount_rows({LOCAL: _row(LOCAL, "cheetah", "giant_rat")})
	main.set("_actor_creation_frame", -1)
	main.call("_spawn_arrivals", [LOCAL])
	var cheetah_scene := str(models.cheetah.scene)
	var rat_scene := str(models.giant_rat.scene)
	expect(_node(LOCAL) == null and _queued(cheetah_scene) == Warmup.PRIORITY_LOCAL
		and _queued(rat_scene) == Warmup.PRIORITY_MOUNT,
		"behind the curtain the body waits; the ridden mount is asked at PRIORITY_LOCAL, the selected one at PRIORITY_MOUNT")
	var misses := _misses()
	var deadline := Time.get_ticks_msec() + DEADLINE_MSEC
	while _node(LOCAL) == null and Time.get_ticks_msec() < deadline:
		main.set("_actor_creation_frame", -1)
		main.call("_update_model_builds")
		main.call("_spawn_arrivals", [LOCAL])
		if _node(LOCAL) == null:
			await process_frame
	expect(_node(LOCAL) != null and GlbSceneCache.missing(PackedStringArray([cheetah_scene])).is_empty(),
		"it is built once the ridden mount's files are in too")
	expect(_shows(LOCAL, "cheetah") and _misses() - misses == 0 and not bool(_binds().call("has", LOCAL)),
		"on its mount, bound in its build, with no main-thread parse")
	_curtain().call("cancel")


func _check_first_seen_rider() -> void:
	await _fresh()
	var stranger := _record(102, 5, {"0": 114, "4": 171})
	app.actors = {102: stranger}
	_mount_rows({102: _row(102, "crystalback_tortoise")})
	var tortoise_scene := str(models.crystalback_tortoise.scene)
	expect(not bool(main.call("_remote_model_ready", 102)) and _queued(tortoise_scene) == Warmup.PRIORITY_NEAR,
		"a first-seen rider's body also waits for its mount's files, at its own priority")
	var ready := false
	var deadline := Time.get_ticks_msec() + DEADLINE_MSEC
	while Time.get_ticks_msec() < deadline:
		main.call("_update_model_builds")
		ready = bool(main.call("_remote_model_ready", 102))
		if ready:
			break
		await process_frame
	expect(ready and GlbSceneCache.missing(PackedStringArray([tortoise_scene])).is_empty(),
		"it is ready once the mount's files are in")
	var misses := _misses()
	main.set("_actor_creation_frame", -1)
	main.call("_spawn_actor", 102, true)
	expect(_shows(102, "crystalback_tortoise") and _misses() - misses == 0
		and not bool(_binds().call("has", 102)), "and is built on its mount at once: never on foot first, no parse")


func _check_dropped() -> void:
	await _fresh()
	for id: int in RIDERS:
		_built_rider(id)
	_mount_rows({101: _row(101, "cave_salamander"), 102: _row(102, "cave_salamander"),
		103: _row(103, "cave_salamander")})
	main.call("_on_state_changed", &"mount_states")
	expect(_binds().call("has", 101) and _binds().call("has", 102) and _binds().call("has", 103),
		"fixture: three riders wait for a cold species")
	var dropped := int(_binds().get("dropped"))
	_mount_rows({101: _row(101, "", "", "on_foot"), 102: _row(102, "cave_salamander"),
		103: _row(103, "cave_salamander")})
	main.call("_on_state_changed", &"mount_states")
	expect(not bool(_binds().call("has", 101)) and _visual(101) == null and int(_binds().get("dropped")) == dropped + 1,
		"a dismount drops the waiting bind")
	var actors: Dictionary = app.actors
	actors.erase(102)
	app.actors = actors
	main.call("_bind_pending_mounts")
	expect(not bool(_binds().call("has", 102)), "a removed actor's bind is dropped by the next pass")
	# Removing a node drops its wait at once: a node built for the same id in
	# the same frame starts its own wait (and its own overdue clock).
	var stale_rider := _built_rider(104)
	var rows: Dictionary = app.actor_mounts
	rows[104] = _row(104, "cave_salamander")
	_mount_rows(rows)
	main.call("_apply_actor_mount", 104)
	expect(stale_rider != null and bool(_binds().call("has", 104)), "fixture: a fourth rider waits")
	actors = app.actors
	actors.erase(104)
	app.actors = actors
	dropped = int(_binds().get("dropped"))
	main.call("_remove_stale_actor_nodes", null)
	expect(not main.actor_nodes.has(104) and not bool(_binds().call("has", 104))
		and int(_binds().get("dropped")) == dropped + 1,
		"a stale actor's removal drops its waiting bind with its node")
	main.call("_clear_actor_nodes_for_map_change")
	expect(not main.actor_nodes.has(103) and not bool(_binds().call("has", 103)),
		"a change of map that takes the nodes drops their waiting binds")
	_built_rider(105)
	rows = app.actor_mounts
	rows[105] = _row(105, "cave_salamander")
	_mount_rows(rows)
	main.call("_apply_actor_mount", 105)
	expect(bool(_binds().call("has", 105)), "fixture: a rider waits at the session's end")
	main.call("_clear_world_presentation", true)
	expect(_binds().call("is_empty"), "a session's end drops every waiting bind")


func _check_as_before() -> void:
	# The kill switch: bound in the handler from main's parses, nothing queued.
	await _fresh()
	OS.set_environment(Warmup.SWITCH_ENVIRONMENT, "off")
	var previous: RefCounted = main.actor_resource_warmup
	main.actor_resource_warmup = Warmup.new()
	_built_rider(101)
	var misses := _misses()
	_mount_rows({101: _row(101, "lantern_stag")})
	var handler := _handler_usec()
	expect(_shows(101, "lantern_stag") and _misses() - misses > 0 and (_warmup().get("_files") as Dictionary).is_empty()
		and int(_warmup().call("snapshot").closureRequests) == 0,
		"with ELORIA_ACTOR_PREPARER=off a cold mount-up binds in the handler as before (%.1f ms), nothing asked"
		% (handler / 1000.0))
	OS.unset_environment(Warmup.SWITCH_ENVIRONMENT)
	main.actor_resource_warmup = previous
	# A hidden game view (no frame drains the kept binds): as before.
	await _fresh()
	_built_rider(101)
	main.game_view.hide()
	_mount_rows({101: _row(101, "cheetah")})
	main.call("_on_state_changed", &"mount_states")
	expect(_shows(101, "cheetah") and _binds().call("is_empty"), "with the game view hidden it binds in the handler")
	main.game_view.show()
	# The player's own body built at once with the curtain down (AW-04d) binds
	# its mount in the same build, as before, even on a cold species.
	await _fresh()
	app.actors = {LOCAL: _record(LOCAL)}
	_mount_rows({LOCAL: _row(LOCAL, "lantern_stag")})
	misses = _misses()
	main.set("_actor_creation_frame", -1)
	main.call("_spawn_actor", LOCAL, true)
	expect(_shows(LOCAL, "lantern_stag") and _misses() - misses > 0 and _binds().call("is_empty"),
		"the player's own body built with the curtain down is built on its mount, as before")


## The plan's market line, headless: riders of three species mount up at once,
## every species cold. Before (ELORIA_ACTOR_PREPARER=off): all three bind in the
## packet handler. Now: the handler binds nothing; Main's frames publish the
## prepared files and bind one rider a frame.
func _measure_three_species() -> void:
	var species := {101: "moor_pony", 102: "golden_plains_horse", 103: "jadefeather_raptor"}
	var rows := {}
	for id: int in species:
		rows[id] = _row(id, str(species[id]))
	# Before.
	await _fresh()
	for id: int in RIDERS:
		_built_rider(id)
	OS.set_environment(Warmup.SWITCH_ENVIRONMENT, "off")
	var previous: RefCounted = main.actor_resource_warmup
	main.actor_resource_warmup = Warmup.new()
	_mount_rows(rows)
	var before := _handler_usec()
	var all_before := true
	for id: int in species:
		all_before = all_before and _shows(id, str(species[id]))
	OS.unset_environment(Warmup.SWITCH_ENVIRONMENT)
	main.actor_resource_warmup = previous
	# Now.
	await _fresh()
	for id: int in RIDERS:
		_built_rider(id)
	_warmup().call("take_publish_usec")
	_mount_rows(rows)
	var handler := _handler_usec()
	var frames := 0
	var worst := 0
	var began := Time.get_ticks_msec()
	var deadline := began + DEADLINE_MSEC
	var all_now := false
	while not all_now and Time.get_ticks_msec() < deadline:
		await process_frame
		main.set("_actor_creation_frame", -1)
		var frame_began := Time.get_ticks_usec()
		main.call("_update_model_builds")
		worst = maxi(worst, Time.get_ticks_usec() - frame_began)
		frames += 1
		all_now = true
		for id: int in species:
			all_now = all_now and _shows(id, str(species[id]))
	print(("TIMING three cold species at once (headless): before, the handler bound all three in %.1f ms; "
		% (before / 1000.0)) + ("now the handler took %.1f ms and Main's actor work at most %.1f ms a frame, "
		% [handler / 1000.0, worst / 1000.0]) + ("all mounted after %d frames, %d ms" % [frames, Time.get_ticks_msec() - began]))
	expect(all_before and all_now and handler < before, "three species: bound in either case, the handler no longer binds")
	expect(worst < 50000, "no frame of Main's actor work over 50 ms for the binds (headless): %.1f ms" % (worst / 1000.0))


## Schedule 1.1 #11 (for AW-06b): at Low a remote Human keeps its unfinished
## body (LAT-L4). Binding its mount outside the handler refits nothing.
func _check_low_remote_rider() -> void:
	await _fresh()
	LookProfile.set_player_quality(ActorRenderQuality.Quality.LOW)
	var rider := _built_rider(101)
	var finish: int = int(rider.get("_human_shape_finish"))
	expect(finish == ReplicatedActor3D.HumanShapeFinish.UNFINISHED, "fixture: a remote Human at Low is unfinished")
	_mount_rows({101: _row(101, "rabbit")})
	main.call("_on_state_changed", &"mount_states")
	var bound := await _frames_until(func() -> bool: return _shows(101, "rabbit"))
	expect(bound and int(rider.get("_human_shape_finish")) == finish
		and not rider.configuration_timings_usec().has("finish.body_refinement"),
		"its mount is bound outside the handler and its body stays unfinished (no refit)")
	LookProfile.set_player_quality(MEDIUM)


func _check_diagnostics() -> void:
	var row: Dictionary = main.call("client_diagnostic_snapshot")
	var binds: Dictionary = row.get("mount_binds", {})
	expect(int(binds.get("bound", 0)) > 0 and int(binds.get("fileWaits", 0)) > 0 and binds.has("turnWaits")
		and bool(binds.get("visualScriptHeld", false)) and bool(binds.get("visualScriptThreaded", false))
		and int(binds.get("profileFileReads", -1)) == Profiles.file_reads
		and int(binds.get("animationMapReads", -1)) == Visual.animation_map_reads,
		"the diagnostics snapshot carries mount_binds: %s" % binds)
	expect(Profiles.file_reads - profile_reads_at_start == Profiles.PATHS.size(),
		"every bind of this run read no profile file again: one read per species (%d)" % Profiles.PATHS.size())
	expect(Visual.animation_map_reads <= Profiles.PATHS.size(),
		"and no animation map twice: %d reads" % Visual.animation_map_reads)


func _cleanup() -> void:
	_curtain().call("cancel")
	RLHeadLibrary.cancel_warm()
	while RLHeadLibrary.warming():
		await process_frame
	if main != null:
		main.actor_resource_warmup.clear()
		await _pump(func() -> bool: return main.actor_resource_warmup.is_idle())
		main.call("_clear_world_presentation")
		main.queue_free()
		await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	ReplicatedActor3D.clear_static_caches()
