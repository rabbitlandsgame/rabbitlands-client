@tool
class_name MapAuthoringPilot
extends Node3D

const _GROUND_REGION_MATERIAL := preload(
	"res://src/dev/map_authoring_pilot/style/ground_region_material.gd")

## A deliberately small, code-first map authoring example. Authored controls live
## under AuthoredControls and are saved in the scene. Everything below
## GeneratedPreview is disposable and is rebuilt from those controls.

const MAP_METRES := 48.0
const HALF_CELL := 0.5
const HALF_CELLS := 96
const SERVER_CELLS := 48
const HEIGHT_STEP := 0.2
const WALKER_SPEED := 5.0
const WATER_HALF_WIDTH := 3.0
const RIVER_SAMPLE_SPACING := 0.5
const RIVER_SAMPLE_LIMIT := 256
const RIVER_SIMPLIFY_TOLERANCE := 0.08
const GROUND_UV_SCALE := 0.24
const TIMBER_UV_SCALE := 0.5

@export_category("Terrain")
@export_range(0.0, 2.0, 0.05) var terrain_relief := 0.8
@export_range(-1.0, 3.0, 0.05) var terrain_base_height := 1.4
@export_range(-1.0, 3.0, 0.05) var water_level := 0.35

## Hidden compatibility template for older saved scenes without local surfaces.
@export_storage var visual_style: MapAuthoringVisualStyle

@export_storage var road_width := 2.5
## Legacy storage used only when an older scene has root BridgeStart/BridgeEnd
## markers and no AuthoredControls/Bridges container.
@export_storage var bridge_width := 3.0
@export_storage var bridge_arch := 0.6
@export_storage var bridge_water_clearance := 0.9

@export_category("Preview")
@export var show_walkability := false
@export_enum("All", "Terrain", "Road", "Bridge", "Building", "Walkability") var refresh_scope := "All"
@export_dir var export_directory := "user://map_authoring_pilot/export"
@export_tool_button("Refresh selected feature", "Callable") var refresh_selected_action := refresh_selected
@export_tool_button("Export EWCG + JSON", "Callable") var export_action := export_contract
@export_tool_button("Edit road points", "Curve3D") var edit_road_action := edit_road_points
@export_tool_button("Edit river points", "Curve3D") var edit_river_action := edit_river_points
@export_tool_button("Edit terrain heights", "Marker3D") var edit_terrain_action := edit_terrain_heights

@onready var authored: Node3D = get_node_or_null("AuthoredControls")
@onready var road: Path3D = get_node_or_null("AuthoredControls/Road")
@onready var river: Path3D = get_node_or_null("AuthoredControls/River")
@onready var ground_control: Node3D = get_node_or_null("AuthoredControls/Ground")
@onready var terrain_heights: Node3D = get_node_or_null("AuthoredControls/TerrainHeights")
@onready var bridges_control: Node3D = get_node_or_null("AuthoredControls/Bridges")
## Compatibility aliases for probes which address the first authored bridge.
@onready var bridge_start: Marker3D = _first_bridge_marker("Start")
@onready var bridge_end: Marker3D = _first_bridge_marker("End")
@onready var building_control: Node3D = get_node_or_null("AuthoredControls/Building")
@onready var entrance: Marker3D = get_node_or_null("AuthoredControls/Building/Entrance")
@onready var spawn_marker: Marker3D = get_node_or_null("AuthoredControls/Spawn")
@onready var authored_scenery: Node3D = get_node_or_null("AuthoredScenery")
@onready var generated: Node3D = get_node_or_null("GeneratedPreview")

var _half_grid := PackedByteArray()
var _server_grid := PackedByteArray()
var _last_signatures: Dictionary = {}
var _editor_debounce := 0.0
var _walker: MeshInstance3D
var _walker_tile := Vector2i.ZERO
var _walk_route: Array[Vector2i] = []
var _walk_route_index := 0
var _walking := false
var _status: Label
var _river_samples := PackedVector2Array()
var _river_half_widths := PackedFloat32Array()
var _bridge_cache: Array[Dictionary] = []
var _ground_regions: Array[Dictionary] = []
var _ground_region_material_cache: Dictionary = {}
var _warned_ground_region_limit := false
var _terrain_height_influences: Array[Dictionary] = []
var _terrain_height_memo: Dictionary = {}


func _ready() -> void:
	set_process(true)
	set_process_input(not Engine.is_editor_hint())
	refresh_all()
	if Engine.is_editor_hint():
		print("map authoring pilot editor preview: generated")
	if not Engine.is_editor_hint():
		_setup_runtime()


func _process(delta: float) -> void:
	if Engine.is_editor_hint():
		_editor_debounce += delta
		if _editor_debounce >= 0.18:
			_editor_debounce = 0.0
			_detect_authored_changes()
		return
	if _walking:
		_advance_walker(delta)


func refresh_selected() -> void:
	_regenerate(refresh_scope)


func refresh_all() -> void:
	_regenerate("All")


func edit_road_points() -> void:
	_cache_nodes()
	_select_authored_control(road)


func edit_river_points() -> void:
	_cache_nodes()
	_select_authored_control(river)


func edit_terrain_heights() -> void:
	_cache_nodes()
	var target: Node = terrain_heights
	if terrain_heights != null:
		for child in terrain_heights.get_children():
			if child is Marker3D:
				target = child
				break
	_select_authored_control(target)


func _select_authored_control(target: Node) -> void:
	# EditorInterface is looked up dynamically so exported/runtime builds never
	# bind an editor-only class or API.
	if not Engine.is_editor_hint() or target == null \
			or not Engine.has_singleton("EditorInterface"):
		return
	var editor_interface: Object = Engine.get_singleton("EditorInterface")
	if editor_interface == null:
		return
	var selection: Object = editor_interface.call("get_selection")
	if selection != null:
		selection.call("clear")
		selection.call("add_node", target)
	if editor_interface.has_method("edit_node"):
		editor_interface.call("edit_node", target)
	if editor_interface.has_method("set_main_screen_editor"):
		editor_interface.call("set_main_screen_editor", "3D")


func export_contract() -> void:
	_cache_nodes()
	_build_walk_grids()
	var absolute := ProjectSettings.globalize_path(export_directory)
	var error := DirAccess.make_dir_recursive_absolute(absolute)
	if error != OK:
		push_error("Map authoring pilot: cannot create export directory %s" % absolute)
		return
	var binary_path := absolute.path_join("collision.bin")
	var binary := FileAccess.open(binary_path, FileAccess.WRITE)
	if binary == null:
		push_error("Map authoring pilot: cannot write %s" % binary_path)
		return
	binary.store_buffer("EWCG".to_ascii_buffer())
	binary.store_16(2)
	binary.store_16(0)
	binary.store_32(HALF_CELLS)
	binary.store_32(HALF_CELLS)
	binary.store_buffer(_half_grid)
	binary.close()
	var document := {
		"schemaVersion": "1.0.0",
		"asset": {"id": "map-authoring-pilot", "name": "Map Authoring Pilot"},
		"coordinateTransform": {
			"metresPerTile": 1.0,
			"serverOrigin": [0, 0],
			"serverCells": [SERVER_CELLS, SERVER_CELLS],
			"origin": [-24.0, 0.0, 24.0],
			"invertServerY": true,
		},
		"collision": {
			"binary": "collision.bin",
			"format": "EWCG-v2",
			"formatVersion": 2,
			"cellSize": HALF_CELL,
			"gridAlignment": "tile-centres-v1",
			"heightEncoding": {"origin": 0.0, "step": HEIGHT_STEP},
		},
		"validation": _validation_probes(),
	}
	var json_path := absolute.path_join("world.json")
	var json_file := FileAccess.open(json_path, FileAccess.WRITE)
	if json_file == null:
		push_error("Map authoring pilot: cannot write %s" % json_path)
		return
	json_file.store_string(JSON.stringify(document, "  ") + "\n")
	json_file.close()
	_set_status("Exported collision.bin + world.json\n%s" % absolute)
	print("map authoring pilot export: ", absolute)


func server_grid() -> PackedByteArray:
	_cache_nodes()
	_build_walk_grids()
	return _server_grid.duplicate()


## Intersects a world-space ray with the actual quantized preview triangles used
## by the editor. This keeps asset placement exact at river cuts and steep banks.
func authoring_ground_intersection(ray_origin: Vector3, ray_direction: Vector3,
		max_distance: float = 2048.0) -> Variant:
	if not ray_origin.is_finite() or not ray_direction.is_finite() or \
			ray_direction.length_squared() < 0.000001 or not is_finite(max_distance) or \
			max_distance <= 0.0:
		return null
	var terrain_mesh := get_node_or_null(
		"GeneratedPreview/Terrain/TerrainMesh") as MeshInstance3D
	if terrain_mesh == null or terrain_mesh.mesh == null or \
			absf(global_transform.basis.determinant()) < 0.000001:
		return null
	var inverse := global_transform.affine_inverse()
	var start := inverse * ray_origin
	var finish := inverse * (ray_origin + ray_direction.normalized() * max_distance)
	var mesh_to_pilot := inverse * terrain_mesh.global_transform
	var faces := terrain_mesh.mesh.get_faces()
	var nearest: Variant = null
	var nearest_distance := INF
	for index in range(0, faces.size() - 2, 3):
		var hit: Variant = Geometry3D.segment_intersects_triangle(start, finish,
			mesh_to_pilot * faces[index], mesh_to_pilot * faces[index + 1],
			mesh_to_pilot * faces[index + 2])
		if hit == null:
			continue
		var distance: float = start.distance_squared_to(hit as Vector3)
		if distance < nearest_distance:
			nearest_distance = distance
			nearest = hit
	return global_transform * (nearest as Vector3) if nearest != null else null


func authored_snapshot() -> Dictionary:
	return {
		"road": _curve_signature(),
		"river": _path_signature(river),
		"ground": _ground_signature(),
		"terrain_heights": _terrain_heights_signature(),
		"bridges": _bridges_signature(),
		"bridge_start": bridge_start.transform if bridge_start else Transform3D.IDENTITY,
		"bridge_end": bridge_end.transform if bridge_end else Transform3D.IDENTITY,
		"building": _building_signature(),
		"entrance": entrance.transform if entrance else Transform3D.IDENTITY,
	}


func validation_route() -> Array[Vector2i]:
	_build_walk_grids()
	if spawn_marker == null or entrance == null:
		return []
	return _find_route(_world_to_server(spawn_marker.global_position),
		_world_to_server(entrance.global_position))


func _regenerate(scope: String) -> void:
	if not is_inside_tree():
		return
	_cache_nodes()
	_sync_authored_style()
	if generated == null:
		return
	if scope != "All" and not _last_signatures.is_empty():
		var current := _signatures()
		if current.params != _last_signatures.params or \
				current.river != _last_signatures.river or \
				current.terrain_heights != _last_signatures.terrain_heights:
			scope = "All"
		elif current.ground != _last_signatures.ground and scope != "Terrain":
			scope = "All"
		elif current.bridge != _last_signatures.bridge and scope != "Bridge":
			scope = "All"
		elif current.road != _last_signatures.road and scope not in ["Road", "Bridge"]:
			scope = "All"
		elif (current.building != _last_signatures.building or \
				current.markers != _last_signatures.markers) and scope != "Building":
			scope = "All"
	_build_walk_grids()
	if scope in ["All", "Terrain"]:
		_replace_feature("Terrain", _build_terrain)
		_replace_feature("Water", _build_water)
	if scope in ["All", "Road", "Bridge"]:
		_replace_feature("Road", _build_road)
	if scope in ["All", "Bridge"]:
		_replace_feature("Bridge", _build_bridge)
	if scope in ["All", "Building"]:
		_replace_feature("Building", _build_building)
	_replace_feature("Walkability", _build_walkability)
	_last_signatures = _signatures()
	_set_status("Preview refreshed: %s" % scope)


func _cache_nodes() -> void:
	authored = get_node_or_null("AuthoredControls")
	authored_scenery = get_node_or_null("AuthoredScenery")
	road = get_node_or_null("AuthoredControls/Road")
	river = get_node_or_null("AuthoredControls/River")
	if road != null and road.has_method("sync_curve_binding"):
		road.call("sync_curve_binding")
	if river != null and river.has_method("sync_curve_binding"):
		river.call("sync_curve_binding")
	if road != null and road.has_method("sync_surface_binding"):
		road.call("sync_surface_binding")
	if river != null and river.has_method("sync_surface_binding"):
		river.call("sync_surface_binding")
	ground_control = get_node_or_null("AuthoredControls/Ground")
	if ground_control != null and ground_control.has_method("sync_surface_binding"):
		ground_control.call("sync_surface_binding")
	terrain_heights = get_node_or_null("AuthoredControls/TerrainHeights")
	bridges_control = get_node_or_null("AuthoredControls/Bridges")
	bridge_start = _first_bridge_marker("Start")
	bridge_end = _first_bridge_marker("End")
	building_control = get_node_or_null("AuthoredControls/Building")
	if building_control != null and building_control.has_method("sync_surface_bindings"):
		building_control.call("sync_surface_bindings")
	entrance = get_node_or_null("AuthoredControls/Building/Entrance")
	spawn_marker = get_node_or_null("AuthoredControls/Spawn")
	generated = get_node_or_null("GeneratedPreview")


func _replace_feature(feature_name: String, builder: Callable) -> void:
	var old := generated.get_node_or_null(feature_name)
	if old != null:
		old.free()
	var feature := Node3D.new()
	feature.name = feature_name
	generated.add_child(feature)
	# Deliberately omit owner: generated preview children never become scene data.
	builder.call(feature)


func _detect_authored_changes() -> void:
	_cache_nodes()
	if generated == null:
		return
	var current := _signatures()
	if _last_signatures.is_empty():
		_regenerate("All")
		return
	var changed: Array[String] = []
	if current.params != _last_signatures.params:
		changed.append("All")
	if current.road != _last_signatures.road:
		changed.append("Road")
	if current.river != _last_signatures.river or \
			current.terrain_heights != _last_signatures.terrain_heights:
		changed.append("All")
	if current.ground != _last_signatures.ground:
		changed.append("Terrain")
	if current.bridge != _last_signatures.bridge:
		changed.append("Bridge")
	if current.building != _last_signatures.building or current.markers != _last_signatures.markers:
		changed.append("Building")
	if changed.is_empty():
		return
	if changed.size() > 1 or changed[0] == "All":
		_regenerate("All")
	else:
		_regenerate(changed[0])


func _signatures() -> Dictionary:
	return {
		"params": [terrain_relief, terrain_base_height, water_level, road_width,
			show_walkability, _visual_style_signature()].hash(),
		"ground": _ground_signature(),
		"road": _curve_signature(),
		"river": _path_signature(river),
		"terrain_heights": _terrain_heights_signature(),
		"bridge": _bridges_signature().hash(),
		"building": _building_signature().hash(),
		"markers": [entrance.transform if entrance else Transform3D.IDENTITY,
			spawn_marker.transform if spawn_marker else Transform3D.IDENTITY].hash(),
	}


func _ground_signature() -> Array:
	if ground_control == null:
		return []
	var result: Array = [ground_control.global_transform]
	if ground_control.has_method("surface_signature"):
		result.append(ground_control.call("surface_signature"))
	return result


func _building_signature() -> Array:
	if building_control == null:
		return []
	var result: Array = [building_control.global_transform]
	if building_control.has_method("surface_signature"):
		result.append(building_control.call("surface_signature"))
	return result


func _first_bridge_marker(marker_name: String) -> Marker3D:
	var container := get_node_or_null("AuthoredControls/Bridges") as Node3D
	if container != null:
		for candidate in container.get_children():
			if not _is_bridge_control(candidate):
				continue
			var start := candidate.get_node_or_null("Start") as Marker3D
			var end := candidate.get_node_or_null("End") as Marker3D
			if start != null and end != null:
				return start if marker_name == "Start" else end
		return null
	return get_node_or_null("AuthoredControls/Bridge%s" % marker_name) as Marker3D


func _is_bridge_control(candidate: Node) -> bool:
	return candidate is Node3D and candidate.has_method("authored_signature")


func _bridges_signature() -> Array:
	var result: Array = []
	var container := get_node_or_null("AuthoredControls/Bridges") as Node3D
	if container != null:
		result.append(container.global_transform)
		for candidate in container.get_children():
			result.append(candidate.name)
			if _is_bridge_control(candidate):
				result.append(candidate.call("authored_signature"))
			elif candidate is Node3D:
				result.append(candidate.global_transform)
				for marker_name in ["Start", "End"]:
					var marker := candidate.get_node_or_null(marker_name) as Marker3D
					result.append(marker.transform if marker else Transform3D.IDENTITY)
		return result
	var legacy_start := get_node_or_null("AuthoredControls/BridgeStart") as Marker3D
	var legacy_end := get_node_or_null("AuthoredControls/BridgeEnd") as Marker3D
	return [legacy_start.transform if legacy_start else Transform3D.IDENTITY,
		legacy_end.transform if legacy_end else Transform3D.IDENTITY,
		bridge_width, bridge_arch, bridge_water_clearance]


func _curve_signature() -> Array:
	return _path_signature(road)


func _path_signature(path: Path3D) -> Array:
	var result: Array = []
	if path == null or path.curve == null:
		return result
	result.append(path.global_transform)
	result.append(path.curve.closed)
	result.append(path.curve.bake_interval)
	for index in path.curve.point_count:
		result.append(path.curve.get_point_position(index))
		result.append(path.curve.get_point_in(index))
		result.append(path.curve.get_point_out(index))
	if path.has_method("width_signature"):
		result.append(path.call("width_signature"))
	return result


func _terrain_heights_signature() -> Array:
	var result: Array = []
	if terrain_heights == null:
		return result
	result.append(terrain_heights.global_transform)
	for child in terrain_heights.get_children():
		if child is Marker3D and child.has_method("authored_height_offset"):
			result.append(child.name)
			result.append(child.transform)
			result.append(child.get("influence_radius"))
			result.append(child.get("neutral_y"))
	return result


func _build_walk_grids() -> void:
	_refresh_authoring_caches()
	_half_grid.resize(HALF_CELLS * HALF_CELLS)
	for cell_y in HALF_CELLS:
		for cell_x in HALF_CELLS:
			var world := _half_cell_world(cell_x, cell_y)
			_half_grid[cell_y * HALF_CELLS + cell_x] = _encoded_floor(world.x, world.z)
	_server_grid.resize(SERVER_CELLS * SERVER_CELLS)
	for tile_y in SERVER_CELLS:
		for tile_x in SERVER_CELLS:
			var folded := 0
			for oy in 2:
				for ox in 2:
					var value := int(_half_grid[(tile_y * 2 + oy) * HALF_CELLS + tile_x * 2 + ox])
					if value == 0:
						folded = 0
						break
					folded = maxi(folded, value)
				if folded == 0:
					break
			_server_grid[tile_y * SERVER_CELLS + tile_x] = folded


func _encoded_floor(x: float, z: float) -> int:
	var bridge := _bridge_at(x, z)
	if not bridge.is_empty():
		return _encode_height(float(bridge.height))
	if _river_distance(Vector2(x, z)) <= WATER_HALF_WIDTH:
		return 0
	if _inside_building(x, z):
		return 0
	return _encode_height(_terrain_height(x, z))


func _encode_height(height: float) -> int:
	return clampi(roundi(height / HEIGHT_STEP), 1, 63)


func _decoded_height(value: int) -> float:
	return float(value) * HEIGHT_STEP


func _terrain_height(x: float, z: float) -> float:
	var memo_key := Vector2(x, z)
	if _terrain_height_memo.has(memo_key):
		return _terrain_height_memo[memo_key]
	var broad := 0.55 * sin(x * 0.12) * cos(z * 0.10)
	var detail := 0.25 * sin((x + z) * 0.24)
	var river_distance := _river_distance(Vector2(x, z))
	var river_bank := 0.0
	var river_cut := 0.0
	if is_finite(river_distance):
		river_bank = 0.45 * smoothstep(0.0, 7.0, river_distance)
		river_cut = 1.45 * (1.0 - smoothstep(2.6, 5.5, river_distance))
	# The bounded cut makes the water visible and leaves the bridge anchors on
	# dry banks. It is visual terrain and the source of the exported heights.
	var height := terrain_base_height + terrain_relief * (broad + detail) + river_bank - river_cut
	for influence in _terrain_height_influences:
		var distance: float = Vector2(x, z).distance_to(influence.position)
		if distance < influence.radius:
			height += influence.offset * (1.0 - smoothstep(0.0, influence.radius, distance))
	height = maxf(0.2, height)
	_terrain_height_memo[memo_key] = height
	return height


func _refresh_authoring_caches() -> void:
	_terrain_height_memo.clear()
	_refresh_river_samples()
	_refresh_bridge_cache()
	_refresh_ground_region_cache()
	_refresh_terrain_height_influences()
	if Engine.is_editor_hint():
		update_configuration_warnings()


func _refresh_ground_region_cache() -> void:
	_ground_regions.clear()
	if ground_control == null:
		return
	var regions := ground_control.get_node_or_null("Regions")
	if regions == null:
		return
	var scene_order := 0
	for candidate in regions.get_children():
		if not candidate.has_method("region_signature"):
			scene_order += 1
			continue
		if candidate.has_method("sync_surface_binding"):
			candidate.call("sync_surface_binding")
		if not bool(candidate.get("enabled")) or not candidate.is_visible_in_tree():
			scene_order += 1
			continue
		var surface := candidate.get("surface") as MapAuthoringSurface
		var world_to_local: Variant = candidate.call("projected_world_to_local")
		if surface == null or world_to_local == null:
			scene_order += 1
			continue
		_ground_regions.append({
			"instance_id": candidate.get_instance_id(),
			"name": String(candidate.name),
			"priority": int(candidate.get("priority")),
			"scene_order": scene_order,
			"surface": surface,
			"world_to_local": world_to_local,
			"half_size": Vector2(candidate.get("size")) * 0.5,
			"shape": int(candidate.get("shape")),
			"blend_width": float(candidate.get("blend_width")),
			"opacity": float(candidate.get("opacity")),
			"bounds": candidate.call("world_bounds"),
			"clip_polygon": candidate.get("clip_polygon"),
			"uv_anchor_continent_enabled": candidate.get("uv_anchor_continent_enabled"),
			"uv_anchor_continent": candidate.get("uv_anchor_continent"),
			"source_layer_ordinal": candidate.get("source_layer_ordinal"),
		})
		scene_order += 1
	_ground_regions.sort_custom(_ground_region_less)
	if _ground_regions.size() > 127 and not _warned_ground_region_limit:
		push_warning("Map authoring pilot: only the first 127 enabled ground regions are drawn; later regions are skipped.")
		_warned_ground_region_limit = true
	if _ground_regions.size() > 127:
		_ground_regions.resize(127)
	var active_ids: Dictionary = {}
	for index in _ground_regions.size():
		var region := _ground_regions[index]
		var instance_id: int = region.instance_id
		active_ids[instance_id] = true
		var render_priority := -128 + (int(region.source_layer_ordinal) if int(region.source_layer_ordinal) >= 0 else index)
		var material_signature := [region.surface.signature(), region.world_to_local,
			region.half_size, region.shape, region.blend_width, region.opacity,
			render_priority, region.clip_polygon]
		var cached: Dictionary = _ground_region_material_cache.get(instance_id, {})
		var material := cached.get("material") as ShaderMaterial
		if cached.get("signature", []) != material_signature:
			material = null
		if material == null:
			material = _GROUND_REGION_MATERIAL.create(region.surface,
				region.world_to_local, region.half_size, region.shape,
				region.blend_width, region.opacity, render_priority, region.clip_polygon)
			if material != null:
				_ground_region_material_cache[instance_id] = {
					"signature": material_signature,
					"material": material,
				}
		region["render_priority"] = render_priority
		region["material"] = material
		_ground_regions[index] = region
	for cached_id in _ground_region_material_cache.keys():
		if not active_ids.has(cached_id):
			_ground_region_material_cache.erase(cached_id)


func _ground_region_less(left: Dictionary, right: Dictionary) -> bool:
	if left.priority != right.priority:
		return int(left.priority) < int(right.priority)
	return int(left.scene_order) < int(right.scene_order)


func _refresh_river_samples() -> void:
	_river_samples.clear()
	_river_half_widths.clear()
	if river == null or river.curve == null or river.curve.point_count < 2:
		return
	var length := river.curve.get_baked_length()
	if length <= 0.001:
		return
	var count := clampi(ceili(length / RIVER_SAMPLE_SPACING) + 1, 2,
		RIVER_SAMPLE_LIMIT)
	var offsets: Array[float] = []
	for index in count:
		offsets.append(length * float(index) / float(count - 1))
	var width_stations := PackedFloat32Array()
	if river.has_method("width_sample_offsets"):
		width_stations = river.call("width_sample_offsets")
	for station in width_stations:
		if station > 0.000001 and station < length - 0.000001:
			offsets.append(station)
	offsets.sort()
	var dense := PackedVector2Array()
	var dense_widths := PackedFloat32Array()
	var dense_offsets := PackedFloat32Array()
	var anchors := PackedByteArray()
	for offset in offsets:
		if not dense_offsets.is_empty() and absf(offset - dense_offsets[-1]) <= 0.000001:
			continue
		var local := river.curve.sample_baked(offset, true)
		var world := river.global_transform * local
		dense.append(Vector2(world.x, world.z))
		dense_offsets.append(offset)
		dense_widths.append(_path_width_at(river, offset, WATER_HALF_WIDTH * 2.0) * 0.5)
		var is_anchor := false
		for station in width_stations:
			if absf(offset - station) <= 0.000001:
				is_anchor = true
				break
		anchors.append(1 if is_anchor else 0)
	var simplified := _simplify_tapered_polyline(dense, dense_widths,
		dense_offsets, anchors, RIVER_SIMPLIFY_TOLERANCE)
	_river_samples = simplified.points
	_river_half_widths = simplified.widths
	if _river_samples.size() < 2 or _polyline_length(_river_samples) <= 0.001:
		_river_samples.clear()
		_river_half_widths.clear()


func _refresh_terrain_height_influences() -> void:
	_terrain_height_influences.clear()
	if terrain_heights == null:
		return
	for child in terrain_heights.get_children():
		if not child is Marker3D or not child.has_method("authored_height_offset"):
			continue
		var radius := maxf(float(child.get("influence_radius")), 0.01)
		var neutral_y := float(child.get("neutral_y"))
		var neutral_world := terrain_heights.global_transform * Vector3(
			child.position.x, neutral_y, child.position.z)
		var offset: float = child.global_position.y - neutral_world.y
		if absf(offset) <= 0.00001:
			continue
		_terrain_height_influences.append({
			"position": Vector2(child.global_position.x, child.global_position.z),
			"offset": offset,
			"radius": radius,
		})


func _simplify_tapered_polyline(points: PackedVector2Array, widths: PackedFloat32Array,
		offsets: PackedFloat32Array, anchors: PackedByteArray,
		tolerance: float) -> Dictionary:
	if points.size() <= 2:
		return {"points": points, "widths": widths}
	var keep := PackedByteArray()
	keep.resize(points.size())
	keep[0] = 1
	keep[points.size() - 1] = 1
	var ranges: Array[Vector2i] = [Vector2i(0, points.size() - 1)]
	while not ranges.is_empty():
		var interval: Vector2i = ranges.pop_back()
		var maximum := tolerance
		var farthest := -1
		for index in interval.y:
			if index <= interval.x:
				continue
			if index >= interval.y:
				break
			if anchors[index]:
				farthest = index
				break
			var distance := _point_segment_distance(points[index], points[interval.x], points[interval.y])
			var span := maxf(offsets[interval.y] - offsets[interval.x], 0.000001)
			var fraction := clampf((offsets[index] - offsets[interval.x]) / span, 0.0, 1.0)
			var width_error := absf(widths[index] - lerpf(widths[interval.x],
				widths[interval.y], fraction))
			var score := maxf(distance / maxf(tolerance, 0.000001),
				width_error / 0.01)
			if score > maximum / maxf(tolerance, 0.000001):
				maximum = score * tolerance
				farthest = index
		if farthest >= 0:
			keep[farthest] = 1
			ranges.append(Vector2i(interval.x, farthest))
			ranges.append(Vector2i(farthest, interval.y))
	var result := PackedVector2Array()
	var result_widths := PackedFloat32Array()
	for index in points.size():
		if keep[index]:
			result.append(points[index])
			result_widths.append(widths[index])
	return {"points": result, "widths": result_widths}


func _polyline_length(points: PackedVector2Array) -> float:
	var result := 0.0
	for index in points.size() - 1:
		result += points[index].distance_to(points[index + 1])
	return result


func _polyline_point_at_fraction(points: PackedVector2Array, fraction: float) -> Vector2:
	if points.is_empty():
		return Vector2.ZERO
	if points.size() == 1:
		return points[0]
	var total := _polyline_length(points)
	if total <= 0.001:
		return points[0]
	var target := total * clampf(fraction, 0.0, 1.0)
	var travelled := 0.0
	for index in points.size() - 1:
		var segment := points[index].distance_to(points[index + 1])
		if travelled + segment >= target:
			return points[index].lerp(points[index + 1],
				(target - travelled) / maxf(segment, 0.000001))
		travelled += segment
	return points[points.size() - 1]


func _river_distance(point: Vector2) -> float:
	var sample := _river_sample(point)
	return float(sample.profile_distance) if not sample.is_empty() else INF


func _river_sample(point: Vector2) -> Dictionary:
	if _river_samples.size() < 2 or _river_half_widths.size() != _river_samples.size():
		return {}
	var result: Dictionary = {}
	var nearest_edge := INF
	for index in _river_samples.size() - 1:
		var a := _river_samples[index]
		var b := _river_samples[index + 1]
		var delta := b - a
		var length_squared := delta.length_squared()
		var t := clampf((point - a).dot(delta) /
			maxf(length_squared, 0.000001), 0.0, 1.0)
		var distance := point.distance_to(a + delta * t)
		var half_width := lerpf(_river_half_widths[index],
			_river_half_widths[index + 1], t)
		var edge_distance := distance - half_width
		if edge_distance < nearest_edge:
			nearest_edge = edge_distance
			result = {"distance": distance, "half_width": half_width,
				"profile_distance": distance + WATER_HALF_WIDTH - half_width}
	return result


func _point_segment_distance(point: Vector2, a: Vector2, b: Vector2) -> float:
	var delta := b - a
	var length_squared := delta.length_squared()
	if length_squared <= 0.000001:
		return point.distance_to(a)
	var t := clampf((point - a).dot(delta) / length_squared, 0.0, 1.0)
	return point.distance_to(a + delta * t)


func _refresh_bridge_cache() -> void:
	_bridge_cache.clear()
	if bridges_control != null:
		for candidate in bridges_control.get_children():
			if _is_bridge_control(candidate):
				_append_bridge_cache(candidate as Node3D,
					candidate.get_node_or_null("Start") as Marker3D,
					candidate.get_node_or_null("End") as Marker3D)
		return
	# Older saved scenes used two markers and global settings. The fallback is
	# deliberately disabled whenever a Bridges container exists, even if empty.
	var legacy_start := get_node_or_null("AuthoredControls/BridgeStart") as Marker3D
	var legacy_end := get_node_or_null("AuthoredControls/BridgeEnd") as Marker3D
	if legacy_start != null and legacy_end != null:
		_append_bridge_cache(null, legacy_start, legacy_end)


func _append_bridge_cache(control: Node3D, start: Marker3D, end: Marker3D) -> void:
	if start == null or end == null:
		return
	var a := Vector2(start.global_position.x, start.global_position.z)
	var b := Vector2(end.global_position.x, end.global_position.z)
	var length := a.distance_to(b)
	if length <= 0.001:
		return
	var width := bridge_width
	var arch := bridge_arch
	var clearance := bridge_water_clearance
	var deck_rotation := 0.0
	var deck_surface: MapAuthoringSurface
	var support_surface: MapAuthoringSurface
	if control != null:
		if control.has_method("sync_surface_bindings"):
			control.call("sync_surface_bindings")
		width = clampf(float(control.get("width")), 1.5, 6.0)
		arch = clampf(float(control.get("arch")), 0.0, 2.0)
		clearance = maxf(float(control.get("water_clearance")), 0.85)
		deck_rotation = float(control.get("deck_texture_rotation_degrees"))
		deck_surface = control.get("deck_surface") as MapAuthoringSurface
		support_surface = control.get("support_surface") as MapAuthoringSurface
	_bridge_cache.append({
		"name": String(control.name) if control != null else "Bridge",
		"control": control,
		"start": start,
		"end": end,
		"start_y": start.global_position.y,
		"end_y": end.global_position.y,
		"a": a,
		"b": b,
		"delta": b - a,
		"length": length,
		"width": width,
		"arch": arch,
		"clearance": clearance,
		"deck_rotation": deck_rotation,
		"deck_surface": deck_surface,
		"support_surface": support_surface,
	})


func _bridge_basis() -> Dictionary:
	if not _bridge_cache.is_empty():
		return _bridge_cache[0]
	return {"a": Vector2(-4.0, 0.0), "b": Vector2(4.0, 0.0),
		"delta": Vector2(8.0, 0.0), "length": 8.0, "width": bridge_width}


func _bridge_projection_for(bridge: Dictionary, x: float, z: float) -> Dictionary:
	var point := Vector2(x, z)
	var delta: Vector2 = bridge.delta
	var a: Vector2 = bridge.a
	var t: float = clampf((point - a).dot(delta) /
		maxf(delta.length_squared(), 0.0001), 0.0, 1.0)
	var nearest: Vector2 = a + delta * t
	return {"t": t, "distance": point.distance_to(nearest)}


func _inside_bridge(x: float, z: float) -> bool:
	return not _bridge_at(x, z).is_empty()


func _bridge_height(x: float, z: float) -> float:
	var found := _bridge_at(x, z)
	return float(found.height) if not found.is_empty() else _terrain_height(x, z)


func _bridge_height_for(bridge: Dictionary, x: float, z: float) -> float:
	var projected := _bridge_projection_for(bridge, x, z)
	var t: float = projected.t
	# Marker Y is an authored height offset above its bank, not discarded data.
	var a: Vector2 = bridge.a
	var b: Vector2 = bridge.b
	var a_height := _terrain_height(a.x, a.y) + float(bridge.start_y)
	var b_height := _terrain_height(b.x, b.y) + float(bridge.end_y)
	var plateau := 1.0
	if t < 0.3:
		plateau = smoothstep(0.0, 0.3, t)
	elif t > 0.7:
		plateau = smoothstep(1.0, 0.7, t)
	var base := lerpf(a_height, b_height, t)
	return maxf(base + float(bridge.arch) * plateau,
		water_level + float(bridge.clearance))


func _bridge_at(x: float, z: float) -> Dictionary:
	var result: Dictionary = {}
	var highest := -INF
	for bridge in _bridge_cache:
		var projected := _bridge_projection_for(bridge, x, z)
		if projected.distance > float(bridge.width) * 0.5 \
				or projected.t <= 0.0 or projected.t >= 1.0:
			continue
		var height := _bridge_height_for(bridge, x, z)
		if height > highest:
			highest = height
			result = {"bridge": bridge, "projection": projected, "height": height}
	return result


func _inside_building(x: float, z: float) -> bool:
	if building_control == null:
		return false
	var local := building_control.global_transform.affine_inverse() * Vector3(x, 0.0, z)
	if absf(local.x) > 3.5 or absf(local.z) > 2.5:
		return false
	# A thin open-front cabin: the interior and centred doorway remain walkable.
	var back_wall := local.x >= 3.0
	var side_walls := absf(local.z) >= 2.0
	var front_wall := local.x <= -3.0 and absf(local.z) >= 1.0
	return back_wall or side_walls or front_wall


func _build_terrain(parent: Node3D) -> void:
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	var step := 1.0
	for row in int(MAP_METRES):
		for column in int(MAP_METRES):
			var x0 := -MAP_METRES * 0.5 + float(column) * step
			var z0 := -MAP_METRES * 0.5 + float(row) * step
			var x1 := x0 + step
			var z1 := z0 + step
			var a := Vector3(x0, _decoded_height(_encode_height(_terrain_height(x0, z0))), z0)
			var b := Vector3(x1, _decoded_height(_encode_height(_terrain_height(x1, z0))), z0)
			var c := Vector3(x1, _decoded_height(_encode_height(_terrain_height(x1, z1))), z1)
			var d := Vector3(x0, _decoded_height(_encode_height(_terrain_height(x0, z1))), z1)
			for vertex in [a, c, b, a, d, c]:
				# Authored texture density is measured in world metres and does not
				# stretch when the terrain extent changes.
				surface.set_uv(Vector2(vertex.x, vertex.z) * GROUND_UV_SCALE)
				surface.add_vertex(vertex)
	surface.generate_normals()
	surface.generate_tangents()
	var mesh := surface.commit()
	var ground_surface: MapAuthoringSurface
	if ground_control != null and "base_surface" in ground_control:
		ground_surface = ground_control.get("base_surface") as MapAuthoringSurface
	_add_mesh(parent, "TerrainMesh", mesh, _surface_material(ground_surface,
		"terrain", Color("#648052"), 0.92))
	var body := StaticBody3D.new()
	body.name = "TerrainCollision"
	var collision := CollisionShape3D.new()
	var shape := ConcavePolygonShape3D.new()
	shape.set_faces(mesh.get_faces())
	collision.shape = shape
	body.add_child(collision)
	parent.add_child(body)
	_build_ground_region_overlays(parent)


func _build_ground_region_overlays(parent: Node3D) -> void:
	for region in _ground_regions:
		var material: ShaderMaterial = region.material
		if material == null:
			continue
		var bounds: Rect2 = region.bounds
		if not bounds.position.is_finite() or not bounds.size.is_finite() or \
				bounds.size.x <= 0.0 or bounds.size.y <= 0.0:
			continue
		var first_column := clampi(floori(bounds.position.x + MAP_METRES * 0.5),
			0, int(MAP_METRES) - 1)
		var last_column := clampi(ceili(bounds.end.x + MAP_METRES * 0.5) - 1,
			0, int(MAP_METRES) - 1)
		var first_row := clampi(floori(bounds.position.y + MAP_METRES * 0.5),
			0, int(MAP_METRES) - 1)
		var last_row := clampi(ceili(bounds.end.y + MAP_METRES * 0.5) - 1,
			0, int(MAP_METRES) - 1)
		if first_column > last_column or first_row > last_row:
			continue
		var overlay := SurfaceTool.new()
		overlay.begin(Mesh.PRIMITIVE_TRIANGLES)
		var has_vertices := false
		for row in range(first_row, last_row + 1):
			for column in range(first_column, last_column + 1):
				var x0 := -MAP_METRES * 0.5 + float(column)
				var z0 := -MAP_METRES * 0.5 + float(row)
				var cell_bounds := Rect2(Vector2(x0, z0), Vector2.ONE)
				if not bounds.intersects(cell_bounds, true):
					continue
				var x1 := x0 + 1.0
				var z1 := z0 + 1.0
				var a := Vector3(x0, _decoded_height(_encode_height(
					_terrain_height(x0, z0))) + 0.008, z0)
				var b := Vector3(x1, _decoded_height(_encode_height(
					_terrain_height(x1, z0))) + 0.008, z0)
				var c := Vector3(x1, _decoded_height(_encode_height(
					_terrain_height(x1, z1))) + 0.008, z1)
				var d := Vector3(x0, _decoded_height(_encode_height(
					_terrain_height(x0, z1))) + 0.008, z1)
				for vertex in [a, c, b, a, d, c]:
					var uv_point := Vector2(vertex.x, vertex.z)
					if region.uv_anchor_continent_enabled:
						uv_point += Vector2(global_position.x, global_position.z) - region.uv_anchor_continent
					overlay.set_uv(uv_point * GROUND_UV_SCALE)
					overlay.add_vertex(vertex)
					has_vertices = true
		if not has_vertices:
			continue
		overlay.generate_normals()
		overlay.generate_tangents()
		var mesh := overlay.commit()
		var node := _add_mesh(parent, "GroundRegion_%s" % region.name,
			mesh, material)
		node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF


func _build_water(parent: Node3D) -> void:
	if _river_samples.size() < 2:
		return
	# Use the same half-metre cell centres as collision export. This keeps bends
	# and end caps visually aligned with the authoritative distance corridor.
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	var emitted_water := false
	for cell_y in HALF_CELLS:
		for cell_x in HALF_CELLS:
			var centre3 := _half_cell_world(cell_x, cell_y)
			var centre := Vector2(centre3.x, centre3.z)
			var centre_sample := _river_sample(centre)
			if centre_sample.is_empty() or centre_sample.distance > centre_sample.half_width:
				continue
			var x0 := centre.x - HALF_CELL * 0.5
			var x1 := centre.x + HALF_CELL * 0.5
			var z0 := centre.y - HALF_CELL * 0.5
			var z1 := centre.y + HALF_CELL * 0.5
			var corners := [Vector2(x0, z0), Vector2(x1, z0),
				Vector2(x1, z1), Vector2(x0, z1)]
			for corner_index in [0, 2, 1, 0, 3, 2]:
				var corner: Vector2 = corners[corner_index]
				var corner_sample := _river_sample(corner)
				surface.set_uv(corner * GROUND_UV_SCALE)
				surface.set_uv2(Vector2(float(corner_sample.distance),
					float(corner_sample.half_width)))
				surface.add_vertex(Vector3(corner.x, water_level, corner.y))
				emitted_water = true
	if not emitted_water:
		return
	surface.generate_normals()
	surface.generate_tangents()
	var mesh := surface.commit()
	if mesh != null:
		var river_surface: MapAuthoringSurface = (river.get("surface") as MapAuthoringSurface
			if "surface" in river else null)
		_add_mesh(parent, "River", mesh, _surface_material(river_surface,
			"water", Color(0.12, 0.48, 0.68, 0.78), 0.2))


func _build_road(parent: Node3D) -> void:
	var points := _road_samples()
	if points.size() < 2:
		return
	var cross_sections: Array[Array] = []
	var distances: Array[float] = []
	var widths: Array[float] = []
	var lateral_steps := 6
	var distance := 0.0
	var baked_length := road.curve.get_baked_length()
	for index in points.size():
		if index > 0:
			distance += points[index - 1].distance_to(points[index])
		distances.append(distance)
		var baked_offset := baked_length * float(index) / float(points.size() - 1)
		var section_width := _path_width_at(road, baked_offset, road_width)
		widths.append(section_width)
		var previous: Vector3 = points[maxi(0, index - 1)]
		var following: Vector3 = points[mini(points.size() - 1, index + 1)]
		var direction := Vector2(following.x - previous.x, following.z - previous.z).normalized()
		var normal := Vector2(-direction.y, direction.x)
		var point: Vector3 = points[index]
		var section: Array[Vector3] = []
		for lateral_index in lateral_steps + 1:
			var lateral := section_width * (0.5 - float(lateral_index) / float(lateral_steps))
			var x := point.x + normal.x * lateral
			var z := point.z + normal.y * lateral
			section.append(Vector3(x, _road_height(x, z), z))
		cross_sections.append(section)
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	for index in points.size() - 1:
		for lateral_index in lateral_steps:
			var vertices := [cross_sections[index][lateral_index],
				cross_sections[index][lateral_index + 1],
				cross_sections[index + 1][lateral_index + 1],
				cross_sections[index + 1][lateral_index]]
			var u0 := float(lateral_index) / float(lateral_steps)
			var u1 := float(lateral_index + 1) / float(lateral_steps)
			var texture_u0a := u0 * widths[index] * GROUND_UV_SCALE
			var texture_u1a := u1 * widths[index] * GROUND_UV_SCALE
			var texture_u0b := u0 * widths[index + 1] * GROUND_UV_SCALE
			var texture_u1b := u1 * widths[index + 1] * GROUND_UV_SCALE
			var emitted := [
				[vertices[0], Vector2(texture_u0a, distances[index] * GROUND_UV_SCALE), Vector2(u0, widths[index])],
				[vertices[2], Vector2(texture_u1b, distances[index + 1] * GROUND_UV_SCALE), Vector2(u1, widths[index + 1])],
				[vertices[1], Vector2(texture_u1a, distances[index] * GROUND_UV_SCALE), Vector2(u1, widths[index])],
				[vertices[0], Vector2(texture_u0a, distances[index] * GROUND_UV_SCALE), Vector2(u0, widths[index])],
				[vertices[3], Vector2(texture_u0b, distances[index + 1] * GROUND_UV_SCALE), Vector2(u0, widths[index + 1])],
				[vertices[2], Vector2(texture_u1b, distances[index + 1] * GROUND_UV_SCALE), Vector2(u1, widths[index + 1])],
			]
			for item in emitted:
				surface.set_uv(item[1])
				surface.set_uv2(item[2])
				var vertex: Vector3 = item[0]
				surface.add_vertex(vertex)
	surface.generate_normals()
	surface.generate_tangents()
	var road_surface: MapAuthoringSurface = (road.get("surface") as MapAuthoringSurface
		if "surface" in road else null)
	_add_mesh(parent, "RoadSurface", surface.commit(), _surface_material(
		road_surface, "road", Color("#8d7958"), 0.95))


func _road_height(x: float, z: float) -> float:
	var bridge := _bridge_at(x, z)
	if not bridge.is_empty():
		return float(bridge.height) + 0.035
	return _rendered_terrain_height(x, z) + 0.055


func _rendered_terrain_height(x: float, z: float) -> float:
	# Match the two triangles emitted by `_build_terrain`. Sampling the scalar
	# height function here can cut a road corner through their planar surface.
	var x0 := clampf(floorf(x), -MAP_METRES * 0.5, MAP_METRES * 0.5 - 1.0)
	var z0 := clampf(floorf(z), -MAP_METRES * 0.5, MAP_METRES * 0.5 - 1.0)
	var u := clampf(x - x0, 0.0, 1.0)
	var v := clampf(z - z0, 0.0, 1.0)
	var a := _decoded_height(_encode_height(_terrain_height(x0, z0)))
	var b := _decoded_height(_encode_height(_terrain_height(x0 + 1.0, z0)))
	var c := _decoded_height(_encode_height(_terrain_height(x0 + 1.0, z0 + 1.0)))
	var d := _decoded_height(_encode_height(_terrain_height(x0, z0 + 1.0)))
	if u >= v:
		return a + (b - a) * u + (c - b) * v
	return a + (d - a) * v + (c - d) * u


func _road_samples() -> Array[Vector3]:
	var points: Array[Vector3] = []
	if road == null or road.curve == null or road.curve.point_count < 2:
		return points
	var length := road.curve.get_baked_length()
	if length <= 0.001:
		return points
	var count := maxi(2, ceili(length / 0.35) + 1)
	for index in count:
		var local := road.curve.sample_baked(length * float(index) / float(count - 1), true)
		points.append(road.global_transform * local)
	return points


func _path_width_at(path: Path3D, baked_offset: float, fallback: float) -> float:
	if path != null and path.has_method("width_at_offset"):
		return maxf(float(path.call("width_at_offset", baked_offset)), 0.05)
	return fallback


func _build_bridge(parent: Node3D) -> void:
	for bridge in _bridge_cache:
		_build_bridge_span(parent, bridge)


func _build_bridge_span(parent: Node3D, bridge: Dictionary) -> void:
	var span_root := Node3D.new()
	span_root.name = String(bridge.name)
	parent.add_child(span_root)
	var direction: Vector2 = bridge.delta.normalized()
	var width: float = bridge.width
	var normal := Vector2(-direction.y, direction.x) * width * 0.5
	var segments := 20
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	for index in segments:
		var t0 := float(index) / float(segments)
		var t1 := float(index + 1) / float(segments)
		var p0: Vector2 = bridge.a.lerp(bridge.b, t0)
		var p1: Vector2 = bridge.a.lerp(bridge.b, t1)
		var y0 := _bridge_height_for(bridge, p0.x, p0.y) + 0.06
		var y1 := _bridge_height_for(bridge, p1.x, p1.y) + 0.06
		var vertices := [Vector3(p0.x + normal.x, y0, p0.y + normal.y),
			Vector3(p0.x - normal.x, y0, p0.y - normal.y),
			Vector3(p1.x - normal.x, y1, p1.y - normal.y),
			Vector3(p1.x + normal.x, y1, p1.y + normal.y)]
		var emitted := [
			[vertices[0], Vector2(0.0, t0 * bridge.length * TIMBER_UV_SCALE)],
			[vertices[2], Vector2(width * TIMBER_UV_SCALE, t1 * bridge.length * TIMBER_UV_SCALE)],
			[vertices[1], Vector2(width * TIMBER_UV_SCALE, t0 * bridge.length * TIMBER_UV_SCALE)],
			[vertices[0], Vector2(0.0, t0 * bridge.length * TIMBER_UV_SCALE)],
			[vertices[3], Vector2(0.0, t1 * bridge.length * TIMBER_UV_SCALE)],
			[vertices[2], Vector2(width * TIMBER_UV_SCALE, t1 * bridge.length * TIMBER_UV_SCALE)],
		]
		for item in emitted:
			surface.set_uv(item[1])
			var vertex: Vector3 = item[0]
			surface.add_vertex(vertex)
	surface.generate_normals()
	surface.generate_tangents()
	_add_mesh(span_root, "BridgeDeck", surface.commit(), _surface_material(
		bridge.deck_surface, "woodwork", Color("#b08a58"), 0.86,
		float(bridge.deck_rotation)))
	var support_index := 0
	for point: Vector2 in [bridge.a, bridge.b]:
		var pier := BoxMesh.new()
		var top := _bridge_height_for(bridge, point.x, point.y)
		pier.size = Vector3(0.45, maxf(0.2, top - water_level), width + 0.6)
		var support_name := "BridgeSupport" if support_index == 0 else "BridgeSupportEnd"
		var node := _add_mesh(span_root, support_name, pier, _surface_material(
			bridge.support_surface, "stonework", Color("#625243"), 1.0))
		node.position = Vector3(point.x, water_level + pier.size.y * 0.5, point.y)
		node.rotation.y = -direction.angle()
		support_index += 1


func _build_building(parent: Node3D) -> void:
	if building_control == null or entrance == null:
		return
	var centre := building_control.global_position
	var floor := _decoded_height(_encode_height(_terrain_height(centre.x, centre.z)))
	var wall_surface: MapAuthoringSurface = (building_control.get("wall_surface") \
		as MapAuthoringSurface if "wall_surface" in building_control else null)
	var roof_surface: MapAuthoringSurface = (building_control.get("roof_surface") \
		as MapAuthoringSurface if "roof_surface" in building_control else null)
	var wall_material := _surface_material(wall_surface,
		"woodwork", Color("#9d876d"), 0.9)
	# Four wall groups form a readable open-front cabin. The gap in the front
	# wall is the same gap `_inside_building` leaves open in the walk grid.
	_add_building_box(parent, "BackWall", Vector3(0.5, 4.0, 5.0),
		Vector3(3.25, 2.0, 0.0), floor, wall_material)
	_add_building_box(parent, "LeftWall", Vector3(6.0, 4.0, 0.5),
		Vector3(0.0, 2.0, -2.25), floor, wall_material)
	_add_building_box(parent, "RightWall", Vector3(6.0, 4.0, 0.5),
		Vector3(0.0, 2.0, 2.25), floor, wall_material)
	_add_building_box(parent, "FrontWallLeft", Vector3(0.5, 4.0, 1.5),
		Vector3(-3.25, 2.0, -1.75), floor, wall_material)
	_add_building_box(parent, "FrontWallRight", Vector3(0.5, 4.0, 1.5),
		Vector3(-3.25, 2.0, 1.75), floor, wall_material)
	var roof := PrismMesh.new()
	roof.size = Vector3(7.8, 2.0, 5.8)
	var roof_node := _add_mesh(parent, "Roof", roof, _surface_material(
		roof_surface, "roof", Color("#5c3f35"), 1.0))
	roof_node.transform = building_control.global_transform
	roof_node.position += Vector3(0.0, floor + 4.8, 0.0)
	var door_mat := wall_material
	for offset in [-1.0, 1.0]:
		var post := BoxMesh.new()
		post.size = Vector3(0.35, 2.6, 0.4)
		var post_node := _add_mesh(parent, "EntrancePost", post, door_mat)
		post_node.global_transform = entrance.global_transform.translated_local(Vector3(0.0, floor + 1.3, offset * 0.8))
	var lintel := BoxMesh.new()
	lintel.size = Vector3(0.4, 0.35, 1.95)
	var lintel_node := _add_mesh(parent, "EntranceLintel", lintel, door_mat)
	lintel_node.global_transform = entrance.global_transform.translated_local(Vector3(0.0, floor + 2.55, 0.0))


func _add_building_box(parent: Node3D, box_name: String, size: Vector3,
		local_position: Vector3, floor: float, material: Material) -> void:
	var mesh := BoxMesh.new()
	mesh.size = size
	var node := _add_mesh(parent, box_name, mesh, material)
	node.global_transform = building_control.global_transform.translated_local(
		local_position + Vector3(0.0, floor, 0.0))


func _build_walkability(parent: Node3D) -> void:
	parent.visible = show_walkability
	var reachable := _server_reachable()
	var open_surface := SurfaceTool.new()
	var blocked_surface := SurfaceTool.new()
	open_surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	blocked_surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	for y in SERVER_CELLS:
		for x in SERVER_CELLS:
			var value := int(_server_grid[y * SERVER_CELLS + x])
			var connected := reachable.has(Vector2i(x, y))
			var surface := open_surface if value and connected else blocked_surface
			var world := _server_tile_world(x, y)
			var height := _decoded_height(value) + 0.09 if value else maxf(
				water_level + 0.11, _terrain_height(world.x, world.z) + 0.09)
			var extent := 0.43
			var a := Vector3(world.x - extent, height, world.z - extent)
			var b := Vector3(world.x + extent, height, world.z - extent)
			var c := Vector3(world.x + extent, height, world.z + extent)
			var d := Vector3(world.x - extent, height, world.z + extent)
			for vertex in [a, c, b, a, d, c]:
				surface.add_vertex(vertex)
	_add_mesh(parent, "WalkableServerTiles", open_surface.commit(),
		_material(Color(0.15, 0.95, 0.35, 0.34), 0.15, true))
	_add_mesh(parent, "BlockedServerTiles", blocked_surface.commit(),
		_material(Color(0.95, 0.12, 0.12, 0.43), 0.15, true))


func _add_mesh(parent: Node3D, node_name: String, mesh: Mesh,
		material: Material) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	node.name = node_name
	node.mesh = mesh
	node.material_override = material
	parent.add_child(node)
	return node


func _material(color: Color, roughness: float, overlay := false) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = roughness
	# Generated surfaces are authoring previews and remain readable from either
	# side while their control points are being moved through the viewport.
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	if color.a < 0.99:
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	if overlay:
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		material.no_depth_test = true
	return material


func _style_material(slot: String, fallback_color: Color,
		fallback_roughness: float, extra_rotation_degrees := 0.0) -> Material:
	if visual_style != null and visual_style.has_method("get_material"):
		var styled: Variant = visual_style.call("get_material", slot,
			extra_rotation_degrees)
		if styled is Material:
			return styled
	elif visual_style != null:
		var legacy_properties := {
			"terrain": &"terrain_material", "road": &"worn_path_material",
			"woodwork": &"timber_material", "stonework": &"stone_material",
			"roof": &"slate_material", "water": &"water_material",
		}
		var saved: Variant = visual_style.get(legacy_properties.get(slot, &""))
		if saved is Material:
			return saved
	return _material(fallback_color, fallback_roughness)


func _surface_material(surface: MapAuthoringSurface, legacy_slot: String,
		fallback_color: Color, fallback_roughness: float,
		extra_rotation_degrees := 0.0) -> Material:
	if surface != null:
		var local := surface.get_material(extra_rotation_degrees)
		if local != null:
			return local
		return _material(fallback_color, fallback_roughness)
	return _style_material(legacy_slot, fallback_color, fallback_roughness,
		extra_rotation_degrees)


func _visual_style_signature() -> Array:
	if visual_style == null:
		return []
	if visual_style.has_method("rotation_signature"):
		return [visual_style.get_instance_id(), visual_style.call("rotation_signature")]
	var signature: Array[int] = [visual_style.get_instance_id()]
	for property_name in [&"terrain_material", &"worn_path_material", &"timber_material",
			&"stone_material", &"slate_material", &"water_material"]:
		var material: Variant = visual_style.get(property_name)
		signature.append(material.get_instance_id() if material is Material else 0)
	return signature


func _sync_authored_style() -> void:
	if authored_scenery == null:
		authored_scenery = get_node_or_null("AuthoredScenery")
	if authored_scenery != null and authored_scenery.has_method("apply_visual_style"):
		authored_scenery.call("apply_visual_style", visual_style)


func _setup_runtime() -> void:
	_status = get_node_or_null("UI/Margin/Panel/VBox/Status")
	var start: Button = get_node_or_null("UI/Margin/Panel/VBox/Buttons/Start")
	var reset: Button = get_node_or_null("UI/Margin/Panel/VBox/Buttons/Reset")
	var overlay: Button = get_node_or_null("UI/Margin/Panel/VBox/Buttons/Overlay")
	if start:
		start.pressed.connect(start_walk)
	if reset:
		reset.pressed.connect(reset_walk)
	if overlay:
		overlay.pressed.connect(toggle_overlay)
	_walker = MeshInstance3D.new()
	_walker.name = "LocalWalker"
	var capsule := CapsuleMesh.new()
	capsule.radius = 0.35
	capsule.height = 1.7
	_walker.mesh = capsule
	_walker.material_override = _material(Color("#f4c95d"), 0.8)
	add_child(_walker)
	reset_walk()


func start_walk() -> void:
	_walking = false
	_walker_tile = _world_to_server(spawn_marker.global_position)
	_place_walker(_walker_tile)
	_walk_route = validation_route()
	_walk_route_index = 0
	_walking = _walk_route.size() > 1
	_set_status("Walking shared 1 m server grid (%d tiles)" % _walk_route.size()
		if _walking else "No legal route to entrance")


func reset_walk() -> void:
	_build_walk_grids()
	_walking = false
	_walk_route.clear()
	_walk_route_index = 0
	_walker_tile = _world_to_server(spawn_marker.global_position)
	_place_walker(_walker_tile)
	_set_status("Ready. Start: Enter/button  Reset: R  Overlay: V")


func toggle_overlay() -> void:
	show_walkability = not show_walkability
	var overlay := generated.get_node_or_null("Walkability")
	if overlay:
		overlay.visible = show_walkability
	_set_status("Walkability overlay %s" % ("shown" if show_walkability else "hidden"))


func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_ENTER:
				start_walk()
			KEY_R:
				reset_walk()
			KEY_V:
				toggle_overlay()


func _advance_walker(delta: float) -> void:
	if _walk_route_index >= _walk_route.size() - 1:
		_walking = false
		_set_status("ARRIVED at entrance on exported server grid")
		return
	var next_tile := _walk_route[_walk_route_index + 1]
	var target := _server_tile_world(next_tile.x, next_tile.y)
	var value := int(_server_grid[next_tile.y * SERVER_CELLS + next_tile.x])
	target.y = _decoded_height(value) + 0.85
	_walker.position = _walker.position.move_toward(target, WALKER_SPEED * delta)
	if _walker.position.distance_to(target) < 0.03:
		_walker_tile = next_tile
		_walk_route_index += 1


func _place_walker(tile: Vector2i) -> void:
	if _walker == null:
		return
	var value := int(_server_grid[tile.y * SERVER_CELLS + tile.x])
	var point := _server_tile_world(tile.x, tile.y)
	point.y = _decoded_height(value) + 0.85
	_walker.position = point


func _find_route(start: Vector2i, goal: Vector2i) -> Array[Vector2i]:
	if not _server_open(start) or not _server_open(goal):
		return []
	var frontier: Array[Vector2i] = [start]
	var parent := {start: Vector2i(-999, -999)}
	var directions := [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]
	while not frontier.is_empty():
		var here: Vector2i = frontier.pop_front() as Vector2i
		if here == goal:
			break
		for direction: Vector2i in directions:
			var there: Vector2i = here + direction
			if parent.has(there) or not _server_step_allowed(here, there):
				continue
			parent[there] = here
			frontier.append(there)
	if not parent.has(goal):
		return []
	var route: Array[Vector2i] = []
	var cursor := goal
	while cursor != Vector2i(-999, -999):
		route.push_front(cursor)
		cursor = parent[cursor]
	return route


func _server_reachable() -> Dictionary:
	var result := {}
	if spawn_marker == null:
		return result
	var start := _world_to_server(spawn_marker.global_position)
	if not _server_open(start):
		return result
	var frontier: Array[Vector2i] = [start]
	result[start] = true
	var directions: Array[Vector2i] = [Vector2i(1, 0), Vector2i(-1, 0),
		Vector2i(0, 1), Vector2i(0, -1)]
	while not frontier.is_empty():
		var here: Vector2i = frontier.pop_front() as Vector2i
		for direction: Vector2i in directions:
			var there := here + direction
			if result.has(there) or not _server_step_allowed(here, there):
				continue
			result[there] = true
			frontier.append(there)
	return result


func _server_open(tile: Vector2i) -> bool:
	return tile.x >= 0 and tile.y >= 0 and tile.x < SERVER_CELLS and tile.y < SERVER_CELLS \
		and int(_server_grid[tile.y * SERVER_CELLS + tile.x]) > 0


func _server_step_allowed(a: Vector2i, b: Vector2i) -> bool:
	if not _server_open(a) or not _server_open(b):
		return false
	return absi(int(_server_grid[a.y * SERVER_CELLS + a.x]) -
		int(_server_grid[b.y * SERVER_CELLS + b.x])) <= 2


func _half_cell_world(x: int, y: int) -> Vector3:
	return Vector3(-24.0 + (float(x) + 0.5) * HALF_CELL, 0.0,
		24.0 - (float(y) + 0.5) * HALF_CELL)


func _server_tile_world(x: int, y: int) -> Vector3:
	return Vector3(-24.0 + float(x) + 0.5, 0.0, 24.0 - float(y) - 0.5)


func _world_to_server(point: Vector3) -> Vector2i:
	return Vector2i(clampi(floori(point.x + 24.0), 0, SERVER_CELLS - 1),
		clampi(floori(24.0 - point.z), 0, SERVER_CELLS - 1))


func _validation_probes() -> Dictionary:
	var basis := _bridge_basis()
	var bridge_mid: Vector2 = basis.a.lerp(basis.b, 0.5)
	var bridge_direction: Vector2 = basis.delta.normalized()
	var bridge_normal := Vector2(-bridge_direction.y, bridge_direction.x)
	var bridge_side := bridge_mid + bridge_normal * (float(basis.width) * 0.5 + 1.0)
	var solid_wall := building_control.global_transform * Vector3(3.25, 0.0, 0.0)
	var road_probe := spawn_marker.global_position if spawn_marker else Vector3.ZERO
	if road != null and road.curve != null and road.curve.point_count >= 2 \
			and road.curve.get_baked_length() > 0.001:
		road_probe = road.global_transform * road.curve.sample_baked(
			road.curve.get_baked_length() * 0.25, true)
	var water_probe2 := _polyline_point_at_fraction(_river_samples, 5.0 / 6.0)
	return {
		"spawn": _tile_array(_world_to_server(spawn_marker.global_position)),
		"roadWaypoint": _tile_array(_world_to_server(road_probe)),
		"bridgeEntry": _tile_array(_world_to_server(Vector3(basis.a.x, 0.0, basis.a.y))),
		"bridgeDeck": _tile_array(_world_to_server(Vector3(bridge_mid.x, 0.0, bridge_mid.y))),
		"bridgeExit": _tile_array(_world_to_server(Vector3(basis.b.x, 0.0, basis.b.y))),
		"entrance": _tile_array(_world_to_server(entrance.global_position)),
		"waterProbe": _tile_array(_world_to_server(Vector3(water_probe2.x, 0.0, water_probe2.y))),
		"solidProbe": _tile_array(_world_to_server(solid_wall)),
		"besideBridgeProbe": _tile_array(_world_to_server(Vector3(bridge_side.x, 0.0, bridge_side.y))),
	}


func _get_configuration_warnings() -> PackedStringArray:
	var warnings := PackedStringArray()
	var river_node: Path3D = get_node_or_null("AuthoredControls/River")
	if river_node == null or river_node.curve == null or river_node.curve.point_count < 2 \
			or river_node.curve.get_baked_length() <= 0.001 or not _path_has_xz_extent(river_node):
		warnings.append("River needs at least two distinct points; water, river cut, and river blocking are disabled.")
	var road_node: Path3D = get_node_or_null("AuthoredControls/Road")
	if road_node == null or road_node.curve == null or road_node.curve.point_count < 2 \
			or road_node.curve.get_baked_length() <= 0.001:
		warnings.append("Road needs at least two distinct points; its preview is disabled.")
	var bridge_container := get_node_or_null("AuthoredControls/Bridges") as Node3D
	if bridge_container != null:
		for candidate in bridge_container.get_children():
			if not candidate is Node3D:
				continue
			if not _is_bridge_control(candidate):
				warnings.append("Bridge entry %s needs the bridge control script; it is skipped." % candidate.name)
				continue
			var start := candidate.get_node_or_null("Start") as Marker3D
			var end := candidate.get_node_or_null("End") as Marker3D
			if start == null or end == null:
				warnings.append("Bridge %s needs Start and End markers; it is skipped." % candidate.name)
			elif Vector2(start.global_position.x, start.global_position.z).distance_to(
					Vector2(end.global_position.x, end.global_position.z)) <= 0.001:
				warnings.append("Bridge %s needs distinct Start and End positions; it is skipped." % candidate.name)
	return warnings


func _path_has_xz_extent(path: Path3D) -> bool:
	if path == null or path.curve == null or path.curve.point_count < 2:
		return false
	var origin := Vector2.ZERO
	var has_origin := false
	for index in path.curve.point_count:
		var point := path.curve.get_point_position(index)
		for local: Vector3 in [point, point + path.curve.get_point_in(index),
				point + path.curve.get_point_out(index)]:
			var world: Vector3 = path.global_transform * local
			var projected := Vector2(world.x, world.z)
			if not has_origin:
				origin = projected
				has_origin = true
			elif projected.distance_squared_to(origin) > 0.000001:
				return true
	return false


func _tile_array(tile: Vector2i) -> Array[int]:
	return [tile.x, tile.y]


func _set_status(message: String) -> void:
	if _status == null:
		_status = get_node_or_null("UI/Margin/Panel/VBox/Status")
	if _status:
		_status.text = message
