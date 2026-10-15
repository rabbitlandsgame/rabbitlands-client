extends SceneTree

const PILOT := preload("res://src/dev/map_authoring_pilot/map_authoring_pilot.tscn")
const RELOAD_PATH := "res://src/dev/map_authoring_pilot/.object-materials-reload.tscn"

var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var pilot := PILOT.instantiate()
	root.add_child(pilot)
	await process_frame
	await process_frame

	var bridges := pilot.get_node("AuthoredControls/Bridges") as Node3D
	var first := bridges.get_node("Bridge")
	first.width = 2.25
	first.deck_texture_rotation_degrees = 7.0
	first.deck_surface.texture_preset = MapAuthoringTexturePresets.SOIL
	first.deck_surface.rotation_degrees = 11.0
	var second := first.duplicate() as Node3D
	second.name = "SandBridge"
	second.position.z = 8.0
	second.width = 5.0
	bridges.add_child(second)
	_set_owner_tree(second, pilot)
	await process_frame
	second.deck_surface.texture_preset = MapAuthoringTexturePresets.SAND
	second.deck_surface.rotation_degrees = -23.0
	second.deck_texture_rotation_degrees = 5.0
	pilot.refresh_all()
	await process_frame
	var first_deck := _mesh(pilot, "GeneratedPreview/Bridge/Bridge/BridgeDeck")
	var second_deck := _mesh(pilot, "GeneratedPreview/Bridge/SandBridge/BridgeDeck")
	_expect(first.deck_surface != second.deck_surface and
		first.deck_surface.source_material != second.deck_surface.source_material,
		"a live duplicated bridge owns independent surface and source resources")
	_expect(first_deck.material_override != second_deck.material_override and
		is_equal_approx(first_deck.get_aabb().size.z, 2.25) and
		is_equal_approx(second_deck.get_aabb().size.z, 5.0),
		"two bridges generate independent textures, angles, and widths")
	var second_geometry := second_deck.get_aabb()
	var second_material := second_deck.material_override
	first.deck_surface.texture_preset = MapAuthoringTexturePresets.METAL
	pilot.call("_detect_authored_changes")
	await process_frame
	second_deck = _mesh(pilot, "GeneratedPreview/Bridge/SandBridge/BridgeDeck")
	_expect(second.deck_surface.texture_preset == MapAuthoringTexturePresets.SAND and
		second_deck.material_override == second_material and
		second_deck.get_aabb() == second_geometry,
		"editing one bridge surface leaves the other bridge unchanged")

	var road := pilot.get_node("AuthoredControls/Road")
	road.surface = MapAuthoringSurface.from_preset(MapAuthoringTexturePresets.SAND, true)
	road.call("sync_surface_binding")
	pilot.refresh_all()
	await process_frame
	var road_material := _mesh(pilot, "GeneratedPreview/Road/RoadSurface").material_override \
		as ShaderMaterial
	_expect(road_material != null and
		float(road_material.get_shader_parameter("edge_feather")) > 0.0,
		"a local road texture keeps the feathered road shader")
	var ground := pilot.get_node("AuthoredControls/Ground")
	var bridge_node_id := _mesh(pilot,
		"GeneratedPreview/Bridge/Bridge/BridgeDeck").get_instance_id()
	ground.base_surface.texture_preset = MapAuthoringTexturePresets.SOIL
	pilot.call("_detect_authored_changes")
	await process_frame
	_expect(_mesh(pilot, "GeneratedPreview/Bridge/Bridge/BridgeDeck").get_instance_id() ==
		bridge_node_id,
		"changing only the ground surface leaves unrelated bridge geometry intact")

	var building := pilot.get_node("AuthoredControls/Building")
	building.wall_surface.texture_preset = MapAuthoringTexturePresets.CANVAS
	building.roof_surface.texture_preset = MapAuthoringTexturePresets.METAL
	pilot.call("_detect_authored_changes")
	await process_frame
	_expect(_mesh(pilot, "GeneratedPreview/Building/BackWall").material_override ==
		building.wall_surface.get_material() and
		_mesh(pilot, "GeneratedPreview/Building/Roof").material_override ==
		building.roof_surface.get_material() and
		building.wall_surface != building.roof_surface,
		"building walls and roof use independent local surfaces")

	var west := _mesh(pilot, "AuthoredScenery/ShoreRockWest")
	var east := _mesh(pilot, "AuthoredScenery/ShoreRockEast")
	var needles := _mesh(pilot, "AuthoredScenery/WindPine/LowerNeedles")
	var glass := _mesh(pilot, "AuthoredScenery/CabinLantern/Glass")
	var needles_before := (needles.material_override as BaseMaterial3D).albedo_color
	var glass_before := (glass.material_override as BaseMaterial3D).emission
	west.surface.texture_preset = MapAuthoringTexturePresets.SOIL
	east.surface.texture_preset = MapAuthoringTexturePresets.SAND
	await _wait_frames(14)
	_expect(west.surface != east.surface and
		west.material_override != east.material_override,
		"the two saved rocks can use different local textures")
	_expect((needles.material_override as BaseMaterial3D).albedo_color == needles_before and
		(glass.material_override as BaseMaterial3D).emission == glass_before,
		"unrelated foliage and lantern glow retain their exact custom defaults")

	west.surface.rotation_degrees = 31.0
	await _wait_frames(14)
	var packed := PackedScene.new()
	_expect(packed.pack(pilot) == OK and ResourceSaver.save(packed, RELOAD_PATH) == OK,
		"local object surfaces can be saved")
	var saved_text := FileAccess.get_file_as_string(RELOAD_PATH)
	_expect("material_override =" not in saved_text,
		"runtime-derived object materials are not serialized beside their surfaces")
	var reopened_scene := ResourceLoader.load(RELOAD_PATH, "PackedScene",
		ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	var reopened := reopened_scene.instantiate()
	root.add_child(reopened)
	await process_frame
	await process_frame
	var reopened_first := reopened.get_node("AuthoredControls/Bridges/Bridge")
	var reopened_second := reopened.get_node("AuthoredControls/Bridges/SandBridge")
	var reopened_west := reopened.get_node("AuthoredScenery/ShoreRockWest")
	var reopened_east := reopened.get_node("AuthoredScenery/ShoreRockEast")
	_expect(reopened_first.deck_surface.texture_preset == MapAuthoringTexturePresets.METAL and
		reopened_second.deck_surface.texture_preset == MapAuthoringTexturePresets.SAND and
		reopened_first.deck_surface != reopened_second.deck_surface,
		"bridge-local texture choices survive save and reopen independently")
	_expect(reopened_west.surface.texture_preset == MapAuthoringTexturePresets.SOIL and
		reopened_east.surface.texture_preset == MapAuthoringTexturePresets.SAND and
		reopened_west.surface != reopened_east.surface,
		"scenery-local texture choices survive save and reopen independently")
	reopened.queue_free()
	DirAccess.remove_absolute(ProjectSettings.globalize_path(RELOAD_PATH))

	print("map authoring object materials: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	pilot.queue_free()
	quit(_failures)


func _mesh(parent: Node, path: NodePath) -> MeshInstance3D:
	return parent.get_node(path) as MeshInstance3D


func _set_owner_tree(node: Node, scene_owner: Node) -> void:
	node.owner = scene_owner
	for child in node.get_children():
		_set_owner_tree(child, scene_owner)


func _wait_frames(count: int) -> void:
	for _index in count:
		await process_frame


func _expect(condition: bool, message: String) -> bool:
	if condition:
		print("PASS: ", message)
		return true
	_failures += 1
	push_error("FAIL: " + message)
	return false
