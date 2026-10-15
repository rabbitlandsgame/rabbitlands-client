@tool
class_name MapAuthoringRegionSnapshot
extends RefCounted

const SCHEMA := "eloria-continent-authoring-v1"
const GLTF_MATERIAL_BINDING := preload(
	"res://src/dev/map_authoring_region/gltf_material_binding.gd")
const OWNERSHIP := preload("res://src/dev/map_authoring_region/ownership_source.gd")
const ARRIVAL_GEOMETRY := preload("res://addons/map_authoring_workspace/ownership_geometry.gd")
const BASE_HEIGHT_SIDECAR := "base-heights.f32le"
const RESOLVED_HEIGHT_SIDECAR := "resolved-heights.f32le"
const BASE_COLOR_SIDECAR := "base-colors.rgba8"
const TERRAIN_SCRIPT := preload("res://src/dev/map_authoring_region/terrain_control.gd")
const PATCH_SCRIPT := preload("res://src/dev/map_authoring_region/terrain_patch.gd")
const PATH_SCRIPT := preload("res://src/dev/map_authoring_region/path_control.gd")
const WATER_SCRIPT := preload(
	"res://src/dev/map_authoring_region/water_region_control.gd")
const GROUND_SCRIPT := preload(
	"res://src/dev/map_authoring_region/ground_region_control.gd")
const BRIDGE_SCRIPT := preload("res://src/dev/map_authoring_region/bridge_control.gd")
const ASSET_SCRIPT := preload("res://src/dev/map_authoring_region/asset_control.gd")
const ASSET_OVERRIDE_SCRIPT := preload(
	"res://src/dev/map_authoring_region/asset_surface_override.gd")
const GAMEPLAY_SCRIPT := preload(
	"res://src/dev/map_authoring_region/gameplay_marker.gd")
const BIOME_PALETTE_ENTRY := preload(
	"res://src/dev/map_authoring_region/biome_palette_entry.gd")

var errors: Array[String] = []
var _validated_generated_arrival: Dictionary = {}
# Programmatic fixture checkout override; never serialized into scenes/snapshots.
var ownership_project_directory := ""


func export_region(region: Node3D, output_json_path: String) -> Dictionary:
	errors.clear()
	_validated_generated_arrival.clear()
	if region == null:
		_fail("Authoring region root is missing.")
		return {}
	var ownership := OWNERSHIP.region_data(OWNERSHIP.load_source(ownership_project_directory), String(region.get("region_id")))
	var storage := OWNERSHIP.scene_contract(ownership, region)
	var ownership_error := String(storage.error)
	if not ownership_error.is_empty():
		_fail(ownership_error)
		return {}
	var verified := OWNERSHIP.validate_for_bake(ownership)
	if not String(verified.get("error", "")).is_empty():
		_fail(verified.error)
		return {}
	var terrain = region.get_node_or_null("Terrain")
	if not _uses_script(terrain, TERRAIN_SCRIPT):
		_fail("%s: Terrain must use MapAuthoringTerrainControl." % region.get_path())
		return {}
	var migration := OWNERSHIP.region_migration(ownership, String(region.get("region_id")))
	if not String(migration.get("error", "")).is_empty():
		_fail(migration.error)
		return {}
	if migration.has("migration"):
		var grid_check := OWNERSHIP.migration_sources(ownership.checkout, {
			"continentTranslation": _vec3(region.get("continent_translation")),
			"terrain": {"origin": [terrain.origin.x, terrain.origin.y], "migration": migration.migration}})
		if not String(grid_check.get("error", "")).is_empty():
			_fail(grid_check.error)
			return {}
	if not terrain.refresh_preview():
		_fail("%s: %s" % [terrain.get_path(), terrain.last_error])
		return {}
	var output_absolute := ProjectSettings.globalize_path(output_json_path)
	var output_directory := output_absolute.get_base_dir()
	var error := DirAccess.make_dir_recursive_absolute(output_directory)
	if error != OK:
		_fail("Could not create snapshot directory %s: %s" % [
			output_directory, error_string(error)])
		return {}
	var base_output := output_directory.path_join(BASE_HEIGHT_SIDECAR)
	if terrain.sculpt_layer == null:
		# Preserve the original bytes exactly when no sculpt layer is active.
		var base_source := ProjectSettings.globalize_path(terrain.base_heights_path)
		var base_bytes := FileAccess.get_file_as_bytes(base_source)
		if base_bytes.size() != terrain.grid_size.x * terrain.grid_size.y * 4:
			_fail("%s: base height byte count changed during export." % terrain.get_path())
			return {}
		if not _write_bytes(base_output, base_bytes):
			return {}
	else:
		var sculpted_base: PackedFloat32Array = terrain.sculpted_base_heights()
		if sculpted_base.size() != terrain.grid_size.x * terrain.grid_size.y:
			_fail("%s: Terrain Sculpt Layer could not produce the bound base grid." % \
				terrain.get_path())
			return {}
		if not _write_float32(base_output, sculpted_base):
			return {}
	var resolved_output := output_directory.path_join(RESOLVED_HEIGHT_SIDECAR)
	if not _write_float32(resolved_output, terrain.effective_heights()):
		return {}
	var base_colors: Variant = null
	var base_colors_path := String(terrain.get("base_colors_path")).strip_edges()
	if not base_colors_path.is_empty():
		if not base_colors_path.begins_with("res://"):
			_fail("%s: base colors must be a saved res:// sidecar." % terrain.get_path())
			return {}
		var color_source := ProjectSettings.globalize_path(base_colors_path)
		var color_bytes := FileAccess.get_file_as_bytes(color_source)
		if color_bytes.size() != terrain.grid_size.x * terrain.grid_size.y * 4:
			_fail("%s: base color byte count must be width Ãƒâ€” height Ãƒâ€” 4." % terrain.get_path())
			return {}
		var color_output := output_directory.path_join(BASE_COLOR_SIDECAR)
		if not _write_bytes(color_output, color_bytes):
			return {}
		base_colors = {"path": BASE_COLOR_SIDECAR,
			"sha256": FileAccess.get_sha256(color_output), "encoding": "rgba8-srgb"}
	var paths := _path_records(region)
	var water_regions := _water_region_records(region)
	var ground_regions := _ground_region_records(region)
	var bridges := _bridge_records(region)
	var objects := _object_records(region, output_directory)
	var gameplay := _gameplay_records(region)
	var generated_arrival := _generated_arrival_record(region, storage, ownership, gameplay)
	var runtime_seed: Variant = _runtime_binding_seed_record(region)
	var replacements := _replacement_record(region, paths, water_regions)
	var base_surface_record := _surface_record(terrain.base_surface,
		String(terrain.get_path()), false, true)
	var biome_palette := _biome_palette_records(terrain)
	var emitted_surface_records: Array = [base_surface_record, biome_palette, ground_regions,
		paths, bridges, objects]
	var terrain_patches: Array[Dictionary] = terrain.patch_records()
	_validate_terrain_patches(terrain_patches)
	_validate_unique_ids("terrain patches", terrain_patches)
	_validate_unique_ids("paths", paths)
	_validate_unique_ids("water regions", water_regions)
	_validate_unique_ids("bridges", bridges)
	_validate_unique_ids("objects", objects)
	for section: String in gameplay:
		_validate_unique_ids("gameplay.%s" % section, gameplay[section],
			String(region.get("region_id")))
	if not errors.is_empty():
		return {}
	var scene_path := region.scene_file_path
	if scene_path.is_empty() or not scene_path.begins_with("res://"):
		_fail("Authoring root must be loaded from a saved res:// scene before export.")
		return {}
	var sources := {
		"scene": {"path": _repo_path(scene_path),
			"sha256": FileAccess.get_sha256(ProjectSettings.globalize_path(scene_path))},
		"dependencies": _dependency_records(scene_path, region, terrain,
			emitted_surface_records),
	}
	if not storage.source.binding.is_empty():
		sources["authoringSpec"] = storage.source.binding.duplicate(true)
	if not generated_arrival.is_empty():
		sources["generatedArrival"] = generated_arrival.binding.duplicate(true)
		sources.dependencies.append(generated_arrival.binding.duplicate(true))
		sources.dependencies.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return a.path < b.path)
	if runtime_seed is Dictionary:
		sources["runtimeBindingSeed"] = runtime_seed
	var repository_dependencies: Array = migration.repository_dependencies.duplicate(true)
	if ownership.get("selected", false):
		repository_dependencies.append_array(verified.repositoryDependencies)
	if not repository_dependencies.is_empty():
		repository_dependencies.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return a.path < b.path)
		sources["repositoryDependencies"] = repository_dependencies
	var terrain_record := {
		"origin": [terrain.origin.x, terrain.origin.y],
		"cellMetres": terrain.cell_metres,
		"previewUvMetresInverse": terrain.preview_uv_metres_inverse,
		"width": terrain.grid_size.x,
		"height": terrain.grid_size.y,
		"baseHeights": {"path": BASE_HEIGHT_SIDECAR,
			"sha256": FileAccess.get_sha256(base_output), "encoding": "float32-le"},
		"resolvedHeights": {"path": RESOLVED_HEIGHT_SIDECAR,
			"sha256": FileAccess.get_sha256(resolved_output), "encoding": "float32-le",
			"includes": ["patches", "road-earthworks", "river-cuts"]},
		"baseSurface": base_surface_record,
		"patches": terrain_patches,
	}
	if migration.has("migration"):
		terrain_record["migration"] = migration.migration
	if not biome_palette.is_empty():
		terrain_record["biomePalette"] = biome_palette
	if base_colors is Dictionary:
		terrain_record["baseColors"] = base_colors
	var document := {
		"schema": SCHEMA,
		"regionId": String(region.get("region_id")),
		"coordinateSpace": "territory-local",
		"axes": {"x": "east", "y": "up", "z": "south"},
		"continentTranslation": _vec3(region.get("continent_translation")),
		"server": storage.server.duplicate(true),
		"sources": sources,
		"authority": {
			"terrain": bool(region.get("authority_terrain")),
			"water": bool(region.get("authority_water")),
			"paths": bool(region.get("authority_paths")),
			"objects": bool(region.get("authority_objects")),
			"gameplay": bool(region.get("authority_gameplay")),
		},
		"replacements": replacements,
		"terrain": terrain_record,
		"groundRegions": ground_regions,
		"paths": paths,
		"waterRegions": water_regions,
		"bridges": bridges,
		"objects": objects,
		"gameplay": gameplay,
		"seams": {
			"ownershipPolygonSha256": String(region.get("ownership_polygon_sha256")),
			"anchors": _seam_records(region),
		},
	}
	if ownership.get("selected", false):
		document["ownershipSource"] = verified.binding
		document.seams["ownershipPolygonSha256"] = verified.ownershipPolygonSha256
	if not generated_arrival.is_empty():
		document["generatedArrival"] = generated_arrival.payload.duplicate(true)
		if FileAccess.get_sha256(generated_arrival.absolute) != generated_arrival.binding.sha256:
			_fail("Generated arrival source changed during export; retry the bake.")
	_validate_document(region, document)
	if not errors.is_empty():
		return {}
	if ownership.get("selected", false) and not OWNERSHIP.unchanged(ownership):
		_fail("Ownership inputs changed during export; retry the bake.")
		return {}
	if OWNERSHIP.region_migration(ownership, String(region.get("region_id"))) != migration:
		_fail("Terrain migration sources changed during export; retry the bake.")
		return {}
	if OWNERSHIP.scene_contract(ownership, region) != storage:
		_fail("Authoring spec or scene storage/frame changed during export; retry the bake.")
		return {}
	var file := FileAccess.open(output_absolute, FileAccess.WRITE)
	if file == null:
		_fail("Could not write authoring snapshot %s." % output_absolute)
		return {}
	file.store_string(JSON.stringify(document, "  ", true, true) + "\n")
	file.close()
	return document


func _path_records(region: Node3D) -> Array[Dictionary]:
	var records: Array[Dictionary] = []
	for container_name in ["Roads", "Rivers"]:
		var container := region.get_node_or_null(NodePath(container_name))
		if container == null:
			continue
		for child in container.get_children():
			if not _uses_script(child, PATH_SCRIPT):
				continue
			var path = child
			var relative: Transform3D = region.global_transform.affine_inverse() * path.global_transform
			var scale_x := Vector2(relative.basis.x.x, relative.basis.x.z).length()
			var scale_z := Vector2(relative.basis.z.x, relative.basis.z.z).length()
			if absf(scale_x - scale_z) > 0.0001 or absf(relative.basis.x.y) > 0.0001 or \
					absf(relative.basis.z.y) > 0.0001:
				_fail("%s: paths support translation, yaw, and uniform X/Z scale only." % path.get_path())
			var points: Array[Dictionary] = []
			for point in path.snapshot_points():
				var local := _array_vec3(point.position)
				var transformed: Vector3 = relative * local
				points.append({"position": _vec3(transformed),
					"width": float(point.width) * scale_x})
			records.append({
				"id": path.path_id,
				"kind": path.kind,
				"routingRole": path.routing_role,
				"replacesRouteId": path.replacement_route_value(),
				"replacesPlanFeatureId": path.replacement_plan_feature_value(),
				"closed": path.curve.closed if path.curve != null else false,
				"surface": _surface_record(path.surface, String(path.get_path()),
					path.kind == "river"),
				"points": points,
				"properties": _clean_value(path.properties, "%s.properties" % path.get_path()),
			})
	records.sort_custom(_sort_id)
	return records


func _water_region_records(region: Node3D) -> Array[Dictionary]:
	var records: Array[Dictionary] = []
	var container := region.get_node_or_null("WaterRegions")
	if container == null:
		return records
	for child in container.get_children():
		if not _uses_script(child, WATER_SCRIPT):
			continue
		var water = child
		var relative: Transform3D = region.global_transform.affine_inverse() * \
			water.global_transform
		if not relative.basis.is_equal_approx(Basis.IDENTITY):
			_fail("%s: elliptical water regions support translation only; rotation and scale are not represented." % water.get_path())
		var replacement := String(water.replaces_plan_feature_id).strip_edges()
		records.append({
			"id": String(water.water_id),
			"shape": "ellipse",
			"replacesPlanFeatureId": null if replacement.is_empty() else replacement,
			"name": String(water.display_name),
			"center": [relative.origin.x, relative.origin.z],
			"level": relative.origin.y,
			"radii": [float(water.radii.x), float(water.radii.y)],
			"depth": float(water.baseline_plan_depth),
		})
	records.sort_custom(_sort_id)
	return records


func _ground_region_records(region: Node3D) -> Array[Dictionary]:
	var records: Array[Dictionary] = []
	var container := region.get_node_or_null("Ground/Regions")
	if container == null:
		return records
	for child in container.get_children():
		if not _uses_script(child, GROUND_SCRIPT):
			continue
		var ground = child
		var relative: Transform3D = region.global_transform.affine_inverse() * ground.global_transform
		var mask_error: String = ground.clip_error(ground.clip_polygon)
		if not mask_error.is_empty(): _fail("%s: %s" % [ground.get_path(), mask_error])
		records.append({
			"id": ground.region_id,
			"enabled": ground.enabled,
			"shape": "ellipse" if ground.shape == 0 \
				else "rectangle",
			"matrix": _matrix(relative),
			"size": [ground.size.x, ground.size.y],
			"blendWidth": ground.blend_width,
			"opacity": ground.opacity,
			"priority": ground.priority,
			"surface": _surface_record(ground.surface, String(ground.get_path())),
		})
		var record := records[-1]
		if not ground.clip_polygon.is_empty():
			record["clipPolygon"] = []
			for point: Vector2 in ground.clip_polygon: record.clipPolygon.append([point.x, point.y])
		if ground.uv_anchor_continent_enabled:
			if not ground.uv_anchor_continent.is_finite(): _fail("Ground UV source anchor must be finite.")
			record["uvAnchorContinent"] = [ground.uv_anchor_continent.x, ground.uv_anchor_continent.y]
		if ground.source_layer_ordinal < -1: _fail("Ground source layer ordinal must be -1 or nonnegative.")
		if ground.source_layer_ordinal >= 0:
			if ground.source_layer_ordinal > 126: _fail("Ground source layer ordinal exceeds 126.")
			record["sourceLayerOrdinal"] = ground.source_layer_ordinal
	records.sort_custom(_sort_id)
	return records


func _bridge_records(region: Node3D) -> Array[Dictionary]:
	var records: Array[Dictionary] = []
	var container := region.get_node_or_null("Bridges")
	if container == null:
		return records
	for child in container.get_children():
		if not _uses_script(child, BRIDGE_SCRIPT):
			continue
		var bridge = child
		var start: Marker3D = bridge.start_marker()
		var end: Marker3D = bridge.end_marker()
		if start == null or end == null:
			_fail("%s: bridge Start/End markers are missing." % bridge.get_path())
			continue
		var inverse: Transform3D = region.global_transform.affine_inverse()
		var relative: Transform3D = inverse * bridge.global_transform
		var scale_x := Vector2(relative.basis.x.x, relative.basis.x.z).length()
		var scale_z := Vector2(relative.basis.z.x, relative.basis.z.z).length()
		var scale_y := relative.basis.y.length()
		if absf(scale_x - scale_z) > 0.0001 or absf(relative.basis.x.y) > 0.0001 or \
				absf(relative.basis.z.y) > 0.0001 or absf(relative.basis.y.x) > 0.0001 or \
				absf(relative.basis.y.z) > 0.0001:
			_fail("%s: bridges support translation, yaw, uniform X/Z scale, and vertical scale only." % bridge.get_path())
		records.append({
			"id": bridge.bridge_id,
			"start": _vec3(inverse * start.global_position),
			"end": _vec3(inverse * end.global_position),
			"width": bridge.width * scale_x,
			"arch": bridge.arch * scale_y,
			"waterClearance": bridge.water_clearance * scale_y,
			"deckTextureRotationDegrees": bridge.deck_texture_rotation_degrees,
			"deckSurface": _surface_record(bridge.deck_surface,
				"%s.deck_surface" % bridge.get_path()),
			"supportSurface": _surface_record(bridge.support_surface,
				"%s.support_surface" % bridge.get_path()),
			"replacesRouteId": null if bridge.replaces_route_id.is_empty() \
				else bridge.replaces_route_id,
			"collisionRole": bridge.collision_role,
			"metadata": _clean_value(bridge.metadata, "%s.metadata" % bridge.get_path()),
		})
	records.sort_custom(_sort_id)
	return records


func _object_records(region: Node3D, output_directory: String) -> Array[Dictionary]:
	var records: Array[Dictionary] = []
	var material_binding := GLTF_MATERIAL_BINDING.new()
	var container := region.get_node_or_null("AuthoredAssets")
	if container == null:
		return records
	for child in container.get_children():
		if not _uses_script(child, ASSET_SCRIPT):
			_fail("%s: production assets must use MapAuthoringAssetControl wrappers." % child.get_path())
			continue
		var asset = child
		_validate_asset_source_boundary(asset)
		var relative: Transform3D = region.global_transform.affine_inverse() * asset.global_transform
		var baked_source := _baked_source_record(asset, output_directory)
		records.append({
			"id": asset.asset_id,
			"nodeName": asset.node_name,
			"assetId": asset.catalog_asset_id,
			"scenePath": asset.scene_path,
			"sourceNode": asset.source_node,
			"bakedSource": baked_source,
			"matrix": _matrix(relative),
			"collisionRole": asset.collision_role,
			"materialOverrides": _asset_surface_records(asset, material_binding, baked_source),
			"metadata": _clean_value(asset.metadata, "%s.metadata" % asset.get_path()),
		})
	records.sort_custom(_sort_id)
	material_binding.clear()
	return records


func _baked_source_record(asset: Node, output_directory: String) -> Dictionary:
	var scene_path := String(asset.get("scene_path"))
	var source_node := String(asset.get("source_node"))
	var absolute := ProjectSettings.globalize_path(scene_path)
	if scene_path.get_extension().to_lower() in ["glb", "gltf"]:
		if not FileAccess.file_exists(absolute):
			_fail("%s: source asset is missing: %s." % [asset.get_path(), scene_path])
			return {}
		return {"path": _repo_path(scene_path),
			"sha256": FileAccess.get_sha256(absolute),
			"sourceNode": source_node if not source_node.is_empty() else "."}
	var packed := ResourceLoader.load(scene_path, "PackedScene",
		ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	if packed == null:
		_fail("%s: source scene cannot be loaded for production export: %s." % [
			asset.get_path(), scene_path])
		return {}
	var template := packed.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE) as Node3D
	if template == null:
		_fail("%s: source scene has no Node3D root." % asset.get_path())
		return {}
	var source: Node3D = template
	if not source_node.is_empty():
		source = template.get_node_or_null(NodePath(source_node)) as Node3D
	if source == null:
		_fail("%s: source node %s is missing from %s." % [asset.get_path(),
			source_node, scene_path])
		template.free()
		return {}
	var prototype_directory := output_directory.path_join("prototypes")
	var make_error := DirAccess.make_dir_recursive_absolute(prototype_directory)
	if make_error != OK:
		_fail("Could not create authored prototype directory %s: %s" % [
			prototype_directory, error_string(make_error)])
		template.free()
		return {}
	var identity := (scene_path + "\n" + source_node).sha256_text().substr(0, 20)
	var filename := "source-%s.glb" % identity
	var target := prototype_directory.path_join(filename)
	var state := GLTFState.new()
	var document := GLTFDocument.new()
	var append_error := document.append_from_scene(source, state)
	if append_error != OK:
		_fail("%s: could not convert source scene to a production GLB: %s." % [
			asset.get_path(), error_string(append_error)])
		template.free()
		return {}
	var write_error := document.write_to_filesystem(state, target)
	template.free()
	if write_error != OK:
		_fail("%s: could not write production GLB %s: %s." % [asset.get_path(),
			target, error_string(write_error)])
		return {}
	return {"path": "prototypes/" + filename,
		"sha256": FileAccess.get_sha256(target), "sourceNode": "."}


func _validate_asset_source_boundary(asset: Node) -> void:
	var content: Node3D = asset.call("content_root")
	var scene_path := String(asset.get("scene_path"))
	if content == null or scene_path.is_empty():
		return
	var packed := ResourceLoader.load(scene_path, "PackedScene",
		ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	if packed == null:
		_fail("%s: source scene cannot be loaded: %s." % [asset.get_path(), scene_path])
		return
	var template := packed.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE) as Node3D
	if template == null:
		_fail("%s: source scene has no Node3D root." % asset.get_path())
		return
	var source: Node3D = template
	var source_node := String(asset.get("source_node"))
	if not source_node.is_empty():
		source = template.get_node_or_null(NodePath(source_node)) as Node3D
	if source == null:
		_fail("%s: source node %s is missing from %s." % [asset.get_path(),
			source_node, scene_path])
		template.free()
		return
	var allowed := {}
	for override in asset.material_overrides:
		if _uses_script(override, ASSET_OVERRIDE_SCRIPT):
			allowed["%s:%d" % [override.mesh_node_path, override.surface_index]] = true
	var current_state := _asset_content_state(content, allowed)
	var source_state := _asset_content_state(source, allowed)
	if current_state != source_state:
		_fail("%s: edits inside Content are not exported. Move/rotate/scale the asset wrapper, use Material Overrides, or edit the source scene; then restore the Content instance." % asset.get_path())
	template.free()


func _asset_content_state(root: Node3D, allowed_overrides: Dictionary) -> Dictionary:
	var result := {}
	_collect_asset_content_state(root, root, allowed_overrides, result)
	return result


func _collect_asset_content_state(root: Node3D, node: Node,
		allowed_overrides: Dictionary, result: Dictionary) -> void:
	if node != root and String(node.name).begins_with("__"):
		return
	var relative_path := "." if node == root else String(root.get_path_to(node))
	if node is Node3D:
		var spatial := node as Node3D
		var state: Array = [_matrix(spatial.transform), spatial.visible]
		if spatial is MeshInstance3D:
			var mesh_instance := spatial as MeshInstance3D
			state.append(_resource_identity(mesh_instance.mesh))
			state.append(_resource_identity(mesh_instance.material_override))
			var surface_overrides: Array = []
			if mesh_instance.mesh != null:
				for surface_index in mesh_instance.mesh.get_surface_count():
					if allowed_overrides.has("%s:%d" % [relative_path, surface_index]):
						surface_overrides.append("<authored-override>")
					else:
						surface_overrides.append(_resource_identity(
							mesh_instance.get_surface_override_material(surface_index)))
			state.append(surface_overrides)
		result[relative_path] = state
	for child in node.get_children():
		_collect_asset_content_state(root, child, allowed_overrides, result)


func _resource_identity(resource: Resource) -> Array:
	if resource == null:
		return []
	return [resource.get_class(), resource.resource_path]


func _asset_surface_records(asset: Node, material_binding = null,
		baked_source: Dictionary = {}) -> Array[Dictionary]:
	var records: Array[Dictionary] = []
	var seen := {}
	for override in asset.material_overrides:
		if not _uses_script(override, ASSET_OVERRIDE_SCRIPT):
			_fail("%s: material overrides must use MapAuthoringAssetSurfaceOverride resources." % asset.get_path())
			continue
		if override.surface_index < 0:
			_fail("%s/%s: material surface index cannot be negative." % [
				asset.get_path(), override.mesh_node_path])
			continue
		var content: Node3D = asset.call("content_root")
		var mesh := (content.get_node_or_null(NodePath(override.mesh_node_path)) as MeshInstance3D
			if content != null else null)
		if mesh == null or mesh.mesh == null or override.surface_index >= mesh.mesh.get_surface_count():
			_fail("%s/%s: material override must identify an existing mesh surface." % [asset.get_path(), override.mesh_node_path])
			continue
		var target := "%s:%d" % [override.mesh_node_path, override.surface_index]
		if seen.has(target):
			_fail("%s: duplicate material override target %s." % [asset.get_path(), target])
			continue
		seen[target] = true
		var binding := {}
		if (material_binding != null and String(asset.scene_path).get_extension().to_lower() == "glb"
				and String(asset.source_node) in ["", "."]):
			binding = material_binding.bind(asset.scene_path, String(baked_source.get("sha256", "")),
				content, override.mesh_node_path, override.surface_index)
			if binding.has("error"):
				_fail("%s/%s: %s" % [asset.get_path(), override.mesh_node_path, binding.error])
				continue
		var record := {"meshNodePath": override.mesh_node_path,
			"surfaceIndex": override.surface_index,
			"surface": _surface_record(override.surface,
				"%s/%s[%d]" % [asset.get_path(), override.mesh_node_path,
					override.surface_index])}
		if binding.has("bakedMeshNodeIndex"):
			record["bakedMeshNodeIndex"] = binding.bakedMeshNodeIndex
		records.append(record)
	records.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return "%s:%08d" % [String(a.meshNodePath), int(a.surfaceIndex)] < \
			"%s:%08d" % [String(b.meshNodePath), int(b.surfaceIndex)])
	return records


func _gameplay_records(region: Node3D) -> Dictionary:
	var output := {"spawnPoints": [], "portals": [], "interactives": [],
		"landmarks": [], "harvestables": [], "npcMarkers": [],
		"ambientPopulation": [], "runtimePoints": [], "runtimeBindings": []}
	var markers: Array[Node] = []
	var seen := {}
	# Conserved dedicated controls may live beside Gameplay in the region scene.
	# Collect each node once, including legacy controls nested under Gameplay.
	for path in ["Gameplay", "RuntimePoints"]:
		var container := region.get_node_or_null(path)
		if container == null:
			continue
		for child in container.find_children("*", "", true, false):
			if not seen.has(child.get_instance_id()):
				seen[child.get_instance_id()] = true
				markers.append(child)
	var inverse: Transform3D = region.global_transform.affine_inverse()
	for child in markers:
		if not _uses_script(child, GAMEPLAY_SCRIPT):
			continue
		var marker = child
		var section: String = marker.output_section()
		if section.is_empty():
			_fail("%s: unsupported gameplay marker kind %s." % [marker.get_path(), marker.kind])
			continue
		var followed: Node3D = marker.followed_asset() if not marker.follow_asset_id.is_empty() \
			else null
		var world_position: Vector3 = marker.global_position
		if followed != null:
			world_position = followed.global_transform * marker.follow_asset_offset
		var local: Vector3 = inverse * world_position
		var record_value: Variant = _clean_value(marker.extras, "%s.extras" % marker.get_path())
		var record: Dictionary = record_value if record_value is Dictionary else {}
		for reserved in ["id", "position", "serverTile", "default", "facing",
				"destinationMap", "destinationSpawn", "key", "node", "assetId"]:
			record.erase(reserved)
		record["id"] = marker.record_id
		record["position"] = _vec3(local)
		record["serverTile"] = _server_tile(region, local)
		if not marker.label.is_empty(): record["label"] = marker.label
		if marker.kind == "spawn":
			record["default"] = marker.default_spawn
			record["facing"] = _vec3(marker.facing)
		if not marker.destination_map.is_empty(): record["destinationMap"] = marker.destination_map
		if not marker.destination_spawn.is_empty(): record["destinationSpawn"] = marker.destination_spawn
		if not marker.key_id.is_empty(): record["key"] = marker.key_id
		if not marker.follow_asset_id.is_empty():
			if followed == null:
				_fail("%s: Follow Asset Id %s does not exist." % [marker.get_path(),
					marker.follow_asset_id])
			else:
				record["assetId"] = marker.follow_asset_id
				record["node"] = String(followed.get("node_name"))
		elif not marker.linked_node_name.is_empty():
			record["node"] = marker.linked_node_name
		(output[section] as Array).append(record)
		for raw_binding in marker.runtime_bindings:
			var binding := _runtime_binding_record(raw_binding, section,
				marker.record_id, String(marker.get_path()))
			if not binding.is_empty():
				(output.runtimeBindings as Array).append(binding)
	for section: String in output:
		(output[section] as Array).sort_custom(_sort_id)
	return output


func _runtime_binding_record(raw: Variant, section: String, marker_id: String,
		where: String) -> Dictionary:
	if not raw is Dictionary:
		_fail("%s: every Runtime Binding must be a dictionary." % where)
		return {}
	var cleaned: Variant = _clean_value(raw, "%s.runtimeBindings" % where)
	if not cleaned is Dictionary:
		return {}
	var record: Dictionary = cleaned
	for generated in ["marker", "initialPosition"]:
		record.erase(generated)
	var identity := String(record.get("id", "")).strip_edges()
	if identity.is_empty():
		_fail("%s: every Runtime Binding needs an exact stable id." % where)
	var source: Variant = record.get("source")
	if not source is Dictionary or String(source.get("path", "")).is_empty() or \
			typeof(source.get("line")) != TYPE_INT or int(source.get("line", 0)) <= 0 or \
			not source.get("oldTile") is Array or \
			(source.get("oldTile") as Array).size() != 2 or \
			typeof(source.oldTile[0]) != TYPE_INT or typeof(source.oldTile[1]) != TYPE_INT:
		_fail("%s runtime binding %s needs source path, positive line, and oldTile [x, y]." % [
			where, identity])
	var role := String(record.get("role", ""))
	if not role in ["door", "return", "interactive", "npc", "harvest", "spawn",
			"territory"]:
		_fail("%s runtime binding %s has unsupported role %s." % [where, identity, role])
	var roads := String(record.get("roads", ""))
	if not roads in ["marker", "entrance"]:
		_fail("%s runtime binding %s must use roads 'marker' or 'entrance'." % [
			where, identity])
	var raw_offset: Variant = record.get("targetOffset")
	if not raw_offset is Array or (raw_offset as Array).size() != 3:
		_fail("%s runtime binding %s needs targetOffset [dx, 0, dz]." % [
			where, identity])
	else:
		var valid_offset := true
		for component in raw_offset:
			if typeof(component) not in [TYPE_INT, TYPE_FLOAT] or \
					not is_finite(float(component)):
				valid_offset = false
		if not valid_offset:
			_fail("%s runtime binding %s targetOffset must contain finite numbers." % [
				where, identity])
		elif not is_zero_approx(float(raw_offset[1])):
			_fail("%s runtime binding %s targetOffset must be horizontal [dx, 0, dz]." % [
				where, identity])
		else:
			record["targetOffset"] = [float(raw_offset[0]), 0.0,
				float(raw_offset[2])]
	var provenance: Variant = record.get("provenance")
	if not provenance is Dictionary or \
			not _is_sha(String(provenance.get("sourceReportSha256", ""))):
		_fail("%s runtime binding %s needs a certified source report hash." % [where,
			identity])
	elif provenance.has("sourceProfileSha256") and \
			not _is_sha(String(provenance.sourceProfileSha256)):
		_fail("%s runtime binding %s has an invalid source profile hash." % [where,
			identity])
	record["marker"] = {"section": section, "id": marker_id}
	return record


func _runtime_binding_seed_record(region: Node3D) -> Variant:
	var path := String(region.get("runtime_binding_seed_path")).strip_edges()
	var expected := String(region.get("runtime_binding_seed_sha256")).strip_edges()
	if path.is_empty() and expected.is_empty():
		return null
	if path.is_empty() or not path.begins_with("res://"):
		_fail("Runtime Binding Seed Path must be a saved res:// JSON file.")
		return null
	if not _is_sha(expected):
		_fail("Runtime Binding Seed Sha256 must contain 64 lowercase hex characters.")
		return null
	var absolute := ProjectSettings.globalize_path(path)
	if not FileAccess.file_exists(absolute):
		_fail("Runtime Binding Seed is missing: %s." % path)
		return null
	var actual := FileAccess.get_sha256(absolute)
	if actual != expected:
		_fail("Runtime Binding Seed hash changed: expected %s, found %s." % [expected,
			actual])
		return null
	return {"path": _repo_path(path), "sha256": actual}


func _replacement_record(region: Node3D, paths: Array[Dictionary],
		water_regions: Array[Dictionary]) -> Dictionary:
	var route_ids := _sorted_unique(region.get("owned_route_ids"), "owned_route_ids")
	var spec_path := "res://world_authoring/regions/%s/region-authoring-spec.json" % \
		String(region.get("region_id"))
	if FileAccess.file_exists(spec_path):
		var spec: Variant = JSON.parse_string(FileAccess.get_file_as_string(spec_path))
		if not spec is Dictionary or String(spec.get("regionId", "")) != \
				String(region.get("region_id")) or not spec.get("authority") is Dictionary:
			_fail("Region route ownership spec is invalid: %s" % spec_path)
		else:
			var persistent := _sorted_unique(spec.authority.get("ownedRouteIds", []),
				"region spec authority.ownedRouteIds")
			for identity in route_ids:
				if not persistent.has(identity):
					_fail("Scene route claim %s is absent from persistent region spec." % identity)
			route_ids = persistent
	var plan_ids := _sorted_unique(region.get("owned_plan_feature_ids"),
		"owned_plan_feature_ids")
	var ferry_ids := _sorted_unique(region.get("owned_ferry_connection_ids"),
		"owned_ferry_connection_ids")
	var plan_claims := {}
	for path in paths:
		if path.replacesRouteId != null and not route_ids.has(String(path.replacesRouteId)):
			_fail("Path %s replaces route %s, which is absent from owned_route_ids." % [
				path.id, path.replacesRouteId])
		if path.replacesPlanFeatureId != null and not plan_ids.has(
				String(path.replacesPlanFeatureId)):
			_fail("Path %s replaces plan feature %s, which is absent from owned_plan_feature_ids." % [
				path.id, path.replacesPlanFeatureId])
		if path.replacesPlanFeatureId != null:
			var path_claim := String(path.replacesPlanFeatureId)
			if plan_claims.has(path_claim):
				_fail("Plan feature %s is claimed by both %s and path %s." % [
					path_claim, plan_claims[path_claim], path.id])
			plan_claims[path_claim] = "path %s" % path.id
	for water in water_regions:
		if water.replacesPlanFeatureId != null and not plan_ids.has(
				String(water.replacesPlanFeatureId)):
			_fail("Water region %s replaces plan feature %s, which is absent from owned_plan_feature_ids." % [
				water.id, water.replacesPlanFeatureId])
		if water.replacesPlanFeatureId != null:
			var water_claim := String(water.replacesPlanFeatureId)
			if plan_claims.has(water_claim):
				_fail("Plan feature %s is claimed by both %s and water region %s." % [
					water_claim, plan_claims[water_claim], water.id])
			plan_claims[water_claim] = "water region %s" % water.id
	return {"routeIds": route_ids, "planFeatureIds": plan_ids,
		"ferryConnectionIds": ferry_ids}


func _surface_record(surface: MapAuthoringSurface, node_path: String,
		allow_default_water: bool = false,
		emit_biome_opt_in: bool = false) -> Dictionary:
	if surface == null:
		if allow_default_water:
			return {"preset": "Water", "rotationDegrees": 0.0,
				"materialMode": "water"}
		_fail("%s: a supported local Surface is required." % node_path)
		return {}
	var record := {"preset": surface.texture_preset,
		"rotationDegrees": surface.rotation_degrees,
		"materialMode": "road" if surface.material_mode == \
			MapAuthoringSurface.MaterialMode.ROAD_SHADER else "surface"}
	if emit_biome_opt_in and surface.biome_blend_enabled:
		record["biomeBlendEnabled"] = true
	var material := surface.source_material
	if surface.material_mode == MapAuthoringSurface.MaterialMode.ROAD_SHADER:
		if surface.texture_preset != MapAuthoringTexturePresets.WORN_EARTH or \
				not material is ShaderMaterial or \
				String((material as ShaderMaterial).shader.resource_path) != \
				"res://src/dev/map_authoring_pilot/style/worn_path.gdshader":
			_fail("%s: road surfaces must use the supported Worn earth shader." % node_path)
			return record
		var road := material as ShaderMaterial
		var factory := MapAuthoringTexturePresets.create_road_material(
			MapAuthoringTexturePresets.WORN_EARTH)
		for parameter in [&"ground_albedo", &"ground_normal", &"ground_orm"]:
			if not _same_resource(road.get_shader_parameter(parameter),
					factory.get_shader_parameter(parameter)):
				_fail("%s: custom road texture bindings are not supported; keep the Worn earth preset textures." % node_path)
				return record
		record["roadOverrides"] = {
			"wornTint": _color(road.get_shader_parameter(&"worn_tint") as Color),
			"textureScale": float(road.get_shader_parameter(&"texture_scale")),
			"roughnessMultiplier": float(road.get_shader_parameter(
				&"roughness_multiplier")),
			"normalStrength": float(road.get_shader_parameter(&"normal_strength")),
			"edgeFeather": float(road.get_shader_parameter(&"edge_feather")),
		}
		return record
	if not material is BaseMaterial3D:
		_fail("%s: surfaces must use a supported standard 3D material; arbitrary shaders cannot be baked." % node_path)
		return record
	var base := material as BaseMaterial3D
	if base.uv1_triplanar or base.uv1_world_triplanar:
		_fail("%s: triplanar materials are not supported by the production bake; choose a named region texture again or disable both triplanar settings." % node_path)
		return record
	var pbr := {
		"albedoColor": _color(base.albedo_color),
		"albedoTexture": _resource_path(base.albedo_texture),
		"normalTexture": _resource_path(base.normal_texture),
		"normalScale": base.normal_scale,
		"roughness": base.roughness,
		"metallic": base.metallic,
		"uvScale": _vec3(base.uv1_scale),
		"uvOffset": _vec3(base.uv1_offset),
		"triplanar": base.uv1_triplanar,
		"worldTriplanar": base.uv1_world_triplanar,
	}
	if base is ORMMaterial3D:
		pbr["ormTexture"] = _resource_path((base as ORMMaterial3D).orm_texture)
	record["pbr" if surface.texture_preset == MapAuthoringTexturePresets.CUSTOM \
		else "pbrOverrides"] = pbr
	return record


func _biome_palette_records(terrain: Node) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	var entries: Array = terrain.get("biome_palette")
	if entries.size() > 1:
		_fail("%s: Biome Palette supports at most one secondary surface." %
			terrain.get_path())
	for raw in entries:
		if not _uses_script(raw, BIOME_PALETTE_ENTRY):
			_fail("%s: invalid Biome Palette entry." % terrain.get_path())
			continue
		raw.bind_local_surface()
		var identity := String(raw.id).strip_edges()
		if identity.is_empty():
			_fail("%s: Biome Palette entry needs a stable Id." % terrain.get_path())
		if not BIOME_PALETTE_ENTRY.VALID_ROLES.has(String(raw.role)):
			_fail("%s: unsupported Biome Palette role %s." % [terrain.get_path(), raw.role])
		result.append({"id": identity, "role": String(raw.role),
			"surface": _surface_record(raw.surface,
				"%s/BiomePalette/%s" % [terrain.get_path(), identity])})
	result.sort_custom(_sort_id)
	return result


func _same_resource(first: Variant, second: Variant) -> bool:
	if first == null or second == null:
		return first == second
	if not first is Resource or not second is Resource:
		return false
	return (first as Resource).resource_path == (second as Resource).resource_path



func _arrival_vector(value: Variant, count: int) -> bool:
	if not value is Array or value.size() != count: return false
	for part: Variant in value:
		if (part is not int and part is not float) or not is_finite(float(part)): return false
	return true


func _generated_arrival_record(region: Node3D, storage: Dictionary, ownership: Dictionary,
		gameplay: Dictionary) -> Dictionary:
	var spec: Dictionary = storage.source.document
	var configuration: Variant = spec.get("gameplay", {})
	if not configuration is Dictionary:
		_fail("Region gameplay spec must be an object.")
		return {}
	if not configuration.has("generatedArrival"): return {}
	var reference: Variant = configuration.generatedArrival
	var map_id := String(region.get("region_id"))
	if not reference is Dictionary or reference.size() != 2 or \
			not reference.has_all(["path", "sha256"]) or reference.path is not String or \
			not _is_sha(String(reference.get("sha256", ""))):
		_fail("Generated arrival requires exactly a contained path and raw SHA-256 binding.")
		return {}
	for spawn: Dictionary in gameplay.get("spawnPoints", []):
		if spawn.get("default", false):
			_fail("Authored and generated default arrivals cannot be mixed.")
			return {}
	var expected := "eloria-assets/maps/continent-v2/" + map_id + "/content/arrival.json"
	var absolute: String = OWNERSHIP.contained(ownership.checkout, reference.path)
	if reference.path != expected or absolute.is_empty() or not FileAccess.file_exists(absolute):
		_fail("Generated arrival source is missing or outside its map content path.")
		return {}
	if FileAccess.get_sha256(absolute) != reference.sha256:
		_fail("Generated arrival source SHA-256 changed; update the reviewed binding.")
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(absolute))
	if not parsed is Dictionary:
		_fail("Generated arrival source must be a JSON object.")
		return {}
	var payload: Dictionary = parsed
	if payload.get("schema") != "eloria-continent-v2-generated-arrival-v1" or \
			payload.get("map") != map_id or payload.get("id") != "generated-arrival-" + map_id or \
			payload.get("default") is not bool or payload.get("default") != true or \
			payload.get("generated") is not bool or payload.get("generated") != true:
		_fail("Generated arrival identity/schema/default is invalid.")
		return {}
	var frame: Variant = payload.get("frame")
	var translation := _vec3(region.get("continent_translation"))
	if not frame is Dictionary or frame.size() != 3 or not OWNERSHIP.STORAGE.same_vector(frame.get("origin"), storage.server.origin) or \
			not OWNERSHIP.STORAGE.same_vector(frame.get("cells"), storage.server.cells) or \
			not OWNERSHIP.STORAGE.same_vector(frame.get("translation"), translation):
		_fail("Generated arrival frame differs from the scene/spec frame.")
		return {}
	if not _arrival_vector(payload.get("position"), 3) or \
			not _arrival_vector(payload.get("facing"), 3) or not _arrival_vector(payload.get("serverTile"), 2):
		_fail("Generated arrival position, facing and tile must be finite numeric vectors.")
		return {}
	var position: Array = payload.position
	var tile: Array = payload.serverTile
	var want_tile := [floor(float(position[0]) + float(storage.server.origin[0])),
		floor(float(storage.server.origin[1]) - float(position[2]))]
	if tile[0] != want_tile[0] or tile[1] != want_tile[1] or \
			tile[0] < 0 or tile[1] < 0 or tile[0] >= storage.server.cells[0] or tile[1] >= storage.server.cells[1]:
		_fail("Generated arrival tile differs from its position or lies outside storage.")
		return {}
	var provenance: Variant = payload.get("provenance")
	if not provenance is Dictionary or provenance.get("algorithm") != "nearest-owned-safe-baseline-tile-v1":
		_fail("Generated arrival provenance algorithm is unsupported.")
		return {}
	for field in ["sectionsSpecSha256", "frameSha256", "sourceWorldSha256", "sourceCollisionSha256", "sourceServedGridSha256"]:
		if not _is_sha(String(provenance.get(field, ""))):
			_fail("Generated arrival provenance has an invalid " + field + ".")
			return {}
	var base_commit := String(provenance.get("clientBaseCommit", ""))
	if base_commit.length() != 40 or base_commit != base_commit.to_lower() or not base_commit.is_valid_hex_number(false) or \
			String(provenance.get("sourceMap", "")).is_empty() or not _arrival_vector(provenance.get("sourceTile"), 2):
		_fail("Generated arrival source provenance is incomplete.")
		return {}
	for coordinate: Variant in provenance.sourceTile:
		if coordinate != floor(float(coordinate)) or coordinate < 0:
			_fail("Generated arrival source tile must contain nonnegative integers.")
			return {}
	var partition := OWNERSHIP.contained(ownership.checkout,
		"eloria-assets/maps/continent-v2/_continent_v2/partition-inputs/sections_spec.json")
	if partition.is_empty() or not FileAccess.file_exists(partition) or \
			FileAccess.get_sha256(partition) != provenance.sectionsSpecSha256:
		_fail("Generated arrival section partition provenance changed.")
		return {}
	var stub_path := OWNERSHIP.contained(ownership.checkout,
		"eloria-assets/maps/continent-v2/" + map_id + "/world.json")
	var stub: Variant = JSON.parse_string(FileAccess.get_file_as_string(stub_path)) if not stub_path.is_empty() else null
	if not stub is Dictionary or not stub.get("continentGeography") is Dictionary:
		_fail("Generated arrival ownership stub is missing.")
		return {}
	var rings := ARRIVAL_GEOMETRY.from_geography(stub.continentGeography)
	var point := Vector2(float(position[0]) + float(translation[0]), float(position[2]) + float(translation[2]))
	if rings.is_empty() or ARRIVAL_GEOMETRY.hash(rings) != String(region.get("ownership_polygon_sha256")) or \
			not (ARRIVAL_GEOMETRY.contains(point, rings) or ARRIVAL_GEOMETRY.edge_distance(point, rings) <= 0.000001):
		_fail("Generated arrival lies outside the bound map ownership union.")
		return {}
	_validated_generated_arrival = payload.duplicate(true)
	return {"payload": payload, "binding": reference.duplicate(true), "absolute": absolute}


func _validate_document(region: Node3D, document: Dictionary) -> void:
	if String(document.regionId).strip_edges().is_empty():
		_fail("%s: Region Id is empty." % region.get_path())
	if document.terrain.width < 2 or document.terrain.height < 2:
		_fail("Terrain grid must be at least 2Ãƒâ€”2.")
	if not is_finite(float(document.terrain.previewUvMetresInverse)) or \
			float(document.terrain.previewUvMetresInverse) <= 0.0:
		_fail("Terrain Preview UV Metres Inverse must be positive and finite.")
	if bool(document.authority.gameplay) and document.gameplay.spawnPoints.is_empty() and \
			(_validated_generated_arrival.is_empty() or document.get("generatedArrival") != _validated_generated_arrival):
		_fail("Authoritative gameplay needs at least one spawn point.")
	for water: Dictionary in document.waterRegions:
		if water.shape != "ellipse":
			_fail("Water region %s uses unsupported shape %s." % [water.id, water.shape])
		if String(water.id).strip_edges().is_empty():
			_fail("Water regions need a stable id.")
		if not water.center is Array or water.center.size() != 2 or \
				not water.radii is Array or water.radii.size() != 2:
			_fail("Water region %s needs two-dimensional center and radii." % water.id)
		elif float(water.radii[0]) <= 0.0 or float(water.radii[1]) <= 0.0:
			_fail("Water region %s radii must be positive." % water.id)
		if not is_finite(float(water.level)) or not is_finite(float(water.depth)) or \
				float(water.depth) < 0.0:
			_fail("Water region %s level/depth reference must be finite and non-negative." % water.id)
	if not _is_sha(String(document.seams.ownershipPolygonSha256)):
		_fail("Ownership Polygon Sha256 must contain 64 lowercase hex characters.")


func _seam_records(region: Node3D) -> Array[Dictionary]:
	var records: Array[Dictionary] = []
	var cleaned: Variant = _clean_value(region.get("seam_anchors"), "seams.anchors")
	if not cleaned is Array:
		_fail("seams.anchors must be an array.")
		return records
	for raw in cleaned:
		if not raw is Dictionary:
			_fail("Every seam anchor must be a dictionary.")
			continue
		var record: Dictionary = raw
		if String(record.get("id", "")).strip_edges().is_empty():
			_fail("Every seam anchor needs a stable id.")
		if not record.has("anchor") or not record.anchor is Array or \
				(record.anchor as Array).size() != 3:
			_fail("Seam anchor %s needs anchor: [x, y, z]." % record.get("id", ""))
		records.append(record)
	records.sort_custom(_sort_id)
	_validate_unique_ids("seams.anchors", records)
	return records


func _validate_terrain_patches(records: Array[Dictionary]) -> void:
	for record in records:
		var matrix: Array = record.get("matrix", [])
		if matrix.size() != 16:
			_fail("Terrain patch %s has an invalid transform matrix." % record.get("id", ""))
			continue
		if absf(float(matrix[1])) > 0.0001 or absf(float(matrix[4])) > 0.0001 or \
				absf(float(matrix[6])) > 0.0001 or absf(float(matrix[9])) > 0.0001:
			_fail("Terrain patch %s is tilted. Patches support X/Z move, vertical height, yaw, and X/Z scale only." % record.get("id", ""))
		var determinant := float(matrix[0]) * float(matrix[10]) - \
			float(matrix[8]) * float(matrix[2])
		if not is_finite(determinant) or absf(determinant) <= 0.000001:
			_fail("Terrain patch %s has a singular X/Z transform." % record.get("id", ""))


func _dependency_records(scene_path: String, region: Node3D,
		terrain: Node, emitted_surface_records: Array) -> Array[Dictionary]:
	var paths: Dictionary = {}
	_collect_dependencies(scene_path, paths)
	_add_dependency_path("res://src/dev/map_authoring_region/gltf_material_binding.gd", paths)
	_add_dependency_path(String(terrain.get("base_heights_path")), paths)
	_add_dependency_path(String(terrain.get("base_colors_path")), paths)
	_add_dependency_path(String(region.get("runtime_binding_seed_path")), paths)
	_collect_emitted_texture_dependencies(emitted_surface_records, paths)
	var assets := region.get_node_or_null("AuthoredAssets")
	if assets != null:
		for child in assets.get_children():
			if _uses_script(child, ASSET_SCRIPT):
				_add_dependency_path(String(child.get("scene_path")), paths)
	paths.erase(scene_path)
	var keys := paths.keys()
	keys.sort()
	var result: Array[Dictionary] = []
	for dependency: String in keys:
		var absolute := ProjectSettings.globalize_path(dependency)
		if not FileAccess.file_exists(absolute):
			_fail("Scene dependency is missing: %s" % dependency)
			continue
		result.append({"path": _repo_path(dependency),
			"sha256": FileAccess.get_sha256(absolute)})
	return result


func _collect_emitted_texture_dependencies(value: Variant,
		found: Dictionary) -> void:
	if value is Dictionary:
		for key in (value as Dictionary).keys():
			var child: Variant = value[key]
			if String(key).ends_with("Texture") and child is String and \
					not String(child).is_empty():
				var path := String(child)
				if path.begins_with("godot-client/"):
					path = "res://" + path.trim_prefix("godot-client/")
				_add_dependency_path(path, found)
			else:
				_collect_emitted_texture_dependencies(child, found)
	elif value is Array:
		for child in value:
			_collect_emitted_texture_dependencies(child, found)


func _add_dependency_path(path: String, found: Dictionary) -> void:
	if path.strip_edges().is_empty():
		return
	if not path.begins_with("res://"):
		_fail("Authoring dependency must stay inside res://: %s" % path)
		return
	_collect_dependencies(path, found)


func _collect_dependencies(path: String, found: Dictionary) -> void:
	if found.has(path) or not path.begins_with("res://"):
		return
	found[path] = true
	for raw in ResourceLoader.get_dependencies(path):
		var dependency := String(raw)
		if "::" in dependency:
			dependency = dependency.get_slice("::", dependency.get_slice_count("::") - 1)
		if dependency.begins_with("res://"):
			_collect_dependencies(dependency, found)


func _write_bytes(path: String, bytes: PackedByteArray) -> bool:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		_fail("Could not write snapshot sidecar %s." % path)
		return false
	file.store_buffer(bytes)
	file.close()
	return true


func _write_float32(path: String, values: PackedFloat32Array) -> bool:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		_fail("Could not write snapshot sidecar %s." % path)
		return false
	file.big_endian = false
	for value in values:
		if not is_finite(value):
			_fail("Resolved terrain contains a non-finite height.")
			return false
		file.store_float(value)
	file.close()
	return true


func _clean_value(value: Variant, where: String) -> Variant:
	match typeof(value):
		TYPE_NIL, TYPE_BOOL, TYPE_STRING, TYPE_INT:
			return value
		TYPE_FLOAT:
			if not is_finite(float(value)):
				_fail("%s contains a non-finite number." % where)
			return value
		TYPE_ARRAY:
			var array: Array = []
			for index in (value as Array).size():
				array.append(_clean_value(value[index], "%s[%d]" % [where, index]))
			return array
		TYPE_DICTIONARY:
			var dictionary := {}
			var keys := (value as Dictionary).keys()
			keys.sort_custom(func(a: Variant, b: Variant) -> bool: return String(a) < String(b))
			for key in keys:
				dictionary[String(key)] = _clean_value(value[key], "%s.%s" % [where, key])
			return dictionary
	_fail("%s contains unsupported value type %s." % [where, type_string(typeof(value))])
	return null


func _sorted_unique(value: Variant, where: String) -> Array[String]:
	var seen := {}
	var result: Array[String] = []
	for raw in value:
		var identity := String(raw).strip_edges()
		if identity.is_empty():
			_fail("%s contains an empty ID." % where)
		elif seen.has(identity):
			_fail("%s contains duplicate ID %s." % [where, identity])
		else:
			seen[identity] = true
			result.append(identity)
	result.sort()
	return result


func _validate_unique_ids(section: String, records: Array, region_id: String = "") -> void:
	var seen := {}
	var legacy_stelae_nodes: Array[String] = []
	for record in records:
		var identity := String(record.get("id", "")).strip_edges()
		if identity.is_empty():
			_fail("%s contains a record without a stable id." % section)
		elif seen.has(identity):
			if region_id == "manymouth_delta" and section == "gameplay.landmarks" and \
					identity == "stelae-court" and seen[identity] == 1:
				legacy_stelae_nodes.append(String(record.get("node", "")))
			else:
				_fail("%s contains duplicate id %s." % [section, identity])
		if region_id == "manymouth_delta" and section == "gameplay.landmarks" and \
				identity == "stelae-court" and not seen.has(identity):
			legacy_stelae_nodes.append(String(record.get("node", "")))
		seen[identity] = int(seen.get(identity, 0)) + 1
	for node in legacy_stelae_nodes:
		if not ["Landmark_StelaeCourt", "Lore_stelae_court"].has(node) or \
				legacy_stelae_nodes.count(node) != 1:
			_fail("Manymouth's published stelae-court landmarks must keep distinct source nodes.")


func _server_tile(region: Node3D, position: Vector3) -> Array:
	var scale := float(region.get("metres_per_tile"))
	var server: Vector2i = region.get("server_origin")
	return [floori(position.x / scale + float(server.x)),
		floori(float(server.y) - position.z / scale)]


func _matrix(value: Transform3D) -> Array:
	return [value.basis.x.x, value.basis.x.y, value.basis.x.z, 0.0,
		value.basis.y.x, value.basis.y.y, value.basis.y.z, 0.0,
		value.basis.z.x, value.basis.z.y, value.basis.z.z, 0.0,
		value.origin.x, value.origin.y, value.origin.z, 1.0]


func _repo_path(res_path: String) -> String:
	return "godot-client/" + res_path.trim_prefix("res://")


func _resource_path(resource: Resource) -> Variant:
	if resource == null:
		return null
	if resource.resource_path.is_empty() or not resource.resource_path.begins_with("res://"):
		_fail("Custom material texture must be a saved res:// resource.")
		return null
	return _repo_path(resource.resource_path)


func _array_vec3(value: Array) -> Vector3:
	return Vector3(float(value[0]), float(value[1]), float(value[2]))


func _vec3(value: Variant) -> Array:
	var vector: Vector3 = value
	return [vector.x, vector.y, vector.z]


func _vec2(value: Variant) -> Array:
	var vector: Vector2 = value
	return [vector.x, vector.y]


func _vec2i(value: Variant) -> Array:
	var vector: Vector2i = value
	return [vector.x, vector.y]


func _color(value: Color) -> Array:
	return [value.r, value.g, value.b, value.a]


func _sort_id(a: Dictionary, b: Dictionary) -> bool:
	return String(a.id) < String(b.id)


func _is_sha(value: String) -> bool:
	return value.length() == 64 and value == value.to_lower() and \
		value.is_valid_hex_number(false)


func _uses_script(value: Variant, script: Script) -> bool:
	return value is Object and (value as Object).get_script() == script


func _fail(message: String) -> void:
	errors.append(message)
