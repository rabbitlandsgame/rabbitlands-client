extends SceneTree

const STORAGE := preload("res://src/dev/map_authoring_region/storage_contract.gd")
const SOURCE := preload("res://src/dev/map_authoring_region/ownership_source.gd")
const REGION := preload("res://src/dev/map_authoring_region/region_control.gd")
const SNAPSHOT := preload("res://src/dev/map_authoring_region/region_snapshot.gd")
const TERRAIN := preload("res://src/dev/map_authoring_region/terrain_control.gd")
const SURFACE := preload("res://src/dev/map_authoring_pilot/style/map_authoring_surface.gd")
const PRESETS := preload("res://src/dev/map_authoring_pilot/style/texture_presets.gd")
const MARKER := preload("res://src/dev/map_authoring_region/gameplay_marker.gd")

var assertions := 0
var failures := 0
var fixture: Dictionary


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var args := OS.get_cmdline_user_args()
	fixture = JSON.parse_string(FileAccess.get_file_as_string(args[args.find("--fixture") + 1]))
	var legacy := {"cells": [6, 12], "origin": [60, 70], "collisionOriginMetres": [-60, 70]}
	_expect(String(STORAGE.validate(legacy).error).is_empty(), "legacy implicit zero frame validates")
	for minimum: Array in [[-6, -12], [7, 13], [0, 0]]:
		var server := legacy.duplicate(true)
		server.merge({"serverStorageVersion": 1, "serverTileMin": minimum,
			"collisionOriginMetres": [minimum[0] - 60, 70 - minimum[1]]}, true)
		_expect(String(STORAGE.validate(server).error).is_empty(), "signed/positive/zero minimum validates")
	for changes: Dictionary in [
		{"serverTileMin": [0, 0]}, {"serverStorageVersion": 1},
		{"serverStorageVersion": 0, "serverTileMin": [0, 0]},
		{"serverStorageVersion": true, "serverTileMin": [0, 0]},
		{"serverStorageVersion": 1, "serverTileMin": [false, 0]},
		{"serverStorageVersion": 1, "serverTileMin": [0.5, 0]},
		{"cells": [2049, 1]}, {"cells": [0, 6]}, {"cells": [true, 6]},
		{"metresPerTile": 2}, {"metresPerTile": true}, {"invertServerY": false},
		{"invertServerY": 1}, {"localOrigin": [0, 1, 0]}, {"walkingHeight": "0"}]:
		var bad := legacy.duplicate(true)
		bad.merge(changes, true)
		_expect(not String(STORAGE.validate(bad).error).is_empty(), "malformed storage/frame rejects " + str(changes))
	var wide := legacy.duplicate(true)
	wide.cells = [2048, 1]
	_expect(String(STORAGE.validate(wide).error).is_empty(), "pure bounds permits rectangular 2048 extent")
	var selected := SOURCE.region_data(SOURCE.load_source(fixture.project), "west")
	_expect(String(SOURCE.frame_error(selected, fixture.spec)).is_empty(), "expanded source contains frozen baseline")
	var shrunk: Dictionary = fixture.spec.duplicate(true)
	shrunk.server.cells[0] -= 1
	_expect(not SOURCE.frame_error(selected, shrunk).is_empty(), "shrunk positive edge rejects")
	await _snapshot(selected)
	print("storage source: %d assertions, %d failures" % [assertions, failures])
	quit(1 if failures else 0)


func _snapshot(selected: Dictionary) -> void:
	var base: String = fixture.res_artifact_dir
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(base))
	var height_path := base.path_join("heights.f32le")
	_write(height_path, PackedFloat32Array([1, 1, 1, 1]).to_byte_array())
	var region := REGION.new()
	region.name = "StorageFixture"
	region.region_id = "west"
	region.continent_translation = Vector3(10, 0, 20)
	region.server_origin = Vector2i(60, 70)
	region.server_cells = Vector2i(126, 132)
	region.server_storage_version = 1
	region.server_tile_min = Vector2i(-6, -12)
	region.collision_origin_metres = Vector2(-66, 82)
	region.ownership_polygon_sha256 = "0".repeat(64)
	var seed_path := base.path_join("runtime-seed.json")
	_write(seed_path, JSON.stringify({"schema": "eloria-runtime-binding-seed-v1", "regionId": "west",
		"provenance": {"profileFiles": [], "sourceReportSha256": "0".repeat(64)}, "bindings": []}).to_utf8_buffer())
	region.runtime_binding_seed_path = seed_path
	region.runtime_binding_seed_sha256 = FileAccess.get_sha256(ProjectSettings.globalize_path(seed_path))
	var terrain := TERRAIN.new()
	terrain.name = "Terrain"
	terrain.origin = Vector2.ZERO
	terrain.grid_size = Vector2i(2, 2)
	terrain.base_heights_path = height_path
	terrain.base_surface = SURFACE.from_preset(PRESETS.GRASS)
	region.add_child(terrain)
	terrain.owner = region
	for label: String in ["Roads", "Rivers", "Bridges", "AuthoredAssets", "Gameplay", "GeneratedPreview"]:
		var node := Node3D.new()
		node.name = label
		region.add_child(node)
		node.owner = region
	var spawn := MARKER.new()
	spawn.name = "Spawn"
	spawn.kind = "spawn"
	spawn.record_id = "arrival"
	spawn.default_spawn = true
	region.get_node("Gameplay").add_child(spawn)
	spawn.owner = region
	var portal := MARKER.new()
	portal.name = "Portal"
	portal.kind = "portal"
	portal.record_id = "west-east"
	portal.destination_map = "east"
	region.get_node("Gameplay").add_child(portal)
	portal.owner = region
	root.add_child(region)
	await process_frame
	_expect(SOURCE.scene_error(selected, region).is_empty(), "negative storage scene matches source")
	region.server_storage_version = 0
	_expect(not SOURCE.scene_error(selected, region).is_empty(), "saved minimum cannot disappear through legacy default")
	region.server_storage_version = 1
	region.server_cells.x += 6
	_expect(not SOURCE.scene_error(selected, region).is_empty(), "two different baseline supersets still mismatch spec")
	region.server_cells.x -= 6
	var packed := PackedScene.new()
	var scene_path := base.path_join("region.tscn")
	_expect(packed.pack(region) == OK and ResourceSaver.save(packed, scene_path) == OK, "storage fixture saves")
	region.free()
	var reopened := (load(scene_path) as PackedScene).instantiate() as Node3D
	root.add_child(reopened)
	await process_frame
	_expect(reopened.server_tile_min == Vector2i(-6, -12) and reopened.server_storage_version == 1,
		"saved and reopened minima/version survive")
	for project: String in [fixture.project, fixture.legacy_project]:
		var exporter := SNAPSHOT.new()
		exporter.ownership_project_directory = project
		var output: String = fixture.snapshot_output + (".legacy" if project == fixture.legacy_project else "")
		var document := exporter.export_region(reopened, output)
		_expect(not document.is_empty() and exporter.errors.is_empty(), "ordinary export: " + "; ".join(exporter.errors))
		if not document.is_empty():
			_expect(document.server.serverTileMin == [-6, -12] and document.server.origin == [60, 70],
				"snapshot separates minimum from unchanged origin")
			_expect(document.server.walkingHeight == 42.25 and STORAGE.same_vector(document.server.localOrigin, [0, 0, 0]) and document.server.invertServerY,
				"explicit optional source frame survives export")
			_expect(document.sources.authoringSpec.sha256 == FileAccess.get_sha256(project.path_join("world_authoring/regions/west/region-authoring-spec.json")),
				"snapshot binds exact spec bytes")
	var spec_path: String = fixture.project.path_join("world_authoring/regions/west/region-authoring-spec.json")
	var bytes := FileAccess.get_file_as_bytes(spec_path)
	var captured := SOURCE.scene_contract(selected, reopened)
	_write(spec_path, bytes + "\n".to_utf8_buffer())
	_expect(SOURCE.scene_contract(selected, reopened) != captured, "byte-only spec mutation changes captured export dependency")
	var entry := {"authoring_spec_path": spec_path, "authoring_spec_sha256": captured.source.binding.sha256}
	_expect("changed since" in SOURCE.entry_error(reopened, entry), "captured catalog entry rejects byte-only spec mutation")
	_write(spec_path, bytes)
	var zero: Dictionary = fixture.spec.duplicate(true)
	zero.server.merge({"cells": [120, 120], "serverTileMin": [0, 0], "collisionOriginMetres": [-60, 70]}, true)
	_write(spec_path, JSON.stringify(zero).to_utf8_buffer())
	reopened.server_storage_version = 0
	reopened.server_tile_min = Vector2i.ZERO
	reopened.server_cells = Vector2i(120, 120)
	reopened.collision_origin_metres = Vector2(-60, 70)
	_expect(SOURCE.scene_error(selected, reopened).is_empty(), "omitted scene zero matches explicit spec zero semantically")
	zero.server.erase("serverStorageVersion")
	zero.server.erase("serverTileMin")
	_write(spec_path, JSON.stringify(zero).to_utf8_buffer())
	reopened.server_storage_version = 1
	_expect(SOURCE.scene_error(selected, reopened).is_empty(), "explicit scene zero matches legacy spec zero semantically")
	_write(spec_path, bytes)
	reopened.server_tile_min = Vector2i(-6, -12)
	reopened.server_cells = Vector2i(126, 132)
	reopened.collision_origin_metres = Vector2(-60, 70)
	var bad_exporter := SNAPSHOT.new()
	bad_exporter.ownership_project_directory = fixture.project
	var bad_path: String = fixture.snapshot_output + ".invalid"
	_expect(bad_exporter.export_region(reopened, bad_path).is_empty() and not FileAccess.file_exists(bad_path),
		"wrong physical origin cannot write snapshot")
	reopened.free()


func _write(path: String, bytes: PackedByteArray) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(bytes)
	file.close()


func _expect(condition: bool, message: String) -> void:
	assertions += 1
	if not condition:
		failures += 1
		push_error(message)
