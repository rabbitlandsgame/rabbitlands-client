@tool
class_name MapAuthoringReferencePreview
extends Node3D

signal status_changed(message: String)

const HOST_NAME := "__TerritoryReferenceHost"
const GEOMETRY := preload("res://addons/map_authoring_workspace/ownership_geometry.gd")
const OWNERSHIP := preload("res://src/dev/map_authoring_region/ownership_source.gd")
const ACTIVE_CLIP_NAME := "ActiveOwnedTerrain"
const BOUNDARY_SAMPLE_METRES := 2.0
const PUBLISHED_HEIGHT_BIN_METRES := 8.0
const BIOME_BLEND_MATERIAL := preload("res://src/world/biome_blend_material.gd")

var active_root: Node3D
var active_entry: Dictionary = {}
var _references: Dictionary = {}
var _source_visibility: Dictionary = {}
var _source_mesh_ids: Dictionary = {}
var _cache: Dictionary = {}
var _cache_order := PackedStringArray()
var _generation := 0
var _sculpt_preview_active := false


func configure(root: Node3D, entry: Dictionary) -> void:
	clear()
	active_root = root
	active_entry = entry.duplicate(true)
	name = HOST_NAME
	set_meta(&"map_authoring_reference_host", true)


func clear() -> void:
	set_sculpt_preview_active(false)
	_generation += 1
	_restore_sources()
	for child in get_children():
		remove_child(child)
		child.queue_free()
	_references.clear()
	_source_mesh_ids.clear()
	active_root = null
	active_entry.clear()


func set_references(entries: Array[Dictionary]) -> void:
	_generation += 1
	var generation := _generation
	_restore_sources()
	for child in get_children():
		remove_child(child)
		child.queue_free()
	_references.clear()
	if entries.is_empty() or active_root == null:
		status_changed.emit("Neighbour references hidden.")
		return
	var active_error := _validate_authored(active_root, active_entry)
	if not active_error.is_empty():
		status_changed.emit(active_error)
		return
	await get_tree().process_frame
	if generation != _generation:
		return
	if not _add_owned_terrain(active_root, active_entry, ACTIVE_CLIP_NAME, false):
		status_changed.emit("Active territory terrain preview is not ready; refresh it and try again.")
		return
	_add_boundary(active_root, active_entry)
	var failures := PackedStringArray()
	for entry in entries:
		if String(entry.id) == String(active_entry.id):
			continue
		var failure := await _add_reference(entry, generation)
		if generation != _generation:
			return
		if not failure.is_empty():
			failures.append(failure)
	_synchronize_live_biome_palettes()
	status_changed.emit("Showing %d read-only reference%s.%s" % [
		_references.size(), "" if _references.size() == 1 else "s",
		" " + " ".join(failures) if not failures.is_empty() else ""])


func source_state() -> Dictionary:
	return {
		"reference_ids": _references.keys(),
		"hidden_source_count": _source_visibility.size(),
		"active_id": String(active_entry.get("id", "")),
	}


func refresh_if_changed() -> bool:
	if _sculpt_preview_active:
		return false
	if active_root == null or _references.is_empty():
		return false
	var source := active_root.get_node_or_null("Terrain/__TerrainPreview") as MeshInstance3D
	var mesh_id := source.mesh.get_instance_id() if source != null and source.mesh != null else 0
	if int(_source_mesh_ids.get(String(active_entry.id), 0)) == mesh_id:
		return false
	var selected: Array[Dictionary] = []
	for value: Variant in _references.values():
		if value is Dictionary:
			selected.append((value as Dictionary).entry)
	set_references(selected)
	return true


## A brush rebuilds the source mesh repeatedly. Show that fresh mesh directly
## during the stroke and defer ownership clipping until the one final refresh.
func set_sculpt_preview_active(active: bool) -> void:
	_sculpt_preview_active = active
	if active_root == null:
		return
	var source := active_root.get_node_or_null(
		"Terrain/__TerrainPreview") as MeshInstance3D
	if source != null and _source_visibility.has(source.get_instance_id()):
		source.visible = active
	for child in get_children(true):
		if child is Node3D and (String(child.name).begins_with("Owned_") or
				String(child.name).begins_with("OwnedTerrain_") or
				String(child.name).begins_with("Reference_") or
				String(child.name) == ACTIVE_CLIP_NAME):
			(child as Node3D).visible = not active


func _add_reference(entry: Dictionary, generation: int) -> String:
	var source_path := String(entry.get("source_path", ""))
	var is_authored := String(entry.source_kind) == "saved_authored"
	var source_error := String(entry.get("source_error", ""))
	if not source_error.is_empty():
		return "%s: %s" % [String(entry.label), source_error]
	if source_path.is_empty() or (not ResourceLoader.exists(source_path) if is_authored \
			else not _published_paths_available(entry)):
		return "%s source is unavailable." % String(entry.label)
	var packed := _cache.get(String(entry.get("cache_key", source_path))) as PackedScene
	if packed == null:
		packed = _load_source(entry, is_authored)
		if packed == null:
			return "%s could not load its declared %s." % [String(entry.label),
				"saved authored scene" if is_authored else "published GLB dependencies"]
		_store_cache(String(entry.get("cache_key", source_path)), packed)
	var instance := packed.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE) as Node3D
	if instance == null:
		return "%s source is not a Node3D scene." % String(entry.label)
	instance.name = "Reference_%s" % String(entry.id)
	instance.position = _relative_translation(entry)
	instance.set_meta(&"map_authoring_reference", true)
	add_child(instance, false, Node.INTERNAL_MODE_FRONT)
	await get_tree().process_frame
	if generation != _generation:
		remove_child(instance)
		instance.queue_free()
		return ""
	if String(entry.source_kind) == "saved_authored":
		var validation := _validate_authored(instance, entry)
		if not validation.is_empty():
			remove_child(instance)
			instance.queue_free()
			return validation
		_hide_authoring_controls(instance)
		if not _add_owned_terrain(instance, entry, "OwnedTerrain_%s" % String(entry.id), true):
			remove_child(instance)
			instance.queue_free()
			return "%s authored terrain preview is unavailable." % String(entry.label)
	else:
		_style_reference_geometry(instance)
		if not _add_published_owned_surfaces(instance, entry):
			remove_child(instance)
			instance.queue_free()
			return "%s published terrain could not be ownership-clipped." % String(entry.label)
	var boundary_coverage := _add_boundary(instance, entry)
	var live_biome_palette := {}
	if String(entry.source_kind) == "saved_authored":
		_collect_live_biome_palette(instance, live_biome_palette)
		_strip_reference_scripts(instance)
	instance.process_mode = Node.PROCESS_MODE_DISABLED
	_references[String(entry.id)] = {
		"entry": entry.duplicate(true),
		"node": instance,
		"boundary_coverage": boundary_coverage,
		"biome_palette": live_biome_palette,
	}
	return ""


func _synchronize_live_biome_palettes() -> void:
	BIOME_BLEND_MATERIAL.begin_source_verification()
	var overrides := {}
	_collect_live_biome_palette(active_root, overrides)
	for value: Variant in _references.values():
		if value is Dictionary:
			overrides.merge((value as Dictionary).get("biome_palette", {}) as Dictionary,
				true)
	if overrides.is_empty():
		return
	for child in get_children(true):
		if not child is MeshInstance3D:
			continue
		var mesh := (child as MeshInstance3D).mesh
		if mesh == null:
			continue
		for surface_index in mesh.get_surface_count():
			var material := mesh.surface_get_material(surface_index) as ShaderMaterial
			if material == null or material.resource_name != "continent_biome_blend" or \
					not material.has_meta(&"biome_blend_config"):
				continue
			var config: Dictionary = material.get_meta(&"biome_blend_config")
			var patched := BIOME_BLEND_MATERIAL.with_palette_overrides(config,
				overrides)
			var replacement := BIOME_BLEND_MATERIAL.create_runtime(patched,
				Vector3.ZERO)
			if replacement == null:
				continue
			var to_continent: Transform3D = material.get_shader_parameter(
				&"terrain_to_continent")
			BIOME_BLEND_MATERIAL.set_terrain_to_continent(replacement, to_continent)
			mesh.surface_set_material(surface_index, replacement)


static func _collect_live_biome_palette(region: Node3D,
		result: Dictionary) -> void:
	if region == null:
		return
	var terrain := region.get_node_or_null("Terrain")
	if terrain == null or not terrain.has_method("live_biome_palette"):
		return
	result.merge(terrain.call("live_biome_palette") as Dictionary, true)


func _load_source(entry: Dictionary, is_authored: bool) -> PackedScene:
	var source_path := String(entry.get("source_path", ""))
	if is_authored:
		return ResourceLoader.load(source_path, "PackedScene",
			ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	var paths: PackedStringArray = entry.get("published_paths",
		PackedStringArray([source_path]))
	if paths.is_empty():
		return null
	if paths.size() == 1:
		var generated := _load_published_glb(paths[0])
		if generated == null:
			return null
		var packed := PackedScene.new()
		if packed.pack(generated) != OK:
			generated.free()
			return null
		generated.free()
		return packed
	var roots: Array[Node3D] = []
	for path: String in paths:
		var generated := _load_published_glb(path)
		if generated == null:
			for root: Node3D in roots:
				root.free()
			return null
		roots.append(generated)
	return _pack_published_roots(roots)


func _load_published_glb(source_path: String) -> Node3D:
	var state := GLTFState.new()
	var document := GLTFDocument.new()
	if document.append_from_file(ProjectSettings.globalize_path(source_path), state) != OK:
		return null
	return document.generate_scene(state) as Node3D


func _pack_published_roots(roots: Array[Node3D]) -> PackedScene:
	if roots.is_empty():
		return null
	var combined := Node3D.new()
	combined.name = "PublishedChunks"
	for index in roots.size():
		var chunk := roots[index]
		chunk.name = "PublishedChunk_%03d" % index
		combined.add_child(chunk, true)
		_assign_owner(chunk, combined)
	var packed := PackedScene.new()
	if packed.pack(combined) != OK:
		combined.free()
		return null
	combined.free()
	return packed


func _assign_owner(node: Node, owner: Node) -> void:
	node.owner = owner
	for child in node.get_children():
		_assign_owner(child, owner)


func _published_paths_available(entry: Dictionary) -> bool:
	var paths: PackedStringArray = entry.get("published_paths", PackedStringArray())
	if paths.is_empty():
		paths.append(String(entry.get("source_path", "")))
	for path: String in paths:
		if path.is_empty() or not FileAccess.file_exists(path):
			return false
	return true


func clear_source_cache() -> void:
	_cache.clear()
	_cache_order.clear()


func _store_cache(key: String, packed: PackedScene) -> void:
	_cache[key] = packed
	_cache_order.erase(key)
	_cache_order.append(key)
	while _cache_order.size() > 24:
		_cache.erase(_cache_order[0])
		_cache_order.remove_at(0)


func _validate_authored(root: Node3D, entry: Dictionary) -> String:
	if root == null or String(root.get("region_id")) != String(entry.id):
		return "%s authored scene has the wrong region ID." % String(entry.label)
	if not OWNERSHIP.entry_error(root, entry).is_empty():
		return "%s ownership polygon does not match its saved authored scene; reference hidden." % \
			String(entry.label)
	return ""


func _relative_translation(entry: Dictionary) -> Vector3:
	var reference_translation: Vector3 = entry.translation
	var active_translation_value: Vector3 = active_entry.translation
	return relative_translation(reference_translation, active_translation_value)


static func relative_translation(reference: Vector3, active: Vector3) -> Vector3:
	return reference - active


func _add_owned_terrain(region: Node3D, entry: Dictionary, display_name: String,
		reference_style: bool) -> bool:
	var source := region.get_node_or_null("Terrain/__TerrainPreview") as MeshInstance3D
	if source == null or source.mesh == null:
		return false
	var mesh := clipped_mesh(source, active_root, GEOMETRY.from_entry(entry),
		active_entry.translation)
	if mesh == null or mesh.get_surface_count() == 0:
		return false
	_hide_source(source)
	var display := MeshInstance3D.new()
	display.name = display_name
	display.mesh = mesh
	display.transform = global_transform.affine_inverse() * source.global_transform
	display.material_override = source.material_override
	display.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF \
		if reference_style else source.cast_shadow
	display.transparency = 0.28 if reference_style else source.transparency
	add_child(display, false, Node.INTERNAL_MODE_FRONT)
	_source_mesh_ids[String(entry.id)] = source.mesh.get_instance_id()
	return true


func _add_published_owned_surfaces(region: Node3D, entry: Dictionary) -> bool:
	var clipped_count := 0
	var claimed_water_exclusions := _active_claimed_water_exclusions()
	var terrain_material := StandardMaterial3D.new()
	terrain_material.albedo_color = Color(0.46, 0.39, 0.56, 0.92)
	terrain_material.roughness = 0.9
	terrain_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	var water_material := StandardMaterial3D.new()
	water_material.albedo_color = Color(0.18, 0.52, 0.68, 0.78)
	water_material.roughness = 0.35
	water_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	for child in region.find_children("*", "MeshInstance3D", true, false):
		var source := child as MeshInstance3D
		var source_name := String(source.name)
		if not source_name.begins_with("Terrain_") and \
				not source_name.begins_with("Water_"):
			continue
		var mesh := clipped_mesh(source, active_root, GEOMETRY.from_entry(entry),
			active_entry.translation, claimed_water_exclusions \
				if source_name.begins_with("Water_") else [])
		_hide_source(source)
		if mesh == null or mesh.get_surface_count() == 0:
			continue
		var display := MeshInstance3D.new()
		display.name = "Owned_%s" % source_name
		display.mesh = mesh
		display.transform = global_transform.affine_inverse() * source.global_transform
		display.material_override = water_material if source_name.begins_with("Water_") \
			else terrain_material
		display.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		display.transparency = 0.08
		add_child(display, false, Node.INTERNAL_MODE_FRONT)
		clipped_count += 1
	return clipped_count > 0


func _active_claimed_water_exclusions() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	if active_root == null:
		return result
	var owned_value: Variant = active_root.get("owned_plan_feature_ids")
	if not owned_value is PackedStringArray:
		return result
	var owned: PackedStringArray = owned_value
	var stable_value: Variant = active_entry.get("claimed_plan_feature_footprints", {})
	if stable_value is Dictionary:
		var stable: Dictionary = stable_value
		for claim_id: String in owned:
			var polygon_value: Variant = stable.get(claim_id)
			if not polygon_value is PackedVector2Array or polygon_value.size() < 3:
				continue
			var polygon: PackedVector2Array = polygon_value
			result.append({
				"claim_id": claim_id,
				"polygon": polygon,
				"bounds": _polygon_bounds(polygon),
				"source": "certified_original",
			})
	for child in active_root.find_children("*", "Path3D", true, false):
		var path := child as Path3D
		if not path.has_method("snapshot_points") or String(path.get("kind")) != "river":
			continue
		var claim_id := String(path.get("replaces_plan_feature_id")).strip_edges()
		if claim_id.is_empty() or not owned.has(claim_id):
			continue
		if path.get("preview_enabled") is bool and not bool(path.get("preview_enabled")):
			continue
		var polygon := _path_corridor_global(path, path.call("snapshot_points"))
		if polygon.size() < 3:
			continue
		result.append({
			"claim_id": claim_id,
			"polygon": polygon,
			"bounds": _polygon_bounds(polygon),
			"source": "saved_current",
		})
	return result


func _path_corridor_global(path: Path3D, points: Array) -> PackedVector2Array:
	if points.size() < 2:
		return PackedVector2Array()
	var centres := PackedVector2Array()
	var half_widths := PackedFloat32Array()
	var path_to_active := active_root.global_transform.affine_inverse() * path.global_transform
	var active_translation_value: Vector3 = active_entry.translation
	for record_value: Variant in points:
		if not record_value is Dictionary:
			return PackedVector2Array()
		var record: Dictionary = record_value
		var raw: Array = record.get("position", [])
		if raw.size() != 3:
			return PackedVector2Array()
		var active_point := path_to_active * Vector3(float(raw[0]), float(raw[1]),
			float(raw[2]))
		centres.append(Vector2(active_point.x + active_translation_value.x,
			active_point.z + active_translation_value.z))
		half_widths.append(maxf(0.0, float(record.get("width", 0.0))) * 0.5)
	var left := PackedVector2Array()
	var right := PackedVector2Array()
	for index in centres.size():
		var previous := centres[maxi(0, index - 1)]
		var following := centres[mini(centres.size() - 1, index + 1)]
		var tangent := (following - previous).normalized()
		if tangent.length_squared() <= 0.000001:
			return PackedVector2Array()
		var side := Vector2(-tangent.y, tangent.x) * half_widths[index]
		left.append(centres[index] + side)
		right.append(centres[index] - side)
	var polygon := left
	for index in range(right.size() - 1, -1, -1):
		polygon.append(right[index])
	return polygon


func _hide_source(source: GeometryInstance3D) -> void:
	var key := source.get_instance_id()
	if not _source_visibility.has(key):
		_source_visibility[key] = {"node": source, "visible": source.visible}
	source.visible = false


func _restore_sources() -> void:
	for value: Variant in _source_visibility.values():
		if value is Dictionary and is_instance_valid(value.node):
			(value.node as GeometryInstance3D).visible = bool(value.visible)
	_source_visibility.clear()


func _hide_authoring_controls(root: Node3D) -> void:
	var gameplay := root.get_node_or_null("Gameplay") as Node3D
	if gameplay != null:
		gameplay.visible = false
	for marker in root.find_children("*", "Marker3D", true, false):
		(marker as Marker3D).visible = false
	root.remove_from_group(&"map_authoring_region")
	_style_reference_geometry(root)


func _style_reference_geometry(root: Node3D) -> void:
	for child in root.find_children("*", "GeometryInstance3D", true, false):
		var geometry := child as GeometryInstance3D
		if not bool(geometry.get_meta(&"map_authoring_owned_terrain", false)):
			geometry.transparency = maxf(geometry.transparency, 0.28)
		geometry.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF


func _strip_reference_scripts(root: Node) -> void:
	for child in root.find_children("*", "", true, false):
		if child.get_script() != null:
			child.set_script(null)
	if root.get_script() != null:
		root.set_script(null)


func _add_boundary(region: Node3D, entry: Dictionary) -> Dictionary:
	var entry_translation: Vector3 = entry.translation
	var active_translation_value: Vector3 = active_entry.translation
	var vertices := PackedVector3Array()
	var terrain := region.get_node_or_null("Terrain")
	var published_sampler := _published_height_sampler(region) if terrain == null else {}
	var sample_count := 0
	var matched_count := 0
	var missing_count := 0
	for polygon in GEOMETRY.from_entry(entry):
		for index in polygon.size():
			var first: Vector2 = polygon[index]
			var second: Vector2 = polygon[(index + 1) % polygon.size()]
			var steps := maxi(1, ceili(first.distance_to(second) / BOUNDARY_SAMPLE_METRES))
			var previous := Vector3.ZERO
			var previous_valid := false
			for step in steps + 1:
				var point := first.lerp(second, float(step) / float(steps))
				var local: Vector2 = point - Vector2(entry_translation.x,
					entry_translation.z)
				var sampled_height := NAN
				if terrain != null and terrain.has_method("height_at_local"):
					sampled_height = terrain.call("height_at_local", local.x, local.y)
				elif not published_sampler.is_empty():
					sampled_height = _sample_published_height(point, published_sampler)
				sample_count += 1
				if is_nan(sampled_height):
					missing_count += 1
					previous_valid = false
					continue
				matched_count += 1
				var current := Vector3(point.x - active_translation_value.x,
					sampled_height + 0.15, point.y - active_translation_value.z)
				if previous_valid:
					vertices.append(previous)
					vertices.append(current)
				previous = current
				previous_valid = true
	var coverage := {
		"samples": sample_count,
		"matched": matched_count,
		"missing": missing_count,
		"segments": vertices.size() / 2,
	}
	if missing_count > 0:
		push_warning("%s ownership boundary sampled %d/%d terrain points; unavailable spans were omitted." % [
			String(entry.label), matched_count, sample_count])
	if vertices.is_empty():
		return coverage
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_LINES, arrays)
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_color = Color(0.18, 0.9, 1.0, 0.9)
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.no_depth_test = true
	mesh.surface_set_material(0, material)
	var boundary := MeshInstance3D.new()
	boundary.name = "OwnershipBoundary_%s" % String(entry.id)
	boundary.mesh = mesh
	boundary.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	boundary.set_meta(&"map_authoring_boundary_coverage", coverage)
	add_child(boundary, false, Node.INTERNAL_MODE_FRONT)
	return coverage


func _published_height_map(region: Node3D) -> Dictionary:
	var result := {}
	for child in region.find_children("*", "MeshInstance3D", true, false):
		var source := child as MeshInstance3D
		if not String(source.name).begins_with("Terrain_") and \
				not String(source.name).begins_with("Water_"):
			continue
		if source.mesh == null:
			continue
		var source_to_active := active_root.global_transform.affine_inverse() * \
			source.global_transform
		for surface_index in source.mesh.get_surface_count():
			var arrays: Array = source.mesh.surface_get_arrays(surface_index)
			var source_vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			for vertex in source_vertices:
				var active_point := source_to_active * vertex
				var global_point := Vector2(active_point.x + active_entry.translation.x,
					active_point.z + active_entry.translation.z)
				var key := _height_key(global_point)
				result[key] = maxf(float(result.get(key, -INF)), active_point.y)
	return result


func _published_height_sampler(region: Node3D) -> Dictionary:
	var sampler := {
		"vertices": _published_height_map(region),
		"triangles": [],
		"bins": {},
	}
	var triangles: Array = sampler.triangles
	var bins: Dictionary = sampler.bins
	for child in region.find_children("*", "MeshInstance3D", true, false):
		var source := child as MeshInstance3D
		var source_name := String(source.name)
		if (not source_name.begins_with("Terrain_") and \
				not source_name.begins_with("Water_")) or source.mesh == null:
			continue
		var source_to_active := active_root.global_transform.affine_inverse() * \
			source.global_transform
		for surface_index in source.mesh.get_surface_count():
			var arrays: Array = source.mesh.surface_get_arrays(surface_index)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] \
				if arrays[Mesh.ARRAY_INDEX] is PackedInt32Array else PackedInt32Array()
			if indices.is_empty():
				indices.resize(vertices.size())
				for vertex_index in vertices.size():
					indices[vertex_index] = vertex_index
			for offset in range(0, indices.size() - 2, 3):
				var triangle := PackedVector3Array()
				for corner in 3:
					var active_point := source_to_active * vertices[indices[offset + corner]]
					triangle.append(Vector3(
						active_point.x + active_entry.translation.x,
						active_point.y,
						active_point.z + active_entry.translation.z))
				var projected := PackedVector2Array([
					Vector2(triangle[0].x, triangle[0].z),
					Vector2(triangle[1].x, triangle[1].z),
					Vector2(triangle[2].x, triangle[2].z)])
				if _barycentric(projected[0], projected) == null:
					continue
				var triangle_index := triangles.size()
				triangles.append(triangle)
				var minimum := projected[0].min(projected[1]).min(projected[2])
				var maximum := projected[0].max(projected[1]).max(projected[2])
				for bin_y in range(floori(minimum.y / PUBLISHED_HEIGHT_BIN_METRES),
						floori(maximum.y / PUBLISHED_HEIGHT_BIN_METRES) + 1):
					for bin_x in range(floori(minimum.x / PUBLISHED_HEIGHT_BIN_METRES),
							floori(maximum.x / PUBLISHED_HEIGHT_BIN_METRES) + 1):
						var key := Vector2i(bin_x, bin_y)
						var bucket: PackedInt32Array = bins.get(key, PackedInt32Array())
						bucket.append(triangle_index)
						bins[key] = bucket
	return sampler


static func _sample_published_height(point: Vector2, sampler: Dictionary) -> float:
	var exact: Dictionary = sampler.get("vertices", {})
	var result := float(exact.get(_height_key(point), NAN))
	var bin_key := Vector2i(floori(point.x / PUBLISHED_HEIGHT_BIN_METRES),
		floori(point.y / PUBLISHED_HEIGHT_BIN_METRES))
	var bins: Dictionary = sampler.get("bins", {})
	var triangles: Array = sampler.get("triangles", [])
	var candidates: PackedInt32Array = bins.get(bin_key, PackedInt32Array())
	for triangle_index in candidates:
		var triangle: PackedVector3Array = triangles[triangle_index]
		var projected := PackedVector2Array([
			Vector2(triangle[0].x, triangle[0].z),
			Vector2(triangle[1].x, triangle[1].z),
			Vector2(triangle[2].x, triangle[2].z)])
		var weight_value = _barycentric(point, projected)
		if weight_value == null:
			continue
		var weights: Vector3 = weight_value
		if weights.x < -0.00001 or weights.y < -0.00001 or weights.z < -0.00001:
			continue
		var sampled: float = triangle[0].y * weights.x + triangle[1].y * weights.y + \
			triangle[2].y * weights.z
		result = sampled if is_nan(result) else maxf(result, sampled)
	return result


static func _height_key(point: Vector2) -> Vector2i:
	return Vector2i(roundi(point.x * 1000.0), roundi(point.y * 1000.0))


static func clipped_mesh(source: MeshInstance3D, active: Node3D,
		polygon_global: Variant, active_translation: Vector3,
		exclusions: Array = []) -> ArrayMesh:
	var polygons := GEOMETRY.polygons(polygon_global)
	if source == null or source.mesh == null or active == null or polygons.is_empty():
		return null
	var result := ArrayMesh.new()
	var source_to_active := active.global_transform.affine_inverse() * source.global_transform
	var edge_bins: Array[Dictionary] = []
	for polygon in polygons:
		edge_bins.append(_polygon_edge_bins(polygon))
	for surface_index in source.mesh.get_surface_count():
		var arrays: Array = source.mesh.surface_get_arrays(surface_index)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var original: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		if vertices.is_empty():
			continue
		if original.is_empty():
			original.resize(vertices.size())
			for index in original.size():
				original[index] = index
		var projected := PackedVector2Array()
		var inside := PackedByteArray()
		projected.resize(vertices.size())
		inside.resize(vertices.size())
		for index in vertices.size():
			var active_point := source_to_active * vertices[index]
			projected[index] = Vector2(active_point.x + active_translation.x,
				active_point.z + active_translation.z)
			inside[index] = 1 if GEOMETRY.contains(projected[index], polygons) else 0
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL] \
			if arrays[Mesh.ARRAY_NORMAL] is PackedVector3Array else PackedVector3Array()
		var tangents: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT] \
			if arrays[Mesh.ARRAY_TANGENT] is PackedFloat32Array else PackedFloat32Array()
		var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV] \
			if arrays[Mesh.ARRAY_TEX_UV] is PackedVector2Array else PackedVector2Array()
		var uv2s: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV2] \
			if arrays[Mesh.ARRAY_TEX_UV2] is PackedVector2Array else PackedVector2Array()
		var colors: PackedColorArray = arrays[Mesh.ARRAY_COLOR] \
			if arrays[Mesh.ARRAY_COLOR] is PackedColorArray else PackedColorArray()
		var output_vertices := vertices.duplicate()
		var output_normals := normals.duplicate()
		var output_tangents := tangents.duplicate()
		var output_uvs := uvs.duplicate()
		var output_uv2s := uv2s.duplicate()
		var output_colors := colors.duplicate()
		var kept := PackedInt32Array()
		for offset in range(0, original.size() - 2, 3):
			var triangle_indices := PackedInt32Array([original[offset], original[offset + 1],
				original[offset + 2]])
			var inside_count := int(inside[triangle_indices[0]]) + \
				int(inside[triangle_indices[1]]) + int(inside[triangle_indices[2]])
			var triangle := PackedVector2Array([projected[triangle_indices[0]],
				projected[triangle_indices[1]], projected[triangle_indices[2]]])
			var triangle_bounds := _polygon_bounds(triangle)
			var relevant_exclusions: Array = []
			for exclusion_value: Variant in exclusions:
				if not exclusion_value is Dictionary:
					continue
				var exclusion: Dictionary = exclusion_value
				var exclusion_bounds: Rect2 = exclusion.get("bounds", Rect2())
				if triangle_bounds.intersects(exclusion_bounds, true):
					relevant_exclusions.append(exclusion)
			var whole_inside := inside_count == 3 and polygons.size() == 1
			if inside_count == 3 and polygons.size() > 1:
				for component in polygons.size():
					var polygon := polygons[component]
					if (not _triangle_near_boundary(triangle, edge_bins[component])
							and Geometry2D.is_point_in_polygon(triangle[0], polygon)
							and Geometry2D.is_point_in_polygon(triangle[1], polygon)
							and Geometry2D.is_point_in_polygon(triangle[2], polygon)):
						whole_inside = true
						break
			if whole_inside and relevant_exclusions.is_empty():
				kept.append_array(triangle_indices)
				continue
			if inside_count == 0:
				var near_boundary := false
				for bins in edge_bins:
					near_boundary = near_boundary or _triangle_near_boundary(triangle, bins)
				if not near_boundary:
					continue
			var pieces: Array[PackedVector2Array] = []
			for polygon in polygons:
				pieces.append_array(Geometry2D.intersect_polygons(triangle, polygon))
			for exclusion: Dictionary in relevant_exclusions:
				var remaining: Array[PackedVector2Array] = []
				var exclusion_polygon: PackedVector2Array = exclusion.polygon
				for piece: PackedVector2Array in pieces:
					remaining.append_array(Geometry2D.clip_polygons(piece,
						exclusion_polygon))
				pieces = remaining
				if pieces.is_empty():
					break
			for piece: PackedVector2Array in pieces:
				if piece.size() < 3:
					continue
				var triangulated := Geometry2D.triangulate_polygon(piece)
				if triangulated.is_empty():
					piece = _reversed_polygon(piece)
					triangulated = Geometry2D.triangulate_polygon(piece)
				for clipped_index in triangulated:
					var weights := _barycentric(piece[clipped_index], triangle)
					if weights == null:
						continue
					var new_index := output_vertices.size()
					output_vertices.append(_interpolate_vec3(vertices, triangle_indices, weights))
					if normals.size() == vertices.size():
						output_normals.append(_interpolate_vec3(normals, triangle_indices,
							weights).normalized())
					if tangents.size() == vertices.size() * 4:
						var tangent := _interpolate_tangent(tangents, triangle_indices, weights)
						output_tangents.append_array(PackedFloat32Array([
							tangent.x, tangent.y, tangent.z, tangent.w]))
					if uvs.size() == vertices.size():
						output_uvs.append(_interpolate_vec2(uvs, triangle_indices, weights))
					if uv2s.size() == vertices.size():
						output_uv2s.append(_interpolate_vec2(uv2s, triangle_indices, weights))
					if colors.size() == vertices.size():
						output_colors.append(_interpolate_color(colors, triangle_indices, weights))
					kept.append(new_index)
		if kept.is_empty():
			continue
		var filtered := arrays.duplicate(true)
		filtered[Mesh.ARRAY_VERTEX] = output_vertices
		if normals.size() == vertices.size():
			filtered[Mesh.ARRAY_NORMAL] = output_normals
		if tangents.size() == vertices.size() * 4:
			filtered[Mesh.ARRAY_TANGENT] = output_tangents
		if uvs.size() == vertices.size():
			filtered[Mesh.ARRAY_TEX_UV] = output_uvs
		if uv2s.size() == vertices.size():
			filtered[Mesh.ARRAY_TEX_UV2] = output_uv2s
		if colors.size() == vertices.size():
			filtered[Mesh.ARRAY_COLOR] = output_colors
		filtered[Mesh.ARRAY_INDEX] = kept
		result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, filtered)
		var material := source.mesh.surface_get_material(surface_index)
		if material != null:
			result.surface_set_material(result.get_surface_count() - 1, material)
	return result


static func _polygon_bounds(polygon: PackedVector2Array) -> Rect2:
	if polygon.is_empty():
		return Rect2()
	var minimum := polygon[0]
	var maximum := polygon[0]
	for point in polygon:
		minimum = minimum.min(point)
		maximum = maximum.max(point)
	return Rect2(minimum, maximum - minimum)


static func _polygon_edge_bins(polygon: PackedVector2Array) -> Dictionary:
	var result := {}
	for index in polygon.size():
		var first := polygon[index]
		var second := polygon[(index + 1) % polygon.size()]
		var minimum := Vector2(floorf(minf(first.x, second.x) / 8.0),
			floorf(minf(first.y, second.y) / 8.0))
		var maximum := Vector2(floorf(maxf(first.x, second.x) / 8.0),
			floorf(maxf(first.y, second.y) / 8.0))
		for y in range(int(minimum.y), int(maximum.y) + 1):
			for x in range(int(minimum.x), int(maximum.x) + 1):
				result[Vector2i(x, y)] = true
	return result


static func _triangle_near_boundary(triangle: PackedVector2Array,
		edge_bins: Dictionary) -> bool:
	var minimum := triangle[0]
	var maximum := triangle[0]
	for point in triangle:
		minimum = minimum.min(point)
		maximum = maximum.max(point)
	for y in range(floori(minimum.y / 8.0), floori(maximum.y / 8.0) + 1):
		for x in range(floori(minimum.x / 8.0), floori(maximum.x / 8.0) + 1):
			if edge_bins.has(Vector2i(x, y)):
				return true
	return false


static func _barycentric(point: Vector2, triangle: PackedVector2Array) -> Variant:
	var a := triangle[0]
	var b := triangle[1]
	var c := triangle[2]
	var denominator := (b.y - c.y) * (a.x - c.x) + \
		(c.x - b.x) * (a.y - c.y)
	if absf(denominator) <= 0.0000001:
		return null
	var first := ((b.y - c.y) * (point.x - c.x) + \
		(c.x - b.x) * (point.y - c.y)) / denominator
	var second := ((c.y - a.y) * (point.x - c.x) + \
		(a.x - c.x) * (point.y - c.y)) / denominator
	return Vector3(first, second, 1.0 - first - second)


static func _interpolate_vec3(values: PackedVector3Array, indices: PackedInt32Array,
		weights: Vector3) -> Vector3:
	return values[indices[0]] * weights.x + values[indices[1]] * weights.y + \
		values[indices[2]] * weights.z


static func _interpolate_vec2(values: PackedVector2Array, indices: PackedInt32Array,
		weights: Vector3) -> Vector2:
	return values[indices[0]] * weights.x + values[indices[1]] * weights.y + \
		values[indices[2]] * weights.z


static func _interpolate_color(values: PackedColorArray, indices: PackedInt32Array,
		weights: Vector3) -> Color:
	return values[indices[0]] * weights.x + values[indices[1]] * weights.y + \
		values[indices[2]] * weights.z


static func _interpolate_tangent(values: PackedFloat32Array,
		indices: PackedInt32Array, weights: Vector3) -> Vector4:
	var tangent := Vector3.ZERO
	var handedness := 0.0
	for corner in 3:
		var offset := indices[corner] * 4
		var weight := weights[corner]
		tangent += Vector3(values[offset], values[offset + 1], values[offset + 2]) * weight
		handedness += values[offset + 3] * weight
	tangent = tangent.normalized()
	return Vector4(tangent.x, tangent.y, tangent.z, 1.0 if handedness >= 0.0 else -1.0)


static func _reversed_polygon(polygon: PackedVector2Array) -> PackedVector2Array:
	var result := PackedVector2Array()
	for index in range(polygon.size() - 1, -1, -1):
		result.append(polygon[index])
	return result
