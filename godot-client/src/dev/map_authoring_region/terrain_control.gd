@tool
class_name MapAuthoringTerrainControl
extends Node3D

const PATCH_SCRIPT := preload("res://src/dev/map_authoring_region/terrain_patch.gd")
const PATH_SCRIPT := preload("res://src/dev/map_authoring_region/path_control.gd")
const GROUND_SCRIPT := preload(
	"res://src/dev/map_authoring_region/ground_region_control.gd")
const GROUND_REGION_MATERIAL := preload(
	"res://src/dev/map_authoring_pilot/style/ground_region_material.gd")
const BIOME_BLEND_MATERIAL := preload("res://src/world/biome_blend_material.gd")
const BIOME_PALETTE_ENTRY := preload(
	"res://src/dev/map_authoring_region/biome_palette_entry.gd")
const SCULPT_LAYER := preload(
	"res://src/dev/map_authoring_region/terrain_sculpt_layer.gd")
const BIOME_CATALOG_PATH := "res://assets/world/biome_blend/catalog.json"

@export var origin := Vector2(-194.0, -500.0)
@export_range(0.25, 16.0, 0.25) var cell_metres := 2.0
@export var grid_size := Vector2i(397, 397)
@export_file("*.f32le", "*.bin") var base_heights_path := ""
@export_file("*.rgba8", "*.bin") var base_colors_path := ""
@export var base_surface: MapAuthoringSurface
## Sparse non-destructive edits bound to the original height file and grid.
@export var sculpt_layer: Resource
## One optional within-region material mixed by a named landscape biome role.
## The production masks retain at most four region channels per chunk.
@export var biome_palette: Array[Resource] = []
@export var preview_enabled := true
@export_range(0.01, 2.0, 0.01) var preview_uv_metres_inverse := 0.24
## Viewer-only preview clips, as continent x, z polygons (the region's continent translation plus the preview's own
## coordinates). With three or more points in preview_clip_inside the preview draws only the cells whose centre lies
## inside it; a cell whose centre lies inside any polygon of preview_clip_outside is not drawn. Neither changes the
## heights, the bake, the sculpt or any other tool: a viewer wrapper uses them so that maps sharing one grid (the
## continent-v2 isle group, whose crops share sw_isle's vertices) each draw their own ground once.
@export var preview_clip_inside := PackedVector2Array()
## Authoritative ordered inside components when provided; gaps are not drawn.
@export var preview_clip_polygons: Array[PackedVector2Array] = []
@export var preview_clip_outside: Array[PackedVector2Array] = []

var _base_heights := PackedFloat32Array()
var _effective_heights := PackedFloat32Array()
var _base_colors := PackedColorArray()
var _loaded_path := ""
var _loaded_sha := ""
var _loaded_colors_path := ""
var _loaded_colors_sha := ""
var _preview_signature: Array = []
var _elapsed := 0.0
var _bound_surface: MapAuthoringSurface
var _bound_sculpt_layer: Resource
var _bound_palette_entries: Array[Resource] = []
var last_error := ""
var preview_revision := 0
## 1 for each grid cell the preview draws (see preview_clip_inside); empty when nothing is clipped.
var _clip_mask := PackedByteArray()


func _ready() -> void:
	set_process(true)
	_sync_surface()
	_sync_sculpt_layer()
	_sync_palette()
	refresh_preview()


func _process(delta: float) -> void:
	if base_surface != _bound_surface:
		_sync_surface()
	if sculpt_layer != _bound_sculpt_layer:
		_sync_sculpt_layer()
	_sync_palette()
	if not Engine.is_editor_hint():
		return
	_elapsed += delta
	if _elapsed < 0.18:
		return
	_elapsed = 0.0
	var signature := _current_signature()
	if signature != _preview_signature:
		refresh_preview()


func refresh_preview() -> bool:
	last_error = ""
	if base_surface != null:
		base_surface.enable_region_uv_projection(preview_uv_metres_inverse)
	_sync_palette()
	if not _load_base_heights():
		_clear_preview()
		update_configuration_warnings()
		return false
	if not _load_base_colors():
		_clear_preview()
		update_configuration_warnings()
		return false
	if not _resolve_sculpted_base():
		_clear_preview()
		update_configuration_warnings()
		return false
	_apply_patches()
	_apply_path_effects()
	_preview_signature = _current_signature()
	_clip_mask = preview_clip_mask()
	if preview_enabled:
		_build_preview_mesh()
		_build_ground_region_previews()
	else:
		_clear_preview()
	preview_revision += 1
	update_configuration_warnings()
	return true


func base_heights() -> PackedFloat32Array:
	_load_base_heights()
	return _base_heights.duplicate()


func sculpted_base_heights() -> PackedFloat32Array:
	if not _load_base_heights():
		return PackedFloat32Array()
	return _sculpted_base_result()


func apply_sculpt_layer(next_layer: Resource) -> bool:
	if not _load_base_heights():
		return false
	if next_layer != null:
		if next_layer.get_script() != SCULPT_LAYER:
			last_error = "Terrain Sculpt Layer uses an unsupported resource type."
			return false
		var error: String = next_layer.validation_error(_loaded_sha, origin,
			grid_size, cell_metres)
		if not error.is_empty():
			last_error = error
			return false
		next_layer.resource_local_to_scene = true
	sculpt_layer = next_layer
	_sync_sculpt_layer()
	return refresh_preview()


func effective_heights() -> PackedFloat32Array:
	if _effective_heights.size() != grid_size.x * grid_size.y:
		refresh_preview()
	return _effective_heights.duplicate()


func base_sha256() -> String:
	_load_base_heights()
	return _loaded_sha


func terrain_hit_world(ray_origin: Vector3, ray_direction: Vector3,
		max_distance: float = 4096.0) -> Variant:
	if not ray_origin.is_finite() or not ray_direction.is_finite() or \
			ray_direction.length_squared() <= 0.000001 or \
			not is_finite(max_distance) or max_distance <= 0.0:
		return null
	var inverse := global_transform.affine_inverse()
	var local_start := inverse * ray_origin
	var local_end := inverse * (ray_origin + ray_direction.normalized() * max_distance)
	var hit: Variant = intersect_local_segment(local_start, local_end)
	return global_transform * (hit as Vector3) if hit is Vector3 else null


func live_biome_palette() -> Dictionary:
	if base_surface == null or not base_surface.biome_blend_enabled:
		return {}
	var region := get_parent()
	var region_id := String(region.get("region_id")) if region != null else ""
	var base := BIOME_BLEND_MATERIAL.surface_palette(base_surface,
		preview_uv_metres_inverse)
	if region_id.is_empty() or base.is_empty():
		return {}
	var secondary: Variant = null
	if biome_palette.size() == 1 and _uses_script(biome_palette[0],
			BIOME_PALETTE_ENTRY):
		var entry: Resource = biome_palette[0]
		secondary = BIOME_BLEND_MATERIAL.surface_palette(entry.surface,
			preview_uv_metres_inverse)
		if secondary is Dictionary and not secondary.is_empty():
			secondary["id"] = "%s:%s" % [region_id, entry.id]
			secondary["role"] = entry.role
	return {region_id: {"base": base, "secondary": secondary}}


func patch_records() -> Array[Dictionary]:
	var records: Array[Dictionary] = []
	var patches := get_node_or_null("Patches")
	if patches == null:
		return records
	for child in patches.get_children():
		if _uses_script(child, PATCH_SCRIPT):
			var patch = child
			records.append(patch.snapshot_record(global_transform.affine_inverse() *
				patch.global_transform))
	records.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return String(a.id) < String(b.id))
	return records


func height_at_local(x: float, z: float) -> float:
	if _effective_heights.size() != grid_size.x * grid_size.y:
		refresh_preview()
	if _effective_heights.is_empty():
		return NAN
	var fx := clampf((x - origin.x) / cell_metres, 0.0, float(grid_size.x - 1))
	var fz := clampf((z - origin.y) / cell_metres, 0.0, float(grid_size.y - 1))
	var x0 := mini(floori(fx), grid_size.x - 2)
	var z0 := mini(floori(fz), grid_size.y - 2)
	var tx := fx - float(x0)
	var tz := fz - float(z0)
	var h00 := _height(x0, z0)
	var h10 := _height(x0 + 1, z0)
	var h01 := _height(x0, z0 + 1)
	var h11 := _height(x0 + 1, z0 + 1)
	if tx + tz <= 1.0:
		return h00 + (h10 - h00) * tx + (h01 - h00) * tz
	return h11 + (h01 - h11) * (1.0 - tx) + (h10 - h11) * (1.0 - tz)


## Returns the highest authored river surface covering this terrain-local point.
## River widths are full metres, matching snapshots and the production composer.
func river_water_height_at_local(x: float, z: float) -> Variant:
	var sample := Vector2(x, z)
	var highest := -INF
	var found := false
	for path in _region_paths():
		if path.kind != "river" or path.curve == null or path.curve.point_count < 2:
			continue
		var points: Array[Dictionary] = path.snapshot_points()
		var path_to_terrain: Transform3D = global_transform.affine_inverse() * \
			path.global_transform
		var width_scale := Vector2(path_to_terrain.basis.x.x,
			path_to_terrain.basis.x.z).length()
		for segment_index in points.size() - 1:
			var first := path_to_terrain * _record_point(points[segment_index])
			var second := path_to_terrain * _record_point(points[segment_index + 1])
			var start_xz := Vector2(first.x, first.z)
			var delta := Vector2(second.x - first.x, second.z - first.z)
			var length_squared := delta.length_squared()
			if length_squared <= 0.000001:
				continue
			var amount := clampf((sample - start_xz).dot(delta) / length_squared,
				0.0, 1.0)
			var nearest := start_xz + delta * amount
			var first_width := float(points[segment_index].width) * width_scale
			var second_width := float(points[segment_index + 1].width) * width_scale
			var half_width := lerpf(first_width, second_width, amount) * 0.5
			if sample.distance_to(nearest) > half_width:
				continue
			found = true
			highest = maxf(highest, lerpf(first.y, second.y, amount))
	return highest if found else null


func intersect_local_segment(segment_start: Vector3, segment_end: Vector3) -> Variant:
	if _effective_heights.size() != grid_size.x * grid_size.y:
		refresh_preview()
	if _effective_heights.is_empty():
		return null
	var minimum_height := INF
	var maximum_height := -INF
	for value in _effective_heights:
		minimum_height = minf(minimum_height, value)
		maximum_height = maxf(maximum_height, value)
	var bounds := AABB(Vector3(origin.x, minimum_height - 0.1, origin.y), Vector3(
		float(grid_size.x - 1) * cell_metres, maximum_height - minimum_height + 0.2,
		float(grid_size.y - 1) * cell_metres))
	if bounds.intersects_segment(segment_start, segment_end) == null:
		return null
	var min_x := clampi(floori((minf(segment_start.x, segment_end.x) - origin.x) /
		cell_metres) - 1, 0, grid_size.x - 2)
	var max_x := clampi(ceili((maxf(segment_start.x, segment_end.x) - origin.x) /
		cell_metres) + 1, 0, grid_size.x - 2)
	var min_z := clampi(floori((minf(segment_start.z, segment_end.z) - origin.y) /
		cell_metres) - 1, 0, grid_size.y - 2)
	var max_z := clampi(ceili((maxf(segment_start.z, segment_end.z) - origin.y) /
		cell_metres) + 1, 0, grid_size.y - 2)
	var nearest: Variant = null
	var nearest_distance := INF
	for z_index in range(min_z, max_z + 1):
		for x_index in range(min_x, max_x + 1):
			var p00 := _point(x_index, z_index)
			var p10 := _point(x_index + 1, z_index)
			var p01 := _point(x_index, z_index + 1)
			var p11 := _point(x_index + 1, z_index + 1)
			var triangles: Array = [[p00, p01, p10], [p10, p01, p11]]
			for triangle_value in triangles:
				var triangle: Array = triangle_value
				var hit: Variant = Geometry3D.segment_intersects_triangle(segment_start,
					segment_end, triangle[0], triangle[1], triangle[2])
				if hit is Vector3:
					var distance := segment_start.distance_squared_to(hit as Vector3)
					if distance < nearest_distance:
						nearest_distance = distance
						nearest = hit
	return nearest


func _load_base_heights() -> bool:
	if grid_size.x < 2 or grid_size.y < 2 or cell_metres <= 0.0:
		last_error = "Terrain grid needs at least 2Ãƒâ€”2 samples and a positive cell size."
		return false
	if base_heights_path.strip_edges().is_empty():
		last_error = "Terrain Base Heights Path is empty."
		return false
	var absolute := ProjectSettings.globalize_path(base_heights_path)
	if not FileAccess.file_exists(absolute):
		last_error = "Terrain base heights file is missing: %s" % base_heights_path
		return false
	var sha := FileAccess.get_sha256(absolute)
	if base_heights_path == _loaded_path and sha == _loaded_sha and \
			_base_heights.size() == grid_size.x * grid_size.y:
		return true
	var file := FileAccess.open(absolute, FileAccess.READ)
	if file == null:
		last_error = "Could not open terrain base heights: %s" % base_heights_path
		return false
	var expected_bytes := grid_size.x * grid_size.y * 4
	if file.get_length() != expected_bytes:
		last_error = "Terrain base heights has %d bytes; expected %d for %dÃƒâ€”%d float32 samples." % [
			file.get_length(), expected_bytes, grid_size.x, grid_size.y]
		return false
	file.big_endian = false
	var loaded := PackedFloat32Array()
	loaded.resize(grid_size.x * grid_size.y)
	for index in loaded.size():
		loaded[index] = file.get_float()
		if not is_finite(loaded[index]):
			last_error = "Terrain base heights contains a non-finite sample at %d." % index
			return false
	_base_heights = loaded
	_loaded_path = base_heights_path
	_loaded_sha = sha
	return true


func _load_base_colors() -> bool:
	if base_colors_path.strip_edges().is_empty():
		_base_colors = PackedColorArray()
		_loaded_colors_path = ""
		_loaded_colors_sha = ""
		return true
	var absolute := ProjectSettings.globalize_path(base_colors_path)
	if not FileAccess.file_exists(absolute):
		last_error = "Terrain base colors file is missing: %s" % base_colors_path
		return false
	var sha := FileAccess.get_sha256(absolute)
	if base_colors_path == _loaded_colors_path and sha == _loaded_colors_sha and \
			_base_colors.size() == grid_size.x * grid_size.y:
		return true
	var bytes := FileAccess.get_file_as_bytes(absolute)
	var expected_bytes := grid_size.x * grid_size.y * 4
	if bytes.size() != expected_bytes:
		last_error = "Terrain base colors has %d bytes; expected %d for %dÃƒâ€”%d RGBA8 samples." % [
			bytes.size(), expected_bytes, grid_size.x, grid_size.y]
		return false
	var loaded := PackedColorArray()
	loaded.resize(grid_size.x * grid_size.y)
	for index in loaded.size():
		var offset := index * 4
		loaded[index] = Color8(bytes[offset], bytes[offset + 1], bytes[offset + 2],
			bytes[offset + 3])
	_base_colors = loaded
	_loaded_colors_path = base_colors_path
	_loaded_colors_sha = sha
	return true


func _resolve_sculpted_base() -> bool:
	var result := _sculpted_base_result()
	if result.size() != _base_heights.size():
		if last_error.is_empty():
			last_error = "Terrain Sculpt Layer could not be applied."
		return false
	_effective_heights = result
	return true


func _sculpted_base_result() -> PackedFloat32Array:
	if sculpt_layer == null:
		return _base_heights.duplicate()
	if sculpt_layer.get_script() != SCULPT_LAYER:
		last_error = "Terrain Sculpt Layer uses an unsupported resource type."
		return PackedFloat32Array()
	var error: String = sculpt_layer.validation_error(_loaded_sha, origin,
		grid_size, cell_metres)
	if not error.is_empty():
		last_error = error
		return PackedFloat32Array()
	return sculpt_layer.apply_to(_base_heights, _loaded_sha, origin, grid_size,
		cell_metres)


func _apply_patches() -> void:
	var patches := get_node_or_null("Patches")
	if patches == null:
		return
	var ordered: Array = []
	for child in patches.get_children():
		if _uses_script(child, PATCH_SCRIPT):
			ordered.append(child)
	ordered.sort_custom(func(a: Variant, b: Variant) -> bool:
		return String(a.patch_id) < String(b.patch_id))
	for patch in ordered:
		if not patch.enabled:
			continue
		var half: Vector2 = patch.size * 0.5
		var patch_to_terrain: Transform3D = global_transform.affine_inverse() * patch.global_transform
		var corners: Array[Vector3] = []
		for corner in [Vector3(-half.x, 0.0, -half.y), Vector3(half.x, 0.0, -half.y),
				Vector3(half.x, 0.0, half.y), Vector3(-half.x, 0.0, half.y)]:
			corners.append(patch_to_terrain * corner)
		var minimum := Vector2(INF, INF)
		var maximum := Vector2(-INF, -INF)
		for corner in corners:
			minimum = minimum.min(Vector2(corner.x, corner.z))
			maximum = maximum.max(Vector2(corner.x, corner.z))
		var x0 := clampi(floori((minimum.x - origin.x) / cell_metres),
			0, grid_size.x - 1)
		var x1 := clampi(ceili((maximum.x - origin.x) / cell_metres),
			0, grid_size.x - 1)
		var z0 := clampi(floori((minimum.y - origin.y) / cell_metres),
			0, grid_size.y - 1)
		var z1 := clampi(ceili((maximum.y - origin.y) / cell_metres),
			0, grid_size.y - 1)
		for z_index in range(z0, z1 + 1):
			for x_index in range(x0, x1 + 1):
				var sample := Vector2(origin.x + float(x_index) * cell_metres,
					origin.y + float(z_index) * cell_metres)
				var weight: float = patch.weight_at_transform(sample, patch_to_terrain)
				if weight <= 0.0:
					continue
				var index := z_index * grid_size.x + x_index
				if patch.operation == PATCH_SCRIPT.Operation.ADD:
					_effective_heights[index] += patch_to_terrain.origin.y * weight
				else:
					_effective_heights[index] = lerpf(_effective_heights[index],
						patch_to_terrain.origin.y, weight)


func _apply_path_effects() -> void:
	var paths := _region_paths()
	paths.sort_custom(func(a: Variant, b: Variant) -> bool:
		if (a.kind == "river") != (b.kind == "river"):
			return a.kind != "river"
		return String(a.path_id) < String(b.path_id))
	for path in paths:
		if path.curve == null or path.curve.point_count < 2 or \
				not bool(path.properties.get("terrainConform", true)):
			continue
		var points: Array[Dictionary] = path.snapshot_points()
		var path_to_terrain: Transform3D = global_transform.affine_inverse() * \
			path.global_transform
		var path_width_scale := Vector2(path_to_terrain.basis.x.x,
			path_to_terrain.basis.x.z).length()
		if path.kind == "river":
			_apply_river_effect(path, points, path_to_terrain, path_width_scale)
			continue
		for segment_index in points.size() - 1:
			var first := path_to_terrain * _record_point(points[segment_index])
			var second := path_to_terrain * _record_point(points[segment_index + 1])
			var first_width := float(points[segment_index].width) * path_width_scale
			var second_width := float(points[segment_index + 1].width) * path_width_scale
			var feather := float(path.properties.get("terrainFeather",
				2.0 if path.kind == "road" else 5.5))
			var reach := maxf(first_width, second_width) * 0.5 + maxf(0.0, feather)
			var x0 := clampi(floori((minf(first.x, second.x) - reach - origin.x) /
				cell_metres), 0, grid_size.x - 1)
			var x1 := clampi(ceili((maxf(first.x, second.x) + reach - origin.x) /
				cell_metres), 0, grid_size.x - 1)
			var z0 := clampi(floori((minf(first.z, second.z) - reach - origin.y) /
				cell_metres), 0, grid_size.y - 1)
			var z1 := clampi(ceili((maxf(first.z, second.z) + reach - origin.y) /
				cell_metres), 0, grid_size.y - 1)
			var start_xz := Vector2(first.x, first.z)
			var delta := Vector2(second.x - first.x, second.z - first.z)
			var length_squared := delta.length_squared()
			if length_squared <= 0.000001:
				continue
			for z_index in range(z0, z1 + 1):
				for x_index in range(x0, x1 + 1):
					var sample := Vector2(origin.x + float(x_index) * cell_metres,
						origin.y + float(z_index) * cell_metres)
					var amount := clampf((sample - start_xz).dot(delta) /
						length_squared, 0.0, 1.0)
					var nearest := start_xz + delta * amount
					var distance := sample.distance_to(nearest)
					var half_width := lerpf(first_width, second_width, amount) * 0.5
					if distance > half_width + feather:
						continue
					var weight := 1.0 if distance <= half_width else \
						_smooth_weight(1.0 - (distance - half_width) / maxf(feather, 0.000001))
					var path_y := lerpf(first.y, second.y, amount)
					var index := z_index * grid_size.x + x_index
					_effective_heights[index] = lerpf(_effective_heights[index], path_y, weight)


func _apply_river_effect(path: Node, points: Array[Dictionary],
		path_to_terrain: Transform3D, path_width_scale: float) -> void:
	# Resolve the strongest segment influence first, then apply the river once.
	# This avoids deepening a bend merely because its densely sampled segments
	# overlap, and makes zero influence at the feather edge truly unchanged.
	var sample_count := grid_size.x * grid_size.y
	var best_weights := PackedFloat32Array()
	best_weights.resize(sample_count)
	best_weights.fill(0.0)
	var best_beds := PackedFloat32Array()
	best_beds.resize(sample_count)
	best_beds.fill(INF)
	var feather := maxf(0.0, float(path.properties.get("terrainFeather", 5.5)))
	var depth := maxf(0.0, float(path.properties.get("channelDepth", 1.45)))
	for segment_index in points.size() - 1:
		var first := path_to_terrain * _record_point(points[segment_index])
		var second := path_to_terrain * _record_point(points[segment_index + 1])
		var first_width := float(points[segment_index].width) * path_width_scale
		var second_width := float(points[segment_index + 1].width) * path_width_scale
		var reach := maxf(first_width, second_width) * 0.5 + feather
		var x0 := clampi(floori((minf(first.x, second.x) - reach - origin.x) /
			cell_metres), 0, grid_size.x - 1)
		var x1 := clampi(ceili((maxf(first.x, second.x) + reach - origin.x) /
			cell_metres), 0, grid_size.x - 1)
		var z0 := clampi(floori((minf(first.z, second.z) - reach - origin.y) /
			cell_metres), 0, grid_size.y - 1)
		var z1 := clampi(ceili((maxf(first.z, second.z) + reach - origin.y) /
			cell_metres), 0, grid_size.y - 1)
		var start_xz := Vector2(first.x, first.z)
		var delta := Vector2(second.x - first.x, second.z - first.z)
		var length_squared := delta.length_squared()
		if length_squared <= 0.000001:
			continue
		for z_index in range(z0, z1 + 1):
			for x_index in range(x0, x1 + 1):
				var sample := Vector2(origin.x + float(x_index) * cell_metres,
					origin.y + float(z_index) * cell_metres)
				var amount := clampf((sample - start_xz).dot(delta) /
					length_squared, 0.0, 1.0)
				var nearest := start_xz + delta * amount
				var distance := sample.distance_to(nearest)
				var half_width := lerpf(first_width, second_width, amount) * 0.5
				if distance > half_width + feather:
					continue
				var weight := 1.0 if distance <= half_width else \
					_smooth_weight(1.0 - (distance - half_width) / \
					maxf(feather, 0.000001))
				if weight <= 0.0:
					continue
				var bed := lerpf(first.y, second.y, amount) - depth
				var index := z_index * grid_size.x + x_index
				if weight > best_weights[index] + 0.000001 or \
						(absf(weight - best_weights[index]) <= 0.000001 and
						bed < best_beds[index]):
					best_weights[index] = weight
					best_beds[index] = bed
	for index in sample_count:
		var weight := best_weights[index]
		if weight <= 0.0:
			continue
		var original := _effective_heights[index]
		var lowered := minf(original, best_beds[index])
		_effective_heights[index] = lerpf(original, lowered, weight)


func _build_preview_mesh() -> void:
	# One refresh may build dozens of chunk materials using the same few large
	# source textures. Share those digests, while making the next Inspector
	# refresh observe even a rapid same-size source edit.
	BIOME_BLEND_MATERIAL.begin_source_verification()
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var uvs := PackedVector2Array()
	var indices := PackedInt32Array()
	vertices.resize(grid_size.x * grid_size.y)
	normals.resize(vertices.size())
	uvs.resize(vertices.size())
	for z_index in grid_size.y:
		for x_index in grid_size.x:
			var index := z_index * grid_size.x + x_index
			vertices[index] = _point(x_index, z_index)
			var left := _height(maxi(0, x_index - 1), z_index)
			var right := _height(mini(grid_size.x - 1, x_index + 1), z_index)
			var back := _height(x_index, maxi(0, z_index - 1))
			var front := _height(x_index, mini(grid_size.y - 1, z_index + 1))
			normals[index] = Vector3(left - right, 2.0 * cell_metres,
				back - front).normalized()
			uvs[index] = Vector2(vertices[index].x, vertices[index].z) * \
				preview_uv_metres_inverse
	for z_index in grid_size.y - 1:
		for x_index in grid_size.x - 1:
			if not _cell_drawn(x_index, z_index):
				continue
			var index := z_index * grid_size.x + x_index
			indices.append_array(PackedInt32Array([index, index + 1,
				index + grid_size.x, index + 1, index + grid_size.x + 1, index + grid_size.x]))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TANGENT] = _generated_tangents(vertices, normals, uvs,
		indices)
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	if not _base_colors.is_empty():
		arrays[Mesh.ARRAY_COLOR] = _base_colors
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	var chunk_configs := _editor_biome_configs()
	if base_surface != null and base_surface.biome_blend_enabled and \
			not chunk_configs.is_empty():
		_build_chunked_preview_mesh(mesh, vertices, normals, uvs, chunk_configs)
	else:
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		mesh.surface_set_material(0,
			base_surface.get_material() if base_surface != null else null)
	var preview := get_node_or_null("__TerrainPreview") as MeshInstance3D
	if preview == null:
		preview = MeshInstance3D.new()
		preview.name = "__TerrainPreview"
		add_child(preview)
	preview.mesh = mesh
	preview.material_override = null


func _build_chunked_preview_mesh(mesh: ArrayMesh, vertices: PackedVector3Array,
		normals: PackedVector3Array, uvs: PackedVector2Array,
		configs: Array[Dictionary]) -> void:
	var usable_configs: Array[Dictionary] = []
	var materials: Array[Material] = []
	for config in configs:
		var material := BIOME_BLEND_MATERIAL.create_runtime(config,
			_continent_translation())
		if material != null:
			var region := get_parent() as Node3D
			var terrain_relative := region.global_transform.affine_inverse() * \
				global_transform if region != null else transform
			BIOME_BLEND_MATERIAL.set_terrain_to_continent(material,
				Transform3D(Basis.IDENTITY, _continent_translation()) * terrain_relative)
			usable_configs.append(config)
			materials.append(material)
	if usable_configs.is_empty():
		var fallback := _preview_arrays_for_all(vertices, normals, uvs)
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, fallback)
		mesh.surface_set_material(0,
			base_surface.get_material() if base_surface != null else null)
		return
	var cell_count := (grid_size.x - 1) * (grid_size.y - 1)
	var assignments := PackedInt32Array()
	assignments.resize(cell_count)
	assignments.fill(-1)
	var translation := _continent_translation()
	for config_index in usable_configs.size():
		var config := usable_configs[config_index]
		var chunk_origin := Vector2(float(config.origin[0]), float(config.origin[1]))
		var chunk_size := Vector2(float(config.innerSize[0]),
			float(config.innerSize[1])) * float(config.metresPerPixel)
		var first_x := maxi(0, ceili((chunk_origin.x - translation.x - origin.x) /
			cell_metres - 0.5))
		var last_x := mini(grid_size.x - 2, ceili((chunk_origin.x + chunk_size.x -
			translation.x - origin.x) / cell_metres - 0.5) - 1)
		var first_z := maxi(0, ceili((chunk_origin.y - translation.z - origin.y) /
			cell_metres - 0.5))
		var last_z := mini(grid_size.y - 2, ceili((chunk_origin.y + chunk_size.y -
			translation.z - origin.y) / cell_metres - 0.5) - 1)
		if first_x > last_x or first_z > last_z:
			continue
		for z_index in range(first_z, last_z + 1):
			for x_index in range(first_x, last_x + 1):
				assignments[z_index * (grid_size.x - 1) + x_index] = config_index
	var groups: Array = []
	groups.resize(usable_configs.size() + 1)
	for index in groups.size():
		groups[index] = []
	for z_index in grid_size.y - 1:
		for x_index in grid_size.x - 1:
			if not _cell_drawn(x_index, z_index):
				continue
			var assignment := assignments[z_index * (grid_size.x - 1) + x_index]
			groups[assignment + 1].append(Vector2i(x_index, z_index))
	for group_index in groups.size():
		if groups[group_index].is_empty():
			continue
		var surface_arrays := _preview_arrays_for_cells(groups[group_index],
			vertices, normals, uvs)
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, surface_arrays)
		var surface_index := mesh.get_surface_count() - 1
		mesh.surface_set_material(surface_index,
			base_surface.get_material() if group_index == 0 else materials[group_index - 1])


func _preview_arrays_for_all(vertices: PackedVector3Array,
		normals: PackedVector3Array, uvs: PackedVector2Array) -> Array:
	var cells: Array = []
	for z_index in grid_size.y - 1:
		for x_index in grid_size.x - 1:
			if _cell_drawn(x_index, z_index):
				cells.append(Vector2i(x_index, z_index))
	return _preview_arrays_for_cells(cells, vertices, normals, uvs)


func _preview_arrays_for_cells(cells: Array, vertices: PackedVector3Array,
		normals: PackedVector3Array, uvs: PackedVector2Array) -> Array:
	var result_vertices := PackedVector3Array()
	var result_normals := PackedVector3Array()
	var result_uvs := PackedVector2Array()
	var result_colors := PackedColorArray()
	var result_indices := PackedInt32Array()
	var remap := {}
	for cell: Vector2i in cells:
		var first := cell.y * grid_size.x + cell.x
		for source_index in [first, first + grid_size.x, first + 1,
				first + 1, first + grid_size.x, first + grid_size.x + 1]:
			if not remap.has(source_index):
				remap[source_index] = result_vertices.size()
				result_vertices.append(vertices[source_index])
				result_normals.append(normals[source_index])
				result_uvs.append(uvs[source_index])
				if not _base_colors.is_empty():
					result_colors.append(_base_colors[source_index])
			result_indices.append(int(remap[source_index]))
	# Match Godot's clockwise front faces while retaining vertex/UV order.
	for triangle_index in range(0, result_indices.size(), 3):
		var second := result_indices[triangle_index + 1]
		result_indices[triangle_index + 1] = result_indices[triangle_index + 2]
		result_indices[triangle_index + 2] = second
	var result := []
	result.resize(Mesh.ARRAY_MAX)
	result[Mesh.ARRAY_VERTEX] = result_vertices
	result[Mesh.ARRAY_NORMAL] = result_normals
	result[Mesh.ARRAY_TANGENT] = _generated_tangents(result_vertices,
		result_normals, result_uvs, result_indices)
	result[Mesh.ARRAY_TEX_UV] = result_uvs
	if not result_colors.is_empty():
		result[Mesh.ARRAY_COLOR] = result_colors
	result[Mesh.ARRAY_INDEX] = result_indices
	return result


func _editor_biome_configs() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	if not FileAccess.file_exists(BIOME_CATALOG_PATH):
		return result
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(
		BIOME_CATALOG_PATH))
	if not parsed is Dictionary or String(parsed.get("schema", "")) != \
			"eloria-biome-blend-catalog-v1" or not parsed.get("chunks") is Array:
		return result
	var region := get_parent()
	var region_id := String(region.get("region_id")) if region != null else ""
	var current_base := BIOME_BLEND_MATERIAL.surface_palette(base_surface,
		preview_uv_metres_inverse)
	if current_base.is_empty():
		return result
	var current_secondary: Variant = null
	if biome_palette.size() == 1 and _uses_script(biome_palette[0],
			BIOME_PALETTE_ENTRY):
		var entry: Resource = biome_palette[0]
		current_secondary = BIOME_BLEND_MATERIAL.surface_palette(entry.surface,
			preview_uv_metres_inverse)
		if not (current_secondary as Dictionary).is_empty():
			current_secondary["id"] = "%s:%s" % [region_id, entry.id]
			current_secondary["role"] = entry.role
	for raw_config in parsed.chunks:
		if not raw_config is Dictionary:
			continue
		var config: Dictionary = raw_config.duplicate(true)
		var contains_region := false
		for palette: Dictionary in config.get("palettes", []):
			if String(palette.get("id", "")) != "%s:base" % region_id:
				continue
			contains_region = true
			palette["base"] = current_base.duplicate(true)
			palette["secondary"] = current_secondary.duplicate(true) \
				if current_secondary is Dictionary else null
		if contains_region:
			result.append(config)
	return result


func _build_ground_region_previews() -> void:
	var old := get_node_or_null("__GroundRegionPreviews")
	if old != null:
		remove_child(old)
		old.queue_free()
	var container := Node3D.new()
	container.name = "__GroundRegionPreviews"
	add_child(container)
	var regions := _ground_regions()
	regions.sort_custom(func(a: Variant, b: Variant) -> bool:
		if a.priority == b.priority:
			return String(a.get_path()) < String(b.get_path())
		return a.priority < b.priority)
	for region_index in mini(regions.size(), 127):
		var region: Node3D = regions[region_index]
		if not region.enabled or not region.is_visible_in_tree() or region.surface == null:
			continue
		region.surface.enable_region_uv_projection(preview_uv_metres_inverse)
		var uv_offset := Vector2.ZERO
		if region.uv_anchor_continent_enabled:
			var source_translation: Vector3 = get_parent().get("continent_translation")
			uv_offset = Vector2(source_translation.x, source_translation.z) - region.uv_anchor_continent
		var bounds: Rect2 = region.world_bounds()
		if bounds.size.x <= 0.0 or bounds.size.y <= 0.0:
			continue
		var x0 := clampi(floori((bounds.position.x - global_position.x - origin.x) /
			cell_metres) - 1, 0, grid_size.x - 2)
		var x1 := clampi(ceili((bounds.end.x - global_position.x - origin.x) /
			cell_metres) + 1, 0, grid_size.x - 2)
		var z0 := clampi(floori((bounds.position.y - global_position.z - origin.y) /
			cell_metres) - 1, 0, grid_size.y - 2)
		var z1 := clampi(ceili((bounds.end.y - global_position.z - origin.y) /
			cell_metres) + 1, 0, grid_size.y - 2)
		var vertices := PackedVector3Array()
		var normals := PackedVector3Array()
		var uvs := PackedVector2Array()
		var indices := PackedInt32Array()
		for z_index in range(z0, z1 + 1):
			for x_index in range(x0, x1 + 1):
				if region.clip_polygon.is_empty() and not _cell_drawn(x_index, z_index):
					continue
				var p00 := _point(x_index, z_index) + Vector3.UP * 0.008
				var p10 := _point(x_index + 1, z_index) + Vector3.UP * 0.008
				var p01 := _point(x_index, z_index + 1) + Vector3.UP * 0.008
				var p11 := _point(x_index + 1, z_index + 1) + Vector3.UP * 0.008
				var quad := PackedVector3Array([p00, p01, p10, p10, p01, p11])
				var normal0 := (p01 - p00).cross(p10 - p00).normalized()
				var normal1 := (p01 - p10).cross(p11 - p10).normalized()
				for vertex in quad:
					indices.append(vertices.size())
					vertices.append(vertex)
					uvs.append((Vector2(vertex.x, vertex.z) + uv_offset) *
						preview_uv_metres_inverse)
				for unused in 3:
					normals.append(normal0)
				for unused in 3:
					normals.append(normal1)
		if vertices.is_empty():
			continue
		for triangle_index in range(0, indices.size(), 3):
			var second := indices[triangle_index + 1]
			indices[triangle_index + 1] = indices[triangle_index + 2]
			indices[triangle_index + 2] = second
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = vertices
		arrays[Mesh.ARRAY_NORMAL] = normals
		arrays[Mesh.ARRAY_TANGENT] = _generated_tangents(vertices, normals, uvs,
			indices)
		arrays[Mesh.ARRAY_TEX_UV] = uvs
		arrays[Mesh.ARRAY_INDEX] = indices
		var mesh := ArrayMesh.new()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		var instance := MeshInstance3D.new()
		instance.name = "GroundRegion_%s" % region.region_id
		instance.mesh = mesh
		instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		var projected: Variant = region.projected_world_to_local()
		if projected == null:
			continue
		instance.material_override = GROUND_REGION_MATERIAL.create(region.surface,
			projected as Transform2D, region.size * 0.5, region.shape,
			region.blend_width, region.opacity, -128 + (region.source_layer_ordinal if region.source_layer_ordinal >= 0 else region_index), region.clip_polygon)
		if instance.material_override != null:
			container.add_child(instance)


## The preview's cell mask (1 = drawn) from preview_clip_inside and preview_clip_outside, one byte per grid cell in
## row-major order; empty when nothing is clipped. Each row is scanned once per polygon (even-odd crossings of the
## row's cell-centre line), so a whole-group grid is masked in a few milliseconds.
func preview_clip_mask() -> PackedByteArray:
	var mask := PackedByteArray()
	var inside_polygons: Array[PackedVector2Array] = preview_clip_polygons
	if inside_polygons.is_empty() and preview_clip_inside.size() >= 3:
		inside_polygons = [preview_clip_inside]
	var inside_used := not inside_polygons.is_empty()
	var outside_used := false
	for polygon in preview_clip_outside:
		outside_used = outside_used or polygon.size() >= 3
	if not inside_used and not outside_used:
		return mask
	var columns := grid_size.x - 1
	var rows := grid_size.y - 1
	mask.resize(columns * rows)
	mask.fill(0 if inside_used else 1)
	var translation := _continent_translation()
	var x0 := origin.x + translation.x + 0.5 * cell_metres
	var z0 := origin.y + translation.z + 0.5 * cell_metres
	if inside_used:
		for polygon in inside_polygons:
			if polygon.size() >= 3:
				_mark_polygon(mask, polygon, x0, z0, columns, rows, 1)
	for polygon in preview_clip_outside:
		if polygon.size() >= 3:
			_mark_polygon(mask, polygon, x0, z0, columns, rows, 0)
	return mask


func _mark_polygon(mask: PackedByteArray, polygon: PackedVector2Array, x0: float, z0: float, columns: int,
		rows: int, value: int) -> void:
	for z_index in rows:
		var z := z0 + float(z_index) * cell_metres
		var crossings: Array[float] = []
		for i in polygon.size():
			var a := polygon[i]
			var b := polygon[(i + 1) % polygon.size()]
			if (a.y > z) != (b.y > z):
				crossings.append(a.x + (z - a.y) * (b.x - a.x) / (b.y - a.y))
		crossings.sort()
		for pair in range(0, crossings.size() - 1, 2):
			var first := maxi(0, ceili((crossings[pair] - x0) / cell_metres))
			var last := mini(columns - 1, ceili((crossings[pair + 1] - x0) / cell_metres) - 1)
			for x_index in range(first, last + 1):
				mask[z_index * columns + x_index] = value


func _cell_drawn(x_index: int, z_index: int) -> bool:
	return _clip_mask.is_empty() or _clip_mask[z_index * (grid_size.x - 1) + x_index] == 1


func _clear_preview() -> void:
	var preview := get_node_or_null("__TerrainPreview") as MeshInstance3D
	if preview != null:
		preview.mesh = null
	var ground := get_node_or_null("__GroundRegionPreviews")
	if ground != null:
		ground.queue_free()


func _height(x_index: int, z_index: int) -> float:
	return _effective_heights[z_index * grid_size.x + x_index]


func _point(x_index: int, z_index: int) -> Vector3:
	return Vector3(origin.x + float(x_index) * cell_metres,
		_height(x_index, z_index), origin.y + float(z_index) * cell_metres)


func _generated_tangents(vertices: PackedVector3Array,
		normals: PackedVector3Array, uvs: PackedVector2Array,
		indices: PackedInt32Array) -> PackedFloat32Array:
	var tangent_accum := PackedVector3Array()
	var bitangent_accum := PackedVector3Array()
	tangent_accum.resize(vertices.size())
	bitangent_accum.resize(vertices.size())
	for triangle_index in range(0, indices.size(), 3):
		var a := indices[triangle_index]
		var b := indices[triangle_index + 1]
		var c := indices[triangle_index + 2]
		var edge1 := vertices[b] - vertices[a]
		var edge2 := vertices[c] - vertices[a]
		var uv1 := uvs[b] - uvs[a]
		var uv2 := uvs[c] - uvs[a]
		var determinant := uv1.x * uv2.y - uv1.y * uv2.x
		if absf(determinant) <= 0.000000001:
			continue
		var reciprocal := 1.0 / determinant
		var tangent := (edge1 * uv2.y - edge2 * uv1.y) * reciprocal
		var bitangent := (edge2 * uv1.x - edge1 * uv2.x) * reciprocal
		for index in [a, b, c]:
			tangent_accum[index] += tangent
			bitangent_accum[index] += bitangent
	var tangents := PackedFloat32Array()
	for index in vertices.size():
		var normal := normals[index]
		var tangent := tangent_accum[index] - normal * normal.dot(
			tangent_accum[index])
		if tangent.length_squared() <= 0.0000000001:
			tangent = Vector3.RIGHT - normal * normal.x
			if tangent.length_squared() <= 0.0000000001:
				tangent = Vector3.FORWARD - normal * normal.z
		tangent = tangent.normalized()
		var handedness := -1.0 if normal.cross(tangent).dot(
			bitangent_accum[index]) < 0.0 else 1.0
		tangents.append_array(PackedFloat32Array([
			tangent.x, tangent.y, tangent.z, handedness]))
	return tangents


func _current_signature() -> Array:
	var patches: Array = []
	var container := get_node_or_null("Patches")
	if container != null:
		for child in container.get_children():
			if _uses_script(child, PATCH_SCRIPT):
				patches.append([child.patch_id, child.transform, child.shape,
					child.operation, child.size, child.feather, child.height_value,
					child.enabled])
	var paths: Array = []
	for path in _region_paths():
		paths.append([path.path_id, path.kind, path.transform, path.properties,
			path.snapshot_points(), path.width_signature()])
	var grounds: Array = []
	for region in _ground_regions():
		grounds.append([region.region_id, region.region_signature()])
	return [origin, cell_metres, grid_size, base_heights_path,
		FileAccess.get_sha256(ProjectSettings.globalize_path(base_heights_path))
			if not base_heights_path.is_empty() and FileAccess.file_exists(
				ProjectSettings.globalize_path(base_heights_path)) else "",
		base_colors_path,
		FileAccess.get_sha256(ProjectSettings.globalize_path(base_colors_path))
			if not base_colors_path.is_empty() and FileAccess.file_exists(
				ProjectSettings.globalize_path(base_colors_path)) else "",
		base_surface.signature() if base_surface != null else [],
		sculpt_layer.signature() if sculpt_layer != null and \
			sculpt_layer.get_script() == SCULPT_LAYER else [],
		_palette_signature(),
		FileAccess.get_sha256(ProjectSettings.globalize_path(BIOME_CATALOG_PATH))
			if FileAccess.file_exists(ProjectSettings.globalize_path(
				BIOME_CATALOG_PATH)) else "",
		preview_enabled,
		preview_uv_metres_inverse, patches, paths, grounds, preview_clip_inside, preview_clip_outside, preview_clip_polygons]


func _region_paths() -> Array:
	var result: Array = []
	var region_root := get_parent()
	if region_root == null:
		return result
	for container_name in ["Roads", "Rivers"]:
		var container := region_root.get_node_or_null(NodePath(container_name))
		if container == null:
			continue
		for child in container.get_children():
			if _uses_script(child, PATH_SCRIPT):
				result.append(child)
	return result


func _ground_regions() -> Array:
	var result: Array = []
	var region_root := get_parent()
	var container := region_root.get_node_or_null("Ground/Regions") if region_root != null else null
	if container == null:
		return result
	for child in container.get_children():
		if _uses_script(child, GROUND_SCRIPT):
			result.append(child)
	return result


func _uses_script(value: Variant, script: Script) -> bool:
	return value is Object and (value as Object).get_script() == script


func _record_point(record: Dictionary) -> Vector3:
	var raw: Array = record.position
	return Vector3(float(raw[0]), float(raw[1]), float(raw[2]))


func _smooth_weight(value: float) -> float:
	var amount := clampf(value, 0.0, 1.0)
	return amount * amount * (3.0 - 2.0 * amount)


func _sync_surface() -> void:
	if base_surface != null:
		base_surface = base_surface.duplicate(true) as MapAuthoringSurface
		base_surface.resource_local_to_scene = true
		base_surface.enable_region_uv_projection(preview_uv_metres_inverse)
	_bound_surface = base_surface


func _sync_sculpt_layer() -> void:
	if sculpt_layer != null and sculpt_layer != _bound_sculpt_layer:
		sculpt_layer = sculpt_layer.duplicate(true)
		sculpt_layer.resource_local_to_scene = true
	_bound_sculpt_layer = sculpt_layer


func _sync_palette() -> void:
	if biome_palette == _bound_palette_entries:
		for entry in biome_palette:
			if _uses_script(entry, BIOME_PALETTE_ENTRY):
				entry.bind_local_surface()
				if entry.surface != null:
					entry.surface.enable_region_uv_projection(
						preview_uv_metres_inverse)
		return
	var localized: Array[Resource] = []
	for raw in biome_palette:
		if not _uses_script(raw, BIOME_PALETTE_ENTRY):
			localized.append(raw)
			continue
		var entry: Resource = raw.duplicate(true)
		entry.resource_local_to_scene = true
		entry.bind_local_surface()
		if entry.surface != null:
			entry.surface.enable_region_uv_projection(preview_uv_metres_inverse)
		localized.append(entry)
	biome_palette = localized
	_bound_palette_entries = biome_palette.duplicate()


func _palette_signature() -> Array:
	var result: Array = []
	for entry in biome_palette:
		result.append(entry.signature() if _uses_script(entry,
			BIOME_PALETTE_ENTRY) else [])
	return result


func _continent_translation() -> Vector3:
	var region := get_parent()
	if region != null:
		var value: Variant = region.get("continent_translation")
		if value is Vector3:
			return value
	return Vector3.ZERO


func _get_configuration_warnings() -> PackedStringArray:
	var warnings := PackedStringArray()
	if not last_error.is_empty():
		warnings.append(last_error)
	if base_surface == null:
		warnings.append("Terrain needs a local Base Surface before export.")
	if biome_palette.size() > 1:
		warnings.append("Biome Palette supports one secondary surface per region.")
	for entry in biome_palette:
		if not _uses_script(entry, BIOME_PALETTE_ENTRY):
			warnings.append("Biome Palette entries must use MapAuthoringBiomePaletteEntry.")
		elif String(entry.id).strip_edges().is_empty() or entry.surface == null:
			warnings.append("Each Biome Palette entry needs a stable Id and Surface.")
	if _catalog_role_is_stale():
		warnings.append("Biome Palette Role changed. Bake/rebuild masks to preview its new area.")
	return warnings


func _catalog_role_is_stale() -> bool:
	if biome_palette.size() != 1 or not _uses_script(biome_palette[0],
			BIOME_PALETTE_ENTRY):
		return false
	var entry: Resource = biome_palette[0]
	if not FileAccess.file_exists(ProjectSettings.globalize_path(BIOME_CATALOG_PATH)):
		return false
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(
		BIOME_CATALOG_PATH))
	if not parsed is Dictionary or not parsed.get("chunks") is Array:
		return false
	for config in parsed.chunks:
		if not config is Dictionary:
			continue
		for palette: Dictionary in config.get("palettes", []):
			if String(palette.get("id", "")) == "%s:base" % String(
					get_parent().get("region_id")):
				var catalog_secondary: Variant = palette.get("secondary")
				return not catalog_secondary is Dictionary or String(
					catalog_secondary.get("role", "")) != String(entry.role)
	return false
