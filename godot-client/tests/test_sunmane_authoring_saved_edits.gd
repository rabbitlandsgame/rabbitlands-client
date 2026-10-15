extends SceneTree

const SOURCE_SCENE := \
	"res://world_authoring/regions/sunmane_steppe/sunmane_steppe.tscn"
const ARTIFACT_ROOT := "res://test-artifacts/sunmane-edit-regression"
const EDITED_SCENE := ARTIFACT_ROOT + "/sunmane-edited.tscn"
const BEFORE_JSON := ARTIFACT_ROOT + "/before/continent-authoring.json"
const AFTER_JSON := ARTIFACT_ROOT + "/after/continent-authoring.json"

const PATCH := preload("res://src/dev/map_authoring_region/terrain_patch.gd")
const GROUND := preload("res://src/dev/map_authoring_region/ground_region_control.gd")
const ASSET := preload("res://src/dev/map_authoring_region/asset_control.gd")
const MARKER := preload("res://src/dev/map_authoring_region/gameplay_marker.gd")
const SURFACE := preload(
	"res://src/dev/map_authoring_pilot/style/map_authoring_surface.gd")
const PRESETS := preload(
	"res://src/dev/map_authoring_pilot/style/texture_presets.gd")

var assertions := 0
var failures := 0


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(ARTIFACT_ROOT))
	var packed := ResourceLoader.load(SOURCE_SCENE, "PackedScene",
		ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	var region := packed.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE) as Node3D
	root.add_child(region)
	await process_frame
	var before: Dictionary = region.call("export_snapshot", BEFORE_JSON)
	_expect(not before.is_empty(), "the committed Sunmane scene bakes before edits")
	if before.is_empty():
		_finish(region)
		return

	var terrain_patch = PATCH.new()
	terrain_patch.name = "RegressionRise"
	terrain_patch.patch_id = "regression-rise"
	terrain_patch.position = Vector3(33.0, 1.25, -47.0)
	terrain_patch.rotation_degrees.y = 17.0
	terrain_patch.scale = Vector3(1.2, 1.0, 0.8)
	terrain_patch.size = Vector2(18.0, 14.0)
	terrain_patch.feather = 3.0
	_add_owned(region.get_node("Terrain/Patches"), terrain_patch, region)

	var road = region.get_node("Roads").get_child(0)
	var road_id := String(road.path_id)
	road.sync_curve_binding()
	var road_widths := PackedFloat32Array()
	road_widths.resize(road.curve.point_count)
	road_widths[0] = road.default_width + 1.75
	road_widths[road_widths.size() - 1] = road.default_width + 0.75
	road.point_widths = road_widths
	road.surface.rotation_degrees = 23.0

	var river = region.get_node("Rivers").get_child(0)
	var river_id := String(river.path_id)
	river.sync_curve_binding()
	var river_widths := PackedFloat32Array()
	river_widths.resize(river.curve.point_count)
	river_widths[0] = 12.0
	river_widths[river_widths.size() - 1] = 14.0
	river.point_widths = river_widths

	var ground = GROUND.new()
	ground.name = "RegressionSand"
	ground.region_id = "regression-sand"
	ground.enabled = true
	ground.shape = 1
	ground.position = Vector3(45.0, 0.0, -32.0)
	ground.rotation_degrees.y = -28.0
	ground.size = Vector2(22.0, 13.0)
	ground.blend_width = 2.25
	ground.opacity = 0.82
	ground.priority = 11
	ground.surface = SURFACE.from_preset(PRESETS.SAND)
	ground.surface.rotation_degrees = 37.0
	_add_owned(region.get_node("Ground/Regions"), ground, region)

	var bridge = region.get_node("Bridges").get_child(0)
	var bridge_id := String(bridge.bridge_id)
	var before_bridge_width: float = bridge.width
	bridge.width += 1.25

	var marker = _first_followed_marker(region)
	var moved_asset = _asset_by_id(region, marker.follow_asset_id)
	var moved_asset_id := String(moved_asset.asset_id)
	var marker_id := String(marker.record_id)
	var marker_section := String(marker.output_section())
	var existing_binding_id := String(marker.runtime_bindings[0].id)
	var existing_target_offsets := {}
	for binding in marker.runtime_bindings:
		existing_target_offsets[String(binding.id)] = binding.targetOffset.duplicate()
	moved_asset.position += Vector3(4.0, 0.5, -3.0)
	var runtime_marker = _first_runtime_marker(region)
	var runtime_marker_id := String(runtime_marker.record_id)
	var runtime_binding_id := String(runtime_marker.runtime_bindings[0].id)
	var runtime_before_position: Vector3 = runtime_marker.position
	runtime_marker.position += Vector3(-5.0, 0.75, 4.0)

	var duplicate = moved_asset.duplicate() as Node3D
	duplicate.name = String(moved_asset.name) + "Copy"
	duplicate.asset_id = moved_asset_id + "-copy"
	duplicate.node_name = String(moved_asset.node_name) + "_Copy"
	duplicate.position += Vector3(8.0, 0.0, 5.0)
	_add_owned(region.get_node("AuthoredAssets"), duplicate, region)
	for child in duplicate.get_children():
		child.owner = region

	var followed_ids := _followed_asset_ids(region)
	var removed = _first_unlinked_asset(region, followed_ids, [moved_asset_id,
		String(duplicate.asset_id)])
	var removed_id := String(removed.asset_id)
	region.get_node("AuthoredAssets").remove_child(removed)

	var edited := PackedScene.new()
	_expect(edited.pack(region) == OK and ResourceSaver.save(edited, EDITED_SCENE) == OK,
		"all representative edits save into a clone without touching the committed scene")
	region.queue_free()
	await process_frame

	var reopened_packed := ResourceLoader.load(EDITED_SCENE, "PackedScene",
		ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	var reopened := reopened_packed.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE) as Node3D
	root.add_child(reopened)
	await process_frame
	var after: Dictionary = reopened.call("export_snapshot", AFTER_JSON)
	_expect(not after.is_empty(), "the saved edit clone reopens and bakes")
	if not after.is_empty():
		var patch_record := _record(after.terrain.patches, "regression-rise")
		_expect(not patch_record.is_empty() and
			is_equal_approx(float(patch_record.height), 1.25),
			"terrain patch transform and vertical height survive save/reopen")
		var road_record := _record(after.paths, road_id)
		var river_record := _record(after.paths, river_id)
		_expect(is_equal_approx(float(road_record.points[0].width),
			float(road_widths[0])) and is_equal_approx(
			float(river_record.points[0].width), 12.0),
			"road and river point-width edits reach the baked paths")
		_expect(is_equal_approx(float(road_record.surface.rotationDegrees), 23.0),
			"path texture rotation reaches the production surface record")
		var ground_record := _record(after.groundRegions, "regression-sand")
		_expect(not ground_record.is_empty() and
			is_equal_approx(float(ground_record.surface.rotationDegrees), 37.0),
			"a transformed local ground region reaches the snapshot")
		var bridge_record := _record(after.bridges, bridge_id)
		_expect(is_equal_approx(float(bridge_record.width), before_bridge_width + 1.25),
			"bridge width survives save/reopen")
		_expect(not _record(after.objects, moved_asset_id).is_empty() and
			not _record(after.objects, moved_asset_id + "-copy").is_empty() and
			_record(after.objects, removed_id).is_empty(),
			"asset move, duplication, and removal are authoritative")
		var marker_record := _record(after.gameplay[marker_section], marker_id)
		var before_marker := _record(before.gameplay[marker_section], marker_id)
		_expect(marker_record.position != before_marker.position and
			marker_record.assetId == moved_asset_id,
			"a linked gameplay marker follows its moved object in the bake")
		var runtime_record := _record(after.gameplay.runtimePoints, runtime_marker_id)
		var runtime_binding := _record(after.gameplay.runtimeBindings, runtime_binding_id)
		var existing_binding := _record(after.gameplay.runtimeBindings,
			existing_binding_id)
		_expect(runtime_record.position != [runtime_before_position.x,
			runtime_before_position.y, runtime_before_position.z] and
			runtime_binding.marker == {"section": "runtimePoints",
				"id": runtime_marker_id},
			"a runtime-only server point move survives save/reopen with its exact binding")
		_expect(existing_binding.marker == {"section": marker_section, "id": marker_id},
			"an existing gameplay marker keeps its exact runtime alias binding")
		var moved_target_offsets := {}
		for binding in after.gameplay.runtimeBindings:
			if binding.marker == {"section": marker_section, "id": marker_id}:
				moved_target_offsets[String(binding.id)] = binding.targetOffset.duplicate()
		_expect(moved_target_offsets == existing_target_offsets and
			runtime_binding.targetOffset == [0.0, 0.0, 0.0],
			"marker moves preserve each certified endpoint offset")
		_expect(after.terrain.resolvedHeights.sha256 != before.terrain.resolvedHeights.sha256,
			"terrain/path edits change the authoritative resolved grid")
	removed.free()
	_finish(reopened)


func _first_followed_marker(region: Node3D) -> Node:
	for child in region.get_node("Gameplay").find_children("*", "", true, false):
		if child.get_script() == MARKER and not String(child.follow_asset_id).is_empty() and \
				child.runtime_bindings.size() > 1:
			return child
	return null


func _first_runtime_marker(region: Node3D) -> Node:
	for child in region.get_node("Gameplay/RuntimePoints").find_children(
			"*", "", true, false):
		if child.get_script() == MARKER:
			return child
	return null


func _asset_by_id(region: Node3D, identity: String) -> Node3D:
	for child in region.get_node("AuthoredAssets").get_children():
		if child.get_script() == ASSET and String(child.asset_id) == identity:
			return child as Node3D
	return null


func _followed_asset_ids(region: Node3D) -> Dictionary:
	var result := {}
	for child in region.get_node("Gameplay").find_children("*", "", true, false):
		if child.get_script() == MARKER and not String(child.follow_asset_id).is_empty():
			result[String(child.follow_asset_id)] = true
	return result


func _first_unlinked_asset(region: Node3D, followed: Dictionary,
		excluded: Array) -> Node3D:
	for child in region.get_node("AuthoredAssets").get_children():
		if child.get_script() == ASSET and not followed.has(String(child.asset_id)) and \
				not excluded.has(String(child.asset_id)):
			return child as Node3D
	return null


func _record(records: Array, identity: String) -> Dictionary:
	for record in records:
		if String(record.get("id", "")) == identity:
			return record
	return {}


func _add_owned(parent: Node, child: Node, scene_owner: Node) -> void:
	parent.add_child(child)
	child.owner = scene_owner


func _finish(region: Node) -> void:
	if region != null:
		region.queue_free()
	print("Sunmane saved-edit regression: %d assertions, %d failures" % [
		assertions, failures])
	quit(1 if failures else 0)


func _expect(condition: bool, message: String) -> void:
	assertions += 1
	if condition:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)
