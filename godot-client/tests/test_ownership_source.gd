extends SceneTree

const SOURCE := preload("res://src/dev/map_authoring_region/ownership_source.gd")
const CATALOG := preload("res://addons/map_authoring_workspace/territory_catalog.gd")
const SNAPSHOT := preload("res://src/dev/map_authoring_region/region_snapshot.gd")
const REGION := preload("res://src/dev/map_authoring_region/region_control.gd")
const TERRAIN := preload("res://src/dev/map_authoring_region/terrain_control.gd")
const MARKER := preload("res://src/dev/map_authoring_region/gameplay_marker.gd")
const SURFACE := preload("res://src/dev/map_authoring_pilot/style/map_authoring_surface.gd")
const PRESETS := preload("res://src/dev/map_authoring_pilot/style/texture_presets.gd")

var assertions := 0
var failures := 0
var fixture: Dictionary


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var index := args.find("--fixture")
	if index < 0 or index + 1 >= args.size():
		push_error("--fixture <external fixture descriptor> required")
		quit(2)
		return
	fixture = JSON.parse_string(FileAccess.get_file_as_string(args[index + 1]))
	var selected := SOURCE.region_data(SOURCE.load_source(fixture.project), "west")
	_expect(String(selected.error).is_empty() and selected.get("selected", false), "relocated source loads: " + String(selected.error))
	if not String(selected.error).is_empty():
		quit(1)
		return
	_expect(selected.binding == fixture.expected.binding, "raw Python/Godot source and plan hashes agree")
	_expect(selected.polygon_scalars[1][0] == 20.500000000001, "scalar polygon precision survives without Vector2 round trip")
	var strict := SOURCE.validate_for_bake(selected)
	_expect(String(strict.error).is_empty(), "strict Python validates source: " + String(strict.error))
	_expect(strict.get("ownershipPolygonSha256") == fixture.expected.ownershipPolygonSha256,
		"Python-derived polygon digest is used at bake")
	var frame: Dictionary = fixture.snapshot
	_expect(SOURCE.frame_error(selected, frame).is_empty(), "matching scene frame is accepted")
	var changed := frame.duplicate(true)
	changed.server.origin[0] += 1
	_expect(not SOURCE.frame_error(selected, changed).is_empty(), "frame drift is rejected")
	for name in ["../escape.json", "ownership/../selected.json", "C:/outside.json", "//host/share.json", "res://source.json"]:
		_expect(SOURCE.contained(selected.checkout, name).is_empty(), "escape rejected: " + name)
	_expect(SOURCE.contained(selected.checkout, "linked/selected.json").is_empty(), "actual Windows junction is rejected")
	_expect(not String(SOURCE.load_source(fixture.missing_project).error).is_empty(), "missing repository markers fail")
	var plan_bytes := FileAccess.get_file_as_bytes(selected.plan_path)
	var source_bytes := FileAccess.get_file_as_bytes(selected.source_path)
	_write(selected.source_path, source_bytes + "\n".to_utf8_buffer())
	_expect(not String(SOURCE.load_source(fixture.project).error).is_empty(), "same parsed source with changed bytes fails hash")
	_expect(not SOURCE.unchanged(selected), "stale catalog/snapshot source is detected")
	_write(selected.source_path, source_bytes)
	var plan: Dictionary = selected.plan.duplicate(true)
	plan.ownership_contract = null
	_write(selected.plan_path, JSON.stringify(plan).to_utf8_buffer())
	_expect(not String(SOURCE.load_source(fixture.project).error).is_empty(), "malformed explicit selection fails closed")
	_write(selected.plan_path, plan_bytes)
	var invalid := SOURCE.region_data(SOURCE.load_source(fixture.invalid_project), "west")
	_expect(String(invalid.error).is_empty(), "structural preview explicitly defers geometric validation")
	_expect("partition" in String(SOURCE.validate_for_bake(invalid).error), "strict bake rejects invalid partition with current source hash")
	var stale := SOURCE.region_data(SOURCE.load_source(fixture.stale_project), "west")
	_expect("changed during" in String(SOURCE.validate_for_bake(stale).error), "dependency mutation during CLI validation fails closed")
	var legacy := SOURCE.load_source(fixture.legacy_project)
	_expect(String(legacy.error).is_empty() and not legacy.selected, "absent selection retains legacy")
	_test_catalog(selected)
	_test_authored_claims()
	await _test_snapshot(selected)
	_expect(FileAccess.get_file_as_bytes(selected.plan_path) == plan_bytes and
		FileAccess.get_file_as_bytes(selected.source_path) == source_bytes, "test restores selected fixture bytes")
	print("ownership source: %d assertions, %d failures" % [assertions, failures])
	quit(1 if failures else 0)


func _test_catalog(selected: Dictionary) -> void:
	var catalog := CATALOG.new()
	var entries := catalog.entries(fixture.candidate_project, fixture.catalog)
	_expect(catalog.errors.is_empty(), "selected candidate catalog validates: " + "; ".join(catalog.errors))
	_expect(entries.size() == 12, "selected catalog preserves all twelve menu entries")
	if entries.is_empty():
		return
	var four := catalog.find(entries, "four_gates")
	_expect(four.ownership_polygon_scalars.size() == 384, "catalog retains all 384 scalar vertices")
	_expect(four.ownership_source.sha256 == fixture.candidate_sha256, "catalog identity is raw source SHA")
	var key: String = four.cache_key
	var dependency: String = four.ownership_dependency_paths[0]
	var bytes := FileAccess.get_file_as_bytes(dependency)
	_write(dependency, bytes + "\n".to_utf8_buffer())
	_expect(catalog._cache_key(four) != key, "plan change invalidates catalog cache")
	_write(dependency, bytes)
	var legacy := catalog.entries(fixture.legacy_project, fixture.catalog)
	_expect(catalog.errors.is_empty() and legacy.size() == 12 and not legacy[0].has("ownership_source"),
		"active legacy catalog remains unchanged")
	var saved := FileAccess.get_file_as_bytes(selected.plan_path)
	_write(selected.plan_path, "{\"ownership_contract\":null}".to_utf8_buffer())
	_expect(catalog.entries(fixture.project, fixture.catalog).is_empty() and not catalog.errors.is_empty(),
		"bad selected catalog never falls back to published ownership")
	_write(selected.plan_path, saved)


func _test_snapshot(selected: Dictionary) -> void:
	var base: String = fixture.res_artifact_dir
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(base))
	var height_path := base.path_join("heights.f32le")
	_write(ProjectSettings.globalize_path(height_path), PackedFloat32Array([1, 1, 1, 1]).to_byte_array())
	var region := REGION.new()
	region.name = "FixtureRegion"
	region.region_id = "west"
	region.continent_translation = Vector3(10, 0, 20)
	region.server_origin = Vector2i(60, 70)
	region.server_cells = Vector2i(120, 120)
	region.collision_origin_metres = Vector2(-60, 70)
	region.ownership_polygon_sha256 = "0".repeat(64) # Selected bake must derive it.
	var seed_path := base.path_join("runtime-seed.json")
	_write(ProjectSettings.globalize_path(seed_path), JSON.stringify({
		"schema": "eloria-runtime-binding-seed-v1", "regionId": "west",
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
	for label in ["Roads", "Rivers", "Bridges", "AuthoredAssets", "Gameplay", "GeneratedPreview"]:
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
	var packed := PackedScene.new()
	var scene_path := base.path_join("region.tscn")
	_expect(packed.pack(region) == OK and ResourceSaver.save(packed, scene_path) == OK, "fixture scene saves")
	region.free()
	var reopened := (load(scene_path) as PackedScene).instantiate() as Node3D
	root.add_child(reopened)
	await process_frame
	var exporter := SNAPSHOT.new()
	exporter.ownership_project_directory = fixture.project
	var document := exporter.export_region(reopened, fixture.snapshot_output)
	_expect(exporter.errors.is_empty() and not document.is_empty(), "selected snapshot exports: " + "; ".join(exporter.errors))
	if not document.is_empty():
		_expect(document.ownershipSource == selected.binding, "snapshot binds exact plan/source/region")
		var expected_dependencies: Array = selected.repository_dependencies.duplicate(true)
		expected_dependencies.append_array(fixture.migration_dependencies)
		expected_dependencies.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return a.path < b.path)
		_expect(document.sources.repositoryDependencies == expected_dependencies, "snapshot records ownership and shared terrain dependencies")
		_expect(document.terrain.migration == fixture.snapshot.terrain.migration, "snapshot preserves exact terrain migration metadata")
		_expect(document.seams.ownershipPolygonSha256 == fixture.expected.ownershipPolygonSha256,
			"snapshot ignores obsolete manually saved digest and uses strict Python digest")
	var legacy_exporter := SNAPSHOT.new()
	legacy_exporter.ownership_project_directory = fixture.legacy_project
	var legacy := legacy_exporter.export_region(reopened, fixture.snapshot_output + ".legacy")
	_expect(not legacy.is_empty() and legacy_exporter.errors.is_empty(), "legacy-selected terrain migration exports: " + "; ".join(legacy_exporter.errors))
	if not legacy.is_empty():
		_expect(not legacy.has("ownershipSource") and legacy.sources.repositoryDependencies == fixture.migration_dependencies,
			"legacy migration retains all three shared-field sources without ownership selection")
	var field: Dictionary = SOURCE.region_migration(selected, "west")
	var array_path: String = field.dependency_paths[0]
	var array_bytes := FileAccess.get_file_as_bytes(array_path)
	_write(array_path, array_bytes + "x".to_utf8_buffer())
	_expect(not String(SOURCE.region_migration(selected, "west").error).is_empty(), "terrain field mutation fails closed")
	_write(array_path, array_bytes)
	var invalid_exporter := SNAPSHOT.new()
	invalid_exporter.ownership_project_directory = fixture.invalid_project
	var bad_path: String = fixture.snapshot_output + ".invalid"
	_expect(invalid_exporter.export_region(reopened, bad_path).is_empty() and
		not FileAccess.file_exists(bad_path), "invalid topology writes no snapshot")
	reopened.free()


func _test_authored_claims() -> void:
	var catalog := CATALOG.new()
	var entries := catalog.entries(fixture.claim_project, fixture.claim_catalog)
	_expect(catalog.errors.is_empty() and entries.size() == 1 and entries[0].editable,
		"ownership-only selector keeps certified authored claims editable: " + "; ".join(catalog.errors))
	if entries.is_empty():
		return
	_expect(entries[0].claimed_plan_feature_footprints.has("fixture-river"),
		"certified baseline supplies original feature footprint")
	var data := SOURCE.region_data(SOURCE.load_source(fixture.claim_project), "west")
	_expect(data.repository_dependencies.size() == 3 and data.dependency_paths.has(data.feature_baseline_path),
		"baseline participates in source and cache dependencies")
	_expect(String(SOURCE.validate_for_bake(data).error).is_empty(), "Python/Godot baseline dependencies agree")
	var plan_bytes := FileAccess.get_file_as_bytes(data.plan_path)
	var baseline_bytes := FileAccess.get_file_as_bytes(data.feature_baseline_path)
	var changed: Dictionary = data.plan.duplicate(true)
	changed.rivers[0].points[0][0] += 1
	_write(data.plan_path, JSON.stringify(changed).to_utf8_buffer())
	_expect(catalog.entries(fixture.claim_project, fixture.claim_catalog).is_empty(),
		"altered original river geometry is rejected")
	changed = data.plan.duplicate(true)
	changed["newOriginalContent"] = true
	_write(data.plan_path, JSON.stringify(changed).to_utf8_buffer())
	_expect(catalog.entries(fixture.claim_project, fixture.claim_catalog).is_empty(),
		"other original plan content changes are rejected")
	_write(data.plan_path, plan_bytes)
	_write(data.feature_baseline_path, baseline_bytes + "\n".to_utf8_buffer())
	_expect(not SOURCE.unchanged(data), "byte-only baseline mutation invalidates final stale check")
	var probe := REGION.new()
	_expect(not SOURCE.entry_error(probe, entries[0]).is_empty(), "byte-only baseline mutation invalidates captured catalog entry")
	probe.free()
	var stale := catalog.entries(fixture.claim_project, fixture.claim_catalog)
	_expect(not catalog.errors.is_empty() and stale.size() == 1 and not stale[0].editable,
		"changed baseline bytes cannot bypass old per-region provenance hash")
	_write(data.feature_baseline_path, baseline_bytes)
	DirAccess.remove_absolute(data.feature_baseline_path)
	_expect(not String(SOURCE.load_source(fixture.claim_project).error).is_empty(), "missing selected baseline fails closed")
	_write(data.feature_baseline_path, baseline_bytes)


func _write(path: String, bytes: PackedByteArray) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(bytes)
	file.close()


func _expect(condition: bool, message: String) -> void:
	assertions += 1
	if not condition:
		failures += 1
		push_error(message)
