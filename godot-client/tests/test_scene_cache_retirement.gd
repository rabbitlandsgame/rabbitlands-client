extends SceneTree
## A geometry-scoped whole map never reads the legacy scene cache, so its old
## entries are removed on its load. Only that map's exact entries go: another
## map whose name merely starts the same, other maps and writes in flight stay.
## Run with an isolated user directory.
const MapCache := preload("res://src/world/map_scene_cache.gd")
var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: " + message)
	else:
		failures += 1
		push_error("FAIL: " + message)

func touch(name: String) -> String:
	var path := MapCache.CACHE_DIRECTORY.path_join(name)
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string("entry")
	file.close()
	return path

func _run() -> void:
	MapCache.ensure_directory()
	var key := "0123456789abcdef"
	var retired := [touch("retire-test-map-" + key + ".scn"), touch("retire-test-map-fedcba9876543210.scn")]
	var kept := [touch("retire-test-map-annex-" + key + ".scn"), touch("retire-test-other-" + key + ".scn"),
		touch(MapCache.STAGING_PREFIX + "retire-test-map-" + key + ".scn"), touch("retire-test-map-notakey.scn")]
	expect(WorldLoader._retire_scene_cache_entries("retire_test_map") == 0,
		"a map id is matched by its cache file name, not loosely")
	WorldLoader._retired_scene_cache.erase("retire_test_map")
	expect(WorldLoader._retire_scene_cache_entries("retire-test-map") == 2, "both entries of the map are removed")
	var gone := true
	for path: String in retired:
		gone = gone and not FileAccess.file_exists(path)
	var left := true
	for path: String in kept:
		left = left and FileAccess.file_exists(path)
	expect(gone and left, "a longer map name, another map, a write in flight and a non-key suffix are kept")
	touch("retire-test-map-" + key + ".scn")
	expect(WorldLoader._retire_scene_cache_entries("retire-test-map") == 0, "the directory is checked once per map per session")
	for path: String in kept + retired:
		DirAccess.remove_absolute(path)
	print("scene cache retirement: ", failures, " failures")
	quit(failures)
