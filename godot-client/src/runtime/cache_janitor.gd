extends Node
## Stale cache janitor (UD-03). Removes cache generations the running client can
## never read again from the player's user folder, on a low-priority worker,
## DELAY_SECONDS after the update checker starts (the login screen), in release
## builds only (`client_release.json` `release_build`), and stops at the next
## file when the client closes. It prints one `RABBITLANDS_CACHE_JANITOR` line
## with what it freed.
##
## What it removes:
## - `user://map-geometry-cache`, `map-collision-cache`, `map-paving-cache`:
##   policy folders whose own entry header proves them stale
##   (MapCollisionCache.classify_policy_dirs). The newest policy of every
##   renderer family is kept: the running policy and each family's policy under
##   this engine, VERSION and format (`forward_plus`, which Mobile shares, and
##   `gl_compatibility`), so a player who switches renderers keeps both caches
##   (schedule 1.1 #17). A folder goes only when its header's schema is older,
##   or equal while its digest is no current one (engine or format changed, or
##   Mobile's retired own key); a newer schema, an unreadable header, a live
##   preparation lock or a foreign name is kept. Nothing here runs while a
##   preparation holds the cache or one is still pending.
## - `user://map-cache`: entries of geometry-scoped whole maps, whose legacy
##   scene-cache format the current loader never reads (the same exact-name
##   rule WorldLoader applies when such a map loads). An entry has no format
##   header to read, so other maps' entries are left to the loader's own prune.
## - `user://shader_cache` (owner-gated, off by default: SHADER_RULE_DEFAULT,
##   `RABBITLANDS_CACHE_JANITOR_SHADERS=on|off`): per shader, generation folders
##   that are not the newest and whose newest file is older than 14 days, and
##   the oldest files of a GLES3 shader over 128 MiB.
## It never touches `vulkan/` or `d3d12/` pipeline caches, `client-updates`,
## settings or anything else.
##
## `RABBITLANDS_CACHE_JANITOR=off` disables it; `on` also runs it in a source or
## editor build (a developer profile). It stays off in timed benchmark runs
## (`RABBITLANDS_CROWD_BENCH_START_TOKEN`) unless switched `on`. Cancellation is
## checked while planning too, so closing the client never waits for a scan.
## No class_name: callers load this file.

const GeometryCache := preload("res://src/world/map_geometry_cache.gd")
const CollisionCache := preload("res://src/world/map_collision_cache.gd")
const PavingCache := preload("res://src/world/map_paving_cache.gd")
const SceneCache := preload("res://src/world/map_scene_cache.gd")

const DELAY_SECONDS := 30.0
const SWITCH_ENVIRONMENT := "RABBITLANDS_CACHE_JANITOR"
const SHADER_ENVIRONMENT := "RABBITLANDS_CACHE_JANITOR_SHADERS"
## Set by the crowd benchmark harness for every timed run (source or exported).
const BENCHMARK_ENVIRONMENT := "RABBITLANDS_CROWD_BENCH_START_TOKEN"
## The shader rule waits for the owner's approval of the 14-day / 128 MiB rule
## (a removed generation that is still in use recompiles once: a hitch).
const SHADER_RULE_DEFAULT := false
const SHADER_DIRECTORY := "user://shader_cache"
const SHADER_MAX_AGE_SECONDS := 14 * 86400
const GLES3_CAP_BYTES := 134217728
const LOG_PREFIX := "RABBITLANDS_CACHE_JANITOR"
const MAX_DEPTH := 4
const POLICY_CACHES := ["geometry","collision","paving"]

signal finished(result: Dictionary)

## Overrides for prepare_options (tests): directories, `delay`, `shaders`, ...
var options: Dictionary = {}
var report: Dictionary = {}
var _thread: Thread
var _timer: Timer
var _cancel_mutex := Mutex.new()
var _cancelled := false

# --------------------------------------------------------------------------
# Switches
# --------------------------------------------------------------------------

static func _switch(variable: String) -> String:
	var value := OS.get_environment(variable).strip_edges().to_lower()
	if value in ["0","off","false","no"]: return "off"
	if value in ["1","on","true","yes"]: return "on"
	return ""

## True when this client should run the janitor: a release build (not the
## editor, not the web, not a timed benchmark run), unless switched off; `on`
## also runs it elsewhere.
static func should_run(identity: Dictionary) -> bool:
	return _should_run(identity,OS.has_feature("editor"))

## should_run() with the editor feature given (tests exercise the release path
## from the editor binary). Maintenance is never part of a timed run: like
## main.gd's pre-login preparation, the janitor stays off while the benchmark
## harness's start token is set (exported release-build A/Bs included).
static func _should_run(identity: Dictionary, editor_build: bool) -> bool:
	var switch := _switch(SWITCH_ENVIRONMENT)
	if switch == "off" or OS.has_feature("web"): return false
	if switch == "on": return true
	if not OS.get_environment(BENCHMARK_ENVIRONMENT).is_empty(): return false
	return not editor_build and identity.get("release_build",false) == true

static func shader_rule_enabled() -> bool:
	var switch := _switch(SHADER_ENVIRONMENT)
	return SHADER_RULE_DEFAULT if switch.is_empty() else switch == "on"

## The node update checker adds (deferred) when should_run(identity); null
## otherwise.
static func schedule(host: Node, identity: Dictionary) -> Node:
	if host == null or not should_run(identity): return null
	var janitor: Node = (load("res://src/runtime/cache_janitor.gd") as Script).new()
	janitor.name = "CacheJanitor"
	host.add_child.call_deferred(janitor)
	return janitor

# --------------------------------------------------------------------------
# Plan (read only) and apply
# --------------------------------------------------------------------------

## Main thread: everything the worker needs that reads engine or cache state.
## `overrides` replaces any key (tests point the directories elsewhere).
static func prepare_options(overrides := {}) -> Dictionary:
	var prepared := {
		"geometry_directory":GeometryCache.DIRECTORY,
		"collision_directory":CollisionCache.DIRECTORY,
		"paving_directory":PavingCache.DIRECTORY,
		"map_cache_directory":SceneCache.CACHE_DIRECTORY,
		"shader_directory":SHADER_DIRECTORY,
		"shaders":shader_rule_enabled(),
		"shader_max_age":SHADER_MAX_AGE_SECONDS,
		"gles3_cap":GLES3_CAP_BYTES,
		"now":int(Time.get_unix_time_from_system()),
		"cooking":GeometryCache.cooking,
	}
	if not overrides.has("tables"):
		prepared["tables"] = {"geometry":GeometryCache.janitor_policies(),
			"collision":CollisionCache.janitor_policies(),"paving":PavingCache.janitor_policies()}
	if not overrides.has("preparation_pending"):
		prepared["preparation_pending"] = GeometryCache.needs_preparation()
	prepared.merge(overrides,true)
	return prepared

## Only folders inside the user data folder are ever planned for removal.
static func _user_folder(path: String) -> bool:
	return path.begins_with("user://") and path.length() > "user://".length() and path.simplify_path() == path \
		and not ".." in path.trim_prefix("user://").split("/")

static func _stopped(cancelled: Callable) -> bool:
	return cancelled.is_valid() and bool(cancelled.call())

## The plan of a run cancelled while planning: nothing to remove.
static func _cancelled_plan() -> Dictionary:
	var result := {"policies":{},"map_cache":PackedStringArray(),"shader_dirs":[],"shader_files":[],"cancelled":true}
	for cache: String in POLICY_CACHES: result.policies[cache] = {"skipped":"cancelled","stale":[],"kept":[]}
	return result

## What a run would remove, without removing anything. Safe on a worker.
## `cancelled` is checked before each step and per shader file: a scan that is
## cancelled (the client is closing) stops there and plans nothing.
static func plan(prepared: Dictionary, cancelled := Callable()) -> Dictionary:
	var result := {"policies":{},"map_cache":PackedStringArray(),"shader_dirs":[],"shader_files":[],"cancelled":false}
	if _stopped(cancelled): return _cancelled_plan()
	var skip := ""
	var geometry := str(prepared.get("geometry_directory",""))
	if not _user_folder(geometry):
		skip = "outside_user_data"
	elif bool(prepared.get("cooking",false)) or CollisionCache.preparation_locked(geometry):
		skip = "preparation_active"
	elif bool(prepared.get("preparation_pending",false)):
		skip = "preparation_pending"
	var tables: Dictionary = prepared.get("tables",{})
	for cache: String in POLICY_CACHES:
		if _stopped(cancelled): return _cancelled_plan()
		var row := {"skipped":skip,"stale":[],"kept":[]}
		var directory := str(prepared.get(cache+"_directory",""))
		if skip.is_empty() and not _user_folder(directory): row.skipped = "outside_user_data"
		elif skip.is_empty():
			var limit := GeometryCache.MAX_METADATA_BYTES if cache == "geometry" else CollisionCache.MAX_METADATA_BYTES
			var sorted := CollisionCache.classify_policy_dirs(directory,tables.get(cache,{}),limit)
			row.skipped = str(sorted.reason) if not bool(sorted.ok) else ""
			row.stale = sorted.stale
			row.kept = sorted.kept
		result.policies[cache] = row
	if _stopped(cancelled): return _cancelled_plan()
	var map_cache := str(prepared.get("map_cache_directory",""))
	var names := SceneCache.entry_map_names(map_cache) if _user_folder(map_cache) else PackedStringArray()
	if not names.is_empty():
		result.map_cache = SceneCache.stale_format_entries(GeometryCache.scoped_whole_map_ids(names),map_cache)
	if _stopped(cancelled): return _cancelled_plan()
	if bool(prepared.get("shaders",false)) and _user_folder(str(prepared.get("shader_directory",""))):
		var shaders := shader_plan(str(prepared.get("shader_directory","")),int(prepared.get("now",0)),
			int(prepared.get("shader_max_age",SHADER_MAX_AGE_SECONDS)),int(prepared.get("gles3_cap",GLES3_CAP_BYTES)),cancelled)
		if bool(shaders.get("cancelled",false)): return _cancelled_plan()
		result.shader_dirs = shaders.dirs
		result.shader_files = shaders.files
	return result

static func _hex(value: String, length: int) -> bool:
	if value.length() != length: return false
	for character: String in value:
		if not character in "0123456789abcdef": return false
	return true

static func _size(path: String) -> int:
	var file := FileAccess.open(path,FileAccess.READ)
	return file.get_length() if file != null else 0

## Per shader folder under `directory`: generation folders (64-hex names) that
## are not the newest and whose newest file is older than `max_age` seconds at
## `now`, and, for a `*GLES3` shader whose kept files exceed `cap` bytes, its
## oldest files (oldest modification first, then by path) until it fits. An
## empty generation is kept (no bytes; the engine may still write into it).
## A cancelled scan returns nothing (`"cancelled": true`): a partial scan cannot
## tell which generation is the newest.
static func shader_plan(directory: String, now: int, max_age := SHADER_MAX_AGE_SECONDS, cap := GLES3_CAP_BYTES, cancelled := Callable()) -> Dictionary:
	var result := {"dirs":[],"files":[]}
	var root := DirAccess.open(directory)
	if root == null: return result
	for shader: String in root.get_directories():
		if _stopped(cancelled): return {"dirs":[],"files":[],"cancelled":true}
		var shader_path := directory.path_join(shader)
		if root.is_link(shader_path): continue
		var folder := DirAccess.open(shader_path)
		if folder == null: continue
		var generations: Array = []
		var newest_all := 0
		for generation: String in folder.get_directories():
			var path := shader_path.path_join(generation)
			if not _hex(generation,64) or folder.is_link(path): continue
			var files_dir := DirAccess.open(path)
			if files_dir == null: continue
			var files: Array = []
			var newest := 0
			for file: String in files_dir.get_files():
				if _stopped(cancelled): return {"dirs":[],"files":[],"cancelled":true}
				var file_path := path.path_join(file)
				var modified := int(FileAccess.get_modified_time(file_path))
				files.append({"path":file_path,"modified":modified,"bytes":_size(file_path)})
				newest = maxi(newest,modified)
			generations.append({"path":path,"newest":newest,"files":files})
			newest_all = maxi(newest_all,newest)
		var kept_files: Array = []
		for generation: Dictionary in generations:
			if generation.files.is_empty() or int(generation.newest) >= newest_all or now - int(generation.newest) <= max_age:
				kept_files.append_array(generation.files)
				continue
			var bytes := 0
			for file: Dictionary in generation.files: bytes += int(file.bytes)
			result.dirs.append({"path":generation.path,"shader":shader,"bytes":bytes,"files":generation.files.size(),"newest":generation.newest})
		if not shader.ends_with("GLES3"): continue
		var total := 0
		for file: Dictionary in kept_files: total += int(file.bytes)
		if total <= cap: continue
		kept_files.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
			return int(a.modified) < int(b.modified) if int(a.modified) != int(b.modified) else str(a.path) < str(b.path))
		for file: Dictionary in kept_files:
			if total <= cap: break
			result.files.append({"path":file.path,"shader":shader,"bytes":file.bytes,"modified":file.modified})
			total -= int(file.bytes)
	return result

## Removes a folder tree: subfolders first with `entries` last (an interrupted
## removal keeps the header that proves the rest stale), then the folder. Never
## follows or removes a link. Returns {"bytes","files","complete"}.
static func remove_tree(folder: String, cancelled: Callable, depth := 0) -> Dictionary:
	var out := {"bytes":0,"files":0,"complete":true}
	var directory := DirAccess.open(folder)
	if directory == null or depth > MAX_DEPTH:
		out.complete = false
		return out
	directory.include_hidden = true
	var children: Array = []
	var last: Array = []
	for name: String in directory.get_directories():
		(last if name == "entries" else children).append(name)
	var steps: Array = []
	for name: String in children: steps.append([true,name])
	for name: String in directory.get_files(): steps.append([false,name])
	for name: String in last: steps.append([true,name])
	for step: Array in steps:
		if cancelled.is_valid() and bool(cancelled.call()):
			out.complete = false
			return out
		var path := folder.path_join(str(step[1]))
		if directory.is_link(path):
			out.complete = false
			continue
		if bool(step[0]):
			var inner := remove_tree(path,cancelled,depth+1)
			out.bytes += int(inner.bytes)
			out.files += int(inner.files)
			if not bool(inner.complete): out.complete = false
		else:
			var bytes := _size(path)
			if DirAccess.remove_absolute(path) == OK:
				out.bytes += bytes
				out.files += 1
			else:
				out.complete = false
	if bool(out.complete) and DirAccess.remove_absolute(folder) != OK: out.complete = false
	return out

static func _remove_file(path: String) -> int:
	var bytes := _size(path)
	return bytes if DirAccess.remove_absolute(path) == OK else -1

## Removes what `planned` lists. Before each policy folder it checks again that
## no preparation has started. Returns the report (see run()).
static func apply(planned: Dictionary, prepared: Dictionary, cancelled := Callable()) -> Dictionary:
	var summary := {"status":"done","freed_bytes":0,"removed_files":0,"policies":{},"map_cache":{"removed":0,"bytes":0},
		"shaders":{"enabled":bool(prepared.get("shaders",false)),"generations":0,"files":0,"bytes":0}}
	var stop := func() -> bool: return cancelled.is_valid() and bool(cancelled.call())
	var geometry := str(prepared.get("geometry_directory",""))
	for cache: String in POLICY_CACHES:
		var row: Dictionary = planned.get("policies",{}).get(cache,{"skipped":"missing","stale":[],"kept":[]})
		var kept := {}
		for item: Dictionary in row.get("kept",[]): kept[str(item.reason)] = int(kept.get(str(item.reason),0))+1
		var out := {"skipped":str(row.get("skipped","")),"removed":[],"kept":kept}
		for item: Dictionary in row.get("stale",[]):
			if stop.call():
				summary.status = "cancelled"
				break
			if GeometryCache.cooking or CollisionCache.preparation_locked(geometry):
				out.skipped = "preparation_started"
				break
			var removed := remove_tree(str(item.path),cancelled)
			out.removed.append({"policy":str(item.policy).substr(0,12),"reason":str(item.reason),
				"bytes":int(removed.bytes),"complete":bool(removed.complete)})
			summary.freed_bytes += int(removed.bytes)
			summary.removed_files += int(removed.files)
		summary.policies[cache] = out
	for path: String in planned.get("map_cache",PackedStringArray()):
		if stop.call():
			summary.status = "cancelled"
			break
		var bytes := _remove_file(path)
		if bytes < 0: continue
		summary.map_cache.removed += 1
		summary.map_cache.bytes += bytes
		summary.freed_bytes += bytes
		summary.removed_files += 1
	for item: Dictionary in planned.get("shader_dirs",[]):
		if stop.call():
			summary.status = "cancelled"
			break
		var removed := remove_tree(str(item.path),cancelled)
		summary.shaders.generations += 1
		summary.shaders.files += int(removed.files)
		summary.shaders.bytes += int(removed.bytes)
		summary.freed_bytes += int(removed.bytes)
		summary.removed_files += int(removed.files)
	for item: Dictionary in planned.get("shader_files",[]):
		if stop.call():
			summary.status = "cancelled"
			break
		var bytes := _remove_file(str(item.path))
		if bytes < 0: continue
		summary.shaders.files += 1
		summary.shaders.bytes += bytes
		summary.freed_bytes += bytes
		summary.removed_files += 1
	if stop.call() or bool(planned.get("cancelled",false)): summary.status = "cancelled"
	return summary

## plan() then apply(), timed. Safe on a worker once `prepared` came from
## prepare_options() on the main thread.
static func run(prepared: Dictionary, cancelled := Callable()) -> Dictionary:
	var began := Time.get_ticks_msec()
	var planned := plan(prepared,cancelled)
	var result := apply(planned,prepared,cancelled)
	result["elapsed_ms"] = Time.get_ticks_msec()-began
	return result

static func log_line(result: Dictionary) -> String:
	return LOG_PREFIX+" "+JSON.stringify(result,"",true)

# --------------------------------------------------------------------------
# Node: delay, low-priority worker, cancellation on exit
# --------------------------------------------------------------------------

func _ready() -> void:
	set_process(false)
	_timer = Timer.new()
	_timer.one_shot = true
	_timer.wait_time = maxf(0.01,float(options.get("delay",DELAY_SECONDS)))
	_timer.timeout.connect(_start)
	add_child(_timer)
	_timer.start()

func cancel() -> void:
	_cancel_mutex.lock()
	_cancelled = true
	_cancel_mutex.unlock()

func is_cancelled() -> bool:
	_cancel_mutex.lock()
	var value := _cancelled
	_cancel_mutex.unlock()
	return value

func is_idle() -> bool:
	return _thread == null

func _start() -> void:
	if _thread != null or is_cancelled(): return
	var prepared := prepare_options(options)
	_thread = Thread.new()
	if _thread.start(_work.bind(prepared),Thread.PRIORITY_LOW) != OK:
		_thread = null
		_finish({"status":"skipped","reason":"worker_unavailable"})
		return
	set_process(true)

func _work(prepared: Dictionary) -> Dictionary:
	return run(prepared,is_cancelled)

func _process(_delta: float) -> void:
	if _thread == null or _thread.is_alive(): return
	var result: Variant = _thread.wait_to_finish()
	_thread = null
	set_process(false)
	_finish(result if result is Dictionary else {"status":"failed"})

func _finish(result: Dictionary) -> void:
	report = result
	print(log_line(result))
	finished.emit(result)

func _exit_tree() -> void:
	cancel()
	if _thread != null:
		var result: Variant = _thread.wait_to_finish()
		_thread = null
		report = result if result is Dictionary else {"status":"cancelled"}
