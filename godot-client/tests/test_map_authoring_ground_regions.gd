extends SceneTree

const PILOT := preload("res://src/dev/map_authoring_pilot/map_authoring_pilot.tscn")
const RELOAD_PATH := "res://src/dev/map_authoring_pilot/.ground-regions-reload.tscn"
const EXPORT_BEFORE := "res://src/dev/map_authoring_pilot/.ground-regions-before"
const EXPORT_AFTER := "res://src/dev/map_authoring_pilot/.ground-regions-after"

var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var pilot := PILOT.instantiate()
	root.add_child(pilot)
	await process_frame
	await process_frame
	var regions := pilot.get_node("AuthoredControls/Ground/Regions")
	var soil := regions.get_node("SoilArea")
	var sand := regions.get_node("SandArea")
	_expect(not soil.enabled and not sand.enabled,
		"the two ready-to-edit starter regions are disabled by default")
	_expect(soil.surface != sand.surface and
		soil.surface.source_material != sand.surface.source_material and
		soil.surface.texture_preset == MapAuthoringTexturePresets.SOIL and
		sand.surface.texture_preset == MapAuthoringTexturePresets.SAND,
		"starter regions own independent Soil and Sand surfaces")
	var proxy_properties := {}
	for property: Dictionary in soil.get_property_list():
		if property.name in [&"texture", &"texture_rotation"]:
			proxy_properties[property.name] = property
	soil.set("texture", MapAuthoringTexturePresets.SAND)
	soil.set("texture_rotation", 27.0)
	_expect(proxy_properties.size() == 2 and
		(int(proxy_properties[&"texture"].usage) & PROPERTY_USAGE_STORAGE) == 0 and
		(int(proxy_properties[&"texture_rotation"].usage) & PROPERTY_USAGE_STORAGE) == 0 and
		soil.surface.texture_preset == MapAuthoringTexturePresets.SAND and
		is_equal_approx(soil.surface.rotation_degrees, 27.0),
		"top-level Texture controls edit the local Surface without duplicate storage")
	var undo := UndoRedo.new()
	undo.create_action("Change ground-region texture")
	undo.add_do_property(soil, "texture", MapAuthoringTexturePresets.STONE)
	undo.add_undo_property(soil, "texture", MapAuthoringTexturePresets.SAND)
	undo.commit_action()
	var proxy_do_worked: bool = \
		soil.surface.texture_preset == MapAuthoringTexturePresets.STONE
	undo.undo()
	_expect(proxy_do_worked and
		soil.surface.texture_preset == MapAuthoringTexturePresets.SAND,
		"Texture proxy participates in property undo without a second saved value")
	var other_region_source: Material = sand.surface.source_material
	soil.enabled = true
	soil.surface.source_material = ShaderMaterial.new()
	var source_warnings: PackedStringArray = \
		soil.call("_get_configuration_warnings")
	_expect(not source_warnings.is_empty() and
		String(source_warnings[0]).contains("Choose a named Texture"),
		"an enabled unsupported Surface gives an actionable editor warning")
	soil.set("texture", MapAuthoringTexturePresets.SAND)
	_expect(soil.surface.source_material is BaseMaterial3D and
		soil.surface.source_material != other_region_source and
		sand.surface.source_material == other_region_source,
		"reselecting a named Texture repairs only that region's invalid source")
	soil.enabled = false
	soil.set("texture", MapAuthoringTexturePresets.SOIL)
	soil.set("texture_rotation", 0.0)
	_expect(_region_meshes(pilot).is_empty(),
		"disabled starter regions do not create preview overlays")

	pilot.export_directory = EXPORT_BEFORE
	pilot.export_contract()
	var baseline_collision := FileAccess.get_file_as_bytes(EXPORT_BEFORE + "/collision.bin")
	var baseline_manifest := FileAccess.get_file_as_string(EXPORT_BEFORE + "/world.json")
	var baseline_grid: PackedByteArray = pilot.server_grid()
	var road_id := pilot.get_node("GeneratedPreview/Road").get_instance_id()
	var bridge_id := pilot.get_node("GeneratedPreview/Bridge").get_instance_id()
	var building_id := pilot.get_node("GeneratedPreview/Building").get_instance_id()
	var terrain_id := pilot.get_node("GeneratedPreview/Terrain").get_instance_id()

	soil.enabled = true
	soil.position = Vector3(-5.0, 9.0, 6.0)
	soil.rotation.y = deg_to_rad(28.0)
	soil.scale = Vector3(1.25, 1.0, 0.8)
	soil.size = Vector2(11.0, 7.0)
	soil.blend_width = 1.7
	soil.opacity = 0.63
	soil.priority = 20
	sand.enabled = true
	sand.position = Vector3(-1.0, -4.0, 4.0)
	sand.size = Vector2(9.0, 8.0)
	sand.blend_width = 0.75
	sand.opacity = 0.82
	sand.priority = 10
	pilot.call("_detect_authored_changes")
	await process_frame
	_expect(pilot.get_node("GeneratedPreview/Terrain").get_instance_id() != terrain_id and
		pilot.get_node("GeneratedPreview/Road").get_instance_id() == road_id and
		pilot.get_node("GeneratedPreview/Bridge").get_instance_id() == bridge_id and
		pilot.get_node("GeneratedPreview/Building").get_instance_id() == building_id,
		"ground edits refresh Terrain only and preserve unrelated generated geometry")

	var soil_mesh := pilot.get_node(
		"GeneratedPreview/Terrain/GroundRegion_SoilArea") as MeshInstance3D
	var sand_mesh := pilot.get_node(
		"GeneratedPreview/Terrain/GroundRegion_SandArea") as MeshInstance3D
	var soil_material := soil_mesh.material_override as ShaderMaterial
	var sand_material := sand_mesh.material_override as ShaderMaterial
	var soil_local: Transform2D = soil.projected_world_to_local()
	_expect(soil_material != null and sand_material != null and
		soil_material.get_shader_parameter("region_half_size") == soil.size * 0.5 and
		is_equal_approx(float(soil_material.get_shader_parameter(
			"region_blend_width")), soil.blend_width) and
		is_equal_approx(float(soil_material.get_shader_parameter(
			"region_opacity")), soil.opacity) and
		soil_local * Vector2(soil.global_position.x, soil.global_position.z) == Vector2.ZERO,
		"region transform, full size, soft edge, and opacity reach the overlay material")
	_expect(sand_material.render_priority == -128 and
		soil_material.render_priority == -127,
		"lower Priority draws first and scene order resolves equal priorities")
	_expect(soil_mesh.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF and
		soil_mesh.get_aabb().size.x > 1.0 and soil_mesh.get_aabb().size.z > 1.0,
		"ground overlays follow terrain cells and cast no shadows")

	var duplicate := soil.duplicate() as Node3D
	duplicate.name = "SoilCopy"
	duplicate.position += Vector3(13.0, 0.0, 0.0)
	regions.add_child(duplicate)
	duplicate.owner = pilot
	await process_frame
	_expect(duplicate.surface != soil.surface and
		duplicate.surface.source_material != soil.surface.source_material,
		"duplicating a region immediately owns an independent local surface")
	duplicate.set("texture", MapAuthoringTexturePresets.SAND)
	duplicate.set("texture_rotation", 37.0)
	_expect(soil.surface.texture_preset == MapAuthoringTexturePresets.SOIL,
		"editing the duplicate surface leaves its source region unchanged")

	var packed := PackedScene.new()
	_expect(packed.pack(pilot) == OK and ResourceSaver.save(packed, RELOAD_PATH) == OK,
		"ground regions and their local surfaces can be saved")
	var saved_text := FileAccess.get_file_as_string(RELOAD_PATH)
	_expect(not saved_text.contains("\ntexture =") and
		not saved_text.contains("\ntexture_rotation ="),
		"top-level Texture proxies are not serialized beside the Surface")
	var reopened_scene := ResourceLoader.load(RELOAD_PATH, "PackedScene",
		ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	var reopened := reopened_scene.instantiate()
	root.add_child(reopened)
	await process_frame
	await process_frame
	var reopened_soil := reopened.get_node("AuthoredControls/Ground/Regions/SoilArea")
	var reopened_copy := reopened.get_node("AuthoredControls/Ground/Regions/SoilCopy")
	_expect(reopened_soil.enabled and reopened_copy.enabled and
		reopened_soil.surface.texture_preset == MapAuthoringTexturePresets.SOIL and
		reopened_copy.surface.texture_preset == MapAuthoringTexturePresets.SAND and
		is_equal_approx(reopened_copy.surface.rotation_degrees, 37.0) and
		reopened_soil.surface != reopened_copy.surface and
		reopened_soil.surface.source_material != reopened_copy.surface.source_material,
		"enabled regions and duplicate-local materials survive save and reopen")
	reopened.queue_free()

	pilot.export_directory = EXPORT_AFTER
	pilot.export_contract()
	_expect(pilot.server_grid() == baseline_grid and
		FileAccess.get_file_as_bytes(EXPORT_AFTER + "/collision.bin") == baseline_collision and
		FileAccess.get_file_as_string(EXPORT_AFTER + "/world.json") == baseline_manifest,
		"active ground patches do not change collision or exported world data")

	print("map authoring ground regions: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	pilot.queue_free()
	_cleanup(RELOAD_PATH)
	_cleanup(EXPORT_BEFORE + "/collision.bin")
	_cleanup(EXPORT_BEFORE + "/world.json")
	_cleanup(EXPORT_BEFORE)
	_cleanup(EXPORT_AFTER + "/collision.bin")
	_cleanup(EXPORT_AFTER + "/world.json")
	_cleanup(EXPORT_AFTER)
	quit(_failures)


func _region_meshes(pilot: Node) -> Array[Node]:
	var result: Array[Node] = []
	for child in pilot.get_node("GeneratedPreview/Terrain").get_children():
		if String(child.name).begins_with("GroundRegion_"):
			result.append(child)
	return result


func _cleanup(path: String) -> void:
	DirAccess.remove_absolute(ProjectSettings.globalize_path(path))


func _expect(condition: bool, message: String) -> bool:
	if condition:
		print("PASS: ", message)
		return true
	_failures += 1
	push_error("FAIL: " + message)
	return false
