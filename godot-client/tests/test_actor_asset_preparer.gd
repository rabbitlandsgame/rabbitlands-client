extends SceneTree
## AW-04a: the actor asset closure, the actor preparer and Main's remote gate.
##
##   * The actor's equipment, fit and hair lookups made static give exactly what
##     the instance methods give (every registry model, four races) and what the
##     former hair lookup gave.
##   * ActorAssetClosure names the race scene, the female shirt repair, the
##     hairstyle and the worn equipment (fit variant for the race), skips empty
##     bare slots, adds a bow's arrow and default bow, leaves creature scenes to
##     the creature job and reports the mount.
##   * ActorResourceWarmup parses a cold closure file by file on its worker,
##     publishes at most one file a process frame with at most
##     PUBLISH_QUEUE_LIMIT roots waiting, installs equipment pieces equal to
##     those read from an instance (same meshes, materials, binds), never waits
##     for a blocked main thread, takes the most urgent job first and raises
##     queued ones, leaves files it cannot prepare to the main thread, is off
##     under ELORIA_ACTOR_PREPARER=off, discards everything on clear(), and
##     frees unpublished (no pieces) a root whose file main cached meanwhile,
##     and joins a running file job when it is freed without being drained.
##   * A body built after its closure is ready parses nothing on the main thread
##     (no GlbSceneCache miss) and equals a body whose files main parsed.
##   * Main: a remote Human waits on a stand-in until its closure is ready and is
##     then built with no main-thread parse, through the build candidates and
##     through the priority (selected) path; the player's own body and the kill
##     switch build at once (the switch computes no closure and keeps only the
##     creature job); a creature keeps its creature job.
##
##   Godot --headless --path godot-client --script res://tests/test_actor_asset_preparer.gd

const Closure := preload("res://src/actors/actor_asset_closure.gd")
const Warmup := preload("res://src/actors/actor_resource_warmup.gd")
const MEDIUM := ActorRenderQuality.Quality.MEDIUM
const LOCAL := 1
const CAPE_LOADOUT := {"0": 114, "1": 106, "2": 1, "3": 117, "4": 171, "5": 184, "6": 192}
const BOW_LOADOUT := {"0": 165, "4": 0, "5": 0, "6": 0}
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
		push_error("actor asset preparer: " + message)


func run() -> void:
	create_timer(900).timeout.connect(func() -> void:
		push_error("actor asset preparer timed out")
		quit(1))
	var previous_prepared := OS.get_environment("RABBITLANDS_PREPARED_CONTENT")
	OS.set_environment("RABBITLANDS_PREPARED_CONTENT", "raw")
	var old_quality := LookProfile.player_quality()
	LookProfile.set_player_quality(MEDIUM)
	models = (JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")) as Dictionary).models
	equipment = EquipmentRegistrySnapshotCache.prepare(
		JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json")) as Dictionary)
	_check_statics()
	_check_closure_shapes()
	await _check_cold_closure()
	await _check_blocked_main()
	await _check_priority()
	await _check_fallbacks_and_switch()
	await _check_clear()
	await _check_main_parsed_meanwhile()
	_check_freed_while_parsing()
	await _check_build_equals_main_parse()
	await _setup_main()
	await _check_main_gate()
	await _cleanup()
	LookProfile.set_player_quality(old_quality)
	if previous_prepared.is_empty():
		OS.unset_environment("RABBITLANDS_PREPARED_CONTENT")
	else:
		OS.set_environment("RABBITLANDS_PREPARED_CONTENT", previous_prepared)
	print("actor asset preparer: %d checks, %d failures" % [checks, failures])
	quit(1 if failures > 0 else 0)


func _record(id: int, model_hair := 2, visuals: Dictionary = CAPE_LOADOUT, name := "Wearer",
		actor_type := 1, x := 3, y := 4) -> Dictionary:
	return {"actor_id": id, "actor_type": actor_type, "kind": 1, "name": name,
		"x": x, "y": y, "rotation": 0, "health": 20, "max_health": 20, "alive": true,
		"appearance": {"skin": 2, "hair": AppearanceVariants.pack_hair(model_hair, 0)},
		"equipment_visuals": visuals.duplicate(), "equipment_fallback_parts": []}


func _animation(config: Dictionary) -> Dictionary:
	return JSON.parse_string(FileAccess.get_file_as_string(str(config.get("animationMap",
		"res://data/animations/luminous.json")))) as Dictionary


func _cold() -> void:
	RLHeadLibrary.cancel_warm()
	RLHeadLibrary.clear()
	GlbSceneCache.clear()
	ReplicatedActor3D.clear_static_caches()
	TorsoBodyCover.clear()
	preload("res://src/actors/wardrobe_shirt_fit.gd").clear()


func _misses() -> int:
	return int(GlbSceneCache.retention_snapshot().get("lookup_misses", 0))


## The former `_add_hair_variant` lookup, kept here as the reference.
func _old_hair_path(model_config: Dictionary, style: int) -> String:
	if style == 0:
		return ""
	var styles_value: Variant = model_config.get("hairStyles", [])
	if styles_value is not Array or (styles_value as Array).is_empty():
		return ""
	var styles: Array = styles_value as Array
	var path: String = str(styles[posmod(style, styles.size())])
	var style_override: Dictionary = (model_config.get("hairStyleOverrides", {}) as Dictionary).get(str(style), {})
	if not style_override.is_empty():
		path = str(style_override.get("scene", path))
	return path


# --- static lookups -------------------------------------------------------------

func _check_statics() -> void:
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0})
	var models_checked := 0
	var mismatches: Array = []
	for model_id: String in ["luminous_male", "luminous_female", "glasswarden_female", "greyhaven_female"]:
		var config: Dictionary = models.get(model_id, {}) as Dictionary
		if config.is_empty():
			continue
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		actor.configure(_record(50), adapter, config, _animation(config), equipment, false)
		if actor.fit_groups() != ReplicatedActor3D.fit_groups_for(equipment, config) \
				or actor.rig_name() != ReplicatedActor3D.rig_name_for(config):
			mismatches.append("%s fit groups" % model_id)
		for key: String in (equipment.models as Dictionary):
			var part := int(key.get_slice(":", 0))
			var visual := int(key.get_slice(":", 1))
			var instance: Dictionary = actor.call("_equipment_model_config", part, visual)
			var static_model := ReplicatedActor3D.equipment_model_config_for(equipment, config, part, visual)
			if instance != static_model:
				mismatches.append("%s %s" % [model_id, key])
			if str(actor.call("_ranged_bow_path", instance)) != ReplicatedActor3D.ranged_bow_path_for(static_model):
				mismatches.append("%s bow %s" % [model_id, key])
			models_checked += 1
		for style: int in range(-2, 16):
			if ReplicatedActor3D.hair_scene_for(config, style) != _old_hair_path(config, style):
				mismatches.append("%s hair %d" % [model_id, style])
		actor.free()
	expect(models_checked > 1000 and mismatches.is_empty(),
		"the static equipment, fit-variant, fit-group, rig, bow and hair lookups equal the actor's (%d models): %s"
		% [models_checked, mismatches.slice(0, 8)])
	var variant := ReplicatedActor3D.equipment_model_config_for(equipment, models.luminous_male as Dictionary, 5, 184)
	expect(str(variant.get("scene", "")).contains("human_male") and not variant.has("variants"),
		"a piece with race variants resolves to the race's own copy: %s" % variant.get("scene", ""))


# --- the closure ------------------------------------------------------------------

func _check_closure_shapes() -> void:
	var male := Closure.closure(_record(60), "luminous_male", models, equipment, MEDIUM)
	var scenes: PackedStringArray = male.scenes
	var pieces: PackedStringArray = male.pieces
	var rl_files: PackedStringArray = male.rl_files
	var race := str(models.luminous_male.scene)
	var hair := ReplicatedActor3D.hair_scene_for(models.luminous_male, 2)
	expect(not bool(male.creature) and scenes.size() > 0 and scenes[0] == race,
		"a Human's closure starts with its race scene: %s" % scenes)
	expect(rl_files.size() == 1 and rl_files[0].contains("/rl_heads/hair/") and not scenes.has(hair),
		"a portrait Human below High draws its RL hairstyle module (for RLHeadLibrary), not the game hairstyle: %s" % rl_files)
	var worn_ok := true
	for part: String in CAPE_LOADOUT:
		var worn := ReplicatedActor3D.equipment_model_config_for(equipment, models.luminous_male,
			int(part), int(CAPE_LOADOUT[part]))
		var scene := str(worn.get("scene", ""))
		worn_ok = worn_ok and not scene.is_empty() and scenes.has(scene) and pieces.has(scene)
	expect(worn_ok and scenes.size() == 1 + CAPE_LOADOUT.size() and pieces.size() == CAPE_LOADOUT.size(),
		"it names every worn piece as the race wears it, each once, read as pieces: %s" % scenes)
	var high := Closure.closure(_record(60), "luminous_male", models, equipment, ActorRenderQuality.Quality.HIGH)
	expect((high.rl_files as PackedStringArray).is_empty() and (high.scenes as PackedStringArray).has(hair)
		and (high.pieces as PackedStringArray).has(hair),
		"at High (the RL head, parsed by RLHeadLibrary meanwhile) the game hairstyle is named, read as pieces")
	var other_race := ""
	for model_id: String in models:
		var config: Dictionary = models[model_id]
		if not ReplicatedActor3D.uses_portrait_customization_for(config) \
				and not (config.get("hairStyles", []) as Array).is_empty():
			other_race = model_id
			break
	var other := Closure.closure(_record(67), other_race, models, equipment, MEDIUM)
	expect(not other_race.is_empty() and (other.rl_files as PackedStringArray).is_empty()
		and (other.scenes as PackedStringArray).has(ReplicatedActor3D.hair_scene_for(models[other_race], 2)),
		"a race without portrait customization (%s) wears the game hairstyle at Medium" % other_race)
	expect(male.libraries == PackedStringArray([str(models.luminous_male.animationLibrary)]) and str(male.mount) == "",
		"the animation library is reported, not prepared; no mount")
	expect(Closure.closure(_record(60), "luminous_male", models, equipment, MEDIUM).key == male.key
		and Closure.closure(_record(60, 3), "luminous_male", models, equipment, MEDIUM).key != male.key
		and high.key != male.key,
		"the key is stable for one record and follows the hairstyle and the quality")
	var female := Closure.closure(_record(61), "luminous_female", models, equipment, MEDIUM)
	expect((female.scenes as PackedStringArray).has(preload("res://src/actors/female_shirt_neckline.gd").REPAIRED)
		and (female.scenes as PackedStringArray)[0] == str(models.luminous_female.scene),
		"the native female body brings its repaired shirt mesh")
	var bow := Closure.closure(_record(62, 0, BOW_LOADOUT), "luminous_male", models, equipment, MEDIUM)
	var bow_scenes: PackedStringArray = bow.scenes
	var bow_scene := str(ReplicatedActor3D.equipment_model_config_for(equipment, models.luminous_male, 0, 165).scene)
	expect(bow_scenes.has(RangerBow3D.ARROW_PATH) and bow_scenes.has(RangerBow3D.DEFAULT_BOW)
		and bow_scenes.has(bow_scene) and bow_scenes.size() == 4 and (bow.rl_files as PackedStringArray).is_empty(),
		"a bow brings the ranged presentation's arrow and default bow; bald and bare slots add nothing: %s" % bow_scenes)
	var rabbit := Closure.closure({"actor_id": 63, "actor_type": 200, "kind": 5}, "rabbit", models, equipment, MEDIUM)
	expect(bool(rabbit.creature) and (rabbit.scenes as PackedStringArray).is_empty(),
		"a creature's scene is left to the creature job")
	expect((Closure.closure(_record(64), "no_such_model", models, equipment, MEDIUM).scenes as PackedStringArray).is_empty(),
		"an unknown model needs nothing")
	var retired: Dictionary = (models.luminous_male as Dictionary).duplicate(true)
	retired["retired"] = true
	expect((Closure.closure(_record(65), "retired_model", {"retired_model": retired}, equipment, MEDIUM).scenes
		as PackedStringArray).is_empty(), "a retired model draws nothing and needs nothing")
	expect(str(Closure.closure(_record(66), "luminous_male", models, equipment, MEDIUM,
		{"mode": "mounted", "mount_id": "moor_pony"}).mount) == "moor_pony", "the mount worn is reported")
	var record := _record(68)
	var first := Closure.memoized(record, "luminous_male", models, equipment, MEDIUM)
	expect(is_same(Closure.memoized(record, "luminous_male", models, equipment, MEDIUM), first)
		and first.key == male.key, "the memo answers a repeated ask with the same closure")
	(record.equipment_visuals as Dictionary)["4"] = 0
	var changed := Closure.memoized(record, "luminous_male", models, equipment, MEDIUM)
	expect(not is_same(changed, first) and not (changed.scenes as PackedStringArray).has(str(
		ReplicatedActor3D.equipment_model_config_for(equipment, models.luminous_male, 4, 171).scene)),
		"a changed wardrobe in the same record is a new closure (the memo keeps its own copy of the key)")
	expect(not is_same(Closure.memoized(record, "luminous_male", models, equipment, ActorRenderQuality.Quality.HIGH),
		changed), "another quality is another closure")


# --- the preparer -------------------------------------------------------------------

## Pumps frames until `done` is true; also tracks publication per frame.
func _pump(warmup: RefCounted, done: Callable, tracker: Dictionary = {}) -> bool:
	var deadline := Time.get_ticks_msec() + DEADLINE_MSEC
	var counts: Dictionary = {}
	while not bool(done.call()) and Time.get_ticks_msec() < deadline:
		var published := int((warmup.call("snapshot") as Dictionary).filesPublished)
		var frame := Engine.get_process_frames()
		counts[frame] = int(counts.get(frame, 0))
		var outbox: Array = warmup.get("_outbox")
		tracker["max_outbox"] = maxi(int(tracker.get("max_outbox", 0)), outbox.size())
		await process_frame
		warmup.call("poll")
		var now := Engine.get_process_frames()
		counts[now] = int(counts.get(now, 0)) + int((warmup.call("snapshot") as Dictionary).filesPublished) - published
		tracker["max_per_frame"] = maxi(int(tracker.get("max_per_frame", 0)), int(counts[now]))
	return bool(done.call())


func _pieces_equal(a: Array, b: Array) -> bool:
	if a.size() != b.size() or a.is_empty():
		return false
	for index: int in a.size():
		var x: Dictionary = a[index]
		var y: Dictionary = b[index]
		if not is_same(x.mesh, y.mesh) or x.name != y.name or x.transform != y.transform \
				or x.bones != y.bones or x.binds != y.binds or not is_same(x.material_override, y.material_override) \
				or x.lod_bias != y.lod_bias or x.cast_shadow != y.cast_shadow or x.body_cover != y.body_cover \
				or x.covers_hair != y.covers_hair or x.repair_quilt_paint != y.repair_quilt_paint \
				or x.match_antler_palette != y.match_antler_palette \
				or (x.surface_overrides as Array).size() != (y.surface_overrides as Array).size():
			return false
		for surface: int in (x.surface_overrides as Array).size():
			if not is_same(x.surface_overrides[surface], y.surface_overrides[surface]):
				return false
	return true


func _check_cold_closure() -> void:
	_cold()
	var warmup = Warmup.new()
	var closure := Closure.closure(_record(70), "luminous_male", models, equipment, MEDIUM)
	var scenes: PackedStringArray = closure.scenes
	expect(warmup.closure_enabled(), "the preparer is on by default (raw content, actor images on)")
	expect(not warmup.request_closure(closure, Warmup.PRIORITY_NEAR), "a cold closure is not ready")
	var pending := 0
	for path: String in scenes:
		if warmup.file_pending(path): pending += 1
	expect(pending == scenes.size(), "every file of it is queued or parsing (%d/%d)" % [pending, scenes.size()])
	var tracker := {}
	var started := Time.get_ticks_msec()
	var ready := await _pump(warmup, func() -> bool: return warmup.request_closure(closure, Warmup.PRIORITY_NEAR), tracker)
	var snapshot: Dictionary = warmup.snapshot()
	print("TIMING cold closure: %d files ready in %d ms; worker %.1f ms (max %.1f), main publish %.1f ms (max %.2f)" % [
		scenes.size(), Time.get_ticks_msec() - started, int(snapshot.workerUsec) / 1000.0,
		int(snapshot.maximumWorkerUsec) / 1000.0, int(snapshot.publishUsec) / 1000.0,
		int(snapshot.maximumPublishUsec) / 1000.0])
	expect(ready and GlbSceneCache.missing(scenes).is_empty(), "the worker prepares the whole closure into the session cache")
	expect(int(tracker.get("max_per_frame", 9)) <= 1, "main publishes at most one prepared file a frame (max %s)"
		% tracker.get("max_per_frame"))
	expect(int(tracker.get("max_outbox", 9)) <= Warmup.PUBLISH_QUEUE_LIMIT,
		"no more than %d parsed roots ever wait for publication" % Warmup.PUBLISH_QUEUE_LIMIT)
	expect(int(snapshot.filesPublished) == scenes.size() and int(snapshot.fallbacks) == 0
		and int(snapshot.piecesPublished) == (closure.pieces as PackedStringArray).size(),
		"every file is published by the preparer with its pieces, none left to main: %s" % snapshot)
	var equal := true
	for path: String in (closure.pieces as PackedStringArray):
		var installed: Array = ReplicatedActor3D._equipment_pieces(path)
		var instance := GlbSceneCache.instantiate(path)
		var fresh := ReplicatedActor3D.equipment_pieces_from(instance, path)
		instance.free()
		equal = equal and ReplicatedActor3D.has_equipment_pieces(path) and _pieces_equal(installed, fresh)
	expect(equal, "the worker's pieces equal pieces read from an instance of the published scene (same meshes, materials, binds)")
	expect(warmup.request_closure(closure, Warmup.PRIORITY_NEAR) and warmup.is_idle(), "a ready closure stays ready; the preparer is idle")
	expect(not ReplicatedActor3D.install_equipment_pieces((closure.pieces as PackedStringArray)[0], [{"mesh": null}]),
		"installed pieces are never replaced")


func _check_blocked_main() -> void:
	_cold()
	var warmup = Warmup.new()
	var cuirass := str(ReplicatedActor3D.equipment_model_config_for(equipment, models.luminous_female, 5, 184).scene)
	var closure := {"scenes": PackedStringArray([cuirass]), "pieces": PackedStringArray([cuirass])}
	expect(not warmup.request_closure(closure), "an equipment file with URI textures is queued")
	var thread: Thread = warmup.get("_thread")
	OS.delay_msec(2500) # main serves nothing meanwhile
	expect(thread != null and not thread.is_alive(),
		"the worker parsed it and read its pieces while the main thread was blocked for 2.5 s (it waits for nothing)")
	expect(await _pump(warmup, func() -> bool: return warmup.request_closure(closure)) \
		and ReplicatedActor3D.has_equipment_pieces(cuirass), "and it is published once main runs")


func _check_priority() -> void:
	_cold()
	var warmup = Warmup.new()
	var crowd := Closure.closure(_record(80, 4), "luminous_female", models, equipment, MEDIUM)
	var target_path := str(ReplicatedActor3D.equipment_model_config_for(equipment, models.luminous_male, 0, 165).scene)
	var target := {"scenes": PackedStringArray([target_path]), "pieces": PackedStringArray([target_path])}
	expect(not (crowd.scenes as PackedStringArray).has(target_path), "fixture: the target's file is not in the crowd closure")
	warmup.request_closure(crowd, Warmup.PRIORITY_OTHER)
	warmup.request_closure(target, Warmup.PRIORITY_TARGET)
	var order: Array = []
	var all := PackedStringArray(crowd.scenes)
	all.append(target_path)
	await _pump(warmup, func() -> bool:
		for path: String in all:
			if not order.has(path) and GlbSceneCache.missing(PackedStringArray([path])).is_empty():
				order.append(path)
		return order.size() == all.size())
	expect(order.find(target_path) >= 0 and order.find(target_path) <= 1,
		"a target's file goes before the crowd's queued files (only the one already parsing is ahead): %s"
		% [order.find(target_path)])
	_cold()
	var raised = Warmup.new()
	raised.request_closure(crowd, Warmup.PRIORITY_OTHER)
	raised.request_closure(crowd, Warmup.PRIORITY_TARGET)
	var queue: Array = raised.get("_queue")
	var all_target := not queue.is_empty()
	for job: Dictionary in queue:
		all_target = all_target and int(job.priority) == Warmup.PRIORITY_TARGET
	expect(all_target and int(raised.snapshot().priorityRaises) >= queue.size(),
		"asking again more urgently raises the queued files")
	raised.clear()
	await _pump(raised, func() -> bool: return raised.is_idle())


func _check_fallbacks_and_switch() -> void:
	_cold()
	var warmup = Warmup.new()
	# A retired actor file (the worker answers "retired") and a file outside
	# the actor folders ("not_actor_document"); neither is parsed anywhere here.
	var retired_file := "res://assets/actors/native/equipment/amberglass_legs.glb"
	var foreign := "res://data/aw04a_not_an_actor.glb"
	var closure := {"scenes": PackedStringArray([retired_file, foreign]), "pieces": PackedStringArray([retired_file])}
	expect(not warmup.request_closure(closure), "files the worker cannot prepare are asked for like any other")
	var ready := await _pump(warmup, func() -> bool: return warmup.request_closure(closure))
	var snapshot: Dictionary = warmup.snapshot()
	expect(ready and int(snapshot.fallbackFiles) == 2 and int(snapshot.filesPublished) == 0
		and not warmup.file_pending(retired_file),
		"a retired file and one outside the actor folders are left to the main thread: %s" % snapshot)
	OS.set_environment(Warmup.SWITCH_ENVIRONMENT, "off")
	var off = Warmup.new()
	var male := Closure.closure(_record(90), "luminous_male", models, equipment, MEDIUM)
	expect(not off.closure_enabled() and off.request_closure(male) and off.is_idle()
		and (off.get("_queue") as Array).is_empty() and str(off.snapshot().closures) == "switch",
		"ELORIA_ACTOR_PREPARER=off: every closure is ready at once, nothing is queued (main parses as before)")
	OS.unset_environment(Warmup.SWITCH_ENVIRONMENT)


func _check_clear() -> void:
	_cold()
	var warmup = Warmup.new()
	# Without its RL file: RLHeadLibrary's own worker would publish that one.
	var closure := Closure.closure(_record(100), "luminous_male", models, equipment, MEDIUM)
	closure["rl_files"] = PackedStringArray()
	warmup.request_closure(closure)
	var active: Thread = warmup.get("_thread")
	expect(active != null, "a job is running")
	warmup.clear()
	var idle := await _pump(warmup, func() -> bool: return warmup.is_idle())
	expect(idle and GlbSceneCache.cached_scene_count() == 0 and int(warmup.snapshot().discarded) >= 1
		and not ReplicatedActor3D.has_equipment_pieces((closure.pieces as PackedStringArray)[0]),
		"clear() discards the running job's result and the queue: nothing is published afterwards")


## The player's own body built at once on main (with no curtain up; AW-04d)
## can parse a file the worker is parsing for a remote closure. The cache keeps main's
## scene; the worker's root is freed unpublished, counted as already cached
## (not published), and no pieces are installed from it (they would hold
## another parse's meshes).
func _check_main_parsed_meanwhile() -> void:
	_cold()
	var warmup = Warmup.new()
	var hair := ReplicatedActor3D.hair_scene_for(models.luminous_male as Dictionary, 2)
	var closure := {"scenes": PackedStringArray([hair]), "pieces": PackedStringArray([hair])}
	expect(not hair.is_empty() and not warmup.request_closure(closure) and warmup.get("_thread") != null,
		"fixture: the worker parses a hairstyle for a remote closure")
	var instance := GlbSceneCache.instantiate(hair) # main parses the same file meanwhile
	expect(instance != null, "fixture: main parsed the same file itself")
	if instance != null:
		instance.free()
	var ready := await _pump(warmup, func() -> bool: return warmup.request_closure(closure) and warmup.is_idle())
	var snapshot: Dictionary = warmup.snapshot()
	expect(ready and int(snapshot.filesPublished) == 0 and int(snapshot.get("alreadyCached", 0)) == 1
		and int(snapshot.fallbacks) == 0 and int(snapshot.piecesPublished) == 0
		and not ReplicatedActor3D.has_equipment_pieces(hair),
		"a file main cached meanwhile is not published again and installs no pieces from the worker's root: %s"
		% snapshot)
	var pieces := ReplicatedActor3D._equipment_pieces(hair)
	var check := GlbSceneCache.instantiate(hair)
	var fresh := ReplicatedActor3D.equipment_pieces_from(check, hair) if check != null else []
	if check != null:
		check.free()
	expect(_pieces_equal(pieces, fresh), "its pieces are read from the scene the cache kept")


## A preparer freed while its file job runs (Main freed without clear() and
## is_idle(), as some tests and tools do) joins that job, which waits for
## nothing on the main thread, instead of leaving GDScript running on a worker
## into engine teardown; nothing is published.
func _check_freed_while_parsing() -> void:
	_cold()
	var warmup = Warmup.new()
	var closure := Closure.closure(_record(105), "luminous_male", models, equipment, MEDIUM)
	closure["rl_files"] = PackedStringArray()
	warmup.request_closure(closure)
	var thread: Thread = warmup.get("_thread")
	expect(thread != null and thread.is_started(), "fixture: a file job is running")
	warmup = null # the last reference: NOTIFICATION_PREDELETE
	var joined := thread != null and not thread.is_started()
	if thread != null and thread.is_started():
		var left: Variant = thread.wait_to_finish()
		if left is Dictionary:
			GlbSceneCache.discard_actor_prepared(left as Dictionary)
	expect(joined and GlbSceneCache.cached_scene_count() == 0,
		"a preparer freed while its file job runs joins it (it waits for nothing) and publishes nothing")


# --- a body built after its closure ---------------------------------------------------

func _mesh_signature(actor: ReplicatedActor3D) -> Dictionary:
	var out := {}
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := node as MeshInstance3D
		if mesh_node.mesh == null or not mesh_node.is_visible_in_tree():
			continue
		var key := str(actor.get_path_to(mesh_node))
		var surfaces: Array = []
		var mesh := mesh_node.mesh
		for surface: int in mesh.get_surface_count():
			var material := mesh_node.get_active_material(surface)
			var textures: Array = []
			if material is BaseMaterial3D:
				var texture := (material as BaseMaterial3D).albedo_texture
				textures.append(texture.resource_path if texture != null and not texture.resource_path.is_empty()
					else (texture.get_size() if texture != null else Vector2.ZERO))
			surfaces.append([hash(mesh.surface_get_arrays(surface)) if mesh is ArrayMesh else 0,
				material.get_class() if material != null else "", textures])
		out[key] = [surfaces, mesh_node.skin.get_bind_count() if mesh_node.skin != null else 0]
	return out


func _check_build_equals_main_parse() -> void:
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0})
	var config: Dictionary = models.luminous_male
	var record := _record(110)
	# A: main parses every file (the preparer's switch off, cold caches).
	_cold()
	var misses := _misses()
	var main_built := ReplicatedActor3D.new()
	root.add_child(main_built)
	main_built.apply_render_quality(MEDIUM, false)
	var started := Time.get_ticks_usec()
	main_built.configure(record, adapter, config, _animation(config), equipment, true)
	var main_usec := Time.get_ticks_usec() - started
	var main_phases := main_built.configuration_timings_usec()
	var main_misses := _misses() - misses
	await process_frame
	var reference := _mesh_signature(main_built)
	main_built.free()
	# B: the preparer first, then the same build.
	_cold()
	var warmup = Warmup.new()
	var closure := Closure.closure(record, "luminous_male", models, equipment, MEDIUM)
	await _pump(warmup, func() -> bool: return warmup.request_closure(closure))
	misses = _misses()
	var prepared := ReplicatedActor3D.new()
	root.add_child(prepared)
	prepared.apply_render_quality(MEDIUM, false)
	started = Time.get_ticks_usec()
	prepared.configure(record, adapter, config, _animation(config), equipment, true)
	var prepared_usec := Time.get_ticks_usec() - started
	var phases := prepared.configuration_timings_usec()
	var prepared_misses := _misses() - misses
	await process_frame
	print("TIMING remote Human build on main: main-parsed %.1f ms (model_scene %.1f, equipment %.1f), "
		% [main_usec / 1000.0, int(main_phases.get("model_scene", 0)) / 1000.0, int(main_phases.get("equipment", 0)) / 1000.0]
		+ "prepared %.1f ms (model_scene %.1f, equipment %.1f); cache misses %d -> %d"
		% [prepared_usec / 1000.0, int(phases.get("model_scene", 0)) / 1000.0, int(phases.get("equipment", 0)) / 1000.0,
			main_misses, prepared_misses])
	expect(main_misses >= (closure.scenes as PackedStringArray).size() - 1,
		"fixture: a cold build parses its files on main (%d misses)" % main_misses)
	expect(prepared_misses == 0, "a body built after its closure is ready parses nothing on the main thread")
	var signature := _mesh_signature(prepared)
	expect(not signature.is_empty() and signature == reference,
		"it equals the body built from main's parses: the same %d visible meshes, geometry, materials and textures"
		% signature.size())
	prepared.free()


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
	# In the world, as after LOG_IN_OK: the body gate runs while the game view
	# is shown (Main's frames drain the preparer then).
	main.game_view.show()
	app.death = {}
	app.local_actor_id = LOCAL
	app.selected_actor_id = -1
	app.combat_state = {}
	app.campaign = {}
	app.current_map = "landfall"
	main.adapter = CoordinateAdapter.new({"walkingHeight": 0.025, "invertServerY": true})


func _node(id: int) -> ReplicatedActor3D:
	var value: Variant = main.actor_nodes.get(id)
	return value as ReplicatedActor3D if is_instance_valid(value) else null


## Main's per-frame body building, as `_process` runs it (with a fresh
## creation frame: under this script the process frame Main reads may repeat).
func _main_builds_until(done: Callable, candidates: Array = []) -> bool:
	var deadline := Time.get_ticks_msec() + DEADLINE_MSEC
	while not bool(done.call()) and Time.get_ticks_msec() < deadline:
		main.set("_actor_creation_frame", -1)
		if not candidates.is_empty():
			main.crowd.set_candidates(candidates)
		main.call("_update_model_builds")
		await process_frame
	return bool(done.call())


func _check_main_gate() -> void:
	# Main's start applied the saved quality; Medium is where portrait Humans
	# draw RL hairstyle modules (rl_files). High follows below.
	LookProfile.set_player_quality(MEDIUM)
	_cold()
	main.actor_resource_warmup.clear()
	await _pump(main.actor_resource_warmup, func() -> bool: return main.actor_resource_warmup.is_idle())
	var me := _record(LOCAL, 1, {"0": 0}, "Me", 1, 0, 0)
	var remote := _record(2, 5, CAPE_LOADOUT, "Passer", 1, 3, 4)
	app.actors = {LOCAL: me, 2: remote}
	var misses := _misses()
	main.set("_actor_creation_frame", -1)
	main.game_view.hide()
	expect(bool(main.call("_remote_model_ready", 2))
		and (main.actor_resource_warmup.get("_files") as Dictionary).is_empty(),
		"with the game view hidden (no frame drains the preparer) a remote body is built at once, as before AW-04a")
	main.game_view.show()
	expect(bool(main.call("_remote_model_ready", LOCAL)),
		"with no curtain up the player's own body is built at once (AW-04d gates it behind the curtain)")
	expect(not bool(main.call("_remote_model_ready", 2)), "a first-seen remote Human waits for its closure")
	main.call("_spawn_arrivals", [2])
	var waiting := _node(2)
	expect(waiting != null and waiting.is_model_deferred(), "it gets a deferred node (its stand-in) meanwhile")
	var files: Dictionary = main.actor_resource_warmup.get("_files")
	var near := not files.is_empty()
	for job: Dictionary in files.values():
		near = near and int(job.priority) == Warmup.PRIORITY_NEAR
	expect(near, "its files are queued at the build-radius class")
	var started := Time.get_ticks_msec()
	var built := await _main_builds_until(func() -> bool:
		return _node(2) != null and not _node(2).is_model_deferred(), [[5.0, 2]])
	print("TIMING Main remote Human: body built %d ms after arrival (headless)" % (Time.get_ticks_msec() - started))
	expect(built, "once the closure is ready the build candidates give it its body")
	expect(_misses() - misses == 0, "the remote body was built without a main-thread glTF parse")
	var row: Dictionary = main.call("client_diagnostic_snapshot")
	expect(row.has("actor_preparer") and int((row.actor_preparer as Dictionary).get("filesPublished", 0)) > 0
		and str((row.actor_preparer as Dictionary).get("closures", "")) == "on",
		"the diagnostics snapshot carries the preparer's counters: %s" % row.get("actor_preparer", {}))
	# What the gate costs Main for a body whose closure is ready (every caller
	# asks it once per candidate pass): the presented record, the closure, the
	# cache lookups and RLHeadLibrary's check.
	var calls := 200
	var ready_all := true
	var began := Time.get_ticks_usec()
	for index: int in calls:
		ready_all = bool(main.call("_remote_model_ready", 2)) and ready_all
	print("TIMING Main remote gate for a ready Human: %.1f us a call (headless, %d calls)"
		% [float(Time.get_ticks_usec() - began) / calls, calls])
	expect(ready_all, "a built Human's closure stays ready")
	# The selection: its files go first, and the priority path builds it.
	var selected := _record(3, 6, {"0": 165, "3": 117, "5": 184}, "Picked", 1, 6, 4)
	app.actors[3] = selected
	app.selected_actor_id = 3
	main.set("_actor_creation_frame", -1)
	main.call("_spawn_arrivals", [3])
	var picked := _node(3)
	var target_class := false
	for job: Dictionary in (main.actor_resource_warmup.get("_files") as Dictionary).values():
		target_class = target_class or int(job.priority) == Warmup.PRIORITY_TARGET
	expect(picked != null and picked.is_model_deferred() and target_class,
		"the selected actor waits too, its files at the target class")
	misses = _misses()
	built = await _main_builds_until(func() -> bool: return _node(3) != null and not _node(3).is_model_deferred())
	expect(built and _misses() - misses == 0, "the priority path builds it once ready, with no main-thread parse")
	app.selected_actor_id = -1
	# High, with RL heads deferred as in a window (a headless process builds them
	# at once): the body draws the classic head and the game hairstyle while
	# RLHeadLibrary parses the RL files on its worker, so the closure names the
	# game hairstyle and the build parses nothing on main.
	LookProfile.set_player_quality(ActorRenderQuality.Quality.HIGH)
	var deferral := RLHeadLibrary.deferred_loading
	RLHeadLibrary.deferred_loading = 1
	var high := _record(6, 7, {"0": 164, "4": 171, "5": 185}, "Tall", 1, 9, 3)
	app.actors[6] = high
	main.set("_actor_creation_frame", -1)
	expect(not bool(main.call("_remote_model_ready", 6)), "at High a first-seen Human waits for its closure too")
	main.call("_spawn_arrivals", [6])
	misses = _misses()
	built = await _main_builds_until(func() -> bool: return _node(6) != null and not _node(6).is_model_deferred(),
		[[5.0, 6]])
	expect(built and _misses() - misses == 0, "at High it is built once ready, with no main-thread parse")
	RLHeadLibrary.deferred_loading = deferral
	LookProfile.set_player_quality(MEDIUM)
	# A creature keeps its creature job.
	var fox := {"actor_id": 4, "actor_type": 212, "kind": 5, "name": "Red Fox", "x": 2, "y": 2,
		"rotation": 0, "health": 5, "max_health": 5, "alive": true}
	app.actors[4] = fox
	var model_id := str(main.call("_model_for_actor", fox))
	var first := bool(main.call("_remote_model_ready", 4))
	var ready := await _main_builds_until(func() -> bool: return bool(main.call("_remote_model_ready", 4)))
	expect(str((models.get(model_id, {}) as Dictionary).get("scene", "")).begins_with(Closure.CREATURE_ROOT)
		and not first and ready and NativeAnimationImporter.cached_library_count() > 0,
		"a creature (%s) still waits for its creature job, scene and clips" % model_id)
	# The kill switch: the remote gate answers at once, main parses as before.
	_cold()
	OS.set_environment(Warmup.SWITCH_ENVIRONMENT, "off")
	var previous: RefCounted = main.actor_resource_warmup
	main.actor_resource_warmup = Warmup.new()
	var switched: RefCounted = main.actor_resource_warmup
	var other := _record(5, 7, {"0": 114, "4": 171}, "Other", 1, 8, 8)
	app.actors[5] = other
	Closure.clear_memo()
	expect(bool(main.call("_remote_model_ready", 5)) and (Closure._memo as Dictionary).is_empty()
		and int((switched.call("snapshot") as Dictionary).closureRequests) == 0,
		"with ELORIA_ACTOR_PREPARER=off a remote body is ready at once, and Main computes no closure for it")
	var creature_waits := not bool(main.call("_remote_model_ready", 4))
	var switched_row: Dictionary = switched.call("snapshot")
	expect(creature_waits and (int(switched_row.queuedCreatures) == 1 or str(switched_row.active) == "creature")
		and int(switched_row.queuedFiles) == 0,
		"with it off a creature keeps its creature job, as before the preparer: %s" % switched_row)
	switched.call("clear")
	await _pump(switched, func() -> bool: return bool(switched.call("is_idle")))
	OS.unset_environment(Warmup.SWITCH_ENVIRONMENT)
	main.actor_resource_warmup = previous


func _cleanup() -> void:
	# The RL library's worker parses (requested RL files) finish before quit:
	# a process that quits while a worker parses can hang.
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
