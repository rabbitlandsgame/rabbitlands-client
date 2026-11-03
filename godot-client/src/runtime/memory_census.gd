extends RefCounted
## Lightweight memory census (perf work 2026-11, memory classes M3; RAM-13,
## GAP-07): one plain-data row that says where the client's memory is, cheap
## enough to ride on every diagnostics snapshot (Main's `viewport_snapshot`,
## every 30 s) and on the QA harness's samples.
##
## `snapshot()` reads counters only: it walks no resource, reads nothing back
## from the GPU and holds no reference (measured 0.1-0.5 ms a call, most of it
## OS.get_memory_info() on Windows; see tests/test_memory_census.gd). Main
## thread only: the scene cache's figures live there. The row:
##
##   class, class_basis, class_source, budgets
##       This session's memory class (memory_budgets.gd) and its budget row.
##   os       {physical, free, available} from OS.get_memory_info(), which
##            release builds also answer. On Windows Godot reports the
##            physical memory still free as "free" and the commit charge still
##            available (physical plus page file) as "available"; on Linux
##            "available" is MemAvailable.
##   process  This process's resident memory: on Linux /proc/self/status
##            (working_set = VmRSS, peak_working_set = VmHWM, anonymous =
##            RssAnon); on Windows the native client runtime's
##            process_memory() when it is loaded and offers one (MEM-M10, not
##            built yet). Otherwise {"available": false, "reason"}. The QA
##            harness samples the working set and private bytes from outside
##            (tests/integration/process_memory_sampler.py).
##   godot    Godot's own counters: static (and static_peak), which only a
##            debug build tracks ("static_tracked"; a release template reports
##            0, GAP-07), the renderer's video/texture/buffer memory, object,
##            resource, node and orphan-node counts, and pipeline compilations.
##   caches   One row per retaining cache, read generically from its own
##            snapshot: {entries, bytes, budget, evictions}, -1 for a figure
##            the cache does not report (`cache_row`). Bytes are the caches'
##            ledger estimates (resource_bytes.gd), not measured allocations,
##            and shared resources can appear in two caches (a pooled texture
##            in a world scene, for one), so the rows are not summed.
##   untracked  The working set that no Godot counter explains: working set -
##            static - (video memory on an integrated GPU, whose memory is
##            the system's), only when both the process counters and static
##            tracking are available; else {"available": false, "reason"}.
##
## Budgets never act on these counters: they act on the caches' ledgers. The
## census is for logs, measurements and the attribution work (MEM-M8).
##
## No `class_name` (preloaded, like memory_budgets.gd).

const MemoryBudgets := preload("res://src/runtime/memory_budgets.gd")
const ExternalMeshPool := preload("res://src/world/external_mesh_pool.gd")
const ExternalTexturePool := preload("res://src/world/external_texture_pool.gd")

## The figures every cache row carries (-1 when the cache does not report one).
const CACHE_FIELDS: Array[String] = ["entries", "bytes", "budget", "evictions"]
## Breakdowns a cache row keeps when the cache reports them.
const CACHE_DETAILS: Array[String] = ["bytes_by_domain", "bytes_by_kind", "idle_bytes", "pending_rows"]
## The caches whose retention_snapshot() Main already collects in its
## diagnostics row ("resource_retention"), by the same names.
const RETENTION_CACHES: Array[String] = ["actor_scenes", "animations", "world_meshes", "world_textures"]
const PROC_STATUS := "/proc/self/status"
## /proc/self/status fields -> census names (values are in kB there).
const PROC_FIELDS := {"VmRSS": "working_set", "VmHWM": "peak_working_set", "RssAnon": "anonymous"}
## /proc/self/status has about 60 lines; never read more than this.
const PROC_MAX_LINES := 256

## The memory census row (see the header). `context` carries what only Main
## holds, every key optional:
##   "world_park": the WorldPark node (kept bytes against its budget);
##   "crowd": the CrowdPresentation (bodies parked for reuse);
##   "retention": {name: retention_snapshot()} already collected this frame
##       (Main's "resource_retention"), so they are not asked twice.
static func snapshot(context: Dictionary = {}) -> Dictionary:
	var started := Time.get_ticks_usec()
	if OS.get_thread_caller_id() != OS.get_main_thread_id():
		return {"available": false, "reason": "main_thread_only"}
	var session := MemoryBudgets.current()
	var godot := godot_counters()
	var process := process_counters()
	var row := {
		"class": str(session.get("class", "")), "class_basis": session.get("basis", []),
		"class_source": str(session.get("source", "")), "budgets": MemoryBudgets.budgets(),
		"os": os_memory(), "process": process, "godot": godot,
		"caches": caches(context),
		"untracked": untracked(process, godot, str(session.get("adapter_class", ""))),
	}
	row["census_usec"] = Time.get_ticks_usec() - started
	return row

## The one-per-session record of the class (Main's `memory_class` diagnostic):
## MemoryBudgets.current() (class, source, probed class, basis, adapter class,
## memory) with the class's budget row and the machine's physical memory.
static func class_record() -> Dictionary:
	var record := MemoryBudgets.current()
	record["budgets"] = MemoryBudgets.budgets()
	record["physical_bytes"] = int(OS.get_memory_info().get("physical", -1))
	return record

## OS.get_memory_info() (see the header for what each figure means per OS);
## -1 for a figure the platform does not give.
static func os_memory() -> Dictionary:
	var info := OS.get_memory_info()
	return {"physical": int(info.get("physical", -1)), "free": int(info.get("free", -1)),
		"available": int(info.get("available", -1))}

## Godot's own counters (see the header). Every read is a counter: no walk.
static func godot_counters() -> Dictionary:
	return {
		"static": OS.get_static_memory_usage(), "static_peak": OS.get_static_memory_peak_usage(),
		"static_tracked": OS.is_debug_build(),
		"video": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_VIDEO_MEM_USED),
		"texture": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TEXTURE_MEM_USED),
		"buffer": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_BUFFER_MEM_USED),
		"objects": int(Performance.get_monitor(Performance.OBJECT_COUNT)),
		"resources": int(Performance.get_monitor(Performance.OBJECT_RESOURCE_COUNT)),
		"nodes": int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)),
		"orphan_nodes": int(Performance.get_monitor(Performance.OBJECT_ORPHAN_NODE_COUNT)),
		"pipeline_compilations": {
			"canvas": int(Performance.get_monitor(Performance.PIPELINE_COMPILATIONS_CANVAS)),
			"mesh": int(Performance.get_monitor(Performance.PIPELINE_COMPILATIONS_MESH)),
			"surface": int(Performance.get_monitor(Performance.PIPELINE_COMPILATIONS_SURFACE)),
			"draw": int(Performance.get_monitor(Performance.PIPELINE_COMPILATIONS_DRAW)),
			"specialization": int(Performance.get_monitor(Performance.PIPELINE_COMPILATIONS_SPECIALIZATION)),
		},
	}

## This process's memory, in bytes: {"available": true, "source", "working_set",
## "peak_working_set", ...} or {"available": false, "reason"}.
static func process_counters() -> Dictionary:
	if OS.get_name() in ["Linux", "FreeBSD", "NetBSD", "OpenBSD", "BSD", "Android"]:
		return read_proc_status(PROC_STATUS)
	var controller := ClientRuntimeController.current()
	var native: Object = controller.native_runtime() if controller != null else null
	return native_process_counters(native)

## The process counters a native client runtime offers (MEM-M10's
## `process_memory()`: a Dictionary of byte counts), or why there are none.
static func native_process_counters(native: Object) -> Dictionary:
	if native == null:
		return {"available": false, "reason": "native_runtime_not_loaded"}
	if not native.has_method(&"process_memory"):
		return {"available": false, "reason": "native_process_memory_missing"}
	var reported: Variant = native.call(&"process_memory")
	if reported is not Dictionary or int((reported as Dictionary).get("working_set", -1)) < 0:
		return {"available": false, "reason": "native_process_memory_invalid"}
	var counters := {"available": true, "source": "native_runtime"}
	for key: Variant in reported:
		var value: Variant = reported[key]
		if value is int or value is float:
			counters[str(key)] = int(value)
	return counters

## Reads a /proc/<pid>/status file (its size reads as 0, so line by line).
## At most PROC_MAX_LINES lines, and it stops at a read error: a failing read
## that never reaches EOF returns empty lines forever, and this runs on the
## main thread.
static func read_proc_status(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {"available": false, "reason": "proc_status_unreadable"}
	var lines := PackedStringArray()
	for count: int in PROC_MAX_LINES:
		var line := file.get_line()
		if file.eof_reached() and line.is_empty():
			break
		if file.get_error() != OK and file.get_error() != ERR_FILE_EOF:
			break
		lines.append(line)
	return parse_proc_status("\n".join(lines))

## The census fields of /proc/self/status text (kB values, in bytes).
static func parse_proc_status(text: String) -> Dictionary:
	var counters := {"available": true, "source": "proc_status"}
	for line: String in text.split("\n", false):
		var name := line.get_slice(":", 0).strip_edges()
		if not PROC_FIELDS.has(name):
			continue
		var value := line.get_slice(":", 1).strip_edges().get_slice(" ", 0)
		if value.is_valid_int():
			counters[PROC_FIELDS[name]] = int(value) * 1024
	if not counters.has("working_set"):
		return {"available": false, "reason": "proc_status_without_vmrss"}
	return counters

## The working set no Godot counter explains (see the header).
static func untracked(process: Dictionary, godot: Dictionary, adapter_class: String) -> Dictionary:
	if not bool(process.get("available", false)):
		return {"available": false, "reason": "no_process_counters"}
	if not bool(godot.get("static_tracked", false)):
		return {"available": false, "reason": "static_untracked"}
	var integrated := adapter_class == "integrated"
	var bytes := int(process.working_set) - int(godot.static) - (int(godot.video) if integrated else 0)
	return {"available": true, "bytes": bytes,
		"basis": "working_set - static - video" if integrated else "working_set - static"}

## One row per retaining cache (see the header and `snapshot` for `context`).
static func caches(context: Dictionary = {}) -> Dictionary:
	var retention: Dictionary = context.get("retention", {}) if context.get("retention") is Dictionary else {}
	var rows := {}
	for name: String in RETENTION_CACHES:
		var given: Variant = retention.get(name)
		rows[name] = cache_row(given if given is Dictionary else _retention(name))
	var bake := RLHeadIdentityBake.describe()
	# The bake names its budget "budget_bytes" and reports no evictions.
	bake["budget"] = int(bake.get("budget_bytes", -1))
	rows["rl_identity_bake"] = cache_row(bake)
	rows["rl_heads"] = rl_head_row()
	rows["world_park"] = world_park_row(context.get("world_park"))
	rows["crowd_park"] = crowd_park_row(context.get("crowd"))
	return rows

static func _retention(name: String) -> Dictionary:
	match name:
		"actor_scenes": return GlbSceneCache.retention_snapshot()
		"animations": return NativeAnimationImporter.retention_snapshot()
		"world_meshes": return ExternalMeshPool.retention_snapshot()
		"world_textures": return ExternalTexturePool.retention_snapshot()
	return {}

## {entries, bytes, budget, evictions} of a cache's own snapshot, -1 for a
## figure it does not report, plus the breakdowns in CACHE_DETAILS it has.
static func cache_row(source: Dictionary) -> Dictionary:
	var row := {}
	for field: String in CACHE_FIELDS:
		var value: Variant = source.get(field)
		row[field] = int(value) if value is int or value is float else -1
	for field: String in CACHE_DETAILS:
		if source.has(field):
			var value: Variant = source[field]
			row[field] = value.duplicate() if value is Dictionary else value
	return row

## The RL head file cache's row once it reports one (MEM-M4 gives
## RLHeadLibrary a static retention_snapshot(); a Script answers has_method
## for its static functions, checked in tests/test_memory_census.gd); until
## then its users and warm-up state only. `library` stands in for
## RLHeadLibrary in tests.
static func rl_head_row(library: Object = null) -> Dictionary:
	var source: Variant = RLHeadLibrary
	if library != null:
		source = library
	if (source as Object).has_method(&"retention_snapshot"):
		var reported: Variant = (source as Object).call(&"retention_snapshot")
		if reported is Dictionary:
			return cache_row(reported)
	var row := cache_row({})
	row["users"] = RLHeadLibrary.users()
	row["warming"] = RLHeadLibrary.warming()
	return row

## WorldPark: parked worlds, the bytes kept (parked and preloaded) against the
## class budget, worlds evicted, and whether it preloads.
static func world_park_row(park: Variant) -> Dictionary:
	if not is_instance_valid(park) or not (park as Object).has_method(&"kept_bytes"):
		return cache_row({})
	var node := park as Object
	var counters: Variant = node.get(&"counters")
	var row := cache_row({"entries": (node.call(&"parked_maps") as Array).size(),
		"bytes": int(node.call(&"kept_bytes")), "budget": int(node.get(&"budget_bytes")),
		"evictions": int((counters as Dictionary).get("evict", -1)) if counters is Dictionary else -1})
	row["preload_enabled"] = bool(node.get(&"preload_enabled"))
	return row

## The crowd's park pool: bodies parked for reuse against the pool's limit
## (`park_limit` once it follows the class, else PARK_LIMIT).
static func crowd_park_row(crowd: Variant) -> Dictionary:
	if crowd == null or (crowd is Object and not is_instance_valid(crowd)) \
			or not (crowd as Object).has_method(&"parked_count"):
		return cache_row({})
	var object := crowd as Object
	var limit: Variant = object.get(&"park_limit")
	if limit == null:
		limit = object.get(&"PARK_LIMIT")
	return cache_row({"entries": int(object.call(&"parked_count")),
		"budget": int(limit) if limit != null else -1})
