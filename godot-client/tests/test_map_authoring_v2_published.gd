extends SceneTree
## Serve plan CV9: the editor finds a continent-v2 territory's published package
## through its catalog entry's publishedManifestPath, and the play-test walker
## walks the served grid that package ships. The entry's manifestPath stays the
## bootstrap's stub (frame, ownership, environment), which never carries one.
##
## Fixtures: an isolated catalog, bound with the project setting
## map_authoring/territory_catalog_path for this run only, whose v2 entry names a
## stub and a package shipping the server's golden served grid. manifest_path_for
## gives the stub, published_manifest_path_for the package, and load_grid on a
## scene root of that region (no manifest argument) walks the package's grid:
## format 2, climb 20. A legacy entry (no publishedManifestPath) publishes its
## manifest; an unpublished v2 entry has no package; a territory the bound
## catalog does not list comes from the shared catalog.
##
## Repository: every active partition entry must have a served registry row and
## a client package with a served grid in its own recorded frame. Missing
## packages fail. ELORIA_V2_PUBLISHED_PACKAGES may point to an external folder
## holding all active <map>/client/world.json packages through a copied catalog.
##
## Godot_v4.7.2-stable_win64_console.exe --headless --path . \
##     --script res://tests/test_map_authoring_v2_published.gd

const Walker := preload("res://addons/map_authoring_usability/playtest_walker.gd")
const TimeOfDay := preload("res://addons/map_authoring_usability/time_of_day_preview.gd")
const Catalog := preload("res://addons/map_authoring_workspace/territory_catalog.gd")
const REGION := preload("res://src/dev/map_authoring_region/region_control.gd")
const SETTING := "map_authoring/territory_catalog_path"
const GOLDEN_PATH := "res://tests/fixtures/served_grid_golden.escg.gz"
const GOLDEN_SHA256 := "7e4522023885486b2a47298826b3fad1d30ba6d660dcc80249c8690d30e66c12"
const FIXTURE := "res://test-artifacts/v2-published"
const V2_CATALOG := "res://world_authoring/continent-v2/territories.json"
const REGISTRY := "res://data/maps/registry.json"
const PACKAGES_ENV := "ELORIA_V2_PUBLISHED_PACKAGES"

var failures := 0
var _had_setting := false
var _saved_setting: Variant = null


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	_had_setting = ProjectSettings.has_setting(SETTING)
	_saved_setting = ProjectSettings.get_setting(SETTING) if _had_setting else null
	_test_fixture_catalog()
	_test_repository_catalog()
	_restore_setting()
	_finish()


func _test_fixture_catalog() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(FIXTURE + "/isle/client"))
	var stub := FIXTURE + "/isle/world.json"
	var package := FIXTURE + "/isle/client/world.json"
	var legacy := FIXTURE + "/legacy/world.json"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(FIXTURE + "/legacy"))
	_write_json(stub, {"asset": {"id": "v2_fixture"}, "server": {"origin": [5, 7], "cells": [24, 16]}})
	_write_json(package, {"asset": {"id": "v2_fixture"}, "coordinateTransform": {"serverOrigin": [5, 7],
		"serverCells": [24, 16], "metresPerTile": 1.0, "invertServerY": true},
		"collision": {"binary": "collision.bin", "servedGrid": {"binary": "served-grid.escg.gz",
			"format": "ESCG-v2", "unitMetres": 0.05, "climbMetres": 1.0, "originMetres": -100.0,
			"sha256": GOLDEN_SHA256}}})
	_write_bytes(FIXTURE + "/isle/client/served-grid.escg.gz", FileAccess.get_file_as_bytes(GOLDEN_PATH))
	_write_json(legacy, {"asset": {"id": "legacy_fixture"}})
	var catalog := FIXTURE + "/territories.json"
	_write_json(catalog, {"schema": Catalog.SCHEMA, "entries": [
		{"id": "v2_fixture", "label": "V2 Fixture", "manifestPath": stub, "publishedManifestPath": package},
		{"id": "v2_unpublished", "label": "V2 Unpublished", "manifestPath": stub,
			"publishedManifestPath": FIXTURE + "/absent/client/world.json"},
		{"id": "legacy_fixture", "label": "Legacy Fixture", "manifestPath": legacy}]})
	ProjectSettings.set_setting(SETTING, catalog)
	_expect(Catalog.configured_path() == catalog,
		"the project setting binds the isolated catalog for this run")
	_expect(TimeOfDay.manifest_path_for("v2_fixture") == stub and
		TimeOfDay.published_manifest_path_for("v2_fixture") == package,
		"a v2 entry's manifest is its stub, its published package the publishedManifestPath")
	_expect(TimeOfDay.published_manifest_path_for("legacy_fixture") == legacy and
		TimeOfDay.manifest_path_for("legacy_fixture") == legacy,
		"a legacy entry, with no publishedManifestPath, publishes its manifest")
	_expect(TimeOfDay.published_manifest_path_for("v2_unpublished") == "" and
		TimeOfDay.manifest_path_for("v2_unpublished") == stub,
		"an unpublished v2 entry has no package, and its stub never stands in for one")
	var shared := TimeOfDay.manifest_path_for("sunmane_steppe")
	_expect(not shared.is_empty() and TimeOfDay.published_manifest_path_for("sunmane_steppe") == shared,
		"a territory the bound catalog does not list comes from the shared catalog (%s)" % shared)
	var root: Node3D = REGION.new()
	root.name = "V2PublishedFixture"
	root.set("region_id", "v2_fixture")
	root.set("server_origin", Vector2i(5, 7))
	get_root().add_child(root)
	var grid := Walker.load_grid(root)
	_expect(not grid.has("error") and String(grid.get("source", "")) == "published" and
		int(grid.get("format", 0)) == 2 and int(grid.get("climb", 0)) == 20 and
		int(grid.get("width", 0)) == 24 and int(grid.get("rows", 0)) == 16 and
		String(grid.get("served_grid", "")).begins_with(FIXTURE + "/isle/client/"),
		"with no manifest argument the walker walks the package's served grid: format 2, climb 20 (%s)" %
			String(grid.get("error", grid.get("served_grid", ""))))
	root.queue_free()


func _test_repository_catalog() -> void:
	var catalog: Variant = JSON.parse_string(FileAccess.get_file_as_string(V2_CATALOG))
	var registry: Variant = JSON.parse_string(FileAccess.get_file_as_string(REGISTRY))
	if not _expect(catalog is Dictionary and registry is Dictionary, "the active catalog and registry parse"):
		return
	var partition: Variant = JSON.parse_string(FileAccess.get_file_as_string(String(catalog.get("partitionSpecPath", ""))))
	if not _expect(partition is Dictionary, "the catalog's exact partition input parses"):
		return
	var expected := PackedStringArray()
	for section: Dictionary in partition.get("sections", []):
		expected.append(String(section.get("mapId", section.id)))
	expected.sort()
	var entries: Array = catalog.get("entries", [])
	var actual := PackedStringArray()
	for entry: Dictionary in entries:
		actual.append(String(entry.id))
	actual.sort()
	_expect(not expected.is_empty() and actual == expected, "the catalog lists every partition section exactly once")
	var maps: Dictionary = registry.get("maps", {})
	for retired: String in catalog.get("retiredMapIds", []):
		_expect(not maps.has(retired), "retired map %s has no active registry row" % retired)
	ProjectSettings.set_setting(SETTING, V2_CATALOG)
	var outside := OS.get_environment(PACKAGES_ENV).strip_edges()
	if not outside.is_empty():
		var copy := FIXTURE + "/v2-catalog-outside.json"
		var bound: Dictionary = catalog.duplicate(true)
		for entry: Dictionary in bound.entries:
			entry["publishedManifestPath"] = outside.path_join(String(entry.id)).path_join("client/world.json")
		_write_json(copy, bound)
		ProjectSettings.set_setting(SETTING, copy)
	for entry: Dictionary in entries:
		var id := String(entry.id)
		var row: Dictionary = maps.get(id, {})
		var published := String(entry.get("publishedManifestPath", ""))
		_expect(published == String(row.get("manifest", "")) and published.ends_with("/%s/client/world.json" % id)
			and String(row.get("status", "")) == "continent-v2-served", "%s names its served registry package" % id)
		var stub_path := String(entry.get("manifestPath", ""))
		var package := TimeOfDay.published_manifest_path_for(id)
		_expect(TimeOfDay.manifest_path_for(id) == stub_path and not package.is_empty(),
			"%s resolves its editor stub and published package separately" % id)
		if not _expect(FileAccess.file_exists(package), "%s published package exists: %s" % [id, package]):
			continue
		var stub: Variant = JSON.parse_string(FileAccess.get_file_as_string(stub_path))
		var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(package))
		if not _expect(stub is Dictionary and manifest is Dictionary, "%s stub and package parse" % id):
			continue
		var frame: Dictionary = stub.get("server", {})
		var raw_origin: Array = frame.get("origin", [])
		var cells: Array = frame.get("cells", [])
		if not _expect(raw_origin.size() == 2 and cells.size() == 2 and
			manifest.get("collision", {}).get("servedGrid") is Dictionary, "%s records its frame and served grid" % id):
			continue
		var origin := Vector2i(int(raw_origin[0]), int(raw_origin[1]))
		var region: Node3D = REGION.new()
		region.name = "Published_" + id
		region.set("region_id", id)
		region.set("server_origin", origin)
		get_root().add_child(region)
		var grid := Walker.load_grid(region)
		_expect(not grid.has("error") and String(grid.get("source", "")) == "published" and
			int(grid.get("format", 0)) == 2 and int(grid.get("climb", 0)) == 20 and
			int(grid.get("width", 0)) == int(cells[0]) and int(grid.get("rows", 0)) == int(cells[1]) and
			grid.get("origin") == origin and String(grid.get("served_grid", "")).get_base_dir() == package.get_base_dir(),
			"%s walker loads its exact frame, format 2 and climb 20 (%s)" % [id, String(grid.get("error", "served"))])
		region.free()


func _restore_setting() -> void:
	ProjectSettings.set_setting(SETTING, _saved_setting if _had_setting else null)


func _write_json(path: String, value: Variant) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(value))
	file.close()


func _write_bytes(path: String, bytes: PackedByteArray) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(bytes)
	file.close()


func _expect(condition: bool, message: String) -> bool:
	if condition:
		print("PASS: ", message)
		return true
	failures += 1
	push_error("FAIL: " + message)
	return false


func _finish() -> void:
	print("map authoring v2 published: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)
