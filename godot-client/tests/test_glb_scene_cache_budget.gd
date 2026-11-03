extends SceneTree
## MEM-M5 (memory classes, owner decision 10): GlbSceneCache's byte ledger and
## creature budget, the warm-up's re-preparation of an evicted creature, and
## the session-end clear of ReplicatedActor3D's static caches.
##
## Uses two real creature GLBs (rabbit, cerberus) parsed raw, as releases do
## (the creature folder carries .gdignore), and a lowered budget with explicit
## clocks, so nothing waits for the class's real idle age. Run headless:
##   Godot --headless --log-file <log> --path godot-client --script res://tests/test_glb_scene_cache_budget.gd
const Warmup := preload("res://src/actors/actor_resource_warmup.gd")
const MemoryBudgets := preload("res://src/runtime/memory_budgets.gd")
const ResourceBytes := preload("res://src/runtime/resource_bytes.gd")
const CREATURES: Array[String] = ["rabbit", "cerberus"]
const HAIR := "res://assets/actors/native/hair/bob_female.glb"
const MISSING_CREATURE := "res://assets/actors/native/creatures/__mem_m5_never_present__.glb"
## No surprise evictions from the cache's own timer while a part sets up.
const HUGE := 1 << 40
## The seven session caches main.gd's _clear_world_presentation must empty
## through ReplicatedActor3D.clear_static_caches() (hook for A2).
const STATIC_CACHES: Array[String] = ["_equipment_pieces_cache", "_rebound_skins", "_drape_envelopes",
	"_draped_capes", "_torso_reaches", "_fabric_lines", "_shin_reaches"]

var failures := 0
var registry: Dictionary

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

func scene_path(name: String) -> String:
	return ProjectSettings.globalize_path(str(registry.models[name].scene))

func row(path: String) -> Dictionary:
	return GlbSceneCache._ledger.get(path, {})

## Publishes `path` the way the creature warm-up does (its worker's prepare(),
## then install_prepared on main). prepare() is the same build on any thread.
func install_like_worker(path: String) -> void:
	var prepared := GlbSceneCache.prepare(PackedStringArray([path]))
	GlbSceneCache.install_prepared(prepared)

## The estimate the ledger must hold for `path`, as plain numbers (the walk's
## strong references end with this function).
func expected_bytes(path: String) -> Dictionary:
	var walked := ResourceBytes.scene_resources(GlbSceneCache._scenes[path] as PackedScene,
		ResourceBytes.MIPMAPS_NONE)
	var full := ResourceBytes.scene_resources(GlbSceneCache._scenes[path] as PackedScene,
		ResourceBytes.MIPMAPS_UNKNOWN)
	return {"bytes": int(walked.bytes), "mesh_bytes": int(walked.mesh_bytes),
		"texture_bytes": int(walked.texture_bytes), "meshes": (walked.meshes as Array).size(),
		"full_chain_texture_bytes": int(full.texture_bytes)}

func busy(path: String) -> bool:
	return GlbSceneCache._is_busy(row(path))

func run() -> void:
	var previous_mode := OS.get_environment("RABBITLANDS_PREPARED_CONTENT")
	OS.set_environment("RABBITLANDS_PREPARED_CONTENT", "raw")
	NativeAnimationImporter.GltfQuantization.ensure_registered()
	NativeAnimationImporter.VramTextures.ensure_registered()
	NativeAnimationImporter.MapMeshExtension.ensure_registered()
	registry = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var memory := MemoryBudgets.current()
	info("memory class %s (%s), creature budget %d MiB, idle %d ms" % [memory["class"], memory["source"],
		int(MemoryBudgets.value(MemoryBudgets.CREATURE_SCENE_BYTES)) >> 20,
		int(MemoryBudgets.value(MemoryBudgets.CREATURE_SCENE_IDLE_MSEC))])
	GlbSceneCache.clear()
	NativeAnimationImporter.clear()
	GlbSceneCache.set_budget_for_tests(HUGE, 1 << 30)
	check_budget_defaults()
	check_domains()
	check_creature_libraries_are_their_scenes()
	check_ledger_and_probes()
	check_budget_eviction()
	check_lru_counts_holding()
	check_prewarm_skip_keeps_libraries()
	await check_warmup_requeue()
	await check_failed_requeue_stops()
	await check_timer_pass()
	check_forget_release_clear()
	await check_static_caches_hook()
	check_snapshot()
	GlbSceneCache.set_budget_for_tests(-1, -1)
	GlbSceneCache.clear()
	NativeAnimationImporter.clear()
	if previous_mode.is_empty():
		OS.unset_environment("RABBITLANDS_PREPARED_CONTENT")
	else:
		OS.set_environment("RABBITLANDS_PREPARED_CONTENT", previous_mode)
	print("glb scene cache budget: ", failures, " failures")
	quit(failures)

func check_budget_defaults() -> void:
	GlbSceneCache.set_budget_for_tests(-1, -1)
	for memory_class: String in MemoryBudgets.CLASSES:
		MemoryBudgets.override_for_tests(memory_class)
		expect(GlbSceneCache.creature_budget_bytes() == int(MemoryBudgets.value_for(memory_class,
				MemoryBudgets.CREATURE_SCENE_BYTES))
			and GlbSceneCache.creature_idle_msec() == int(MemoryBudgets.value_for(memory_class,
				MemoryBudgets.CREATURE_SCENE_IDLE_MSEC)),
			"%s: creature budget and idle age come from MemoryBudgets" % memory_class)
	MemoryBudgets.override_for_tests(MemoryBudgets.SMALL)
	expect(GlbSceneCache.creature_budget_bytes() == 256 << 20 and GlbSceneCache.creature_idle_msec() == 20000,
		"small: 256 MiB, idle >= 20 s (design table)")
	MemoryBudgets.reset()
	GlbSceneCache.set_budget_for_tests(HUGE, 1 << 30)

func check_domains() -> void:
	var cases := {
		"res://assets/actors/native/creatures/basic_expansion/rabbit.glb": GlbSceneCache.DOMAIN_CREATURE,
		"res://assets/actors/native/races/human_male.glb": GlbSceneCache.DOMAIN_RACE,
		"res://assets/actors/native/hair/bob_female.glb": GlbSceneCache.DOMAIN_HAIR,
		"res://assets/actors/native/equipment/adventurer_headwear_01.glb": GlbSceneCache.DOMAIN_EQUIPMENT,
		"res://assets/actors/native/rl_heads/head.glb": GlbSceneCache.DOMAIN_RL_HEAD,
		"res://assets/actors/native/mounts/horse.glb": GlbSceneCache.DOMAIN_OTHER,
		"res://assets/actors/native/shared/Universal_Animation_Library.glb": GlbSceneCache.DOMAIN_OTHER,
		"res://assets/world/props/crate.glb": GlbSceneCache.DOMAIN_WORLD,
		"C:/elsewhere/creatures/rabbit.glb": GlbSceneCache.DOMAIN_OTHER,
	}
	for path: String in cases:
		expect(GlbSceneCache.domain_of(path) == cases[path]
			and GlbSceneCache.domain_of(ProjectSettings.globalize_path(path)) == cases[path],
			"domain of %s is %s (res:// and globalized)" % [path.get_file(), cases[path]])

## Eviction releases the importer's libraries by the creature's own path: that
## is complete only while every creature names its own GLB as its library and
## no other model names a creature GLB.
func check_creature_libraries_are_their_scenes() -> void:
	var creatures := 0
	var mismatched := PackedStringArray()
	for name: String in registry.models:
		var config: Variant = registry.models[name]
		if config is not Dictionary:
			continue
		var scene := str(config.get("scene", ""))
		var library := str(config.get("animationLibrary", ""))
		if scene.begins_with("res://assets/actors/native/creatures/"):
			creatures += 1
			if not library.is_empty() and library != scene:
				mismatched.append(name)
		elif library.begins_with("res://assets/actors/native/creatures/"):
			mismatched.append(name)
	info("%d creature models checked" % creatures)
	expect(creatures > 100 and mismatched.is_empty(),
		"every creature's animation library is its own scene, and no other model uses one %s" % mismatched)

func check_ledger_and_probes() -> void:
	GlbSceneCache.clear()
	var a := scene_path("rabbit")
	var b := scene_path("cerberus")
	var began := Time.get_ticks_usec()
	install_like_worker(a)
	info("rabbit prepare+install (parse included): %.1f ms" % ((Time.get_ticks_usec() - began) / 1000.0))
	var entry := row(a)
	expect(not entry.is_empty() and entry.origin == GlbSceneCache.ORIGIN_WORKER
		and entry.domain == GlbSceneCache.DOMAIN_CREATURE and bool(entry.evictable),
		"worker-published raw creature: creature row, origin worker, evictable")
	var expected := expected_bytes(a)
	expect(int(entry.bytes) == int(expected.bytes) and int(entry.mesh_bytes) == int(expected.mesh_bytes)
		and int(entry.texture_bytes) == int(expected.texture_bytes) and int(entry.bytes) > 0,
		"creature row measured at publication: %d B (meshes %d, textures %d without mips)" % [
			int(entry.bytes), int(entry.mesh_bytes), int(entry.texture_bytes)])
	info("rabbit textures with full mip chains would count %d B" % int(expected.full_chain_texture_bytes))
	expect((entry.probes as Array).size() == int(expected.meshes) and int(expected.meshes) > 0
		and (entry.baseline as PackedInt32Array).size() == int(expected.meshes),
		"one probe and one baseline count per mesh (%d)" % int(expected.meshes))
	var snapshot := GlbSceneCache.retention_snapshot()
	expect(int(snapshot.bytes_by_domain.get("creature", -1)) == int(entry.bytes) and int(snapshot.bytes) == int(entry.bytes)
		and int(snapshot.evictable_entries) == 1 and int(snapshot.pending_rows) == 0,
		"snapshot carries the creature bytes and one evictable entry")
	# Reference-count probe (memory-classes design, experiment 5).
	expect(not busy(a), "idle at publication")
	var instance := GlbSceneCache.instantiate(a)
	expect(instance != null and busy(a), "an instance makes the entry in use")
	var copy := instance.duplicate()
	instance.free()
	expect(busy(a), "a duplicate() of the instance still holds it")
	copy.free()
	expect(not busy(a), "freeing every holder makes it idle again")
	var direct := GlbSceneCache.packed_scene(a).instantiate()
	expect(busy(a), "an instance made from packed_scene() directly holds it too")
	direct.free()
	expect(not busy(a), "and frees it")
	# A creature built on the main thread (a cache miss) is counted, never evicted.
	began = Time.get_ticks_usec()
	var main_built := GlbSceneCache.packed_scene(b)
	info("cerberus main-thread miss build (parse included): %.1f ms" % ((Time.get_ticks_usec() - began) / 1000.0))
	var main_row := row(b)
	expect(main_built != null and main_row.origin == GlbSceneCache.ORIGIN_MAIN and not bool(main_row.evictable)
		and int(main_row.bytes) > 0, "main-built creature: counted (%d B), not evictable" % int(main_row.bytes))
	expect(GlbSceneCache.domain_bytes("creature") == int(entry.bytes) + int(main_row.bytes),
		"creature domain total is the sum of its rows")
	# The ledger's own share of a creature publication: the scene is already
	# built, so install_prepared here is the row (walk, probes, baseline).
	var scene := GlbSceneCache._scenes[a] as PackedScene
	var timings := PackedFloat64Array()
	for round: int in 5:
		GlbSceneCache.forget(a)
		began = Time.get_ticks_usec()
		GlbSceneCache.install_prepared({a: scene})
		timings.append((Time.get_ticks_usec() - began) / 1000.0)
	timings.sort()
	info("ledger cost of one creature publication (rabbit, scene already built): median %.3f ms, max %.3f ms" % [
		timings[2], timings[4]])
	# The actor worker path (prepare_actor / install_actor_prepared) is a worker publication too.
	GlbSceneCache.forget(a)
	var record := GlbSceneCache.prepare_actor(a)
	expect(GlbSceneCache.install_actor_prepared(record) and row(a).origin == GlbSceneCache.ORIGIN_WORKER
		and bool(row(a).evictable), "install_actor_prepared publishes an evictable worker row")
	GlbSceneCache.discard_actor_prepared(record)
	# Non-creature rows wait for a pass, then are measured.
	GlbSceneCache.packed_scene(ProjectSettings.globalize_path(HAIR))
	var hair := row(ProjectSettings.globalize_path(HAIR))
	expect(not hair.is_empty() and hair.domain == GlbSceneCache.DOMAIN_HAIR and int(hair.bytes) == -1
		and int(GlbSceneCache.retention_snapshot().pending_rows) == 1,
		"a hair row is pending until a pass measures it")
	GlbSceneCache.enforce_budget()
	hair = row(ProjectSettings.globalize_path(HAIR))
	expect(int(hair.bytes) > 0 and int(GlbSceneCache.retention_snapshot().pending_rows) == 0
		and GlbSceneCache.domain_bytes("hair") == int(hair.bytes),
		"the pass measures it (%d B) and counts it under hair" % int(hair.bytes))
	GlbSceneCache.clear()

func check_budget_eviction() -> void:
	GlbSceneCache.clear()
	NativeAnimationImporter.clear()
	var a := scene_path("rabbit")
	var b := scene_path("cerberus")
	install_like_worker(a)
	install_like_worker(b)
	var bytes_a := int(row(a).bytes)
	var bytes_b := int(row(b).bytes)
	# A library cached for each file: eviction must release the evicted one's only.
	var key_a := "%s|mem-m5" % a
	var key_b := "%s|mem-m5" % b
	NativeAnimationImporter.install_prepared({"key": key_a, "built": {}})
	NativeAnimationImporter.install_prepared({"key": key_b, "built": {}})
	var budget := bytes_a + bytes_b - 1
	GlbSceneCache.set_budget_for_tests(budget, 1000)
	# Use A, so B is the least recently used.
	OS.delay_msec(2)
	GlbSceneCache.instantiate(a).free()
	var before := GlbSceneCache.retention_snapshot()
	var now := Time.get_ticks_msec()
	var first := GlbSceneCache.enforce_budget(now)
	expect(int(first.evicted) == 0 and int(first.idle_candidates) == 0 and GlbSceneCache.missing(
		PackedStringArray([a, b])).is_empty(), "over budget, but seen idle only now: nothing evicted")
	var early := GlbSceneCache.enforce_budget(now + 999)
	expect(int(early.evicted) == 0, "idle 999 ms of 1000: nothing evicted")
	# An instance alive keeps A whatever its age and the budget.
	var held := GlbSceneCache.instantiate(a)
	var due := GlbSceneCache.enforce_budget(now + 1000)
	var expect_both := bytes_a > int(budget * GlbSceneCache.EVICT_TO_FRACTION)
	expect(int(due.evicted) == 1 and GlbSceneCache.evicted(b) and not GlbSceneCache.evicted(a)
		and GlbSceneCache.missing(PackedStringArray([a, b])) == PackedStringArray([b]),
		"idle for the idle age and over budget: the idle entry (B) is evicted, the one in use (A) kept")
	expect(row(b).is_empty() and GlbSceneCache.domain_bytes("creature") == bytes_a,
		"the evicted row leaves the ledger and the domain total")
	expect(not NativeAnimationImporter._libraries.has(key_b) and NativeAnimationImporter._libraries.has(key_a),
		"eviction releases the evicted creature's animation libraries only")
	var after := GlbSceneCache.retention_snapshot()
	expect(int(after.evictions) - int(before.evictions) == 1
		and int(after.evicted_bytes) - int(before.evicted_bytes) == bytes_b,
		"snapshot counts the eviction and its %d B" % bytes_b)
	# A is still in use: even a 1-byte budget does not evict it.
	GlbSceneCache.set_budget_for_tests(1, 1000)
	expect(int(GlbSceneCache.enforce_budget(now + 100000).evicted) == 0 and not GlbSceneCache.evicted(a),
		"an entry in use is never evicted, even far over budget")
	held.free()
	var seen_idle := GlbSceneCache.enforce_budget(now + 200000)
	expect(int(seen_idle.evicted) == 0, "after its last holder goes, the idle age starts again")
	var gone := GlbSceneCache.enforce_budget(now + 201000)
	expect(int(gone.evicted) == 1 and GlbSceneCache.evicted(a) and GlbSceneCache.domain_bytes("creature") == 0,
		"then it is evicted too")
	# LRU order and the 85 % target with both idle: rebuild both, B used last.
	GlbSceneCache.set_budget_for_tests(HUGE, 1000)
	install_like_worker(a)
	install_like_worker(b)
	expect(not GlbSceneCache.evicted(a) and not GlbSceneCache.evicted(b), "publishing again clears the eviction mark")
	OS.delay_msec(2)
	GlbSceneCache.instantiate(b).free()
	GlbSceneCache.set_budget_for_tests(budget, 1000)
	now = Time.get_ticks_msec()
	GlbSceneCache.enforce_budget(now)
	var lru := GlbSceneCache.enforce_budget(now + 1000)
	var b_kept := bytes_b <= int(budget * GlbSceneCache.EVICT_TO_FRACTION)
	expect(GlbSceneCache.evicted(a) and GlbSceneCache.evicted(b) != b_kept and int(lru.evicted) == (1 if b_kept else 2),
		"both idle: the least recently used (A) goes first, down to 85 %% of the budget (B kept: %s)" % b_kept)
	# Under budget nothing is evicted, however idle.
	GlbSceneCache.set_budget_for_tests(HUGE, 0)
	install_like_worker(a)
	install_like_worker(b)
	expect(int(GlbSceneCache.enforce_budget(now + 10000000).evicted) == 0
		and GlbSceneCache.missing(PackedStringArray([a, b])).is_empty(), "under budget: nothing is evicted")
	if expect_both:
		info("rabbit alone exceeds 85 % of rabbit+cerberus")
	GlbSceneCache.set_budget_for_tests(HUGE, 1 << 30)
	GlbSceneCache.clear()
	NativeAnimationImporter.clear()

## Least recently used counts holding as use: an entry whose instance lived
## until recently was used more recently than one instantiated after it but
## let go at once, so with both idle the second goes first.
func check_lru_counts_holding() -> void:
	GlbSceneCache.clear()
	NativeAnimationImporter.clear()
	var a := scene_path("rabbit")
	var b := scene_path("cerberus")
	install_like_worker(a)
	install_like_worker(b)
	var budget := int(row(a).bytes) + int(row(b).bytes) - 1
	GlbSceneCache.set_budget_for_tests(HUGE, 1000)
	var held := GlbSceneCache.instantiate(a) # A instantiated first ...
	OS.delay_msec(2)
	GlbSceneCache.instantiate(b).free() # ... B after it, and let go at once
	var now := Time.get_ticks_msec() + 10
	GlbSceneCache.enforce_budget(now) # A still held at `now`, B idle
	held.free()
	GlbSceneCache.enforce_budget(now + 1) # A seen idle too
	GlbSceneCache.set_budget_for_tests(budget, 1000)
	var report := GlbSceneCache.enforce_budget(now + 2000)
	expect(int(report.idle_candidates) == 2 and int(report.evicted) == 1
		and GlbSceneCache.evicted(b) and not GlbSceneCache.evicted(a),
		"both idle: the entry let go first (B) is evicted, not the one held until recently (A)")
	GlbSceneCache.set_budget_for_tests(HUGE, 1 << 30)
	GlbSceneCache.clear()
	NativeAnimationImporter.clear()

## A prewarm thread still parsing a creature's file as an animation library:
## the entry is skipped whole (scene and libraries kept) and evicted on a
## later pass once that thread has ended.
func check_prewarm_skip_keeps_libraries() -> void:
	GlbSceneCache.clear()
	NativeAnimationImporter.clear()
	var a := scene_path("rabbit")
	install_like_worker(a)
	var key_a := "%s|mem-m5" % a
	NativeAnimationImporter.install_prepared({"key": key_a, "built": {}})
	var gate := Semaphore.new()
	var thread := Thread.new()
	thread.start(func() -> Variant:
		gate.wait()
		return null)
	# The res:// spelling: the importer may key a prewarm either way.
	NativeAnimationImporter._prewarming[str(registry.models.rabbit.scene)] = thread
	GlbSceneCache.set_budget_for_tests(1, 0)
	var skipped := GlbSceneCache.enforce_budget()
	expect(int(skipped.evicted) == 0 and int(skipped.skipped) == 1 and not GlbSceneCache.evicted(a)
		and GlbSceneCache.missing(PackedStringArray([a])).is_empty()
		and NativeAnimationImporter._libraries.has(key_a),
		"a live prewarm of the file skips the entry whole: its scene and its libraries are kept")
	gate.post()
	while thread.is_alive():
		OS.delay_msec(1)
	var done := GlbSceneCache.enforce_budget()
	expect(int(done.evicted) == 1 and GlbSceneCache.evicted(a) and not NativeAnimationImporter._libraries.has(key_a)
		and NativeAnimationImporter._prewarming.is_empty(),
		"once the prewarm has ended a pass evicts it (the finished thread joined, libraries released)")
	GlbSceneCache.set_budget_for_tests(HUGE, 1 << 30)
	GlbSceneCache.clear()
	NativeAnimationImporter.clear()

func wait_ready(warmup: RefCounted, config: Dictionary, animation: Dictionary) -> bool:
	var deadline := Time.get_ticks_msec() + 60000
	while not warmup.request(config, animation) and Time.get_ticks_msec() < deadline:
		await process_frame
	return warmup.request(config, animation)

func check_warmup_requeue() -> void:
	GlbSceneCache.clear()
	NativeAnimationImporter.clear()
	var config: Dictionary = registry.models.rabbit
	var animation: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	var path := scene_path("rabbit")
	var warmup := Warmup.new()
	expect(not warmup.request(config, animation), "cold creature queues its preparation")
	expect(await wait_ready(warmup, config, animation), "the worker prepares it")
	expect(GlbSceneCache.missing(PackedStringArray([path])).is_empty() and bool(row(path).evictable),
		"the warm-up's publication is an evictable worker row")
	var libraries := NativeAnimationImporter.cached_library_count()
	expect(libraries > 0, "its retargeted library is cached")
	# A real actor (as main builds it) holds the entry while it lives and lets
	# it go when freed: nothing the actor builds keeps the scene's meshes.
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var errors := actor.configure({"actor_id": 32001, "actor_type": 200, "kind": ReplicatedActor3D.CREATURE_ACTOR_KIND,
		"name": "Rabbit", "x": 0, "y": 0, "rotation": 0},
		CoordinateAdapter.new({"metresPerTile": 1.0}), config, animation)
	for frame: int in 3:
		await process_frame
	expect(errors.is_empty() and busy(path), "a configured creature actor holds its entry")
	expect(NativeAnimationImporter.cached_library_count() == libraries
		and not NativeAnimationImporter.has_source(ProjectSettings.globalize_path(str(config.animationLibrary))),
		"the actor took the prepared library: no main-thread source instance is kept")
	actor.free()
	for frame: int in 3:
		await process_frame
	expect(not busy(path), "freeing the actor makes the entry idle (nothing it built keeps the meshes)")
	var before := GlbSceneCache.retention_snapshot()
	# Evict it: a 1-byte budget and no idle age.
	GlbSceneCache.set_budget_for_tests(1, 0)
	var report := GlbSceneCache.enforce_budget()
	expect(int(report.evicted) == 1 and GlbSceneCache.evicted(path)
		and NativeAnimationImporter.cached_library_count() == libraries - 1,
		"the idle creature and its library are evicted")
	GlbSceneCache.set_budget_for_tests(HUGE, 1 << 30)
	expect(not warmup.request(config, animation) and warmup.requeued_after_eviction == 1,
		"a ready creature whose scene was evicted is cold again: re-queued on the worker")
	expect(not warmup.request(config, animation) and warmup.requeued_after_eviction == 1,
		"asked again while it is being prepared: still deferred, queued once")
	expect(await wait_ready(warmup, config, animation), "the worker prepares it again")
	var after := GlbSceneCache.retention_snapshot()
	expect(not GlbSceneCache.evicted(path) and GlbSceneCache.missing(PackedStringArray([path])).is_empty()
		and NativeAnimationImporter.cached_library_count() == libraries,
		"scene and library are back")
	expect(int(after.lookup_misses) == int(before.lookup_misses)
		and int(after.evicted_main_rebuilds) == int(before.evicted_main_rebuilds),
		"no main-thread build of the evicted creature (no cache miss)")
	var instance := GlbSceneCache.instantiate(path)
	expect(instance != null and int(GlbSceneCache.retention_snapshot().lookup_misses) == int(before.lookup_misses),
		"its next instance is a cache hit")
	instance.free()
	warmup.clear()
	while not warmup.is_idle():
		await process_frame
	GlbSceneCache.clear()
	NativeAnimationImporter.clear()

## A preparation after an eviction that publishes nothing (a failed parse)
## clears the mark, so the warm-up does not ask for it again on every request.
## The completed job is simulated: a real failure would log a parse error.
func check_failed_requeue_stops() -> void:
	var config := {"scene": MISSING_CREATURE, "animationLibrary": MISSING_CREATURE}
	var animation := {}
	var key := JSON.stringify([config, animation])
	var canonical := ProjectSettings.globalize_path(MISSING_CREATURE)
	var warmup := Warmup.new()
	warmup._known[key] = true
	GlbSceneCache._evicted[canonical] = true
	expect(GlbSceneCache.evicted(MISSING_CREATURE), "marked evicted")
	# The job that request() would start, as a failure: no scenes.
	var job := Thread.new()
	job.start(func() -> Dictionary: return {})
	warmup._thread = job
	warmup._active = key
	warmup._active_scene = MISSING_CREATURE
	warmup._known[key] = false
	while job.is_alive():
		await process_frame
	warmup.poll()
	expect(not GlbSceneCache.evicted(MISSING_CREATURE) and bool(warmup._known.get(key, false)),
		"a failed re-preparation clears the mark and counts as done")
	expect(warmup.request(config, animation) and warmup.requeued_after_eviction == 0 and warmup.is_idle(),
		"the next request is answered without queueing it again")

func check_timer_pass() -> void:
	GlbSceneCache.clear()
	install_like_worker(ProjectSettings.globalize_path(HAIR)) # a pending (non-creature) row
	expect(GlbSceneCache._budget_timer_armed, "a publication arms the budget timer")
	var passes := int(GlbSceneCache.retention_snapshot().budget_passes)
	var deadline := Time.get_ticks_msec() + int(GlbSceneCache.BUDGET_PASS_SECONDS * 1000) + 3000
	while int(GlbSceneCache.retention_snapshot().budget_passes) == passes and Time.get_ticks_msec() < deadline:
		await process_frame
	var snapshot := GlbSceneCache.retention_snapshot()
	expect(int(snapshot.budget_passes) > passes and int(snapshot.pending_rows) == 0
		and int(snapshot.bytes_by_domain.get("hair", 0)) > 0,
		"the timer runs a pass on its own, which measures the pending row")
	expect(GlbSceneCache._budget_timer_armed, "and re-arms while rows remain")
	GlbSceneCache.clear()

func check_forget_release_clear() -> void:
	GlbSceneCache.clear()
	var a := scene_path("rabbit")
	var b := scene_path("cerberus")
	install_like_worker(a)
	install_like_worker(b)
	GlbSceneCache.forget(str(registry.models.rabbit.scene)) # res:// spelling
	expect(not GlbSceneCache._scenes.has(a) and row(a).is_empty() and not GlbSceneCache.evicted(a)
		and GlbSceneCache.domain_bytes("creature") == int(row(b).bytes),
		"forget() drops exactly that entry and its row, and is not an eviction")
	GlbSceneCache.release_sources(PackedStringArray([str(registry.models.cerberus.scene)]))
	expect(row(b).is_empty() and GlbSceneCache.domain_bytes("creature") == 0,
		"release_sources() drops the rows of the released files")
	install_like_worker(a)
	GlbSceneCache._scenes.erase(a) # as rl_head_library.gd _forget_scene erases directly
	GlbSceneCache.enforce_budget()
	expect(row(a).is_empty() and int(GlbSceneCache.retention_snapshot().evictable_entries) == 0,
		"a pass prunes rows whose scene was erased behind the cache's back")
	install_like_worker(a)
	GlbSceneCache._evicted[b] = true
	GlbSceneCache.clear()
	var snapshot := GlbSceneCache.retention_snapshot()
	expect(GlbSceneCache._ledger.is_empty() and int(snapshot.bytes) == 0 and (snapshot.bytes_by_domain as Dictionary).is_empty()
		and int(snapshot.pending_rows) == 0 and int(snapshot.evictable_entries) == 0 and not GlbSceneCache.evicted(b),
		"clear() empties the ledger, its totals and the eviction marks")

func static_hook_present() -> bool:
	for method: Dictionary in (ReplicatedActor3D as GDScript).get_script_method_list():
		if str(method.name) == "clear_static_caches":
			return true
	return false

func fill_static_caches() -> void:
	ReplicatedActor3D._equipment_pieces_cache["mem-m5"] = []
	ReplicatedActor3D._rebound_skins["mem-m5"] = null
	ReplicatedActor3D._drape_envelopes["mem-m5"] = PackedFloat32Array()
	ReplicatedActor3D._draped_capes["mem-m5"] = null
	ReplicatedActor3D._torso_reaches["mem-m5"] = []
	ReplicatedActor3D._fabric_lines["mem-m5"] = []
	ReplicatedActor3D._shin_reaches["mem-m5"] = []

func static_caches_empty() -> bool:
	return ReplicatedActor3D._equipment_pieces_cache.is_empty() and ReplicatedActor3D._rebound_skins.is_empty() \
		and ReplicatedActor3D._drape_envelopes.is_empty() and ReplicatedActor3D._draped_capes.is_empty() \
		and ReplicatedActor3D._torso_reaches.is_empty() and ReplicatedActor3D._fabric_lines.is_empty() \
		and ReplicatedActor3D._shin_reaches.is_empty()

## The hook A2 applies (replicated_actor_3d.gd clear_static_caches, main.gd
## _clear_world_presentation). Until it is applied this part only proves the
## seven caches it names exist (the references above compile) and says so.
func check_static_caches_hook() -> void:
	var main_source := FileAccess.get_file_as_string("res://src/app/main.gd")
	var clear_body := main_source.get_slice("func _clear_world_presentation(", 1).get_slice("\nfunc ", 0)
	var main_hooked := clear_body.contains("ReplicatedActor3D.clear_static_caches()")
	if not static_hook_present():
		print("PENDING: ReplicatedActor3D.clear_static_caches() is a hook for A2 (not applied yet)")
		expect(not main_hooked, "main.gd does not call a clear_static_caches() that does not exist")
		return
	fill_static_caches()
	(ReplicatedActor3D as GDScript).call("clear_static_caches")
	expect(static_caches_empty(), "clear_static_caches() empties all seven session caches")
	if not main_hooked:
		print("PENDING: main.gd _clear_world_presentation does not call clear_static_caches() yet (A2)")
		return
	expect(clear_body.find("ReplicatedActor3D.clear_static_caches()") > clear_body.find("not retain_map_resources")
		and clear_body.find("GlbSceneCache.clear()") >= 0, "main clears them with GlbSceneCache, when not retaining")
	var main: Variant = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	for frame: int in 4:
		await process_frame
	fill_static_caches()
	main._clear_world_presentation(true)
	expect(not static_caches_empty(), "a reconnect that keeps map resources keeps them")
	main._clear_world_presentation(false)
	expect(static_caches_empty(), "leaving the session (disconnect) leaves all seven empty")
	main.queue_free()
	await process_frame

func check_snapshot() -> void:
	GlbSceneCache.clear()
	install_like_worker(scene_path("rabbit"))
	var snapshot := GlbSceneCache.retention_snapshot()
	for key: String in ["entries", "bytes", "bytes_by_domain", "budget", "evictions", "pending_rows",
			"evictable_entries", "evicted_bytes", "eviction_skips", "evicted_main_rebuilds", "idle_msec",
			"budget_domain", "budget_passes", "strong_scene_entries", "lookup_hits", "actor_images"]:
		expect(snapshot.has(key), "retention_snapshot has %s" % key)
	expect(bool(snapshot.bytes_estimate_available) and int(snapshot.entries) == 1 and int(snapshot.budget) == HUGE,
		"bytes are available; one entry; the budget in force")
	var began := Time.get_ticks_usec()
	for call: int in 100:
		GlbSceneCache.retention_snapshot()
	var average := (Time.get_ticks_usec() - began) / 100.0
	info("retention_snapshot average %.1f us" % average)
	expect(average < 1000.0, "retention_snapshot stays cheap (%.1f us < 1 ms)" % average)
	GlbSceneCache.clear()
