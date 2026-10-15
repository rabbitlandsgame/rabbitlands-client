extends SceneTree

const PILOT := preload("res://src/dev/map_authoring_pilot/map_authoring_pilot.tscn")
const TEMP_ROOT := "res://pilot"
const CUSTOM_STYLE_PATH := TEMP_ROOT + "/.texture-preset-smoke-custom.tres"
const ADVANCED_STYLE_PATH := TEMP_ROOT + "/.texture-preset-smoke-advanced.tres"

var _failures := 0
var _made_temp_root := false


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_prepare_temp_root()
	_test_every_preset_resolves()

	var pilot: Node = PILOT.instantiate()
	root.add_child(pilot)
	await process_frame
	await process_frame
	var shared_style := pilot.visual_style as MapAuthoringVisualStyle
	var style := shared_style.duplicate(true) as MapAuthoringVisualStyle
	pilot.visual_style = style

	_test_property_visibility(style)
	_test_slot_isolation(style, shared_style)
	_test_road_shader_survives_swaps(style)
	await _test_generated_consumers(pilot, style)
	await _test_custom_save_and_reopen(pilot, style)
	_test_advanced_edit_save_and_reopen(style)

	pilot.queue_free()
	_cleanup_temp_resources()
	print("map authoring texture presets: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)


func _test_every_preset_resolves() -> void:
	for preset: String in MapAuthoringTexturePresets.PRESET_NAMES:
		if preset == MapAuthoringTexturePresets.CUSTOM:
			continue
		var material := MapAuthoringTexturePresets.create_material(preset)
		if preset == MapAuthoringTexturePresets.SLATE:
			_expect(material is StandardMaterial3D and
				(material as BaseMaterial3D).albedo_texture == null,
				"Slate resolves the established solid material")
		else:
			_expect(material is BaseMaterial3D and _base_texture_triple_is_loaded(material),
				"%s resolves a complete PBR texture triple" % preset)
		var second := MapAuthoringTexturePresets.create_material(preset)
		_expect(second != material,
			"%s creates an independent material instance" % preset)
		var road := MapAuthoringTexturePresets.create_road_material(preset)
		_expect(road is ShaderMaterial and _road_texture_triple_is_loaded(road),
			"%s resolves a complete road texture triple" % preset)
		_expect(is_equal_approx(float(road.get_shader_parameter("texture_scale")) * 0.24,
			(material as BaseMaterial3D).uv1_scale.x),
			"%s keeps the same world texture density on roads and solid meshes" % preset)


func _test_property_visibility(style: MapAuthoringVisualStyle) -> void:
	style.terrain_texture = MapAuthoringTexturePresets.GRASS
	style.road_texture = MapAuthoringTexturePresets.WORN_EARTH
	style.woodwork_texture = MapAuthoringTexturePresets.TIMBER
	style.stonework_texture = MapAuthoringTexturePresets.STONE
	style.roof_texture = MapAuthoringTexturePresets.SLATE
	style.show_advanced_materials = false
	for property_name: StringName in [&"terrain_material", &"worn_path_material",
			&"timber_material", &"stone_material", &"slate_material", &"water_material"]:
		var usage := _property_usage(style, property_name)
		_expect((usage & PROPERTY_USAGE_STORAGE) != 0 and
			(usage & PROPERTY_USAGE_EDITOR) == 0,
			"%s stays stored while hidden by the simple preset view" % property_name)
	style.terrain_texture = MapAuthoringTexturePresets.CUSTOM
	_expect((_property_usage(style, &"terrain_material") & PROPERTY_USAGE_EDITOR) != 0,
		"choosing Custom exposes that slot's material")
	style.show_advanced_materials = true
	_expect((_property_usage(style, &"water_material") & PROPERTY_USAGE_EDITOR) != 0,
		"Advanced Materials exposes the remaining material editor fields")
	style.show_advanced_materials = false


func _test_slot_isolation(style: MapAuthoringVisualStyle,
		shared_style: MapAuthoringVisualStyle) -> void:
	var custom := StandardMaterial3D.new()
	custom.albedo_color = Color(0.17, 0.29, 0.41, 1.0)
	style.terrain_texture = MapAuthoringTexturePresets.CUSTOM
	style.terrain_material = custom
	var road_before := style.worn_path_material
	var timber_before := style.timber_material
	var stone_before := style.stone_material
	var slate_before := style.slate_material
	var shared_terrain_before := shared_style.terrain_material
	style.terrain_texture = MapAuthoringTexturePresets.GRASS
	_expect(style.terrain_material != custom and style.terrain_material is BaseMaterial3D,
		"a terrain preset replaces only the terrain material with its expected type")
	var grass := style.terrain_material as BaseMaterial3D
	grass.normal_scale = 0.31
	_expect(style.worn_path_material == road_before and style.timber_material == timber_before and
		style.stone_material == stone_before and style.slate_material == slate_before,
		"a terrain selection leaves every other style slot unchanged")
	_expect(custom.albedo_color == Color(0.17, 0.29, 0.41, 1.0),
		"replacing a slot does not mutate its former custom resource")
	style.terrain_texture = MapAuthoringTexturePresets.CUSTOM
	_expect(style.terrain_material == custom,
		"returning a selector to Custom recovers its prior custom resource")
	style.terrain_texture = MapAuthoringTexturePresets.GRASS
	_expect(style.terrain_material == grass and
		is_equal_approx((style.terrain_material as BaseMaterial3D).normal_scale, 0.31),
		"returning to a preset recovers its unsaved advanced tweaks for Inspector undo")
	_expect(shared_style.terrain_material == shared_terrain_before,
		"editing a personal style does not mutate the shared style template")


func _test_road_shader_survives_swaps(style: MapAuthoringVisualStyle) -> void:
	style.road_texture = MapAuthoringTexturePresets.WORN_EARTH
	var first := style.worn_path_material as ShaderMaterial
	var shader := first.shader
	var edge_feather: Variant = first.get_shader_parameter("edge_feather")
	style.road_texture = MapAuthoringTexturePresets.SLATE
	var swapped := style.worn_path_material as ShaderMaterial
	_expect(swapped != first and swapped.shader == shader,
		"road texture swaps retain the feathered road shader")
	_expect(is_equal_approx(float(swapped.get_shader_parameter("edge_feather")),
		float(edge_feather)), "road texture swaps retain the edge feather parameter")
	style.road_texture = MapAuthoringTexturePresets.SLATE
	_expect(style.worn_path_material == swapped,
		"reassigning the selected texture is a no-op that preserves advanced tweaks")


func _test_generated_consumers(pilot: Node,
		style: MapAuthoringVisualStyle) -> void:
	var ground := pilot.get_node("AuthoredControls/Ground")
	var road := pilot.get_node("AuthoredControls/Road")
	var building := pilot.get_node("AuthoredControls/Building")
	var rock := pilot.get_node("AuthoredScenery/ShoreRockWest")
	style.terrain_texture = MapAuthoringTexturePresets.CAVERN
	style.road_texture = MapAuthoringTexturePresets.LEATHER
	style.woodwork_texture = MapAuthoringTexturePresets.CANVAS
	style.stonework_texture = MapAuthoringTexturePresets.CRYSTAL
	style.roof_texture = MapAuthoringTexturePresets.THATCH
	pilot.refresh_all()
	await process_frame
	_expect(_mesh_material(pilot, "GeneratedPreview/Terrain/TerrainMesh") ==
		ground.base_surface.get_material(), "terrain keeps its explicit local surface")
	_expect(_mesh_material(pilot, "GeneratedPreview/Road/RoadSurface") ==
		road.surface.get_material(), "road keeps its explicit local surface")
	_expect(_mesh_material(pilot, "GeneratedPreview/Building/BackWall") ==
		building.wall_surface.get_material(), "cabin walls keep their explicit local surface")
	_expect(_mesh_material(pilot, "GeneratedPreview/Building/Roof") ==
		building.roof_surface.get_material(), "cabin roof keeps its explicit local surface")
	_expect(_mesh_material(pilot, "AuthoredScenery/ShoreRockWest") ==
		rock.surface.get_material(), "saved stone scenery keeps its explicit local surface")


func _test_custom_save_and_reopen(pilot: Node,
		style: MapAuthoringVisualStyle) -> void:
	style.terrain_texture = MapAuthoringTexturePresets.CUSTOM
	var custom := style.terrain_material.duplicate() as BaseMaterial3D
	var custom_tint := Color(0.33, 0.24, 0.57, 1.0)
	custom.albedo_color = custom_tint
	style.terrain_material = custom
	pilot.refresh_all()
	await process_frame
	_expect(_mesh_material(pilot, "GeneratedPreview/Terrain/TerrainMesh") != custom,
		"a legacy Custom material does not replace explicit local terrain")
	_expect(ResourceSaver.save(style, CUSTOM_STYLE_PATH) == OK,
		"a style with a Custom slot can be saved")
	var reopened := ResourceLoader.load(CUSTOM_STYLE_PATH, "Resource",
		ResourceLoader.CACHE_MODE_IGNORE) as MapAuthoringVisualStyle
	_expect(reopened != null and reopened.terrain_texture ==
		MapAuthoringTexturePresets.CUSTOM and reopened.terrain_material is BaseMaterial3D,
		"a Custom selection and material survive reopen")
	_expect(reopened != null and (reopened.terrain_material as BaseMaterial3D).albedo_color ==
		custom_tint, "Custom material parameters survive reopen")


func _test_advanced_edit_save_and_reopen(style: MapAuthoringVisualStyle) -> void:
	style.terrain_texture = MapAuthoringTexturePresets.GRASS
	style.show_advanced_materials = true
	var material := style.terrain_material as BaseMaterial3D
	var edited_tint := Color(0.62, 0.71, 0.49, 1.0)
	material.albedo_color = edited_tint
	material.normal_scale = 0.37
	_expect(ResourceSaver.save(style, ADVANCED_STYLE_PATH) == OK,
		"advanced edits on a selected preset can be saved")
	var reopened := ResourceLoader.load(ADVANCED_STYLE_PATH, "Resource",
		ResourceLoader.CACHE_MODE_IGNORE) as MapAuthoringVisualStyle
	var reopened_material := reopened.terrain_material as BaseMaterial3D if reopened != null else null
	_expect(reopened != null and reopened.terrain_texture == MapAuthoringTexturePresets.GRASS,
		"the selected preset survives reopen after advanced edits")
	_expect(reopened_material != null and reopened_material.albedo_color.is_equal_approx(edited_tint) and
		is_equal_approx(reopened_material.normal_scale, 0.37),
		"reopen does not reapply the factory over saved advanced tweaks")


func _base_texture_triple_is_loaded(material: Material) -> bool:
	if not material is ORMMaterial3D:
		return false
	var base := material as ORMMaterial3D
	return (base.albedo_texture != null and base.normal_texture != null and
		base.orm_texture != null)


func _road_texture_triple_is_loaded(material: Material) -> bool:
	if not material is ShaderMaterial:
		return false
	var road := material as ShaderMaterial
	return (road.get_shader_parameter("ground_albedo") is Texture2D and
		road.get_shader_parameter("ground_normal") is Texture2D and
		road.get_shader_parameter("ground_orm") is Texture2D)


func _property_usage(resource: Resource, property_name: StringName) -> int:
	for property: Dictionary in resource.get_property_list():
		if StringName(property["name"]) == property_name:
			return int(property["usage"])
	return 0


func _mesh_material(parent: Node, path: NodePath) -> Material:
	var mesh := parent.get_node_or_null(path) as MeshInstance3D
	return mesh.material_override if mesh != null else null


func _prepare_temp_root() -> void:
	_cleanup_temp_resources()
	var absolute_root := ProjectSettings.globalize_path(TEMP_ROOT)
	if not DirAccess.dir_exists_absolute(absolute_root):
		_made_temp_root = DirAccess.make_dir_recursive_absolute(absolute_root) == OK


func _cleanup_temp_resources() -> void:
	for path in [CUSTOM_STYLE_PATH, ADVANCED_STYLE_PATH]:
		var absolute_path := ProjectSettings.globalize_path(path)
		if FileAccess.file_exists(path):
			DirAccess.remove_absolute(absolute_path)
	if _made_temp_root:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(TEMP_ROOT))


func _expect(condition: bool, message: String) -> bool:
	if condition:
		print("PASS: ", message)
		return true
	_failures += 1
	push_error("FAIL: " + message)
	return false
