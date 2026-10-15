extends SceneTree

const TEMP_ROOT := "res://pilot"
const SURFACE_PATH := TEMP_ROOT + "/.object-surface-test.tres"
const SurfaceClass := preload(
	"res://src/dev/map_authoring_pilot/style/map_authoring_surface.gd")

var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_prepare_temp_root()
	_test_named_ground_presets()
	_test_factory_ownership_and_zero_passthrough()
	_test_preset_switch_and_undo()
	_test_road_rotation_and_direct_source_edits()
	_test_advanced_material_persistence()
	_cleanup()
	print("map authoring object surface: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)


func _test_named_ground_presets() -> void:
	_expect(MapAuthoringTexturePresets.SOIL in MapAuthoringTexturePresets.PRESET_NAMES and
		MapAuthoringTexturePresets.SAND in MapAuthoringTexturePresets.PRESET_NAMES and
		MapAuthoringTexturePresets.DESERT in MapAuthoringTexturePresets.PRESET_NAMES,
		"Soil, Sand, and Desert are named texture choices")
	var grass := MapAuthoringTexturePresets.create_material(
		MapAuthoringTexturePresets.GRASS) as ORMMaterial3D
	var soil := MapAuthoringTexturePresets.create_material(
		MapAuthoringTexturePresets.SOIL) as ORMMaterial3D
	var sand := MapAuthoringTexturePresets.create_material(
		MapAuthoringTexturePresets.SAND) as ORMMaterial3D
	var desert := MapAuthoringTexturePresets.create_material(
		MapAuthoringTexturePresets.DESERT) as ORMMaterial3D
	_expect(soil != null and sand != null and soil != sand,
		"Soil and Sand each create a fresh material")
	_expect(soil.albedo_texture == grass.albedo_texture and
		sand.albedo_texture == grass.albedo_texture,
		"new ground choices reuse the licensed ground texture maps")
	_expect(soil.albedo_color != sand.albedo_color and
		soil.albedo_color.get_luminance() < sand.albedo_color.get_luminance(),
		"Soil is deliberately brown and Sand is deliberately lighter")
	_expect(desert != null and desert.albedo_texture != grass.albedo_texture and
		desert.normal_texture == grass.normal_texture and
		desert.orm_texture == grass.orm_texture,
		"Desert uses its authored albedo with the neutral ground detail maps")


func _test_factory_ownership_and_zero_passthrough() -> void:
	var first := SurfaceClass.from_preset(MapAuthoringTexturePresets.TIMBER)
	var second := SurfaceClass.from_preset(MapAuthoringTexturePresets.TIMBER)
	_expect(first.resource_local_to_scene and second.resource_local_to_scene,
		"object surfaces are local to their owning scene")
	_expect(first.source_material != null and
		first.source_material != second.source_material,
		"preset factories give different objects independent source materials")
	_expect(first.get_material() == first.source_material,
		"zero rotation returns the exact authored source")
	var first_base := first.source_material as BaseMaterial3D
	var second_base := second.source_material as BaseMaterial3D
	first_base.albedo_color = Color(0.21, 0.33, 0.47, 1.0)
	_expect(second_base.albedo_color != first_base.albedo_color,
		"editing one object's material does not edit another object")

	var authored := StandardMaterial3D.new()
	authored.albedo_color = Color(0.17, 0.29, 0.41, 0.73)
	authored.emission_enabled = true
	authored.emission = Color(0.8, 0.2, 0.1)
	var copied := SurfaceClass.from_material(
		authored, MapAuthoringTexturePresets.TIMBER)
	var copied_base := copied.source_material as StandardMaterial3D
	_expect(copied.texture_preset == MapAuthoringTexturePresets.TIMBER and
		copied_base != authored and copied_base.albedo_color == authored.albedo_color and
		copied_base.emission_enabled and copied_base.emission == authored.emission,
		"from_material keeps the label and deep-copies the exact advanced source")


func _test_preset_switch_and_undo() -> void:
	var surface := SurfaceClass.from_preset(
		MapAuthoringTexturePresets.TIMBER)
	surface.rotation_degrees = 28.0
	var timber := surface.source_material as BaseMaterial3D
	timber.normal_scale = 0.37
	surface.texture_preset = MapAuthoringTexturePresets.STONE
	var stone := surface.source_material
	surface.texture_preset = MapAuthoringTexturePresets.TIMBER
	_expect(surface.source_material == timber and
		is_equal_approx((surface.source_material as BaseMaterial3D).normal_scale, 0.37),
		"switching back restores the object's hand-adjusted preset material")

	var undo := UndoRedo.new()
	undo.create_action("Change object texture")
	undo.add_do_property(surface, "texture_preset", MapAuthoringTexturePresets.STONE)
	undo.add_undo_property(surface, "texture_preset", MapAuthoringTexturePresets.TIMBER)
	undo.commit_action()
	_expect(surface.source_material == stone,
		"redo selects the cached Stone material")
	undo.undo()
	_expect(surface.source_material == timber and
		is_equal_approx(surface.rotation_degrees, 28.0),
		"texture undo restores Timber without changing its rotation")


func _test_road_rotation_and_direct_source_edits() -> void:
	var road := SurfaceClass.from_preset(
		MapAuthoringTexturePresets.WORN_EARTH, true)
	road.rotation_degrees = 17.0
	var duplicated := road.duplicate(true)
	var duplicated_oriented := duplicated.get_material(8.0) as ShaderMaterial
	_expect(duplicated != road and duplicated.source_material != road.source_material and
		duplicated.material_mode == SurfaceClass.MaterialMode.ROAD_SHADER and
		is_equal_approx(duplicated.rotation_degrees, 17.0) and
		is_equal_approx(rad_to_deg(float(duplicated_oriented.get_shader_parameter(
			"texture_rotation_radians"))), 25.0),
		"a deep-copied road surface keeps an independent source, mode, and rotation")
	var source := road.source_material as ShaderMaterial
	var first := road.get_material(8.0) as ShaderMaterial
	_expect(road.material_mode == SurfaceClass.MaterialMode.ROAD_SHADER and
		first != source and is_equal_approx(rad_to_deg(float(
		first.get_shader_parameter("texture_rotation_radians"))), 25.0),
		"road mode composes object and extra rotation")
	_expect(first.get_shader_parameter("edge_feather") ==
		source.get_shader_parameter("edge_feather"),
		"road derivatives preserve the UV2 edge feather parameter")
	var signature_before := road.signature()
	source.set_shader_parameter("edge_feather", 0.31)
	var second := road.get_material(8.0) as ShaderMaterial
	var signature_after := road.signature()
	_expect(second != first and is_equal_approx(float(
		second.get_shader_parameter("edge_feather")), 0.31),
		"direct shader uniform edits invalidate the oriented cache")
	_expect(signature_after != signature_before,
		"the public signature reports direct source edits")


func _test_advanced_material_persistence() -> void:
	var authored := StandardMaterial3D.new()
	authored.albedo_color = Color(0.12, 0.24, 0.36, 0.64)
	authored.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	authored.emission_enabled = true
	authored.emission = Color(0.7, 0.3, 0.1)
	var surface := SurfaceClass.from_material(
		authored, MapAuthoringTexturePresets.TIMBER, true)
	# Non-default saved mode and label make the load-order contract explicit;
	# from_material must still preserve this hand-authored source exactly.
	surface.rotation_degrees = 41.0
	surface.show_advanced_materials = true
	# Exercise the nonzero lookup before saving. This advanced source fails closed,
	# while all private backend state must stay out of the resource file.
	surface.get_material()
	_expect(ResourceSaver.save(surface, SURFACE_PATH) == OK,
		"an object surface saves")
	var saved_text := FileAccess.get_file_as_string(SURFACE_PATH)
	var mode_position := saved_text.find("material_mode")
	var preset_position := saved_text.find("texture_preset")
	var source_position := saved_text.find("source_material")
	_expect(mode_position >= 0 and preset_position > mode_position and
		source_position > preset_position,
		"mode and preset serialize before the advanced source material")
	_expect(saved_text.find("oriented_pbr.gdshader") < 0,
		"private oriented backend state is absent from the saved resource")
	var reopened := ResourceLoader.load(
		SURFACE_PATH, "Resource", ResourceLoader.CACHE_MODE_IGNORE)
	var reopened_source := reopened.source_material as StandardMaterial3D
	_expect(reopened != null and reopened.texture_preset ==
		MapAuthoringTexturePresets.TIMBER and reopened.show_advanced_materials and
		reopened.material_mode == SurfaceClass.MaterialMode.ROAD_SHADER and
		is_equal_approx(reopened.rotation_degrees, 41.0),
		"surface choices and rotation survive reload")
	_expect(reopened_source != null and reopened_source.transparency ==
		BaseMaterial3D.TRANSPARENCY_ALPHA and reopened_source.emission_enabled and
		reopened_source.emission == authored.emission,
		"advanced source features survive reload without factory replacement")


func _cleanup() -> void:
	if FileAccess.file_exists(SURFACE_PATH):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(SURFACE_PATH))


func _prepare_temp_root() -> void:
	var absolute := ProjectSettings.globalize_path(TEMP_ROOT)
	if not DirAccess.dir_exists_absolute(absolute):
		DirAccess.make_dir_recursive_absolute(absolute)


func _expect(condition: bool, message: String) -> bool:
	if condition:
		print("PASS: ", message)
		return true
	_failures += 1
	push_error("FAIL: " + message)
	return false
