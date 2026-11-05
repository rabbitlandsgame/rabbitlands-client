extends SceneTree
## NH-A2 qualification tour: the content-digest work of N whole-map loads and
## M continent chunk loads, run through ContentDigest in one mode (default
## `compare`: native and FileAccess on every native-readable row, FileAccess
## values used, every disagreement counted). Per package it does what a load
## does with these files: the package digest (`MapSceneCache.package_digest_parts`:
## world.glb raw + world.json CRLF-folded) and one `verify` batch over the
## manifest's `externalResources` against their authored SHA-256. Nothing is
## remembered between packages, as in a load.
##
##   Godot --headless --path . --script res://tests/integration/content_digest_compare_tour.gd -- \
##       [--maps=10] [--chunks=200] [--mode=compare|native|gdscript|sequential] \
##       [--runtime-dir=<payload dir>] [--expect-native=present] [--report=<json path>]
##
## Maps are the registry's first N with a world.glb, in registry order. Chunks
## are taken round-robin over the streaming maps' chunk lists. Exit status: the
## number of failures (a mismatch, an authored digest that does not verify, a
## package that cannot be digested, or no native backend under
## `--expect-native=present`). One `CONTENT_DIGEST_TOUR {json}` line summarises.

const Digest := preload("res://src/runtime/content_digest.gd")
const MapCache := preload("res://src/world/map_scene_cache.gd")
const REGISTRY := "res://data/maps/registry.json"

var _failures := 0
var _notes: Array = []

func _init() -> void:
	_run.call_deferred()

func _option(name: String, fallback: String) -> String:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--%s=" % name):
			return argument.trim_prefix("--%s=" % name)
	return fallback

func _fail(message: String) -> void:
	_failures += 1
	if _notes.size() < 40:
		_notes.append(message)
	push_error("FAIL: " + message)

func _run() -> void:
	var map_limit := int(_option("maps", "10"))
	var chunk_limit := int(_option("chunks", "200"))
	var mode := _option("mode", "compare")
	Digest.initialize(_option("runtime-dir", ""))
	Digest.configure(mode)
	var start := Digest.snapshot()
	print("NOTE: digest backend ", start.backend, " reason ", start.reason, " native ", JSON.stringify(start.native))
	if _option("expect-native", "") == "present" and not bool((start.native as Dictionary).get("ready", false)):
		_fail("native payload not ready: %s" % JSON.stringify(start.native))
	var registry: Variant = JSON.parse_string(FileAccess.get_file_as_string(REGISTRY))
	var maps: Dictionary = (registry as Dictionary).get("maps", {}) if registry is Dictionary else {}
	var chunk_lists: Array = []
	var tour := {"maps": [], "chunks": 0, "packages": 0, "external_rows": 0, "verify_failures": 0,
		"package_failures": 0}
	var began := Time.get_ticks_usec()
	for id: Variant in maps:
		var manifest_path := str((maps[id] as Dictionary).get("manifest", ""))
		if manifest_path.is_empty() or not FileAccess.file_exists(manifest_path):
			continue
		var manifest := WorldManifest.load_file(manifest_path)
		if not manifest.is_valid() or not FileAccess.file_exists(manifest.glb_path()):
			continue
		if (tour.maps as Array).size() < map_limit:
			_package(str(id), manifest, tour)
			(tour.maps as Array).append(str(id))
		if manifest.has_streaming_chunks():
			var list: Array = []
			for chunk: Variant in (manifest.data.streamingChunks as Dictionary).get("chunks", []):
				if chunk is Dictionary and not str((chunk as Dictionary).get("manifest", "")).is_empty():
					list.append(manifest.source_path.get_base_dir().path_join(str(chunk.manifest)))
			if not list.is_empty():
				chunk_lists.append(list)
	var maps_us := Time.get_ticks_usec() - began
	began = Time.get_ticks_usec()
	var pass_index := 0
	var taken := 0
	while taken < chunk_limit and not chunk_lists.is_empty():
		var any := false
		for list: Array in chunk_lists:
			if pass_index >= list.size() or taken >= chunk_limit:
				continue
			any = true
			var chunk := WorldManifest.load_file(str(list[pass_index]))
			if not chunk.is_valid():
				_fail("chunk manifest invalid: %s %s" % [list[pass_index], JSON.stringify(chunk.errors)])
			else:
				_package(str(list[pass_index]).get_base_dir().get_file(), chunk, tour)
			taken += 1
		if not any:
			break
		pass_index += 1
	tour.chunks = taken
	var chunks_us := Time.get_ticks_usec() - began
	var snap := Digest.snapshot()
	if int(snap.mismatches) > 0:
		_fail("%d content_digest mismatches: %s" % [int(snap.mismatches), JSON.stringify(snap.mismatch_samples)])
	if mode == "compare" and bool((start.native as Dictionary).get("ready", false)) and int(snap.compared_rows) == 0:
		_fail("compare mode compared no rows")
	if (tour.maps as Array).size() < mini(map_limit, 1) or taken < mini(chunk_limit, 1):
		_fail("tour found too few packages: %d maps, %d chunks" % [(tour.maps as Array).size(), taken])
	var summary := {"mode": mode, "backend_start": start.backend, "backend_end": snap.backend,
		"reason_end": snap.reason, "native": start.native, "maps": tour.maps, "map_count": (tour.maps as Array).size(),
		"chunks": taken, "packages": tour.packages, "external_rows": tour.external_rows,
		"verify_failures": tour.verify_failures, "package_failures": tour.package_failures,
		"compared_rows": snap.compared_rows, "mismatches": snap.mismatches, "rechecked": snap.rechecked,
		"fallbacks": snap.fallbacks, "native_calls": snap.native_calls, "native_rows": snap.native_rows,
		"calls": snap.calls, "files": snap.files, "bytes": snap.bytes, "digest_us": snap.us,
		"maps_us": maps_us, "chunks_us": chunks_us, "failures": _failures, "notes": _notes}
	print("CONTENT_DIGEST_TOUR ", JSON.stringify(summary))
	var report := _option("report", "")
	if not report.is_empty():
		var file := FileAccess.open(report, FileAccess.WRITE)
		if file != null:
			file.store_string(JSON.stringify(summary, "  ") + "\n")
			file.close()
	Digest.reset()
	quit(_failures)

## The package digest and the externals verify batch of one manifest.
func _package(label: String, manifest: WorldManifest, tour: Dictionary) -> void:
	tour.packages = int(tour.packages) + 1
	var parts := MapCache.package_digest_parts(manifest.source_path, manifest.glb_path())
	if str(parts.digest).length() != 64:
		tour.package_failures = int(tour.package_failures) + 1
		_fail("package digest failed: %s" % label)
	var resources: Variant = manifest.data.get("externalResources", {})
	if not resources is Dictionary or (resources as Dictionary).is_empty():
		return
	var base := ProjectSettings.globalize_path(manifest.glb_path()).replace("\\", "/").get_base_dir()
	var rows: Array = []
	for uri: Variant in resources:
		var expected := str(resources[uri])
		if expected.length() != 64:
			continue
		rows.append({"path": base.path_join(str(uri).replace("\\", "/")).simplify_path(), "sha256": expected})
	tour.external_rows = int(tour.external_rows) + rows.size()
	var result := Digest.verify(rows)
	if not bool(result.ok):
		var failing := 0
		for value: int in result.matches:
			failing += 1 if value == 0 else 0
		tour.verify_failures = int(tour.verify_failures) + failing
		_fail("%s: %d of %d external digests do not verify (first %s)" % [label, failing, rows.size(),
			str(rows[int(result.first_failure)].path)])
