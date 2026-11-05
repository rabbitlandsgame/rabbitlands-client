extends SceneTree
## FIX-MEM (memory classes, stage-B follow-up): GlbSceneCache drops the world
## models only worlds the player has left used, once nothing holds them, and
## WorldPark says which worlds those are (glb_scene_cache.gd "World scenery",
## world_park.gd "Scenery of worlds left behind").
##
## Real underground models parsed raw (no prepared content, no geometry
## cache), explicit clocks, no renderer. Run headless:
##   Godot --headless --log-file <log> --path godot-client --script res://tests/test_world_scenery_release.gd
const WorldParkScript := preload("res://src/world/world_park.gd")
const SceneryStepper := preload("res://src/world/interior_scenery_stepper.gd")
const MemoryBudgets := preload("res://src/runtime/memory_budgets.gd")
const ROOT := "res://assets/world/underground/"
const A := ROOT + "crystal_cluster.glb"
const B := ROOT + "shell_scree.glb"
const C := ROOT + "vein_scree_1.glb"
const D := ROOT + "vein_scree_2.glb"
const HAIR := "res://assets/actors/native/hair/bob_female.glb"
const MIB := 1 << 20
## Far enough past every row's last use that the grace never holds a row.
const LATER := 1 << 40

var failures := 0
var _environment := {}

func _init() -> void:
	run.call_deferred()

func expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: " + message)
	else:
		failures += 1
		push_error("FAIL: " + message)

func info(message: String) -> void:
	print("INFO: " + message)

func key(path: String) -> String:
	return GlbSceneCache._canonical_path(path)

func row(path: String) -> Dictionary:
	return GlbSceneCache._ledger.get(key(path), {})

func cached(path: String) -> bool:
	return GlbSceneCache.missing(PackedStringArray([key(path)])).is_empty()

func owners(path: String) -> Array:
	return Array(GlbSceneCache.world_owners(path))

## A model placed and taken away again under `scope`: published (when new)
## and used by that world, no instance left.
func use(path: String, scope: String) -> void:
	GlbSceneCache.set_world_scope(scope)
	var instance := GlbSceneCache.instantiate(path)
	expect(instance != null, "%s builds raw" % path.get_file())
	if instance != null:
		instance.free()

func release(left: Array, allowance := 0, now := LATER, grace := GlbSceneCache.WORLD_RELEASE_GRACE_MSEC) -> Dictionary:
	var worlds := {}
	for world: String in left:
		worlds[world] = true
	return GlbSceneCache.release_left_worlds(worlds, allowance, now, 1 << 30, grace)

func set_environment(name: String, value: String) -> void:
	if not _environment.has(name):
		_environment[name] = OS.get_environment(name)
	OS.set_environment(name, value)

func restore_environment() -> void:
	for name: String in _environment:
		if str(_environment[name]).is_empty():
			OS.unset_environment(name)
		else:
			OS.set_environment(name, str(_environment[name]))

func run() -> void:
	# Raw parses only: every row is a main-thread build of the file itself.
	set_environment("RABBITLANDS_PREPARED_CONTENT", "raw")
	set_environment("ELORIA_NO_GEOMETRY_CACHE", "1")
	set_environment(WorldParkScript.SCENERY_RELEASE_ENVIRONMENT, "")
	NativeAnimationImporter.GltfQuantization.ensure_registered()
	NativeAnimationImporter.VramTextures.ensure_registered()
	NativeAnimationImporter.MapMeshExtension.ensure_registered()
	MemoryBudgets.override_for_tests(MemoryBudgets.SMALL)
	GlbSceneCache.clear()
	GlbSceneCache.set_budget_for_tests(1 << 40, 1 << 30)
	check_attribution()
	check_release()
	check_allowance()
	check_other_rows()
	check_off_main()
	check_progress()
	check_index()
	check_released_mark()
	check_mode_switch()
	await check_park_residency()
	await check_park_release()
	await check_medium_park()
	check_preload_scope()
	GlbSceneCache.clear()
	GlbSceneCache.set_world_scope("")
	GlbSceneCache.set_budget_for_tests()
	MemoryBudgets.reset()
	restore_environment()
	print("WORLD_SCENERY_RELEASE %s failures=%d" % ["PASS" if failures == 0 else "FAIL", failures])
	quit(1 if failures > 0 else 0)

# --------------------------------------------------------------------------
# GlbSceneCache
# --------------------------------------------------------------------------

func check_attribution() -> void:
	# No world named: the row has no owner and is never released.
	GlbSceneCache.clear()
	use(A, "")
	expect(owners(A).is_empty() and bool(row(A).world), "a world row published with no world named has no owner")
	var report := release(["cave", ""])
	expect(int(report.released) == 0 and cached(A), "a row no world was named for is never released")
	GlbSceneCache.clear()

	GlbSceneCache.set_world_scope("cave")
	var held := GlbSceneCache.instantiate(A)
	expect(owners(A) == ["cave"], "a row published while the cave is built belongs to the cave (%s)" % [owners(A)])
	expect(not (row(A).probes as Array).is_empty() and (row(A).baseline as PackedInt32Array).size() == (row(A).probes as Array).size(),
		"a world row takes mesh probes and their baseline when published (%d)" % (row(A).probes as Array).size())
	expect(GlbSceneCache._is_busy(row(A)), "an instance holds the row")
	held.free()
	expect(not GlbSceneCache._is_busy(row(A)), "the row is idle once its instance is freed")
	var duplicate_source := GlbSceneCache.instantiate(A)
	var copy := duplicate_source.duplicate()
	duplicate_source.free()
	expect(GlbSceneCache._is_busy(row(A)), "a duplicate of an instance holds the row too")
	copy.free()
	use(A, "town")
	expect(owners(A) == ["cave", "town"], "instantiating it in the town adds the town (%s)" % [owners(A)])
	var walk_began := Time.get_ticks_usec()
	var probes := GlbSceneCache._scene_probes(GlbSceneCache._scenes[key(A)] as PackedScene)
	info("probe walk of %s: %d us, %d probes" % [A.get_file(), Time.get_ticks_usec() - walk_began, probes.size()])

func check_release() -> void:
	GlbSceneCache.clear()
	use(A, "cave")
	use(A, "town")
	use(B, "town")
	use(C, "cave")
	GlbSceneCache.set_world_scope("cave")
	var held_d := GlbSceneCache.instantiate(D)
	GlbSceneCache.set_world_scope("landfall")
	var report := release(["cave"])
	expect(int(report.released) == 1 and not cached(C) and GlbSceneCache.world_released(C),
		"leaving the cave drops the model only the cave used, once idle (%s)" % [report])
	expect(cached(A) and cached(B), "a model the town also used, and the town's own, stay while the town is not left")
	expect(cached(D) and int(report.waiting) == 1, "a cave model an instance still holds waits (%s)" % [report])
	expect(int(report.released_bytes) > 0 or int(report.released_unmeasured) == 0,
		"a released row is measured first within the slice (%s)" % [report])

	# The grace: a row used just now waits.
	use(C, "cave")
	var last := int(row(C).last_used_msec)
	report = release(["cave"], 0, last + 500, 1000)
	expect(cached(C) and int(report.waiting) == 2, "a row used within the grace waits (%s)" % [report])
	report = release(["cave"], 0, last + 1000, 1000)
	expect(not cached(C) and int(report.released) == 1, "and goes once the grace has passed (%s)" % [report])

	held_d.free()
	report = release(["cave"])
	expect(not cached(D) and int(report.released) == 1, "the held model goes once its instance is freed (%s)" % [report])
	report = release(["cave", "town"])
	expect(not cached(A) and not cached(B) and int(report.released) == 2,
		"leaving the town as well drops the models the two shared and the town's (%s)" % [report])

	# A released model wanted again on a gameplay frame is built on main and
	# counted; its mark goes with the new publication.
	var before := int(GlbSceneCache.retention_snapshot().world_released_main_rebuilds)
	use(A, "landfall")
	var snapshot := GlbSceneCache.retention_snapshot()
	expect(int(snapshot.world_released_main_rebuilds) == before + 1 and not GlbSceneCache.world_released(A)
		and owners(A) == ["landfall"], "a released model built again is counted and belongs to its new world (%s)" % [owners(A)])
	for field: String in ["world_scope", "world_releases", "world_released_bytes", "world_released_unmeasured",
			"world_released_awaiting", "world_released_main_rebuilds", "world_release_passes",
			"world_retained_entries", "world_retained_bytes", "world_release_waiting"]:
		expect(snapshot.has(field), "retention_snapshot reports %s" % field)
	expect(str(snapshot.world_scope) == "landfall" and int(snapshot.world_releases) >= 5,
		"the snapshot names the world and counts the releases (%s, %d)" % [snapshot.world_scope, int(snapshot.world_releases)])
	GlbSceneCache.forget(A)
	expect(not cached(A) and owners(A).is_empty(), "forget drops a world row like any other")

func check_allowance() -> void:
	GlbSceneCache.clear()
	use(A, "cave")
	use(B, "cave")
	# A was used before B.
	(GlbSceneCache._ledger[key(A)] as Dictionary).last_used_msec = 1000
	(GlbSceneCache._ledger[key(B)] as Dictionary).last_used_msec = 2000
	var report := release(["cave"], 1 << 40)
	var bytes_a := int(row(A).bytes)
	var bytes_b := int(row(B).bytes)
	expect(int(report.released) == 0 and int(report.retained) == 2 and bytes_a > 0 and bytes_b > 0
		and int(report.retained_bytes) == bytes_a + bytes_b and int(report.unmeasured) == 0,
		"within the allowance the left world keeps its models, measured (%s; %d + %d)" % [report, bytes_a, bytes_b])
	report = release(["cave"], bytes_b)
	expect(not cached(A) and cached(B) and int(report.released) == 1 and int(report.released_bytes) == bytes_a
		and int(report.retained_bytes) == bytes_b,
		"over it the least recently used goes first, down to the allowance (%s)" % [report])
	report = release(["cave"], maxi(1, bytes_b - 1))
	expect(not cached(B) and int(report.released) == 1, "and the next while still over (%s)" % [report])
	var last := GlbSceneCache.retention_snapshot()
	expect(int(last.world_retained_entries) == 0 and int(last.world_retained_bytes) == 0,
		"the snapshot reports what the left worlds keep after the pass")

func check_other_rows() -> void:
	GlbSceneCache.clear()
	GlbSceneCache.set_world_scope("cave")
	var hair := GlbSceneCache.packed_scene(HAIR)
	expect(hair != null and not bool(row(HAIR).world) and owners(HAIR).is_empty(),
		"an actor row is not a world row")
	var report := release(["cave"])
	expect(cached(HAIR) and int(report.released) == 0, "the world release never touches actor rows (%s)" % [report])
	# A world scene found in the cache without a publication (a direct write)
	# gets a pruning row: no owner, never released.
	use(A, "cave")
	var packed := GlbSceneCache._scenes[key(A)] as PackedScene
	GlbSceneCache._erase_scene(key(A))
	GlbSceneCache._scenes[key(A)] = packed
	report = release(["cave"])
	expect(cached(A) and int(report.released) == 0 and not (GlbSceneCache._world_rows.get("cave", {}) as Dictionary).has(key(A)),
		"a scene cached without a publication is not released, and its stale index entry goes (%s)" % [report])
	GlbSceneCache._prune_ledger() # As the budget pass does.
	report = release(["cave"])
	expect(cached(A) and str(row(A).origin) == GlbSceneCache.ORIGIN_UNKNOWN and owners(A).is_empty()
		and int(report.released) == 0, "a world row without a publication is never released (%s)" % [report])
	# A row whose scene was replaced without a publication is pruned by the
	# pass, never dropped (dropping it would drop the replacement).
	GlbSceneCache.clear()
	use(A, "cave")
	var replacement := GlbSceneCache._build(key(A))
	GlbSceneCache._scenes[key(A)] = replacement
	report = release(["cave"])
	expect(int(report.released) == 0 and GlbSceneCache._scenes.get(key(A)) == replacement and row(A).is_empty(),
		"a row whose scene was replaced without a publication is pruned, not released (%s)" % [report])
	GlbSceneCache.clear()

func check_off_main() -> void:
	GlbSceneCache.clear()
	use(A, "cave")
	var thread := Thread.new()
	thread.start(func() -> Dictionary:
		GlbSceneCache.set_world_scope("worker")
		return GlbSceneCache.release_left_worlds({"cave": true}, 0, LATER, 1 << 30, 0))
	var report: Dictionary = thread.wait_to_finish()
	expect(int(report.released) == 0 and cached(A) and GlbSceneCache.world_scope() == "cave",
		"off the main thread the release and the scope do nothing")
	GlbSceneCache.clear()

## Review fix: a pass whose slice is gone before it drops anything (on a long
## ledger the prune and the scan alone can take it) still drops one due row;
## before, it dropped none and left "more" set, so a pass ran every frame for
## ever and nothing was released.
func check_progress() -> void:
	GlbSceneCache.clear()
	use(A, "cave")
	use(B, "cave")
	var report := GlbSceneCache.release_left_worlds({"cave": true}, 0, LATER, 0, 0)
	expect(int(report.released) == 1 and bool(report.more) and int(report.released_unmeasured) == 0,
		"a pass with no time left still drops one row, measured first (%s)" % [report])
	report = GlbSceneCache.release_left_worlds({"cave": true}, 0, LATER, 0, 0)
	expect(int(report.released) == 1 and not bool(report.more) and not cached(A) and not cached(B),
		"and the next pass the other (%s)" % [report])
	# The budget rule: one pending row is measured and, while over, dropped.
	use(A, "cave")
	use(B, "cave")
	(GlbSceneCache._ledger[key(A)] as Dictionary).last_used_msec = 1000
	(GlbSceneCache._ledger[key(B)] as Dictionary).last_used_msec = 2000
	report = GlbSceneCache.release_left_worlds({"cave": true}, 1, LATER, 0, 0)
	expect(int(report.released) == 1 and not cached(A) and cached(B) and bool(report.more),
		"under the budget rule a pass with no time left measures and drops the least recently used (%s)" % [report])
	report = GlbSceneCache.release_left_worlds({"cave": true}, 1, LATER, 0, 0)
	expect(int(report.released) == 1 and not cached(B), "and the next pass the other (%s)" % [report])
	GlbSceneCache.clear()

func tiny_scene() -> PackedScene:
	var top := Node3D.new()
	var mesh_node := MeshInstance3D.new()
	mesh_node.mesh = BoxMesh.new()
	top.add_child(mesh_node)
	mesh_node.owner = top
	var packed := PackedScene.new()
	packed.pack(top)
	top.free()
	return packed

## Review fix: a pass visits only the rows the left worlds used (the
## `_world_rows` index), never the whole ledger, and the index forgets what
## was released. Before, every pass pruned and walked the ledger: about 2.4 ms
## for 1,000 rows in this build (review probe), every frame while a burst
## lasted and every 5 s while any world was left.
func check_index() -> void:
	GlbSceneCache.clear()
	use(A, "cave")
	use(B, "town")
	var index: Dictionary = GlbSceneCache._world_rows
	expect((index.get("cave", {}) as Dictionary).has(key(A)) and (index.get("town", {}) as Dictionary).has(key(B))
		and not (index.get("cave", {}) as Dictionary).has(key(B)), "each world indexes the rows it used")
	use(A, "town")
	expect((index.get("town", {}) as Dictionary).has(key(A)), "a use in another world indexes the row there too")
	var report := release(["cave", "town"])
	expect(int(report.released) == 2 and not cached(A) and not cached(B), "both worlds' rows go (%s)" % [report])
	release(["cave", "town"])
	expect(not index.has("cave") and not index.has("town"), "the next pass forgets the released rows (%s)" % [index.keys()])
	GlbSceneCache.clear()
	GlbSceneCache.set_world_scope("landfall")
	for i: int in 1000:
		GlbSceneCache._put(key("res://assets/world/review_probe/m%d.glb" % i), tiny_scene(), GlbSceneCache.ORIGIN_MAIN)
	GlbSceneCache.set_world_scope("cave")
	use(C, "cave")
	var began := Time.get_ticks_usec()
	report = release(["cave"])
	var spent := Time.get_ticks_usec() - began
	info("release pass beside 1,000 rows of a resident world: %d us (%s)" % [spent, report])
	expect(int(report.released) == 1 and not cached(C) and GlbSceneCache._ledger.size() == 1000,
		"a pass beside 1,000 rows of a resident world drops only the left world's row (%s)" % [report])
	began = Time.get_ticks_usec()
	report = release(["cave"])
	spent = Time.get_ticks_usec() - began
	expect(spent < 1000 and int(report.released) == 0,
		"an idle pass beside a 1,000-row ledger does not walk it (%d us)" % spent)
	GlbSceneCache.clear()

## Review fix: `world_released` is about a model that is gone; one published
## again off the main thread (no ledger row, so the mark stays) is cached and
## is neither reported released nor counted as a rebuild when found.
func check_released_mark() -> void:
	GlbSceneCache.clear()
	use(A, "cave")
	release(["cave"])
	expect(GlbSceneCache.world_released(A) and not cached(A), "a released row is marked")
	var packed := GlbSceneCache._build(key(A))
	var thread := Thread.new()
	thread.start(func() -> void: GlbSceneCache.install_prepared({key(A): packed}))
	thread.wait_to_finish()
	expect(packed != null and cached(A) and not GlbSceneCache.world_released(A),
		"a model published again off the main thread is not reported released")
	var before := int(GlbSceneCache.retention_snapshot().world_released_main_rebuilds)
	var instance := GlbSceneCache.instantiate(A)
	expect(instance != null and int(GlbSceneCache.retention_snapshot().world_released_main_rebuilds) == before,
		"nor counted as a main-thread rebuild when it is found cached")
	if instance != null:
		instance.free()
	GlbSceneCache.clear()

# --------------------------------------------------------------------------
# WorldPark
# --------------------------------------------------------------------------

func check_mode_switch() -> void:
	set_environment(WorldParkScript.SCENERY_RELEASE_ENVIRONMENT, "")
	expect(WorldParkScript.scenery_release_mode(MemoryBudgets.SMALL) == WorldParkScript.SCENERY_RELEASE_ALL,
		"by default a small machine keeps no model of a left world")
	# The memory-class approval covers small machines only: medium and large
	# keep every model until logout, as before.
	for label: String in [MemoryBudgets.MEDIUM, MemoryBudgets.LARGE, ""]:
		expect(WorldParkScript.scenery_release_mode(label) == WorldParkScript.SCENERY_RELEASE_OFF,
			"by default a %s machine keeps every model (off)" % (label if not label.is_empty() else "classless"))
	for value: String in ["0", "off", "OFF"]:
		set_environment(WorldParkScript.SCENERY_RELEASE_ENVIRONMENT, value)
		expect(WorldParkScript.scenery_release_mode(MemoryBudgets.SMALL) == WorldParkScript.SCENERY_RELEASE_OFF
			and WorldParkScript.scenery_release_mode(MemoryBudgets.MEDIUM) == WorldParkScript.SCENERY_RELEASE_OFF,
			"%s turns it off on every class" % value)
	set_environment(WorldParkScript.SCENERY_RELEASE_ENVIRONMENT, "all")
	expect(WorldParkScript.scenery_release_mode(MemoryBudgets.MEDIUM) == WorldParkScript.SCENERY_RELEASE_ALL,
		"all forces nothing kept on medium too")
	set_environment(WorldParkScript.SCENERY_RELEASE_ENVIRONMENT, "budget")
	expect(WorldParkScript.scenery_release_mode(MemoryBudgets.SMALL) == WorldParkScript.SCENERY_RELEASE_BUDGET,
		"budget forces the budget rule on small too")
	set_environment(WorldParkScript.SCENERY_RELEASE_ENVIRONMENT, "")

func new_park() -> Node:
	var park: Node = WorldParkScript.new()
	root.add_child(park)
	park.configure({})
	park.scenery_release_grace_msec = 0
	return park

func check_park_residency() -> void:
	var park := new_park()
	expect(str(park.scenery_release) == WorldParkScript.SCENERY_RELEASE_ALL
		and str((park.events.back() as Dictionary).get("scenery_release", "")) == "all",
		"configure sets and records the scenery release (small: all)")
	var loader := WorldLoader.new() # No world: nothing to park.
	park.leave(null, "", "landfall")
	expect(GlbSceneCache.world_scope() == "landfall" and str(park._arriving) == "landfall" and park.left_worlds().is_empty(),
		"the first arrival names its world")
	park.bind_map("landfall")
	expect(GlbSceneCache.world_scope() == "landfall" and str(park._arriving) == "", "binding names the bound map")
	park.leave(loader, "landfall", "cave")
	expect(park.left_worlds() == ["landfall"] and GlbSceneCache.world_scope() == "cave",
		"a map change that keeps nothing leaves the map left (%s)" % [park.left_worlds()])
	park.bind_map("cave")
	park.leave(null, "cave", "cave_east")
	expect(park.left_worlds() == ["landfall"] and park._crossed.has("cave"),
		"a seamless crossing does not leave the map it crossed from")
	park.bind_map("cave_east")
	park.leave(loader, "cave_east", "town")
	var left: Array = park.left_worlds()
	left.sort()
	expect(left == ["cave", "cave_east", "landfall"] and park._crossed.is_empty(),
		"the next change that is not seamless leaves it too (%s)" % [left])
	park.bind_map("town")
	park.leave(loader, "town", "landfall")
	left = park.left_worlds()
	left.sort()
	expect(left == ["cave", "cave_east", "town"], "arriving on a left map makes it resident again (%s)" % [left])
	park.bind_map("landfall")
	# Parked and preloading worlds are resident.
	park._parked["cave"] = {"resident": {}, "at_msec": park._now(), "bytes": 0}
	park._preload = {"map": "town", "state": "running"}
	park.release_scenery_now()
	left = park.left_worlds()
	expect(left == ["cave_east"], "a parked and a preloading world are not left (%s)" % [left])
	park._parked.erase("cave")
	park._preload = {}
	# A tree the park frees counts as left; a dropped preload too.
	var tree := Node3D.new()
	park._retire_tree(tree, "refused_cave", "budget")
	expect(park.left_worlds().has("refused_cave"), "a world the park frees is left")
	park._preload = {"map": "dropped_room", "state": "running", "thread": null}
	park._drop_preload("far")
	expect(park.left_worlds().has("dropped_room"), "a dropped preload's world is left")
	await _drain(park)
	var snapshot: Dictionary = park.diagnostic_snapshot()
	expect(str(snapshot.scenery_release) == "all" and (snapshot.left as Array).has("dropped_room")
		and snapshot.has("crossed") and snapshot.has("arriving"), "the diagnostics snapshot carries the release state")
	loader.free()
	park.queue_free()
	await process_frame

func _drain(park: Node) -> void:
	for frame: int in 200:
		if park.retiring_count() == 0:
			return
		await process_frame

func check_park_release() -> void:
	GlbSceneCache.clear()
	var park := new_park()
	expect(int(park.budget_bytes) == 384 * MIB, "the park runs as small (384 MiB)")
	# The budget rule (ELORIA_WORLD_SCENERY_RELEASE=budget; forced here on small).
	park.scenery_release = WorldParkScript.SCENERY_RELEASE_BUDGET
	park.leave(null, "", "cave")
	park.bind_map("cave")
	use(A, GlbSceneCache.world_scope())
	use(B, GlbSceneCache.world_scope())
	GlbSceneCache.set_world_scope("cave")
	var loader := WorldLoader.new()
	park.leave(loader, "cave", "landfall")
	park.bind_map("landfall")
	# Small: what the 384 MiB budget leaves (nothing is kept) holds both models.
	var report: Dictionary = park.release_scenery_now()
	expect(int(report.released) == 0 and int(report.retained) == 2 and cached(A) and cached(B)
		and int(report.allowance) == 384 * MIB, "within the class budget a left world keeps its models (%s)" % [report])
	# A parked world takes that room first: the left world's models go, least
	# recently used first, down to what is left.
	(GlbSceneCache._ledger[key(A)] as Dictionary).last_used_msec = 1000
	(GlbSceneCache._ledger[key(B)] as Dictionary).last_used_msec = 2000
	var bytes_b := int(row(B).bytes)
	park._parked["town"] = {"resident": {}, "at_msec": park._now(), "bytes": int(park.budget_bytes) - bytes_b}
	report = park.release_scenery_now()
	expect(not cached(A) and cached(B) and int(report.released) == 1 and int(report.allowance) == bytes_b,
		"a parked world's bytes shrink what a left world keeps (%s)" % [report])
	park._parked.erase("town")
	report = park.release_scenery_now()
	var released: Array = park.events.filter(func(e: Dictionary) -> bool: return str(e.event) == "scenery_released")
	expect(int(report.released) == 0 and released.size() == 1 and int(released[0].released) == 1
		and (released[0].left as Array) == ["cave"], "a burst of releases is recorded once when it ends (%s)" % [released])
	# All: everything the left world used goes.
	park.scenery_release = WorldParkScript.SCENERY_RELEASE_ALL
	report = park.release_scenery_now()
	expect(not cached(B) and int(report.released) == 1 and int(report.allowance) == 0,
		"with ELORIA_WORLD_SCENERY_RELEASE=all nothing is kept (%s)" % [report])
	# Off: nothing goes.
	use(C, "cave")
	park.scenery_release = WorldParkScript.SCENERY_RELEASE_OFF
	report = park.release_scenery_now()
	expect(report.is_empty() and cached(C), "off keeps every model")
	park.scenery_release = WorldParkScript.SCENERY_RELEASE_ALL
	# Going back: the cave is resident again and keeps its model.
	park.leave(loader, "landfall", "cave")
	report = park.release_scenery_now()
	expect(cached(C) and not park.left_worlds().has("cave"), "a world entered again keeps what is left of its models")
	park.bind_map("cave")
	# The pass runs from tick() when due: freed with the next pass.
	park.leave(loader, "cave", "landfall")
	park.bind_map("landfall")
	park._release_due_msec = 0
	park.tick()
	expect(not cached(C), "tick runs the pass when one is due")
	# The burst C opened is still open; going back in (a seamless crossing, so
	# nothing else is left) records it then.
	var recorded: int = park.events.filter(func(e: Dictionary) -> bool: return str(e.event) == "scenery_released").size()
	park.leave(null, "landfall", "cave")
	park.release_scenery_now()
	var bursts: Array = park.events.filter(func(e: Dictionary) -> bool: return str(e.event) == "scenery_released")
	expect(bursts.size() == recorded + 1 and int(bursts.back().released) == 1 and park.left_worlds().is_empty(),
		"a burst still open when its world is entered again is recorded then (%s)" % [bursts.back() if not bursts.is_empty() else {}])
	loader.free()
	park.queue_free()
	await process_frame
	GlbSceneCache.clear()

## Review fix: medium (and large) keep today's behaviour by default - the
## memory-class approval covers small machines only - so a left world's
## models stay and no release pass runs.
func check_medium_park() -> void:
	GlbSceneCache.clear()
	MemoryBudgets.override_for_tests(MemoryBudgets.MEDIUM)
	var park := new_park()
	expect(str(park.scenery_release) == WorldParkScript.SCENERY_RELEASE_OFF
		and str((park.events.back() as Dictionary).get("scenery_release", "")) == "off",
		"a medium park keeps every model (off) and records it")
	park.leave(null, "", "cave")
	park.bind_map("cave")
	use(A, GlbSceneCache.world_scope())
	var loader := WorldLoader.new()
	park.leave(loader, "cave", "landfall")
	park.bind_map("landfall")
	var passes := int(GlbSceneCache.retention_snapshot().world_release_passes)
	park._release_due_msec = 0
	park.tick()
	var report: Dictionary = park.release_scenery_now()
	expect(report.is_empty() and cached(A) and owners(A) == ["cave"]
		and int(GlbSceneCache.retention_snapshot().world_release_passes) == passes,
		"on medium a left world keeps its models and no release pass runs")
	loader.free()
	park.queue_free()
	await process_frame
	MemoryBudgets.override_for_tests(MemoryBudgets.SMALL)
	GlbSceneCache.clear()

func check_preload_scope() -> void:
	GlbSceneCache.clear()
	var park := new_park()
	park.bind_map("landfall")
	var room := Node3D.new()
	var config := {"map": "room", "assets": {"a": A},
		"placements": [{"asset": "a", "position": [0.0, 0.0, 0.0]}]}
	var stepper := SceneryStepper.new("room", room, {}, config)
	park._preload = {"map": "room", "state": "publishing", "stepper": stepper, "resident": {"root": room},
		"bytes": 0, "worker_usec": 0, "publish_usec": 0, "max_slice_usec": 0, "slices": 0, "ready_msec": -1}
	park._publish_slice(0)
	expect(str(park._preload.state) == "ready" and stepper.count == 1, "the fake preload publishes its one placement")
	expect(owners(A) == ["room"] and GlbSceneCache.world_scope() == "landfall",
		"a preload's models belong to its interior, and the scope is restored (%s)" % [owners(A)])
	park._preload = {}
	room.free()
	park.queue_free()
	GlbSceneCache.clear()
