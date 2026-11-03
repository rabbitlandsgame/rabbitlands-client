extends SceneTree
## Memory census (src/runtime/memory_census.gd, memory classes M3) and the byte
## ledgers it reads:
## - the census row: every key present and numeric, the class and its budget
##   row, the cache rows read generically (-1 for a figure a cache does not
##   report), WorldPark and crowd park-pool rows from the real scripts, the
##   process counters per OS (/proc parsing; native runtime absent, missing,
##   invalid and present), the untracked figure, the worker-thread refusal,
##   and the cost: under 1 ms a call over 100 calls, with and without Main's
##   already-collected retention snapshots;
## - the ledgers: ExternalTexturePool (share and load_image, with their mip
##   state), ExternalMeshPool (shadow mesh, adoption, weak expiry),
##   NativeAnimationImporter (a library's bytes from `_build`, a source shared
##   with GlbSceneCache counting animations only, a prewarmed source measured
##   on the worker, release and clear);
## - the animation estimator against the static memory counter (debug builds):
##   synthetic tracks of every measured type and the shared universal library.
## Forces the memory class (medium, then small) and restores it at the end.

const MemoryCensus := preload("res://src/runtime/memory_census.gd")
const MemoryBudgets := preload("res://src/runtime/memory_budgets.gd")
const ResourceBytes := preload("res://src/runtime/resource_bytes.gd")
const ExternalMeshPool := preload("res://src/world/external_mesh_pool.gd")
const ExternalTexturePool := preload("res://src/world/external_texture_pool.gd")
const WorldParkScript := preload("res://src/world/world_park.gd")
const CrowdPresentationScript := preload("res://src/world/crowd_presentation.gd")
const Warmup := preload("res://src/actors/actor_resource_warmup.gd")
const UNIVERSAL_LIBRARY := "res://assets/actors/native/shared/Universal_Animation_Library.glb"
const CREATURE := "rabbit"
const MIB := 1 << 20
const PNG_PATH := "user://test_memory_census.png"
const PROC_PATH := "user://test_memory_census_status.txt"

var failures := 0

## Stands in for the native client runtime (MEM-M10's process_memory()).
class FakeNative extends RefCounted:
	var answer: Variant = {}
	func process_memory() -> Variant:
		return answer

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
	else:
		print("PASS: " + label)

func info(text: String) -> void:
	print("INFO: " + text)

func _run() -> void:
	var previous_mode := OS.get_environment("RABBITLANDS_PREPARED_CONTENT")
	OS.set_environment("RABBITLANDS_PREPARED_CONTENT", "raw")
	NativeAnimationImporter.GltfQuantization.ensure_registered()
	NativeAnimationImporter.VramTextures.ensure_registered()
	NativeAnimationImporter.MapMeshExtension.ensure_registered()
	MemoryBudgets.override_for_tests("medium")
	_check_row_shape()
	_check_class()
	_check_cache_rows()
	_check_world_park_row()
	_check_crowd_row()
	_check_process_counters()
	_check_untracked()
	await _check_worker_refusal()
	await _check_texture_ledger()
	_check_mesh_ledger()
	await _check_animation_ledger()
	_check_animation_estimate()
	_check_universal_library()
	_check_cost()
	MemoryBudgets.reset()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	if previous_mode.is_empty():
		OS.unset_environment("RABBITLANDS_PREPARED_CONTENT")
	else:
		OS.set_environment("RABBITLANDS_PREPARED_CONTENT", previous_mode)
	for path: String in [PNG_PATH, PROC_PATH]:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	print("memory census tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _is_number(value: Variant) -> bool:
	return value is int or value is float

## Every key the census promises, with numbers where it promises numbers.
func _check_row_shape() -> void:
	var row := MemoryCensus.snapshot()
	for key: String in ["class", "class_basis", "class_source", "budgets", "os", "process", "godot",
			"caches", "untracked", "census_usec"]:
		expect(row.has(key), "the census row has %s" % key)
	var os_row: Dictionary = row.get("os", {})
	expect(["physical", "free", "available"].all(func(key: String) -> bool: return _is_number(os_row.get(key))),
		"os physical/free/available are numbers: %s" % os_row)
	expect(int(os_row.get("physical", 0)) > 0, "the OS reports physical memory")
	var godot: Dictionary = row.get("godot", {})
	var numeric := ["static", "static_peak", "video", "texture", "buffer", "objects", "resources",
		"nodes", "orphan_nodes"]
	expect(numeric.all(func(key: String) -> bool: return _is_number(godot.get(key))),
		"godot counters are numbers: %s" % godot)
	expect(godot.get("static_tracked") is bool and bool(godot.static_tracked) == OS.is_debug_build(),
		"static_tracked says whether this build tracks static memory")
	var pipelines: Dictionary = godot.get("pipeline_compilations", {})
	expect(pipelines.size() == 5 and pipelines.values().all(func(value: Variant) -> bool: return value is int),
		"five pipeline-compilation counters: %s" % pipelines)
	expect(int(godot.get("static", 0)) > 0 if OS.is_debug_build() else true, "a debug build tracks static memory")
	expect(int(godot.get("video", -1)) == RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_VIDEO_MEM_USED)
		and int(godot.get("texture", -1)) == RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TEXTURE_MEM_USED),
		"video and texture memory are the renderer's own figures (Main's video_memory_bytes)")
	var caches: Dictionary = row.get("caches", {})
	var names := ["actor_scenes", "animations", "world_meshes", "world_textures", "rl_identity_bake",
		"rl_heads", "world_park", "crowd_park"]
	expect(caches.keys() == names, "one row per cache: %s" % [caches.keys()])
	var malformed := PackedStringArray()
	for name: String in caches:
		for field: String in MemoryCensus.CACHE_FIELDS:
			if not (caches[name] as Dictionary).get(field) is int:
				malformed.append("%s.%s" % [name, field])
	expect(malformed.is_empty(), "every cache row has integer entries/bytes/budget/evictions: %s" % malformed)
	expect(int(caches.actor_scenes.bytes) >= 0 and int(caches.animations.bytes) >= 0
		and int(caches.world_meshes.bytes) >= 0 and int(caches.world_textures.bytes) >= 0,
		"the four retention caches report bytes (their ledgers)")
	expect(int(caches.rl_identity_bake.budget) == int(RLHeadIdentityBake.describe().budget_bytes),
		"the RL bake row reads its budget_bytes as the budget")
	expect(caches.world_park == MemoryCensus.cache_row({}) and caches.crowd_park == MemoryCensus.cache_row({}),
		"without Main's objects the WorldPark and crowd rows are all -1")
	expect(_is_number(row.get("census_usec")), "the row records its own cost")
	expect(JSON.parse_string(JSON.stringify(row)) is Dictionary, "the row is plain data (JSON round trip)")

func _check_class() -> void:
	var medium := MemoryCensus.snapshot()
	expect(medium["class"] == "medium" and medium.class_source == "test"
		and medium.budgets == MemoryBudgets.budgets("medium"),
		"the row carries the forced class, its source and its budget row")
	MemoryBudgets.override_for_tests("small")
	var small := MemoryCensus.snapshot()
	expect(small["class"] == "small" and int(small.budgets.world_park_bytes) == 384 * MIB
		and small.budgets.world_park_preload == false, "as small: 384 MiB WorldPark, no preload")
	var record := MemoryCensus.class_record()
	expect(record["class"] == "small" and record.source == "test" and record.budgets == MemoryBudgets.budgets("small")
		and int(record.physical_bytes) == int(OS.get_memory_info().physical),
		"class_record: the class, where it came from, its budgets and the machine's memory: %s" % record)
	MemoryBudgets.override_for_tests("medium")

func _check_cache_rows() -> void:
	expect(MemoryCensus.cache_row({}) == {"entries": -1, "bytes": -1, "budget": -1, "evictions": -1},
		"a cache that reports nothing reads -1 everywhere")
	var row := MemoryCensus.cache_row({"entries": 3, "bytes": 1.5e6, "budget": 512 * MIB, "evictions": "two",
		"bytes_by_domain": {"creature": 10}, "pending_rows": 1, "timings": {"x": 1}})
	expect(row.entries == 3 and row.bytes == 1500000 and row.budget == 512 * MIB and row.evictions == -1
		and row.bytes_by_domain == {"creature": 10} and row.pending_rows == 1 and not row.has("timings"),
		"cache_row: numbers kept as integers, a non-number is -1, known breakdowns kept, the rest dropped: %s" % row)
	var source := {"bytes_by_kind": {"libraries": 5}}
	var copied := MemoryCensus.cache_row(source)
	copied.bytes_by_kind.libraries = 9
	expect(int(source.bytes_by_kind.libraries) == 5, "a breakdown is copied, not shared with the cache")
	var retention := {"actor_scenes": {"entries": 7, "bytes": 70}, "world_textures": {"entries": 2, "bytes": 20}}
	var rows := MemoryCensus.caches({"retention": retention})
	expect(rows.actor_scenes.entries == 7 and rows.actor_scenes.bytes == 70 and rows.world_textures.bytes == 20,
		"snapshots Main already collected are used as given")
	expect(rows.animations == MemoryCensus.cache_row(NativeAnimationImporter.retention_snapshot())
		and rows.world_meshes == MemoryCensus.cache_row(ExternalMeshPool.retention_snapshot()),
		"caches Main did not pass are asked directly")
	var heads: Dictionary = rows.rl_heads
	expect(heads.has("users") and heads.has("warming") and int(heads.bytes) == -1,
		"RL heads: users and warm-up until the library reports a ledger (MEM-M4)")
	# MEM-M4 adds a static retention_snapshot() to RLHeadLibrary and the census
	# picks it up unchanged: a Script answers has_method for its statics.
	var reporting := GDScript.new()
	reporting.source_code = "extends RefCounted\nstatic func retention_snapshot() -> Dictionary:\n" \
		+ "\treturn {\"entries\": 2, \"bytes\": 4096, \"budget\": 8192, \"evictions\": 1, \"idle_bytes\": 1024}\n"
	expect(reporting.reload() == OK, "a stand-in RL head library with a static retention_snapshot() compiles")
	var reported := MemoryCensus.rl_head_row(reporting)
	expect(reported == {"entries": 2, "bytes": 4096, "budget": 8192, "evictions": 1, "idle_bytes": 1024},
		"RL heads: a library with a static retention_snapshot() is read like any cache: %s" % reported)
	var silent := GDScript.new()
	silent.source_code = "extends RefCounted\nstatic func users() -> int:\n\treturn 0\n"
	silent.reload()
	expect(MemoryCensus.rl_head_row(silent).has("users"), "a library without one falls back to users and warm-up")

func _check_world_park_row() -> void:
	var park := WorldParkScript.new()
	var row := MemoryCensus.world_park_row(park)
	expect(row.entries == 0 and row.bytes == 0 and row.budget == park.budget_bytes and row.evictions == 0
		and row.preload_enabled == true, "an empty WorldPark: nothing kept, its budget, preloading: %s" % row)
	park.budget_bytes = 384 * MIB
	park.preload_enabled = false
	park._parked["landfall"] = {"resident": {}, "at_msec": 0, "bytes": 243 * MIB}
	park._parked["landfall_town"] = {"resident": {}, "at_msec": 0, "bytes": 120 * MIB}
	park.counters.evict = 3
	row = MemoryCensus.world_park_row(park)
	expect(row.entries == 2 and row.bytes == 363 * MIB and row.budget == 384 * MIB and row.evictions == 3
		and row.preload_enabled == false, "two parked worlds against a small budget: %s" % row)
	var census := MemoryCensus.snapshot({"world_park": park})
	expect(census.caches.world_park == row, "the census row carries WorldPark's figures")
	park._parked.clear()
	park.free()
	expect(MemoryCensus.world_park_row(park) == MemoryCensus.cache_row({}), "a freed WorldPark reads -1")

func _check_crowd_row() -> void:
	var crowd: RefCounted = CrowdPresentationScript.new()
	var row := MemoryCensus.crowd_park_row(crowd)
	expect(row.entries == 0 and row.budget == int(MemoryBudgets.value(MemoryBudgets.CROWD_PARK_LIMIT))
		and row.bytes == -1, "the crowd pool: nothing parked, its limit (%d) as the budget" % int(row.budget))
	expect(MemoryCensus.snapshot({"crowd": crowd}).caches.crowd_park == row, "the census row carries the crowd pool")
	expect(MemoryCensus.crowd_park_row(null) == MemoryCensus.cache_row({}), "no crowd reads -1")

func _check_process_counters() -> void:
	var text := "Name:\tgodot\nVmPeak:\t 9000 kB\nVmHWM:\t  204800 kB\nVmRSS:\t  102400 kB\nRssAnon:\t   51200 kB\nThreads:\t42\n"
	var parsed := MemoryCensus.parse_proc_status(text)
	expect(parsed == {"available": true, "source": "proc_status", "working_set": 100 * MIB,
		"peak_working_set": 200 * MIB, "anonymous": 50 * MIB}, "/proc/self/status kB figures in bytes: %s" % parsed)
	expect(MemoryCensus.parse_proc_status("Name:\tgodot\n").reason == "proc_status_without_vmrss",
		"a status without VmRSS is not a reading")
	var file := FileAccess.open(PROC_PATH, FileAccess.WRITE)
	file.store_string(text.trim_suffix("\n"))
	file.close()
	expect(MemoryCensus.read_proc_status(PROC_PATH) == parsed, "the status file is read line by line, last line too")
	expect(MemoryCensus.read_proc_status("user://no_such_status").reason == "proc_status_unreadable",
		"an unreadable status file is reported, not guessed")
	# The read is bounded (it runs on the main thread): a VmRSS line past
	# PROC_MAX_LINES is never reached.
	file = FileAccess.open(PROC_PATH, FileAccess.WRITE)
	for line: int in MemoryCensus.PROC_MAX_LINES:
		file.store_line("Filler%d:\t0" % line)
	file.store_string(text)
	file.close()
	expect(MemoryCensus.read_proc_status(PROC_PATH).get("reason", "") == "proc_status_without_vmrss",
		"the status read stops after %d lines" % MemoryCensus.PROC_MAX_LINES)
	expect(MemoryCensus.native_process_counters(null).reason == "native_runtime_not_loaded",
		"no native runtime: no process counters")
	expect(MemoryCensus.native_process_counters(RefCounted.new()).reason == "native_process_memory_missing",
		"a native runtime without process_memory() (today's build)")
	var native := FakeNative.new()
	native.answer = {"working_set": 300 * MIB, "private_bytes": 400 * MIB, "peak_working_set": 350.0 * MIB, "label": "x"}
	expect(MemoryCensus.native_process_counters(native) == {"available": true, "source": "native_runtime",
		"working_set": 300 * MIB, "private_bytes": 400 * MIB, "peak_working_set": 350 * MIB},
		"the native runtime's byte counts are taken as they come")
	native.answer = []
	expect(MemoryCensus.native_process_counters(native).reason == "native_process_memory_invalid",
		"a malformed native answer is refused")
	var live := MemoryCensus.process_counters()
	if OS.get_name() == "Linux":
		expect(bool(live.available) and int(live.working_set) > 0, "Linux: this process's VmRSS: %s" % live)
	else:
		expect(not bool(live.available) and live.reason == "native_runtime_not_loaded",
			"%s without the native runtime: unavailable, with the reason: %s" % [OS.get_name(), live])

func _check_untracked() -> void:
	var process := {"available": true, "working_set": 900 * MIB}
	var godot := {"static_tracked": true, "static": 300 * MIB, "video": 200 * MIB}
	var integrated := MemoryCensus.untracked(process, godot, "integrated")
	expect(integrated == {"available": true, "bytes": 400 * MIB, "basis": "working_set - static - video"},
		"iGPU: working set - static - video memory: %s" % integrated)
	expect(int(MemoryCensus.untracked(process, godot, "discrete").bytes) == 600 * MIB,
		"dGPU: working set - static (video memory is on the card)")
	expect(MemoryCensus.untracked({"available": false}, godot, "discrete").reason == "no_process_counters",
		"no process counters: unavailable")
	godot.static_tracked = false
	expect(MemoryCensus.untracked(process, godot, "discrete").reason == "static_untracked",
		"a release template's untracked static memory: unavailable")

func _check_worker_refusal() -> void:
	var thread := Thread.new()
	thread.start(MemoryCensus.snapshot)
	while thread.is_alive():
		await process_frame
	var answer: Dictionary = thread.wait_to_finish()
	expect(answer == {"available": false, "reason": "main_thread_only"}, "a worker gets a refusal, not a census")

func _texture_bytes() -> int:
	return int(ExternalTexturePool.retention_snapshot().bytes)

func _check_texture_ledger() -> void:
	await process_frame
	var before := ExternalTexturePool.retention_snapshot()
	expect(bool(before.bytes_estimate_available) and before.has("entries") and before.has("published_bytes"),
		"the texture pool reports a ledger")
	var image := Image.create(16, 8, false, Image.FORMAT_RGBA8)
	image.fill(Color.RED)
	var texture := ImageTexture.create_from_image(image)
	var state := GLTFState.new()
	state.set_json({"images": [{"uri": "census.png"}]})
	var images: Array[Texture2D] = [texture]
	state.set_images(images)
	var key := "census-texture-%d" % Time.get_ticks_usec()
	ExternalTexturePool.share(state, {"census.png": key})
	var expected := ResourceBytes.image_layout_bytes(16, 8, Image.FORMAT_RGBA8, -1)
	var after := ExternalTexturePool.retention_snapshot()
	expect(int(after.bytes) - int(before.bytes) == expected and int(after.entries) == int(before.entries) + 1
		and int(after.published_bytes) - int(before.published_bytes) == expected,
		"a shared texture is counted with the mip chain share() gave it (%d B)" % expected)
	var adopter := GLTFState.new()
	adopter.set_json({"images": [{"uri": "again.png"}]})
	var other: Array[Texture2D] = [ImageTexture.create_from_image(Image.create(16, 8, false, Image.FORMAT_RGBA8))]
	adopter.set_images(other)
	ExternalTexturePool.share(adopter, {"again.png": key})
	expect(_texture_bytes() == int(after.bytes), "an adopter of the same content adds nothing")
	state = null
	adopter = null
	images.clear()
	other.clear()
	texture = null
	await process_frame
	expect(_texture_bytes() == int(before.bytes), "once the last holder lets go its bytes leave the ledger")
	# Parallel sharers of one new content key: one publication, counted once.
	var parallel_delta: int = await _share_in_parallel(key + "-parallel", 4)
	expect(parallel_delta == expected, "four parallel sharers of one key are counted once (%d B)" % parallel_delta)
	await process_frame
	expect(_texture_bytes() == int(before.bytes), "and leave together")
	# load_image: decoded with its chain (VramTextures.decode_source).
	var png := Image.create(32, 32, false, Image.FORMAT_RGBA8)
	png.fill(Color.BLUE)
	png.save_png(PNG_PATH)
	var loaded := ExternalTexturePool.load_image(ProjectSettings.globalize_path(PNG_PATH))
	expect(loaded != null and _texture_bytes() - int(before.bytes)
		== ResourceBytes.texture_bytes(loaded, ResourceBytes.MIPMAPS_FULL),
		"load_image counts the uploaded texture with its chain (%d B)" % ResourceBytes.texture_bytes(loaded, ResourceBytes.MIPMAPS_FULL))
	var census := MemoryCensus.snapshot()
	expect(int(census.caches.world_textures.bytes) == _texture_bytes()
		and int(census.caches.world_textures.entries) == int(ExternalTexturePool.retention_snapshot().entries),
		"the census row is the pool's ledger")
	loaded = null
	await process_frame
	expect(_texture_bytes() == int(before.bytes), "the loaded texture leaves the ledger with its last holder")

## `count` threads share textures under one new key; the ledger's growth while
## they are held. Everything they held is let go on return.
func _share_in_parallel(key: String, count: int) -> int:
	var before := _texture_bytes()
	var states: Array[GLTFState] = []
	var threads: Array[Thread] = []
	for index: int in count:
		states.append(_one_image_state("p%d.png" % index))
		threads.append(Thread.new())
		threads[index].start(ExternalTexturePool.share.bind(states[index], {"p%d.png" % index: key}))
	while threads.any(func(thread: Thread) -> bool: return thread.is_alive()):
		await process_frame
	for thread: Thread in threads:
		thread.wait_to_finish()
	return _texture_bytes() - before

## A state whose one image the map image extension already prepared
## (VramTextures.DONE_KEY): share() then makes no RenderingServer call on the
## worker. The headless dummy renderer's texture table is not thread-safe, so
## four workers reading back and re-uploading at once logged "Parameter t is
## null" errors (texture_2d_initialize / texture_free) in some runs.
func _one_image_state(uri: String) -> GLTFState:
	var state := GLTFState.new()
	state.set_json({"images": [{"uri": uri}]})
	var images: Array[Texture2D] = [ImageTexture.create_from_image(Image.create(16, 8, false, Image.FORMAT_RGBA8))]
	state.set_images(images)
	state.set_additional_data(ExternalTexturePool.VramTextures.DONE_KEY, {0: true})
	return state

func _surface(size: float) -> Array:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO, Vector3(size, 0, 0), Vector3(0, size, 0), Vector3(size, size, 0)])
	arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.BACK, Vector3.BACK, Vector3.BACK, Vector3.BACK])
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0, 1, 2, 2, 1, 3])
	return arrays

func _check_mesh_ledger() -> void:
	var before := ExternalMeshPool.retention_snapshot()
	expect(bool(before.bytes_estimate_available) and before.has("entries"), "the mesh pool reports a ledger")
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, _surface(1.0))
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, _surface(2.0))
	var shadow := ArrayMesh.new()
	shadow.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, _surface(1.0))
	mesh.shadow_mesh = shadow
	var expected := ResourceBytes.mesh_bytes(mesh) + ResourceBytes.mesh_bytes(shadow)
	expect(ExternalMeshPool.mesh_bytes(mesh) == expected and ResourceBytes.mesh_bytes(shadow) > 0,
		"a prototype counts its surfaces and its shadow mesh")
	var key := "census-mesh-%d" % Time.get_ticks_usec()
	expect(ExternalMeshPool._publish_or_adopt(key, mesh) == mesh, "the first sharer publishes")
	var after := ExternalMeshPool.retention_snapshot()
	expect(int(after.bytes) - int(before.bytes) == expected and int(after.entries) == int(before.entries) + 1,
		"the published prototype's bytes enter the ledger (%d B)" % expected)
	var candidate := ArrayMesh.new()
	candidate.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, _surface(3.0))
	expect(ExternalMeshPool._publish_or_adopt(key, candidate) == mesh
		and int(ExternalMeshPool.retention_snapshot().bytes) == int(after.bytes),
		"an adopter adds nothing")
	expect(int(MemoryCensus.snapshot().caches.world_meshes.bytes) == int(after.bytes), "the census row is the pool's ledger")
	mesh = null
	candidate = null
	expect(int(ExternalMeshPool.retention_snapshot().bytes) == int(before.bytes),
		"a prototype no placement holds leaves the ledger")

func _check_animation_ledger() -> void:
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var config: Dictionary = registry.models[CREATURE]
	var animation: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	var source_path := ProjectSettings.globalize_path(str(config.animationLibrary))
	var empty := NativeAnimationImporter.retention_snapshot()
	expect(bool(empty.bytes_estimate_available) and int(empty.bytes) == 0 and int(empty.entries) == 0,
		"an empty importer reports a zero ledger")
	# A library built by the warm-up (the same _build a main-thread retarget runs).
	var prepared: Dictionary = Warmup._prepare(config, animation)
	var record: Dictionary = prepared.get("library", {})
	var built: Dictionary = record.get("built", {})
	var library := built.get("library") as AnimationLibrary
	expect(library != null and int(built.get("bytes", 0)) > 0
		and int(built.bytes) == ResourceBytes.animation_library_bytes(library),
		"%s: the built library carries its bytes (%d B)" % [CREATURE, int(built.get("bytes", 0))])
	if library != null:
		var started := Time.get_ticks_usec()
		for call: int in 20:
			ResourceBytes.animation_library_bytes(library)
		info("%s library: %d clips counted in %.1f us a call"
			% [CREATURE, library.get_animation_list().size(), (Time.get_ticks_usec() - started) / 20.0])
	NativeAnimationImporter.install_prepared(record)
	var installed := NativeAnimationImporter.retention_snapshot()
	expect(int(installed.bytes) == int(built.bytes) and int(installed.bytes_by_kind.libraries) == int(built.bytes)
		and int(installed.entries) == 1, "an installed library's bytes are the importer's ledger")
	# Main-thread source in raw mode: an instance of GlbSceneCache's own parse.
	GlbSceneCache.install_prepared(prepared.get("scenes", {}))
	var shared_scene := NativeAnimationImporter._source_scene(source_path)
	var row: Dictionary = NativeAnimationImporter._source_bytes.get(source_path, {})
	var shared_animation := ResourceBytes.node_animation_bytes(shared_scene) if shared_scene != null else -1
	expect(shared_scene != null and bool(row.get("shared", false)) and int(row.mesh_bytes) == 0
		and int(row.texture_bytes) == 0 and int(row.animation_bytes) == shared_animation and shared_animation > 0,
		"a source shared with the scene cache counts its animations only (%d B): %s" % [shared_animation, row])
	var with_source := NativeAnimationImporter.retention_snapshot()
	expect(int(with_source.bytes) == int(built.bytes) + shared_animation and int(with_source.shared_source_scenes) == 1
		and int(with_source.entries) == 2, "library + shared source in the ledger")
	expect(NativeAnimationImporter.release_sources(PackedStringArray([source_path]))
		and not NativeAnimationImporter._source_bytes.has(source_path)
		and int(NativeAnimationImporter.retention_snapshot().bytes) == 0,
		"release_sources drops the library and the source rows")
	GlbSceneCache.clear()
	# A prewarmed source: parsed and measured on the worker, adopted on main.
	expect(NativeAnimationImporter.prewarm(source_path), "prewarm starts a worker")
	var thread: Thread = NativeAnimationImporter._prewarming.get(source_path)
	while thread != null and thread.is_alive():
		await process_frame
	var scene := NativeAnimationImporter._source_scene(source_path)
	row = NativeAnimationImporter._source_bytes.get(source_path, {})
	var on_main := ResourceBytes.node_resources(scene) if scene != null else {}
	expect(scene != null and not bool(row.get("shared", true)) and not scene.has_meta(NativeAnimationImporter.SOURCE_BYTES_META)
		and int(row.mesh_bytes) > 0 and int(row.texture_bytes) > 0 and int(row.animation_bytes) > 0,
		"a prewarmed source carries meshes, textures and animations, measured off the main thread: %s" % row)
	expect(int(row.get("bytes", -1)) == int(on_main.get("bytes", -2)) and int(row.mesh_bytes) == int(on_main.mesh_bytes)
		and int(row.texture_bytes) == int(on_main.texture_bytes) and int(row.animation_bytes) == int(on_main.animation_bytes),
		"the worker's measurement equals the same walk on the main thread")
	var census := MemoryCensus.snapshot()
	expect(int(census.caches.animations.bytes) == int(row.bytes) and int(census.caches.animations.entries) == 1
		and census.caches.animations.bytes_by_kind.source_meshes == row.mesh_bytes,
		"the census row is the importer's ledger, with its breakdown")
	info("%s source: meshes %d B, textures %d B, animations %d B; library %d B" % [CREATURE,
		int(row.mesh_bytes), int(row.texture_bytes), int(row.animation_bytes), int(built.bytes)])
	NativeAnimationImporter.clear()
	expect(NativeAnimationImporter._source_bytes.is_empty() and int(NativeAnimationImporter.retention_snapshot().bytes) == 0,
		"clear() empties the ledger")

## The estimator against the static memory counter (debug builds track it).
func _check_animation_estimate() -> void:
	if not OS.is_debug_build():
		print("SKIP: static memory is not tracked in this build")
		return
	var counts := [37, 100, 260, 500, 700, 1000, 1500, 2048, 3000]
	var values := {Animation.TYPE_POSITION_3D: Vector3.ONE, Animation.TYPE_ROTATION_3D: Quaternion.IDENTITY,
		Animation.TYPE_SCALE_3D: Vector3.ONE, Animation.TYPE_BLEND_SHAPE: 0.5, Animation.TYPE_VALUE: Vector3.ONE}
	for type: int in values:
		var animation := Animation.new()
		var before := OS.get_static_memory_usage()
		for count: int in counts:
			var track := animation.add_track(type)
			animation.track_set_path(track, NodePath("Skeleton3D:bone_%d" % count))
			for key: int in count:
				animation.track_insert_key(track, key * 0.01, values[type])
		var measured := OS.get_static_memory_usage() - before
		var estimate := ResourceBytes.animation_bytes(animation)
		var ratio := float(estimate) / float(measured)
		expect(ratio > 0.85 and ratio < 1.15,
			"type %d: %d tracks estimated %d B, static counter %d B (%.2fx)" % [type, counts.size(), estimate, measured, ratio])

## The shared universal library (10,000 tracks): the estimate against the whole
## parse's static memory, and what counting it costs.
func _check_universal_library() -> void:
	var path := ProjectSettings.globalize_path(UNIVERSAL_LIBRARY)
	var before := OS.get_static_memory_usage()
	var scene := NativeAnimationImporter._parse_library(path, false) as Node
	var measured := OS.get_static_memory_usage() - before
	expect(scene != null, "the universal library parses")
	if scene == null:
		return
	var started := Time.get_ticks_usec()
	var estimate := ResourceBytes.node_animation_bytes(scene)
	var elapsed := Time.get_ticks_usec() - started
	info("universal library: animations estimated %.1f MiB, whole parse %.1f MiB static, counted in %.2f ms"
		% [estimate / float(MIB), measured / float(MIB), elapsed / 1000.0])
	if OS.is_debug_build():
		expect(estimate <= measured and estimate > measured * 0.8,
			"its animations are most of the parse's memory and no more than it (%.2fx)" % (float(estimate) / measured))
	scene.free()

## Under 1 ms a call over 100 calls, Main's way (retention passed) and alone.
func _check_cost() -> void:
	var park := WorldParkScript.new()
	var crowd: RefCounted = CrowdPresentationScript.new()
	var retention := {"actor_scenes": GlbSceneCache.retention_snapshot(),
		"animations": NativeAnimationImporter.retention_snapshot(),
		"world_meshes": ExternalMeshPool.retention_snapshot(),
		"world_textures": ExternalTexturePool.retention_snapshot()}
	for passes: Dictionary in [{"world_park": park, "crowd": crowd, "retention": retention},
			{"world_park": park, "crowd": crowd}]:
		MemoryCensus.snapshot(passes)
		var started := Time.get_ticks_usec()
		for call: int in 100:
			MemoryCensus.snapshot(passes)
		var average := (Time.get_ticks_usec() - started) / 100.0
		var label := "with Main's retention" if passes.has("retention") else "asking every cache"
		info("census %s: %.1f us a call" % [label, average])
		expect(average < 1000.0, "the census costs under 1 ms a call %s (%.1f us)" % [label, average])
	_check_class_record_cost()
	var started := Time.get_ticks_usec()
	for call: int in 100:
		MemoryCensus.os_memory()
	info("of which OS.get_memory_info: %.1f us a call" % ((Time.get_ticks_usec() - started) / 100.0))
	park.free()

func _check_class_record_cost() -> void:
	var started := Time.get_ticks_usec()
	for call: int in 100:
		MemoryCensus.class_record()
	var average := (Time.get_ticks_usec() - started) / 100.0
	info("class_record: %.1f us a call" % average)
	expect(average < 1000.0, "class_record costs under 1 ms (%.1f us)" % average)
