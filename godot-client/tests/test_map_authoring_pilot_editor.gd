extends SceneTree

const PILOT := preload("res://src/dev/map_authoring_pilot/map_authoring_pilot.tscn")


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	if not Engine.is_editor_hint():
		push_error("map authoring pilot editor preview: Engine.is_editor_hint() is false")
		quit(1)
		return
	var pilot: Node = PILOT.instantiate()
	root.add_child(pilot)
	await process_frame
	await process_frame
	var preview := pilot.get_node_or_null("GeneratedPreview")
	var terrain := pilot.get_node_or_null("GeneratedPreview/Terrain")
	var bridge := pilot.get_node_or_null("GeneratedPreview/Bridge")
	var building := pilot.get_node_or_null("GeneratedPreview/Building")
	var overlay := pilot.get_node_or_null("GeneratedPreview/Walkability")
	var water := pilot.get_node_or_null("GeneratedPreview/Water/River")
	if preview == null or terrain == null or water == null or bridge == null or \
			building == null or overlay == null:
		push_error("map authoring pilot editor preview: generated subtree is incomplete")
		quit(1)
		return
	if overlay.visible:
		push_error("map authoring pilot editor preview: overlay should start hidden")
		quit(1)
		return
	var scenery := pilot.get_node_or_null("AuthoredScenery")
	var warm_light := pilot.get_node_or_null("AuthoredScenery/CabinLantern/WarmLight")
	var styled_rock := pilot.get_node_or_null("AuthoredScenery/ShoreRockWest") as MeshInstance3D
	if scenery == null or preview.is_ancestor_of(scenery) or warm_light == null:
		push_error("map authoring pilot editor preview: saved scenery/light separation is invalid")
		quit(1)
		return
	var rock_surface := styled_rock.get("surface") as MapAuthoringSurface \
		if styled_rock != null else null
	if rock_surface == null or styled_rock.material_override != rock_surface.get_material():
		push_error("map authoring pilot editor preview: authored scenery did not receive its local surface")
		quit(1)
		return
	var road := pilot.get_node_or_null("AuthoredControls/Road") as Path3D
	var river := pilot.get_node_or_null("AuthoredControls/River") as Path3D
	var terrain_heights := pilot.get_node_or_null("AuthoredControls/TerrainHeights") as Node3D
	if road == null or river == null or terrain_heights == null or \
			terrain_heights.get_child_count() < 2 or terrain_heights.get_child_count() > 3:
		push_error("map authoring pilot editor preview: visual authored controls are incomplete")
		quit(1)
		return
	for child in terrain_heights.get_children():
		if not child is Marker3D or not child.has_method("authored_height_offset") or \
				child.get("influence_radius") == null:
			push_error("map authoring pilot editor preview: terrain height handle API is invalid")
			quit(1)
			return
	var ground_regions := pilot.get_node_or_null(
		"AuthoredControls/Ground/Regions") as Node3D
	if ground_regions == null or ground_regions.get_child_count() != 2:
		push_error("map authoring pilot editor preview: saved ground-region starters are incomplete")
		quit(1)
		return
	for region in ground_regions.get_children():
		var footprint := region.get_node_or_null(
			"__GroundRegionFootprint") as MeshInstance3D
		if footprint == null or footprint.owner != null or footprint.cast_shadow != \
				GeometryInstance3D.SHADOW_CASTING_SETTING_OFF:
			push_error("map authoring pilot editor preview: ground-region editor footprint is invalid")
			quit(1)
			return
	var soil_region := ground_regions.get_node("SoilArea")
	soil_region.set("texture", MapAuthoringTexturePresets.SAND)
	soil_region.set("texture_rotation", 19.0)
	soil_region.enabled = true
	await create_timer(0.35).timeout
	await process_frame
	if soil_region.surface.texture_preset != MapAuthoringTexturePresets.SAND or \
			not is_equal_approx(soil_region.surface.rotation_degrees, 19.0) or \
			pilot.get_node_or_null(
				"GeneratedPreview/Terrain/GroundRegion_SoilArea") == null:
		push_error("map authoring pilot editor preview: enabled region did not auto-refresh")
		quit(1)
		return
	soil_region.visible = false
	await create_timer(0.35).timeout
	await process_frame
	if pilot.get_node_or_null(
			"GeneratedPreview/Terrain/GroundRegion_SoilArea") != null:
		push_error("map authoring pilot editor preview: hidden region overlay stayed visible")
		quit(1)
		return
	var editor_interface: Object = Engine.get_singleton("EditorInterface")
	var selection: Object = editor_interface.call("get_selection")
	for action in [
		[&"edit_road_points", road],
		[&"edit_river_points", river],
		[&"edit_terrain_heights", terrain_heights.get_child(0)],
	]:
		pilot.call(action[0])
		if not selection.call("get_selected_nodes").has(action[1]):
			push_error("map authoring pilot editor preview: root visual-control action selected the wrong node")
			quit(1)
			return
	print("map authoring pilot editor preview: PASS")
	quit(0)
