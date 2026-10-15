extends SceneTree

const REGION := preload("res://src/dev/map_authoring_region/region_control.gd")
const TERRAIN := preload("res://src/dev/map_authoring_region/terrain_control.gd")
const PATCH := preload("res://src/dev/map_authoring_region/terrain_patch.gd")
const PATH := preload("res://src/dev/map_authoring_region/path_control.gd")
const WATER := preload(
	"res://src/dev/map_authoring_region/water_region_control.gd")
const GROUND := preload(
	"res://src/dev/map_authoring_region/ground_region_control.gd")
const ASSET := preload("res://src/dev/map_authoring_region/asset_control.gd")
const ASSET_OVERRIDE := preload(
	"res://src/dev/map_authoring_region/asset_surface_override.gd")
const MARKER := preload("res://src/dev/map_authoring_region/gameplay_marker.gd")
const SNAPSHOT := preload("res://src/dev/map_authoring_region/region_snapshot.gd")
const REVIEW_NOTES := preload("res://addons/map_authoring_usability/review_notes.gd")
const SURFACE := preload(
	"res://src/dev/map_authoring_pilot/style/map_authoring_surface.gd")
const PRESETS := preload(
	"res://src/dev/map_authoring_pilot/style/texture_presets.gd")
const BIOME_PALETTE_ENTRY := preload(
	"res://src/dev/map_authoring_region/biome_palette_entry.gd")

const SCENE_PATH := "res://tests/.continent-authoring-framework.tscn"
const ASSET_SCENE_PATH := "res://tests/.continent-authoring-asset.tscn"
const HEIGHT_PATH := "res://tests/.continent-authoring-heights.f32le"
const COLOR_PATH := "res://tests/.continent-authoring-colors.rgba8"
const RUNTIME_SEED_PATH := "res://tests/.continent-authoring-runtime-seed.json"
const OUTPUT_PATH := \
	"res://test-artifacts/continent-authoring-framework/continent-authoring.json"
const TEST_ROUTE_ID := "east-gate-main-ramp"

var failures := 0


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	_write_heights()
	_write_colors()
	_write_asset_scene()
	_write_runtime_seed()
	var authored := _scene()
	root.add_child(authored)
	await process_frame
	var packed := PackedScene.new()
	_expect(packed.pack(authored) == OK and ResourceSaver.save(packed, SCENE_PATH) == OK,
		"production authoring controls save as one editable scene")
	authored.queue_free()
	await process_frame
	var reopened_scene := ResourceLoader.load(SCENE_PATH, "PackedScene",
		ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	var reopened := reopened_scene.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE) as Node3D
	root.add_child(reopened)
	await process_frame
	var document: Dictionary = reopened.call("export_snapshot", OUTPUT_PATH)
	_expect(not document.is_empty(), "saved production scene exports a snapshot")
	if not document.is_empty():
		_expect(document.schema == "eloria-continent-authoring-v1" and
			document.continentTranslation == [1200.0, 0.0, 720.0] and
			document.server.origin == [194, 292] and
			is_equal_approx(float(document.terrain.previewUvMetresInverse), 0.24),
			"snapshot keeps the production coordinate contract")
		var fixture_spec: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
			"res://world_authoring/regions/sunmane_steppe/region-authoring-spec.json"))
		_expect(document.replacements.routeIds == fixture_spec.authority.ownedRouteIds and
			document.paths[0].replacesRouteId == TEST_ROUTE_ID,
			"persistent replacement registry and path identity agree")
		_expect(document.replacements.planFeatureIds == ["test-lake"] and
			document.waterRegions.size() == 1 and
			document.waterRegions[0].center == [1.0, 2.0] and
			is_equal_approx(float(document.waterRegions[0].level), 3.0) and
			document.waterRegions[0].radii == [4.0, 2.0] and
			is_equal_approx(float(document.waterRegions[0].depth), 1.25),
			"elliptical water control exports its persistent claim and exact parameters")
		_expect(document.terrain.baseColors.encoding == "rgba8-srgb" and
			FileAccess.get_file_as_bytes(
				ProjectSettings.globalize_path(OUTPUT_PATH).get_base_dir().path_join(
					"base-colors.rgba8")).size() == 36,
			"optional full-grid RGBA8 terrain colors export as a hash-bound sidecar")
		_expect(document.objects[0].matrix.size() == 16 and
			document.objects[0].matrix[12] == 3.0,
			"object transform uses glTF column-major translation slots")
		_expect(document.objects[0].bakedSource.sourceNode == "." and
			FileAccess.file_exists(ProjectSettings.globalize_path(OUTPUT_PATH).get_base_dir().path_join(
				String(document.objects[0].bakedSource.path))),
			"non-GLB picker sources bake to a hash-bound reusable production GLB")
		_expect(document.gameplay.spawnPoints[0].serverTile == [195, 293],
			"marker transform derives its server tile")
		_expect(document.gameplay.runtimePoints.size() == 1 and
			document.gameplay.runtimeBindings.size() == 2,
			"visible runtime points and exact server bindings export together")
		_expect(document.gameplay.runtimeBindings[0].marker == {
			"section": "runtimePoints", "id": "runtime-npc-test"} and
			document.gameplay.runtimeBindings[1].marker == {
			"section": "spawnPoints", "id": "continent-arrival"} and
			document.gameplay.runtimeBindings[0].targetOffset == [0.0, 0.0, 0.0] and
			document.gameplay.runtimeBindings[1].targetOffset == [1.25, 0.0, -0.75],
			"runtime bindings keep qualified markers and independent target offsets")
		_expect(document.sources.runtimeBindingSeed.sha256 ==
			FileAccess.get_sha256(ProjectSettings.globalize_path(RUNTIME_SEED_PATH)) and
			_dependency_matches_file(document.sources.dependencies,
				"godot-client/tests/.continent-authoring-runtime-seed.json"),
			"runtime identity seed is explicitly hash-bound")
		_expect(FileAccess.get_file_as_bytes(
			ProjectSettings.globalize_path(OUTPUT_PATH).get_base_dir().path_join(
				"resolved-heights.f32le")) != FileAccess.get_file_as_bytes(
				ProjectSettings.globalize_path(HEIGHT_PATH)),
			"resolved preview terrain includes current patch/path effects")
		_expect(_array_color_close(
			document.paths[0].surface.roadOverrides.wornTint,
			Color(0.9, 0.78, 0.59, 1.0)),
			"saved known road shader edits reach the production material contract")
		_expect(_array_color_close(
			document.terrain.baseSurface.pbrOverrides.albedoColor,
			Color(0.7, 0.6, 0.5, 1.0)),
			"saved preset StandardMaterial edits cannot silently fall back to defaults")
		_expect(bool(document.terrain.baseSurface.biomeBlendEnabled) and
			document.terrain.biomePalette.size() == 1 and
			document.terrain.biomePalette[0].id == "forest-floor" and
			document.terrain.biomePalette[0].role == "woodland" and
			document.terrain.biomePalette[0].surface.preset == PRESETS.SAND,
			"terrain exports its explicit blend opt-in and one stable secondary palette")
		_expect(not bool(document.groundRegions[0].surface.pbrOverrides.triplanar) and
			not bool(document.groundRegions[0].surface.pbrOverrides.worldTriplanar),
			"named region textures normalize to the supported UV projection")
		_expect(_dependency_matches_file(document.sources.dependencies,
			"godot-client/src/dev/map_authoring_pilot/style/textures/ground-basecolor.png") and
			_dependency_matches_file(document.sources.dependencies,
			"godot-client/src/dev/map_authoring_pilot/style/textures/ground-normal.png") and
			_dependency_matches_file(document.sources.dependencies,
			"godot-client/src/dev/map_authoring_pilot/style/textures/ground-orm.png"),
			"every emitted PBR texture has a current hash-bound dependency")
	_check_review_notes_stay_out(reopened, document)
	_check_ground_preview_uvs(reopened)
	_check_override_removal(reopened)
	_check_export_rejections(reopened)
	var hit: Variant = reopened.call("authoring_ground_intersection",
		Vector3(0.0, 20.0, 0.0), Vector3.DOWN, 40.0)
	_expect(hit is Vector3 and is_finite((hit as Vector3).y),
		"asset placement ray intersects actual authored terrain triangles")
	reopened.queue_free()
	_cleanup()
	print("continent authoring framework: %d assertions, %d failures" % [
		33, failures])
	quit(1 if failures else 0)


func _scene() -> Node3D:
	var region := REGION.new()
	region.name = "TestRegion"
	region.region_id = "sunmane_steppe"
	region.continent_translation = Vector3(1200.0, 0.0, 720.0)
	region.server_origin = Vector2i(194, 292)
	region.server_cells = Vector2i(792, 792)
	region.collision_origin_metres = Vector2(-194.0, 292.0)
	region.ownership_polygon_sha256 = "a".repeat(64)
	# The persistent registry is the source of deletion authority; the test
	# route therefore uses a real owned ID from the Sunmane fixture spec.
	region.owned_route_ids = PackedStringArray([TEST_ROUTE_ID])
	region.owned_plan_feature_ids = PackedStringArray(["test-lake"])
	region.runtime_binding_seed_path = RUNTIME_SEED_PATH
	region.runtime_binding_seed_sha256 = FileAccess.get_sha256(
		ProjectSettings.globalize_path(RUNTIME_SEED_PATH))
	var terrain := TERRAIN.new()
	terrain.name = "Terrain"
	terrain.origin = Vector2(-2.0, -2.0)
	terrain.grid_size = Vector2i(3, 3)
	terrain.cell_metres = 2.0
	terrain.base_heights_path = HEIGHT_PATH
	terrain.base_colors_path = COLOR_PATH
	terrain.base_surface = SURFACE.from_preset(PRESETS.GRASS)
	terrain.base_surface.biome_blend_enabled = true
	(terrain.base_surface.source_material as BaseMaterial3D).albedo_color = \
		Color(0.7, 0.6, 0.5, 1.0)
	var palette := BIOME_PALETTE_ENTRY.new()
	palette.id = "forest-floor"
	palette.role = "woodland"
	palette.surface = SURFACE.from_preset(PRESETS.SAND)
	terrain.biome_palette = [palette]
	_add_owned(region, terrain)
	var patches := Node3D.new()
	patches.name = "Patches"
	_add_owned(terrain, patches, region)
	var patch := PATCH.new()
	patch.name = "RaisedPatch"
	patch.patch_id = "raised-patch"
	patch.size = Vector2(3.0, 3.0)
	patch.position = Vector3(0.0, 1.0, 0.0)
	_add_owned(patches, patch, region)
	var ground := Node3D.new()
	ground.name = "Ground"
	_add_owned(region, ground)
	var regions := Node3D.new()
	regions.name = "Regions"
	_add_owned(ground, regions, region)
	var ground_region := GROUND.new()
	ground_region.name = "TestGround"
	ground_region.region_id = "test-ground"
	ground_region.enabled = true
	ground_region.size = Vector2(3.0, 3.0)
	ground_region.surface = SURFACE.from_preset(PRESETS.SAND)
	_add_owned(regions, ground_region, region)
	var roads := Node3D.new()
	roads.name = "Roads"
	_add_owned(region, roads)
	var road := PATH.new()
	road.name = "TestRoad"
	road.path_id = "test-road"
	road.replaces_route_id = TEST_ROUTE_ID
	road.surface = SURFACE.from_preset(PRESETS.WORN_EARTH, true)
	(road.surface.source_material as ShaderMaterial).set_shader_parameter(
		"worn_tint", Color(0.9, 0.78, 0.59, 1.0))
	road.curve = Curve3D.new()
	road.curve.add_point(Vector3(-2.0, 2.0, 0.0))
	road.curve.add_point(Vector3(2.0, 2.0, 0.0))
	_add_owned(roads, road, region)
	for name in ["Rivers", "Bridges"]:
		var container := Node3D.new()
		container.name = name
		_add_owned(region, container)
	var water_regions := Node3D.new()
	water_regions.name = "WaterRegions"
	_add_owned(region, water_regions)
	var lake := WATER.new()
	lake.name = "TestLake"
	lake.water_id = "test-lake-control"
	lake.replaces_plan_feature_id = "test-lake"
	lake.display_name = "Test Lake"
	lake.position = Vector3(1.0, 3.0, 2.0)
	lake.radii = Vector2(4.0, 2.0)
	lake.baseline_plan_depth = 1.25
	_add_owned(water_regions, lake, region)
	var assets := Node3D.new()
	assets.name = "AuthoredAssets"
	_add_owned(region, assets)
	var asset := ASSET.new()
	asset.name = "TestAsset"
	asset.asset_id = "test-asset"
	asset.node_name = "Authored_test_asset"
	asset.catalog_asset_id = "test:asset"
	asset.scene_path = ASSET_SCENE_PATH
	asset.position = Vector3(3.0, 0.0, 4.0)
	_add_owned(assets, asset, region)
	var content_scene := ResourceLoader.load(ASSET_SCENE_PATH, "PackedScene",
		ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	var content := content_scene.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE) as Node3D
	content.name = "Content"
	_add_owned(asset, content, region)
	var override := ASSET_OVERRIDE.new()
	override.mesh_node_path = "First"
	override.surface_index = 0
	override.surface = SURFACE.from_preset(PRESETS.STONE)
	asset.material_overrides = [override]
	var gameplay := Node3D.new()
	gameplay.name = "Gameplay"
	_add_owned(region, gameplay)
	var spawns := Node3D.new()
	spawns.name = "Spawns"
	_add_owned(gameplay, spawns, region)
	var spawn := MARKER.new()
	spawn.name = "Arrival"
	spawn.record_id = "continent-arrival"
	spawn.kind = "spawn"
	spawn.default_spawn = true
	spawn.position = Vector3(1.5, 2.0, -1.5)
	spawn.follow_asset_id = "test-asset"
	spawn.follow_asset_offset = Vector3(-1.5, 2.0, -5.5)
	spawn.runtime_bindings = [_binding("spawns.txt:1:arrival@195:293", "spawn",
		[1.25, 0.0, -0.75])]
	_add_owned(spawns, spawn, region)
	var runtime_points := Node3D.new()
	runtime_points.name = "RuntimePoints"
	_add_owned(gameplay, runtime_points, region)
	var runtime_npc := MARKER.new()
	runtime_npc.name = "RuntimeNpcTest"
	runtime_npc.record_id = "runtime-npc-test"
	runtime_npc.kind = "runtime_point"
	runtime_npc.label = "Test runtime NPC"
	runtime_npc.position = Vector3(-1.0, 1.0, 1.0)
	runtime_npc.runtime_bindings = [_binding("npcs.txt:2:test@193:291", "npc")]
	_add_owned(runtime_points, runtime_npc, region)
	var generated := Node3D.new()
	generated.name = "GeneratedPreview"
	_add_owned(region, generated)
	return region


## A review-notes sidecar beside the scene (review_notes.gd) changes nothing
## the snapshot exports: document, dependencies and written sidecars.
func _check_review_notes_stay_out(region: Node3D, before: Dictionary) -> void:
	var notes_path := REVIEW_NOTES.path_for(region)
	var output := ProjectSettings.globalize_path(OUTPUT_PATH).get_base_dir()
	var written := {}
	for name in ["base-heights.f32le", "resolved-heights.f32le", "base-colors.rgba8"]:
		written[name] = FileAccess.get_file_as_bytes(output.path_join(name))
	var file := FileAccess.open(notes_path, FileAccess.WRITE)
	file.store_string(JSON.stringify(REVIEW_NOTES.document(String(region.get("region_id")), [
		{"id": "review-001", "position": Vector3(1.0, 2.0, 3.0), "text": "Check the ramp",
			"status": "open"}])))
	file.close()
	var with_notes: Dictionary = region.call("export_snapshot", OUTPUT_PATH)
	var same_files := true
	for name: String in written:
		same_files = same_files and FileAccess.get_file_as_bytes(output.path_join(name)) == written[name]
	DirAccess.remove_absolute(ProjectSettings.globalize_path(notes_path))
	_expect(not notes_path.is_empty() and not before.is_empty() and with_notes == before and
		same_files and not "editor-notes" in JSON.stringify(with_notes),
		"a review-notes sidecar beside the scene leaves the snapshot and its files unchanged")


func _check_override_removal(region: Node3D) -> void:
	var asset = region.get_node("AuthoredAssets/TestAsset")
	var first := asset.get_node("Content/First") as MeshInstance3D
	var second := asset.get_node("Content/Second") as MeshInstance3D
	asset.call("_apply_material_overrides")
	_expect(first.get_surface_override_material(0) != null,
		"asset local material applies only to its selected mesh surface")
	var override = asset.material_overrides[0]
	override.mesh_node_path = "Second"
	asset.call("_apply_material_overrides")
	_expect(first.get_surface_override_material(0) == null and
		second.get_surface_override_material(0) != null,
		"removing or retargeting an override restores the former source material")


func _check_ground_preview_uvs(region: Node3D) -> void:
	var instance := region.get_node_or_null(
		"Terrain/__GroundRegionPreviews/GroundRegion_test-ground") as MeshInstance3D
	var arrays: Array = instance.mesh.surface_get_arrays(0) if \
		instance != null and instance.mesh != null else []
	var vertices := arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array if \
		arrays.size() == Mesh.ARRAY_MAX else PackedVector3Array()
	var uvs := arrays[Mesh.ARRAY_TEX_UV] as PackedVector2Array if \
		arrays.size() == Mesh.ARRAY_MAX else PackedVector2Array()
	var normals := arrays[Mesh.ARRAY_NORMAL] as PackedVector3Array if \
		arrays.size() == Mesh.ARRAY_MAX else PackedVector3Array()
	var tangents := arrays[Mesh.ARRAY_TANGENT] as PackedFloat32Array if \
		arrays.size() == Mesh.ARRAY_MAX else PackedFloat32Array()
	_expect(vertices.size() > 0 and uvs.size() == vertices.size() and
		uvs[0] != uvs[uvs.size() - 1],
		"enabled textured ground regions use nonconstant terrain-metre UVs")
	_expect(normals.size() == vertices.size() and
		tangents.size() == vertices.size() * 4,
		"ground region previews provide a complete tangent basis")


func _check_export_rejections(region: Node3D) -> void:
	var asset = region.get_node("AuthoredAssets/TestAsset")
	asset.position.x += 1.0
	var followed_exporter = SNAPSHOT.new()
	var followed_document: Dictionary = followed_exporter.export_region(region, OUTPUT_PATH)
	_expect(not followed_document.is_empty() and
		is_equal_approx(float(followed_document.gameplay.spawnPoints[0].position[0]), 2.5),
		"linked gameplay markers follow an authored asset move during bake")
	asset.position.x -= 1.0
	var runtime_point := region.get_node("Gameplay/RuntimePoints/RuntimeNpcTest") as Node3D
	runtime_point.position.x += 2.0
	var moved_exporter = SNAPSHOT.new()
	var moved_document: Dictionary = moved_exporter.export_region(region, OUTPUT_PATH)
	_expect(not moved_document.is_empty() and
		is_equal_approx(float(moved_document.gameplay.runtimePoints[0].position[0]), 1.0) and
		moved_document.gameplay.runtimeBindings[0].id == "npcs.txt:2:test@193:291",
		"moving a saved runtime point changes its authority without changing its binding")
	runtime_point.position.x -= 2.0
	var second := asset.get_node("Content/Second") as MeshInstance3D
	second.position.x += 0.25
	var exporter = SNAPSHOT.new()
	_expect(exporter.export_region(region, OUTPUT_PATH).is_empty() and
		"edits inside Content" in " ".join(exporter.errors),
		"bake rejects child transforms that source identity would discard")
	second.position.x -= 0.25
	var duplicate = asset.material_overrides[0].duplicate(true)
	asset.material_overrides.append(duplicate)
	exporter = SNAPSHOT.new()
	_expect(exporter.export_region(region, OUTPUT_PATH).is_empty() and
		"duplicate material override target" in " ".join(exporter.errors),
		"bake rejects duplicate material override targets")
	asset.material_overrides.pop_back()
	var override = asset.material_overrides[0]
	var saved_index: int = override.surface_index
	override.surface_index = -1
	exporter = SNAPSHOT.new()
	_expect(exporter.export_region(region, OUTPUT_PATH).is_empty() and
		"cannot be negative" in " ".join(exporter.errors),
		"bake rejects negative material surface indices")
	override.surface_index = saved_index
	var patch := region.get_node("Terrain/Patches/RaisedPatch") as Node3D
	patch.rotation_degrees.x = 5.0
	exporter = SNAPSHOT.new()
	_expect(exporter.export_region(region, OUTPUT_PATH).is_empty() and
		"is tilted" in " ".join(exporter.errors),
		"bake rejects terrain patch tilt rather than ignoring it")
	patch.rotation_degrees.x = 0.0
	var lake := region.get_node("WaterRegions/TestLake") as Node3D
	lake.rotation_degrees.y = 5.0
	exporter = SNAPSHOT.new()
	_expect(exporter.export_region(region, OUTPUT_PATH).is_empty() and
		"support translation only" in " ".join(exporter.errors),
		"bake rejects water-region rotation instead of silently ignoring it")
	lake.rotation_degrees.y = 0.0
	var saved_seed_hash: String = region.runtime_binding_seed_sha256
	region.runtime_binding_seed_sha256 = "0".repeat(64)
	exporter = SNAPSHOT.new()
	_expect(exporter.export_region(region, OUTPUT_PATH).is_empty() and
		"Runtime Binding Seed hash changed" in " ".join(exporter.errors),
		"bake rejects an edited runtime binding seed until its reviewed hash is updated")
	region.runtime_binding_seed_sha256 = saved_seed_hash
	var saved_binding: Dictionary = runtime_point.runtime_bindings[0]
	var invalid_binding := saved_binding.duplicate(true)
	invalid_binding.targetOffset = [0.0, 1.0, 0.0]
	runtime_point.runtime_bindings[0] = invalid_binding
	exporter = SNAPSHOT.new()
	_expect(exporter.export_region(region, OUTPUT_PATH).is_empty() and
		"targetOffset must be horizontal" in " ".join(exporter.errors),
		"bake rejects vertical per-binding target offsets")
	runtime_point.runtime_bindings[0] = saved_binding


func _mesh(node_name: String) -> MeshInstance3D:
	var result := MeshInstance3D.new()
	result.name = node_name
	result.mesh = BoxMesh.new()
	return result


func _array_color_close(values: Array, expected: Color) -> bool:
	return values.size() == 4 and is_equal_approx(float(values[0]), expected.r) and \
		is_equal_approx(float(values[1]), expected.g) and \
		is_equal_approx(float(values[2]), expected.b) and \
		is_equal_approx(float(values[3]), expected.a)


func _dependency_matches_file(dependencies: Array, repo_path: String) -> bool:
	for dependency in dependencies:
		if String(dependency.path) != repo_path:
			continue
		var res_path := "res://" + repo_path.trim_prefix("godot-client/")
		return String(dependency.sha256) == FileAccess.get_sha256(
			ProjectSettings.globalize_path(res_path))
	return false


func _write_heights() -> void:
	var file := FileAccess.open(HEIGHT_PATH, FileAccess.WRITE)
	file.big_endian = false
	for _index in 9:
		file.store_float(0.0)
	file.close()


func _write_colors() -> void:
	var file := FileAccess.open(COLOR_PATH, FileAccess.WRITE)
	for index in 9:
		file.store_8(index * 11)
		file.store_8(255 - index * 7)
		file.store_8(index * 3)
		file.store_8(255)
	file.close()


func _write_asset_scene() -> void:
	var source := Node3D.new()
	source.name = "FixtureAsset"
	for node_name in ["First", "Second"]:
		var mesh := _mesh(node_name)
		source.add_child(mesh)
		mesh.owner = source
	var packed := PackedScene.new()
	packed.pack(source)
	ResourceSaver.save(packed, ASSET_SCENE_PATH)
	source.free()


func _write_runtime_seed() -> void:
	var file := FileAccess.open(RUNTIME_SEED_PATH, FileAccess.WRITE)
	file.store_string('{"schema":"eloria-runtime-binding-seed-v1","regionId":"sunmane_steppe"}\n')
	file.close()


func _binding(identity: String, role: String,
		target_offset: Array = [0.0, 0.0, 0.0]) -> Dictionary:
	return {"id": identity,
		"source": {"path": "config/eloria/%ss.txt" % role, "line": 1,
			"oldTile": [1, 2]},
		"role": role, "roads": "marker", "targetOffset": target_offset,
		"provenance": {"sourceReportSha256": "b".repeat(64)}}


func _add_owned(parent: Node, child: Node, scene_owner: Node = null) -> void:
	parent.add_child(child)
	child.owner = scene_owner if scene_owner != null else parent


func _cleanup() -> void:
	for path in [SCENE_PATH, SCENE_PATH + ".uid", ASSET_SCENE_PATH,
			ASSET_SCENE_PATH + ".uid", HEIGHT_PATH, HEIGHT_PATH + ".uid",
			COLOR_PATH, COLOR_PATH + ".uid",
			RUNTIME_SEED_PATH, RUNTIME_SEED_PATH + ".uid"]:
		if FileAccess.file_exists(path):
			DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	var output_dir := ProjectSettings.globalize_path(OUTPUT_PATH).get_base_dir()
	for name in ["continent-authoring.json", "base-heights.f32le",
			"resolved-heights.f32le", "base-colors.rgba8"]:
		DirAccess.remove_absolute(output_dir.path_join(name))
	var prototypes := output_dir.path_join("prototypes")
	if DirAccess.dir_exists_absolute(prototypes):
		for filename in DirAccess.get_files_at(prototypes):
			DirAccess.remove_absolute(prototypes.path_join(filename))
		DirAccess.remove_absolute(prototypes)


func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)
