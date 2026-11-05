extends SceneTree
## UD-03 stale cache janitor: a fake user tree (policy folders of the three map
## caches, map-cache entries, shader generations), what one run keeps and
## removes, the per-renderer keep rule (schedule 1.1 #17; Mobile keys as
## forward_plus), runs during an active or pending preparation, cancellation,
## the shader owner gate, and the node's worker and exit.
const Janitor := preload("res://src/runtime/cache_janitor.gd")
const GeometryCache := preload("res://src/world/map_geometry_cache.gd")
const CollisionCache := preload("res://src/world/map_collision_cache.gd")
const PavingCache := preload("res://src/world/map_paving_cache.gd")
const SceneCache := preload("res://src/world/map_scene_cache.gd")
const RendererFamily := preload("res://src/runtime/renderer_family.gd")
const ROOT := "user://cache-janitor-test"
const GEOMETRY := ROOT + "/map-geometry-cache"
const COLLISION := ROOT + "/map-collision-cache"
const PAVING := ROOT + "/map-paving-cache"
const MAP_CACHE := ROOT + "/map-cache"
const SHADERS := ROOT + "/shader_cache"
const KEY := "0123456789abcdef"

var _checks := 0
var _failures := 0
var _fixture: Dictionary = {}

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, label: String) -> void:
	_checks += 1
	if not ok:
		_failures += 1
		push_error(label)

func _hash(text: String) -> String:
	return text.sha256_text()

func _write(path: String, text: String) -> int:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(text)
	file.close()
	return text.to_utf8_buffer().size()

## A policy folder with one entry header (`schema`, `header_policy`, default
## the folder's own name) and one blob; returns its bytes.
func _policy(directory: String, name: String, schema: int, header_policy := "", blob_extension := "scn") -> int:
	var folder := directory.path_join(name)
	var bytes := 0
	if schema >= 0:
		var header := {"schema": schema, "policy": name if header_policy.is_empty() else header_policy,
			"source": "res://fixture/world.json"}
		bytes += _write(folder.path_join("entries").path_join(_hash(name + "entry") + ".json"), JSON.stringify(header, "", true, true))
	bytes += _write(folder.path_join("blobs").path_join(_hash(name + "blob") + "." + blob_extension), "blob " + name)
	return bytes

func _exists(path: String) -> bool:
	return DirAccess.dir_exists_absolute(path) or FileAccess.file_exists(path)

func _clear(folder: String) -> void:
	if DirAccess.dir_exists_absolute(folder):
		Janitor.remove_tree(folder, Callable())

func _sleep_past_second() -> void:
	OS.delay_msec(2100)

## The fixture; `_fixture` records every path and the bytes that must go.
func _build(locked := false) -> void:
	_clear(ROOT)
	_fixture = {"stale_bytes": 0, "map_cache_bytes": 0}
	var geometry_version := GeometryCache.VERSION
	var fplus := GeometryCache.policy_for(RendererFamily.FORWARD_PLUS)
	var compat := GeometryCache.policy_for(RendererFamily.COMPATIBILITY)
	var mobile := GeometryCache.policy_for(RendererFamily.MOBILE)
	var names := {
		"fplus": fplus, "compat": compat, "mobile": mobile,
		"old_version": _hash("geometry old version"), "old_engine": _hash("geometry other engine"),
		"newer": _hash("geometry newer client"), "unverified": _hash("geometry blobs only"),
		"mismatch": _hash("geometry header names another policy"), "empty": _hash("geometry empty"),
		"locked": _hash("geometry locked"),
	}
	_fixture["geometry"] = names
	_policy(GEOMETRY, fplus, geometry_version)
	_policy(GEOMETRY, compat, geometry_version)
	_fixture.stale_bytes += _policy(GEOMETRY, mobile, geometry_version)
	_fixture.stale_bytes += _policy(GEOMETRY, names.old_version, geometry_version - 1)
	_fixture.stale_bytes += _policy(GEOMETRY, names.old_engine, geometry_version)
	_write(GEOMETRY.path_join(names.old_engine).path_join("complete.json"), "{}")
	_fixture.stale_bytes += 2
	_policy(GEOMETRY, names.newer, geometry_version + 1)
	_policy(GEOMETRY, names.unverified, -1)
	_policy(GEOMETRY, names.mismatch, geometry_version, _hash("someone else"))
	DirAccess.make_dir_recursive_absolute(GEOMETRY.path_join(names.empty).path_join("entries"))
	DirAccess.make_dir_recursive_absolute(GEOMETRY.path_join(names.empty).path_join("blobs"))
	DirAccess.make_dir_recursive_absolute(GEOMETRY.path_join("notes"))
	_write(GEOMETRY.path_join("notes/readme.txt"), "not a policy folder")
	if locked:
		_policy(GEOMETRY, names.locked, geometry_version - 1)
		_write(GEOMETRY.path_join(names.locked).path_join("preparing.lock/owner.json"),
			JSON.stringify({"pid": OS.get_process_id()}))
	var collision := {"fplus": CollisionCache.policy_for(RendererFamily.FORWARD_PLUS),
		"compat": CollisionCache.policy_for(RendererFamily.COMPATIBILITY),
		"mobile": CollisionCache.policy_for(RendererFamily.MOBILE),
		"old_engine": _hash("collision other engine"), "old_version": _hash("collision old version")}
	_fixture["collision"] = collision
	_policy(COLLISION, collision.fplus, CollisionCache.VERSION, "", "rlc")
	_policy(COLLISION, collision.compat, CollisionCache.VERSION, "", "rlc")
	_fixture.stale_bytes += _policy(COLLISION, collision.mobile, CollisionCache.VERSION, "", "rlc")
	_fixture.stale_bytes += _policy(COLLISION, collision.old_engine, CollisionCache.VERSION, "", "rlc")
	_fixture.stale_bytes += _policy(COLLISION, collision.old_version, CollisionCache.VERSION - 1, "", "rlc")
	var paving := {"fplus": PavingCache.policy_for(RendererFamily.FORWARD_PLUS),
		"compat": PavingCache.policy_for(RendererFamily.COMPATIBILITY),
		"old_engine": _hash("paving other engine")}
	_fixture["paving"] = paving
	_policy(PAVING, paving.fplus, PavingCache.VERSION, "", "res")
	_policy(PAVING, paving.compat, PavingCache.VERSION, "", "res")
	_fixture.stale_bytes += _policy(PAVING, paving.old_engine, PavingCache.VERSION, "", "res")
	# Map cache: two geometry-scoped whole maps (stale), a map outside the
	# scope, a streamed chunk, a write in flight and a foreign name (kept).
	var entries := {
		"scoped_a": MAP_CACHE + "/amberwood_gauntlet-" + KEY + ".scn",
		"scoped_b": MAP_CACHE + "/resin_road_gauntlet-" + KEY.reverse() + ".scn",
		"unscoped": MAP_CACHE + "/lantern_reach-" + KEY + ".scn",
		"chunk": MAP_CACHE + "/boarsend__chunk_09_06-" + KEY + ".scn",
		"staging": MAP_CACHE + "/writing-amberwood_gauntlet-" + KEY + ".scn",
		"short": MAP_CACHE + "/amberwood_gauntlet-0123.scn",
		"other": MAP_CACHE + "/amberwood_gauntlet_old-" + KEY + ".scn",
	}
	_fixture["map_cache"] = entries
	for key: String in entries:
		var bytes := _write(entries[key], "scene " + key)
		if key in ["scoped_a", "scoped_b"]:
			_fixture.map_cache_bytes += bytes
	# Shaders: RD shader with an old generation, a young non-newest one, the
	# newest and an empty one; a GLES3 shader whose newest generation is over
	# the (test) cap, with its oldest file written first.
	var rd := SHADERS + "/SceneForwardClusteredShaderRD"
	var gles := SHADERS + "/SceneShaderGLES3"
	var shaders := {"rd_old": rd.path_join(_hash("rd old")), "rd_young": rd.path_join(_hash("rd young")),
		"rd_newest": rd.path_join(_hash("rd newest")), "rd_empty": rd.path_join(_hash("rd empty")),
		"gles_oldest": gles.path_join(_hash("gles newest")).path_join("z-oldest.cache"),
		"gles_a": gles.path_join(_hash("gles newest")).path_join("a.cache"),
		"gles_b": gles.path_join(_hash("gles newest")).path_join("b.cache"),
		"gles_c": gles.path_join(_hash("gles newest")).path_join("c.cache"),
		"foreign": rd.path_join("not-a-generation")}
	_fixture["shaders"] = shaders
	_write(shaders.rd_old.path_join("old.vulkan.cache"), "x".repeat(300))
	_write(shaders.gles_oldest, "o".repeat(400))
	_sleep_past_second()
	_write(shaders.rd_young.path_join("young.vulkan.cache"), "y".repeat(300))
	_sleep_past_second()
	_write(shaders.rd_newest.path_join("newest.vulkan.cache"), "n".repeat(300))
	_write(shaders.gles_a, "a".repeat(400))
	_write(shaders.gles_b, "b".repeat(400))
	_write(shaders.gles_c, "c".repeat(400))
	DirAccess.make_dir_recursive_absolute(shaders.rd_empty)
	_write(shaders.foreign.path_join("file.cache"), "f")
	var old_time := int(FileAccess.get_modified_time(shaders.rd_old.path_join("old.vulkan.cache")))
	var young_time := int(FileAccess.get_modified_time(shaders.rd_young.path_join("young.vulkan.cache")))
	var newest_time := int(FileAccess.get_modified_time(shaders.rd_newest.path_join("newest.vulkan.cache")))
	_expect(old_time < young_time and young_time < newest_time, "shader fixture generations have distinct times")
	_fixture["now"] = newest_time
	# Older than this many seconds at `now`: the old generation, not the young.
	_fixture["max_age"] = newest_time - young_time

func _options(overrides := {}) -> Dictionary:
	var base := {"geometry_directory": GEOMETRY, "collision_directory": COLLISION, "paving_directory": PAVING,
		"map_cache_directory": MAP_CACHE, "shader_directory": SHADERS, "shaders": true,
		"now": int(_fixture.get("now", 0)), "shader_max_age": int(_fixture.get("max_age", 0)), "gles3_cap": 1000,
		"preparation_pending": false, "cooking": false}
	base.merge(overrides, true)
	return Janitor.prepare_options(base)

func _policy_keys() -> void:
	# The helpers agree with the code that reads each cache.
	_expect(CollisionCache.renderer_families() == PackedStringArray(["forward_plus", "gl_compatibility"]),
		"two renderer families: Mobile keys as forward_plus")
	_expect(GeometryCache.policy_for(RendererFamily.cache_renderer()) == GeometryCache.policy(), "geometry policy_for = policy()")
	_expect(CollisionCache.policy_for(RendererFamily.cache_renderer()) == CollisionCache.policy(), "collision policy_for = policy()")
	_expect(PavingCache.policy_for(RendererFamily.cache_renderer()) == PavingCache.policy(), "paving policy_for = policy()")
	for method: String in ["forward_plus", "mobile", "gl_compatibility"]:
		RendererFamily.override_for_tests(method)
		var family := RendererFamily.cache_renderer(method)
		_expect(CollisionCache.policy_for(family) == CollisionCache.policy(), "collision policy_for under " + method)
		_expect(PavingCache.policy_for(family) == PavingCache.policy(), "paving policy_for under " + method)
		_expect(GeometryCache.policy_for(family) == GeometryCache._policy_digest(), "geometry policy_for under " + method)
		for table: Dictionary in [CollisionCache.janitor_policies(), PavingCache.janitor_policies()]:
			_expect(bool(table.ok), "janitor table valid under " + method)
			_expect((table.current as Dictionary).size() == 2, "two current policies under " + method)
			_expect((table.retired as Dictionary).size() == 1, "the Mobile key is retired under " + method)
		var collision := CollisionCache.janitor_policies()
		_expect(collision.current.has(CollisionCache.policy_for("forward_plus")) and collision.current.has(CollisionCache.policy_for("gl_compatibility")),
			"both families current under " + method)
		_expect(collision.retired.has(CollisionCache.policy_for("mobile")), "Mobile's own key retired under " + method)
	RendererFamily.override_for_tests("")
	# Geometry keeps its initialized policy; a renderer that changed after it
	# initialized (tests only) is refused, not guessed.
	_expect(bool(GeometryCache.janitor_policies().ok), "geometry table valid for the running renderer")
	RendererFamily.override_for_tests("forward_plus" if RendererFamily.cache_renderer() == "gl_compatibility" else "gl_compatibility")
	var drift := GeometryCache.janitor_policies()
	_expect(not bool(drift.ok) and str(drift.reason) == "policy_drift", "geometry table refused when it disagrees with policy()")
	_expect(CollisionCache.classify_policy_dirs(GEOMETRY, drift).stale.is_empty(), "a refused table removes nothing")
	RendererFamily.override_for_tests("")

func _full_run() -> void:
	_build()
	var prepared := _options()
	var planned := Janitor.plan(prepared)
	var geometry: Dictionary = planned.policies.geometry
	var reasons := {}
	for row: Dictionary in geometry.stale: reasons[str(row.policy)] = str(row.reason)
	var kept := {}
	for row: Dictionary in geometry.kept: kept[str(row.policy)] = str(row.reason)
	var names: Dictionary = _fixture.geometry
	_expect(reasons.get(names.mobile) == "renderer_key", "Mobile's retired key is stale")
	_expect(reasons.get(names.old_version) == "version", "an older VERSION is stale")
	_expect(reasons.get(names.old_engine) == "engine_or_format", "another engine or format is stale")
	_expect(reasons.get(names.empty) == "empty", "an empty non-current folder goes")
	_expect(reasons.size() == 4, "exactly four geometry folders are stale")
	# Under any engine method (`--rendering-method`): the running family's policy
	# is "current", the other family's is kept under its own name.
	var running_family := RendererFamily.cache_renderer()
	_expect(kept.get(names.fplus) == ("current" if running_family == "forward_plus" else "current_forward_plus"),
		"the Forward+/Mobile family's policy is kept")
	_expect(kept.get(names.compat) == ("current" if running_family == "gl_compatibility" else "current_gl_compatibility"),
		"the compatibility family's policy is kept")
	_expect(kept.get(names.newer) == "newer_version", "a newer client's folder is kept")
	_expect(kept.get(names.unverified) == "unverified", "a folder without a header is kept")
	_expect(kept.get(names.mismatch) == "unverified", "a header naming another policy proves nothing")
	_expect(planned.map_cache.size() == 2, "two scoped scene-cache entries are stale")
	_expect(planned.shader_dirs.size() == 1 and str(planned.shader_dirs[0].path) == _fixture.shaders.rd_old, "only the old RD generation is planned")
	var gles_files: Array = []
	for item: Dictionary in planned.shader_files: gles_files.append(str(item.path))
	_expect(gles_files == [_fixture.shaders.gles_oldest, _fixture.shaders.gles_a], "GLES3 over the cap loses its oldest files first")
	var result := Janitor.run(prepared)
	_expect(str(result.status) == "done", "run finishes")
	var shader_bytes := 300 + 800
	_expect(int(result.freed_bytes) == int(_fixture.stale_bytes) + int(_fixture.map_cache_bytes) + shader_bytes,
		"freed bytes are the stale fixture's bytes (%d)" % int(result.freed_bytes))
	for key: String in ["mobile", "old_version", "old_engine", "empty"]:
		_expect(not _exists(GEOMETRY.path_join(names[key])), "geometry %s folder removed" % key)
	for key: String in ["fplus", "compat", "newer", "unverified", "mismatch"]:
		_expect(_exists(GEOMETRY.path_join(names[key]).path_join("blobs")), "geometry %s folder kept" % key)
	_expect(FileAccess.file_exists(GEOMETRY.path_join("notes/readme.txt")), "a foreign folder is untouched")
	var collision: Dictionary = _fixture.collision
	for key: String in ["mobile", "old_engine", "old_version"]:
		_expect(not _exists(COLLISION.path_join(collision[key])), "collision %s removed" % key)
	for key: String in ["fplus", "compat"]:
		_expect(_exists(COLLISION.path_join(collision[key]).path_join("entries")), "collision %s kept" % key)
	var paving: Dictionary = _fixture.paving
	_expect(not _exists(PAVING.path_join(paving.old_engine)), "paving stale policy removed")
	_expect(_exists(PAVING.path_join(paving.fplus)) and _exists(PAVING.path_join(paving.compat)), "paving family policies kept")
	var entries: Dictionary = _fixture.map_cache
	_expect(not FileAccess.file_exists(entries.scoped_a) and not FileAccess.file_exists(entries.scoped_b), "scoped entries removed")
	for key: String in ["unscoped", "chunk", "staging", "short", "other"]:
		_expect(FileAccess.file_exists(entries[key]), "scene-cache %s kept" % key)
	var shaders: Dictionary = _fixture.shaders
	_expect(not _exists(shaders.rd_old), "old RD generation removed")
	_expect(_exists(shaders.rd_young) and _exists(shaders.rd_newest) and _exists(shaders.rd_empty), "young, newest and empty generations kept")
	_expect(not FileAccess.file_exists(shaders.gles_oldest) and not FileAccess.file_exists(shaders.gles_a), "GLES3 oldest files removed")
	_expect(FileAccess.file_exists(shaders.gles_b) and FileAccess.file_exists(shaders.gles_c), "GLES3 keeps what fits")
	_expect(FileAccess.file_exists(shaders.foreign.path_join("file.cache")), "a foreign shader folder is untouched")
	_expect(Janitor.log_line(result).begins_with("RABBITLANDS_CACHE_JANITOR {"), "diagnostics line")
	var again := Janitor.run(_options())
	_expect(int(again.freed_bytes) == 0 and int(again.removed_files) == 0, "a second run removes nothing")

func _guards() -> void:
	# A live preparation lock anywhere in the geometry cache: no policy folder of
	# any of the three caches goes; nor while cooking or a preparation is pending.
	for case: Array in [[true, {}], [false, {"cooking": true}], [false, {"preparation_pending": true}]]:
		_build(bool(case[0]))
		var result := Janitor.run(_options(case[1]))
		var expected := "preparation_pending" if (case[1] as Dictionary).has("preparation_pending") else "preparation_active"
		for cache: String in Janitor.POLICY_CACHES:
			_expect(str(result.policies[cache].skipped) == expected, "%s skipped: %s" % [cache, expected])
			_expect((result.policies[cache].removed as Array).is_empty(), "%s removes nothing: %s" % [cache, expected])
		_expect(_exists(GEOMETRY.path_join(_fixture.geometry.old_engine)) and _exists(COLLISION.path_join(_fixture.collision.old_engine))
			and _exists(PAVING.path_join(_fixture.paving.old_engine)), "stale policies survive: " + expected)
	# The lock alone, classified directly: only the locked folder is kept.
	_build(true)
	var sorted := CollisionCache.classify_policy_dirs(GEOMETRY, GeometryCache.janitor_policies())
	var locked := false
	for row: Dictionary in sorted.kept:
		if str(row.policy) == str(_fixture.geometry.locked): locked = str(row.reason) == "locked"
	_expect(locked, "a locked stale folder is kept")
	# Cancellation before the first file: nothing is removed.
	_build()
	var cancelled := Janitor.run(_options(), func() -> bool: return true)
	_expect(str(cancelled.status) == "cancelled" and int(cancelled.removed_files) == 0, "a cancelled run removes nothing")
	_expect(_exists(GEOMETRY.path_join(_fixture.geometry.old_engine)), "cancelled: stale folder survives")
	# An interrupted removal keeps the header that proves the rest stale: blobs,
	# other folders and loose files go first, entries last.
	_build()
	var folder := GEOMETRY.path_join(_fixture.geometry.old_engine)
	var dead_lock := folder.path_join("preparing.lock/owner.json")
	_write(dead_lock, JSON.stringify({"pid": 0}))
	var partial := Janitor.remove_tree(folder, func() -> bool: return not FileAccess.file_exists(dead_lock))
	_expect(not bool(partial.complete), "an interrupted removal is incomplete")
	_expect(not DirAccess.dir_exists_absolute(folder.path_join("blobs")), "blobs went first")
	_expect(DirAccess.dir_exists_absolute(folder.path_join("entries"))
		and not DirAccess.get_files_at(folder.path_join("entries")).is_empty(), "the header survives an interrupted removal")
	var still_stale := false
	for row: Dictionary in CollisionCache.classify_policy_dirs(GEOMETRY, GeometryCache.janitor_policies()).stale:
		if str(row.policy) == str(_fixture.geometry.old_engine): still_stale = true
	_expect(still_stale, "the remainder is still proven stale")
	# The shader rule is off unless the owner turns it on.
	_expect(Janitor.SHADER_RULE_DEFAULT == false, "the shader rule defaults off")
	if OS.get_environment(Janitor.SHADER_ENVIRONMENT).is_empty():
		_expect(Janitor.shader_rule_enabled() == false, "no shader removal by default")
	var gated := Janitor.run(_options({"shaders": false}))
	_expect(int(gated.shaders.files) == 0 and _exists(_fixture.shaders.rd_old) and FileAccess.file_exists(_fixture.shaders.gles_oldest),
		"shader caches untouched with the rule off")
	# Nothing outside the user data folder is ever planned.
	var outside := Janitor.plan(_options({"geometry_directory": "res://", "map_cache_directory": "", "shaders": true,
		"shader_directory": "user://../x"}))
	_expect(str(outside.policies.geometry.skipped) == "outside_user_data" and outside.map_cache.is_empty()
		and outside.shader_dirs.is_empty(), "outside the user folder nothing is planned")
	# Release gate.
	if OS.get_environment(Janitor.SWITCH_ENVIRONMENT).is_empty():
		_expect(not Janitor.should_run({}), "not in a source build")
		_expect(Janitor.should_run({"release_build": true}) == (not OS.has_feature("editor")), "release builds run it")
	_expect(not Janitor.should_run({"release_build": false}) or not OS.get_environment(Janitor.SWITCH_ENVIRONMENT).is_empty(), "release_build false skips")
	# The exported release path, and timed benchmark runs: never during one
	# unless switched on (main.gd keeps maintenance out of timed runs too).
	var previous_switch := OS.get_environment(Janitor.SWITCH_ENVIRONMENT)
	var previous_token := OS.get_environment(Janitor.BENCHMARK_ENVIRONMENT)
	OS.unset_environment(Janitor.SWITCH_ENVIRONMENT)
	OS.unset_environment(Janitor.BENCHMARK_ENVIRONMENT)
	_expect(Janitor._should_run({"release_build": true}, false), "an exported release build runs it")
	_expect(not Janitor._should_run({"release_build": true}, true), "an editor build does not")
	OS.set_environment(Janitor.BENCHMARK_ENVIRONMENT, "bench-token")
	_expect(not Janitor._should_run({"release_build": true}, false), "a timed benchmark run does not")
	OS.set_environment(Janitor.SWITCH_ENVIRONMENT, "on")
	_expect(Janitor._should_run({"release_build": true}, false), "`on` still runs it in a benchmark run")
	for pair: Array in [[Janitor.SWITCH_ENVIRONMENT, previous_switch], [Janitor.BENCHMARK_ENVIRONMENT, previous_token]]:
		if str(pair[1]).is_empty(): OS.unset_environment(str(pair[0]))
		else: OS.set_environment(str(pair[0]), str(pair[1]))
	# Cancelled while planning (the client closing during the scan): the plan
	# stops at its next step and lists nothing; the shader scan stops per file.
	_build()
	var calls := [0]
	var after_first := func() -> bool:
		calls[0] += 1
		return calls[0] > 1
	var stopped := Janitor.plan(_options(), after_first)
	_expect(bool(stopped.get("cancelled", false)) and stopped.map_cache.is_empty() and stopped.shader_dirs.is_empty()
		and stopped.shader_files.is_empty(), "a plan cancelled mid-scan lists nothing")
	for cache: String in Janitor.POLICY_CACHES:
		_expect(str(stopped.policies[cache].skipped) == "cancelled" and (stopped.policies[cache].stale as Array).is_empty(),
			"%s planning stops when cancelled" % cache)
	calls[0] = 0
	var scan := Janitor.shader_plan(SHADERS, int(_fixture.now), int(_fixture.max_age), 1000, after_first)
	_expect(bool(scan.get("cancelled", false)) and scan.dirs.is_empty() and scan.files.is_empty(), "a cancelled shader scan plans nothing")
	_expect(not bool(Janitor.shader_plan(SHADERS, int(_fixture.now), int(_fixture.max_age), 1000).get("cancelled", false)),
		"an uncancelled shader scan completes")
	var applied := Janitor.apply(stopped, _options())
	_expect(str(applied.status) == "cancelled" and int(applied.removed_files) == 0, "applying a cancelled plan removes nothing")
	_expect(_exists(GEOMETRY.path_join(_fixture.geometry.old_engine)) and FileAccess.file_exists(_fixture.map_cache.scoped_a),
		"cancelled while planning: stale data survives")

func _scene_cache_names() -> void:
	_expect(SceneCache.entry_map_name("user://map-cache/amberwood_gauntlet-" + KEY + ".scn") == "amberwood_gauntlet", "entry map name")
	_expect(SceneCache.entry_map_name("user://map-cache/writing-amberwood_gauntlet-" + KEY + ".scn") == "", "staging has no map name")
	_expect(SceneCache.entry_map_name("user://map-cache/amberwood_gauntlet-0123456789ABCDEF.scn") == "", "upper-case key is foreign")
	_expect(SceneCache.entry_map_name("user://map-cache/" + KEY + ".scn") == "", "a bare key has no map name")
	var ids := GeometryCache.scoped_whole_map_ids(PackedStringArray(["amberwood_gauntlet", "lantern_reach", "boarsend", "landfall_insides"]))
	_expect("amberwood_gauntlet" in ids and "landfall_insides" in ids, "scoped whole maps found")
	_expect(not "lantern_reach" in ids and not "boarsend" in ids, "unscoped and streamed maps are not")

func _node() -> void:
	_build()
	var janitor: Node = Janitor.new()
	janitor.options = {"delay": 0.05, "geometry_directory": GEOMETRY, "collision_directory": COLLISION, "paving_directory": PAVING,
		"map_cache_directory": MAP_CACHE, "shader_directory": SHADERS, "shaders": false, "preparation_pending": false}
	var reports: Array = []
	janitor.finished.connect(func(result: Dictionary) -> void: reports.append(result))
	root.add_child(janitor)
	var deadline := Time.get_ticks_msec() + 30000
	while reports.is_empty() and Time.get_ticks_msec() < deadline:
		await process_frame
	_expect(reports.size() == 1 and str(reports[0].status) == "done", "the node runs once on its worker")
	_expect(not reports.is_empty() and int(reports[0].freed_bytes) == int(_fixture.stale_bytes) + int(_fixture.map_cache_bytes),
		"the node frees the stale policies and scoped entries")
	_expect(janitor.is_idle(), "the worker is joined")
	janitor.queue_free()
	await process_frame
	# Leaving the tree before the delay: no worker starts.
	_build()
	var early: Node = Janitor.new()
	early.options = {"delay": 30.0, "geometry_directory": GEOMETRY}
	root.add_child(early)
	await process_frame
	root.remove_child(early)
	_expect(early.is_cancelled() and early.is_idle(), "closing before the delay cancels it")
	early.free()
	_expect(_exists(GEOMETRY.path_join(_fixture.geometry.old_engine)), "nothing removed when closed early")
	# The update checker's call: the script loaded by path, `schedule` on it.
	var previous := OS.get_environment(Janitor.SWITCH_ENVIRONMENT)
	OS.set_environment(Janitor.SWITCH_ENVIRONMENT, "on")
	var host := Node.new()
	root.add_child(host)
	var scheduled: Variant = (load("res://src/runtime/cache_janitor.gd") as Script).call("schedule", host, {})
	OS.set_environment(Janitor.SWITCH_ENVIRONMENT, "off")
	_expect((load("res://src/runtime/cache_janitor.gd") as Script).call("schedule", host, {"release_build": true}) == null,
		"switched off: not scheduled")
	OS.set_environment(Janitor.SWITCH_ENVIRONMENT, previous)
	_expect(scheduled is Node, "schedule returns the janitor")
	if scheduled is Node:
		(scheduled as Node).set("options", {"delay": 30.0, "geometry_directory": GEOMETRY})
		_expect((scheduled as Node).get_parent() == null, "added deferred, not during the caller's _ready")
		await process_frame
		_expect((scheduled as Node).get_parent() == host and str((scheduled as Node).name) == "CacheJanitor", "added under the update checker")
	host.queue_free()
	await process_frame

func _source_guard() -> void:
	var updates := FileAccess.get_file_as_string("res://src/updates/client_updates.gd")
	_expect(updates.contains("\"res://src/runtime/cache_janitor.gd\"") and updates.contains("_schedule_cache_janitor()"),
		"client_updates schedules the janitor")
	_expect(not updates.contains("preload(\"res://src/runtime/cache_janitor.gd\")") and not updates.contains("preload(CACHE_JANITOR"),
		"client_updates loads the janitor by path only")

func _run() -> void:
	_policy_keys()
	_scene_cache_names()
	_full_run()
	_guards()
	await _node()
	_source_guard()
	_clear(ROOT)
	print("test_cache_janitor: %d checks, %d failures" % [_checks, _failures])
	print("PASS" if _failures == 0 else "FAIL")
	quit(0 if _failures == 0 else 1)
