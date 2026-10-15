extends SceneTree

const LAYER := preload(
	"res://src/dev/map_authoring_region/terrain_sculpt_layer.gd")
const BRUSH := preload(
	"res://src/dev/map_authoring_region/terrain_sculpt_brush.gd")
const TERRAIN := preload("res://src/dev/map_authoring_region/terrain_control.gd")
const REGION := preload("res://src/dev/map_authoring_region/region_control.gd")
const PATCH := preload("res://src/dev/map_authoring_region/terrain_patch.gd")
const GAMEPLAY := preload(
	"res://src/dev/map_authoring_region/gameplay_marker.gd")
const SURFACE := preload(
	"res://src/dev/map_authoring_pilot/style/map_authoring_surface.gd")
const PRESETS := preload(
	"res://src/dev/map_authoring_pilot/style/texture_presets.gd")

const HEIGHT_PATH := "res://tests/.terrain-sculpt-base.f32le"
const LAYER_PATH := "res://tests/.terrain-sculpt-layer.tres"
const SCENE_PATH := "res://tests/.terrain-sculpt-region.tscn"
const RUNTIME_SEED_PATH := "res://tests/.terrain-sculpt-runtime-seed.json"
const ORIGINAL_OUTPUT := "res://test-artifacts/terrain-sculpt/original/continent-authoring.json"
const SCULPT_OUTPUT := "res://test-artifacts/terrain-sculpt/sculpted/continent-authoring.json"
const GRID := Vector2i(5, 5)
const ORIGIN := Vector2(-4.0, -4.0)
const CELL := 2.0

var failures := 0


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var base := PackedFloat32Array()
	base.resize(GRID.x * GRID.y)
	base.fill(10.0)
	_write_float32(HEIGHT_PATH, base)
	_write_runtime_seed()
	var original_bytes := FileAccess.get_file_as_bytes(
		ProjectSettings.globalize_path(HEIGHT_PATH))
	var sha := FileAccess.get_sha256(ProjectSettings.globalize_path(HEIGHT_PATH))

	var raised: Resource = BRUSH.apply_stamp(base, null, sha, ORIGIN, GRID, CELL,
		Vector2.ZERO, BRUSH.Mode.RAISE, 4.0, 2.0, 1.0)
	_expect(raised != null and is_equal_approx(raised.deltas[raised.indices.find(12)], 2.0) and
		raised.indices.find(10) == -1,
		"Raise applies metres with smooth radial falloff and a zero outer edge")
	if raised == null:
		_cleanup()
		print("terrain sculpt: initialization failed")
		call_deferred("_finish", 1)
		return
	var original_raised: PackedFloat32Array = raised.deltas.duplicate()
	var lowered: Resource = BRUSH.apply_stamp(base, raised, sha, ORIGIN, GRID, CELL,
		Vector2.ZERO, BRUSH.Mode.LOWER, 0.5, 0.5, 0.0)
	_expect(lowered != null and raised.deltas == original_raised and
		lowered != raised and is_equal_approx(lowered.apply_to(base, sha, ORIGIN,
		GRID, CELL)[12], 11.5),
		"stamps return independent sparse layers without mutating undo state")

	var locked := PackedByteArray()
	locked.resize(25)
	var boundary := PackedFloat32Array()
	boundary.resize(25)
	boundary.fill(1.0)
	for z_index in GRID.y:
		for x_index in GRID.x:
			var index := z_index * GRID.x + x_index
			if x_index + z_index <= 4:
				locked[index] = 1
			elif x_index + z_index == 5:
				boundary[index] = 0.5
	var protected: Resource = BRUSH.apply_stamp(base, null, sha, ORIGIN, GRID, CELL,
		Vector2.ZERO, BRUSH.Mode.RAISE, 4.0, 2.0, 0.0, NAN, locked, boundary)
	var protected_values: PackedFloat32Array = protected.apply_to(base, sha, ORIGIN,
		GRID, CELL)
	_expect(is_equal_approx(protected_values[12], 10.0) and
		is_equal_approx(protected_values[13], 11.0) and
		is_equal_approx(protected_values[14], 12.0),
		"hard locks and feathered weights protect a diagonal territory boundary")

	var spike := base.duplicate()
	spike[12] = 19.0
	var smoothed: Resource = BRUSH.apply_stamp(spike, null, sha, ORIGIN, GRID, CELL,
		Vector2.ZERO, BRUSH.Mode.SMOOTH, 2.2, 1.0, 0.0)
	var smooth_values: PackedFloat32Array = smoothed.apply_to(spike, sha, ORIGIN,
		GRID, CELL)
	_expect(is_equal_approx(smooth_values[12], 11.0) and
		is_equal_approx(smooth_values[11], smooth_values[13]),
		"Smooth reads one frozen stamp source and is direction independent")
	var flattened: Resource = BRUSH.apply_stamp(base, null, sha, ORIGIN, GRID, CELL,
		Vector2.ZERO, BRUSH.Mode.FLATTEN, 1.2, 0.5, 0.0, 14.0)
	_expect(is_equal_approx(flattened.apply_to(base, sha, ORIGIN, GRID, CELL)[12], 12.0),
		"Flatten blends toward its explicit terrain-local target")
	_expect(BRUSH.apply_stamp(base, null, sha, ORIGIN, GRID, CELL, Vector2.ZERO,
		BRUSH.Mode.RAISE, 1.0, 0.0, 0.0) == null,
		"a no-op stamp does not create an undo action")
	var production_base := PackedFloat32Array()
	production_base.resize(397 * 397)
	production_base.fill(0.0)
	var benchmark_start := Time.get_ticks_usec()
	var bounded_stamp: Resource = BRUSH.apply_stamp(production_base, null,
		"b".repeat(64), Vector2(-396.0, -396.0), Vector2i(397, 397), 2.0,
		Vector2.ZERO, BRUSH.Mode.RAISE, 12.0, 0.25, 1.0)
	var benchmark_usec := Time.get_ticks_usec() - benchmark_start
	_expect(bounded_stamp != null and bounded_stamp.indices.size() < 160,
		"a production-size grid stamp visits only its bounded brush footprint")
	print("terrain sculpt 397x397 radius12 stamp usec=", benchmark_usec,
		" changed=", bounded_stamp.indices.size())

	var malformed := LAYER.new()
	malformed.bind_base(sha, ORIGIN, GRID, CELL)
	malformed.indices = PackedInt32Array([3, 3])
	malformed.deltas = PackedFloat32Array([1.0, INF])
	_expect(not malformed.validation_error(sha, ORIGIN, GRID, CELL).is_empty() and
		not raised.validation_error("0".repeat(64), ORIGIN, GRID, CELL).is_empty(),
		"malformed and stale layers fail validation")

	_expect(ResourceSaver.save(raised, LAYER_PATH) == OK, "sculpt layer saves as a resource")
	var loaded := ResourceLoader.load(LAYER_PATH, "Resource",
		ResourceLoader.CACHE_MODE_IGNORE)
	_expect(loaded != null and loaded.resource_local_to_scene and
		loaded.indices == raised.indices and loaded.deltas == raised.deltas,
		"sparse edits round-trip independently through a saved resource")

	var region := _make_region()
	root.add_child(region)
	await process_frame
	var packed := PackedScene.new()
	_expect(packed.pack(region) == OK and ResourceSaver.save(packed, SCENE_PATH) == OK,
		"terrain control saves as an editable scene")
	region.queue_free()
	await process_frame
	var reopened_scene := ResourceLoader.load(SCENE_PATH, "PackedScene",
		ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	region = reopened_scene.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE)
	root.add_child(region)
	await process_frame
	var original_document: Dictionary = region.call("export_snapshot", ORIGINAL_OUTPUT)
	_expect(not original_document.is_empty() and FileAccess.get_file_as_bytes(
		ProjectSettings.globalize_path(ORIGINAL_OUTPUT).get_base_dir().path_join(
			"base-heights.f32le")) == original_bytes,
		"no-layer snapshot keeps the original height bytes exactly")

	var terrain = region.get_node("Terrain")
	terrain.set("sculpt_layer", malformed)
	print("Expected fail-closed error: malformed Sculpt Layer blocks snapshot export.")
	_expect((region.call("export_snapshot", SCULPT_OUTPUT) as Dictionary).is_empty(),
		"snapshot export blocks a malformed sculpt layer")
	terrain.set("sculpt_layer", null)
	var embedded_layer: Resource = raised.copy_with(raised.indices, raised.deltas)
	_expect(terrain.call("apply_sculpt_layer", embedded_layer) and
		FileAccess.get_file_as_bytes(ProjectSettings.globalize_path(HEIGHT_PATH)) ==
		original_bytes,
		"applying a layer refreshes preview without modifying the original height file")
	var effective_before_getter: PackedFloat32Array = terrain.call("effective_heights")
	var sculpted_getter: PackedFloat32Array = terrain.call("sculpted_base_heights")
	_expect(is_equal_approx(sculpted_getter[12], 12.0) and
		terrain.call("effective_heights") == effective_before_getter and
		effective_before_getter[12] > sculpted_getter[12],
		"sculpted base getter cannot erase downstream patch effects from preview/export")
	packed = PackedScene.new()
	_expect(packed.pack(region) == OK and ResourceSaver.save(packed, SCENE_PATH) == OK,
		"the edited layer persists with the region scene")
	region.queue_free()
	await process_frame
	reopened_scene = ResourceLoader.load(SCENE_PATH, "PackedScene",
		ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	var reopened := reopened_scene.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE)
	root.add_child(reopened)
	await process_frame
	var document: Dictionary = reopened.call("export_snapshot", SCULPT_OUTPUT)
	var sculpted_base := _read_float32(SCULPT_OUTPUT.get_base_dir().path_join(
		"base-heights.f32le"))
	var resolved := _read_float32(SCULPT_OUTPUT.get_base_dir().path_join(
		"resolved-heights.f32le"))
	_expect(not document.is_empty() and is_equal_approx(sculpted_base[12], 12.0) and
		resolved[12] > sculpted_base[12] and document.terrain.baseHeights.sha256 !=
		FileAccess.get_sha256(ProjectSettings.globalize_path(HEIGHT_PATH)),
		"snapshot base is sculpted while resolved terrain still adds downstream patches")
	var reopened_layer: Resource = reopened.get_node("Terrain").get("sculpt_layer")
	_expect(reopened_layer != embedded_layer and reopened_layer.resource_path.is_empty() and
		reopened_layer.get("indices") == raised.indices,
		"scene reload owns an independent editable sculpt layer")

	reopened.queue_free()
	if not OS.get_cmdline_user_args().has("--retain-fixture"):
		_cleanup()
	else:
		print("terrain sculpt fixture retained: ", SCULPT_OUTPUT)
	print("terrain sculpt: %d assertions, %d failures" % [18, failures])
	call_deferred("_finish", 1 if failures else 0)


func _make_region() -> Node3D:
	var region := REGION.new()
	region.name = "SculptRegion"
	region.region_id = "sculpt_test"
	# Five vertices at two metre spacing cover an eight metre storage square.
	region.server_cells = Vector2i(8, 8)
	region.server_origin = Vector2i(4, 4)
	region.collision_origin_metres = Vector2(-4.0, 4.0)
	region.ownership_polygon_sha256 = "a".repeat(64)
	region.runtime_binding_seed_path = RUNTIME_SEED_PATH
	region.runtime_binding_seed_sha256 = FileAccess.get_sha256(
		ProjectSettings.globalize_path(RUNTIME_SEED_PATH))
	var terrain := TERRAIN.new()
	terrain.name = "Terrain"
	terrain.origin = ORIGIN
	terrain.grid_size = GRID
	terrain.cell_metres = CELL
	terrain.base_heights_path = HEIGHT_PATH
	terrain.base_surface = SURFACE.from_preset(PRESETS.GRASS)
	terrain.preview_enabled = false
	_add_owned(region, terrain)
	var patches := Node3D.new()
	patches.name = "Patches"
	_add_owned(terrain, patches, region)
	var patch := PATCH.new()
	patch.name = "CenterPatch"
	patch.patch_id = "center-patch"
	patch.size = Vector2(3.0, 3.0)
	patch.position = Vector3(0.0, 1.0, 0.0)
	_add_owned(patches, patch, region)
	for name in ["Roads", "Rivers", "WaterRegions", "Bridges", "AuthoredAssets"]:
		var container := Node3D.new()
		container.name = name
		_add_owned(region, container)
	var ground := Node3D.new()
	ground.name = "Ground"
	_add_owned(region, ground)
	var ground_regions := Node3D.new()
	ground_regions.name = "Regions"
	_add_owned(ground, ground_regions, region)
	var gameplay := Node3D.new()
	gameplay.name = "Gameplay"
	_add_owned(region, gameplay)
	var spawns := Node3D.new()
	spawns.name = "Spawns"
	_add_owned(gameplay, spawns, region)
	var spawn := GAMEPLAY.new()
	spawn.name = "TestSpawn"
	spawn.kind = "spawn"
	spawn.record_id = "sculpt-test-spawn"
	spawn.default_spawn = true
	_add_owned(spawns, spawn, region)
	var portals := Node3D.new()
	portals.name = "Portals"
	_add_owned(gameplay, portals, region)
	var portal := GAMEPLAY.new()
	portal.name = "TestPortal"
	portal.kind = "portal"
	portal.record_id = "sculpt-test-portal"
	portal.destination_map = "sculpt_test"
	portal.destination_spawn = "sculpt-test-spawn"
	_add_owned(portals, portal, region)
	return region


func _add_owned(parent: Node, child: Node, owner: Node = null) -> void:
	parent.add_child(child)
	child.owner = owner if owner != null else parent


func _write_float32(path: String, values: PackedFloat32Array) -> void:
	var file := FileAccess.open(ProjectSettings.globalize_path(path), FileAccess.WRITE)
	file.big_endian = false
	for value in values:
		file.store_float(value)
	file.close()


func _write_runtime_seed() -> void:
	var seed := {
		"schema": "eloria-runtime-binding-seed-v1",
		"regionId": "sculpt_test",
		"provenance": {
			"sourceReportSha256": "c".repeat(64),
			"profileFiles": [],
		},
		"bindings": [],
	}
	var file := FileAccess.open(ProjectSettings.globalize_path(RUNTIME_SEED_PATH),
		FileAccess.WRITE)
	file.store_string(JSON.stringify(seed, "  ", true, true) + "\n")
	file.close()


func _read_float32(path: String) -> PackedFloat32Array:
	var file := FileAccess.open(ProjectSettings.globalize_path(path), FileAccess.READ)
	file.big_endian = false
	var result := PackedFloat32Array()
	while file.get_position() < file.get_length():
		result.append(file.get_float())
	file.close()
	return result


func _cleanup() -> void:
	for path in [HEIGHT_PATH, LAYER_PATH, SCENE_PATH, RUNTIME_SEED_PATH]:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	for directory in [ORIGINAL_OUTPUT.get_base_dir(), SCULPT_OUTPUT.get_base_dir()]:
		var absolute := ProjectSettings.globalize_path(directory)
		for file_name in DirAccess.get_files_at(absolute):
			DirAccess.remove_absolute(absolute.path_join(file_name))


func _finish(exit_code: int) -> void:
	await process_frame
	quit(exit_code)


func _expect(condition: bool, message: String) -> void:
	if condition:
		return
	failures += 1
	push_error(message)
