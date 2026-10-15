@tool
extends RefCounted

const SCHEMA := "eloria-map-authoring-territories-v1"
const CATALOG_PATH := "res://world_authoring/territories.json"
## A project setting that names another territory catalog for the editor. A
## branch that authors a different continent (continent v2 keeps its territories
## in world_authoring/continent-v2/territories.json) sets it in project.godot;
## without it the editor uses the shared catalog.
const CATALOG_SETTING := "map_authoring/territory_catalog_path"
const GEOMETRY := preload("res://addons/map_authoring_workspace/ownership_geometry.gd")
const OWNERSHIP := preload("res://src/dev/map_authoring_region/ownership_source.gd")

var errors: PackedStringArray = []


## The catalog the editor reads: the project setting when it names one, else
## the shared catalog.
static func configured_path() -> String:
	var value := String(ProjectSettings.get_setting(CATALOG_SETTING, "")).strip_edges()
	return value if not value.is_empty() else CATALOG_PATH


func entries(ownership_project_directory: String = "", catalog_path: String = CATALOG_PATH) -> Array[Dictionary]:
	errors.clear()
	var ownership := OWNERSHIP.load_source(ownership_project_directory)
	if not String(ownership.get("error", "")).is_empty():
		errors.append(ownership.error)
		return []
	var source := _json(catalog_path)
	if source.is_empty() or String(source.get("schema", "")) != SCHEMA:
		errors.append("Territory catalog is missing or has an unsupported schema.")
		return []
	var result: Array[Dictionary] = []
	var seen := {}
	for raw: Variant in source.get("entries", []):
		if raw is not Dictionary:
			errors.append("Territory catalog entries must be objects.")
			continue
		var declared: Dictionary = raw
		var id := String(declared.get("id", "")).strip_edges()
		var label := String(declared.get("label", "")).strip_edges()
		var manifest_path := String(declared.get("manifestPath", ""))
		if id.is_empty() or label.is_empty() or seen.has(id):
			errors.append("Territory entries need unique IDs and labels: %s" % id)
			continue
		seen[id] = true
		var manifest := _json(manifest_path)
		var geography: Dictionary = manifest.get("continentGeography", {})
		var asset: Dictionary = manifest.get("asset", {})
		var translation := _vec3(geography.get("translation"))
		var polygons := GEOMETRY.from_geography(geography)
		var polygon := polygons[0] if not polygons.is_empty() else PackedVector2Array()
		var selected := OWNERSHIP.region_data(ownership, id)
		if not String(selected.get("error", "")).is_empty():
			errors.append(selected.error)
			return []
		if selected.get("selected", false):
			translation = _vec3(selected.frame.continentTranslation)
			polygon = _polygon(selected.polygon_scalars)
			polygons = GEOMETRY.polygons(polygon)
		if translation == null or polygon.size() < 3:
			errors.append("%s has no valid continent translation/ownership polygon." % id)
			continue
		var scene_path := _optional_path(declared.get("scenePath"))
		var spec_path := _optional_path(declared.get("authoringSpecPath"))
		if scene_path.is_empty() != spec_path.is_empty():
			errors.append("%s must declare both scenePath and authoringSpecPath, or neither." % id)
			continue
		var authored_error := ""
		var migration := {"error": "", "dependency_paths": PackedStringArray()}
		var claim_source := {"features": {}, "dependencies": PackedStringArray(), "error": ""}
		if not scene_path.is_empty():
			migration = OWNERSHIP.migration_sources(ownership.checkout, _json(spec_path))
			if not String(migration.get("error", "")).is_empty():
				errors.append("%s: %s" % [id, migration.error])
				return []
			var frame_message := OWNERSHIP.frame_error(selected, _json(spec_path))
			if not frame_message.is_empty():
				errors.append("%s: %s" % [id, frame_message])
				return []
			authored_error = _authored_error(scene_path, spec_path, manifest_path, id, label)
			claim_source = _claimed_plan_feature_footprints(spec_path, label, ownership)
			if authored_error.is_empty() and not String(claim_source.error).is_empty():
				authored_error = String(claim_source.error)
			if not authored_error.is_empty():
				errors.append(authored_error)
		var scene_exists := not scene_path.is_empty() and authored_error.is_empty()
		var glb_name := String(asset.get("glb", "world.glb"))
		var published_path := manifest_path.get_base_dir().path_join(glb_name)
		var published_sources := _published_sources(manifest_path, published_path)
		var published_error := String(published_sources.get("error", ""))
		if not scene_exists and not published_error.is_empty():
			errors.append("%s published reference is unavailable: %s" % [
				label, published_error])
		var published_paths: PackedStringArray = published_sources.get(
			"paths", PackedStringArray())
		var published_dependencies: PackedStringArray = published_sources.get(
			"dependencies", PackedStringArray())
		result.append({
			"id": id,
			"label": label,
			"manifest_path": manifest_path,
			"manifest_sha256": _sha(manifest_path),
			"scene_path": scene_path,
			"authoring_spec_path": spec_path,
			"authoring_spec_sha256": _sha(spec_path) if not spec_path.is_empty() else "",
			"ownership_project": ownership.project,
			"editable": scene_exists,
			"source_kind": "saved_authored" if scene_exists else "published",
			"source_label": "Saved authored source" if scene_exists else "Published reference only",
			"source_path": scene_path if scene_exists else published_path,
			"source_sha256": _sha(scene_path) if scene_exists else \
				_paths_sha(published_dependencies),
			"source_error": authored_error if not scene_path.is_empty() else published_error,
			"published_paths": published_paths,
			"source_dependencies": published_dependencies,
			"claimed_plan_feature_footprints": claim_source.features,
			"claim_source_dependencies": claim_source.dependencies,
			"translation": translation,
			"ownership_polygon": polygon,
			"ownership_polygons": polygons,
			"ownership_sha256": selected.source_sha256 if selected.get("selected", false) else \
				GEOMETRY.hash(polygons),
			"revision": String(geography.get("revision", "unversioned")),
		})
		var entry := result[-1]
		entry["ownership_dependency_paths"] = ownership.dependency_paths
		entry["migration_dependency_paths"] = migration.dependency_paths
		if selected.get("selected", false):
			entry["ownership_source"] = selected.binding
			entry["ownership_repository_dependencies"] = selected.repository_dependencies
			entry["ownership_project"] = selected.project
			entry["ownership_polygon_scalars"] = selected.polygon_scalars
			entry["ownership_sha256"] = selected.source_sha256
			entry["ownership_identity"] = "%s:%s" % [selected.source_sha256, id]
			entry["ownership_validation"] = "Source hash/frame checked; strict topology validation runs at bake."
			entry["revision"] = selected.document.revision
	result.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return String(a.label).naturalnocasecmp_to(String(b.label)) < 0)
	for entry in result:
		entry["cache_key"] = _cache_key(entry)
	return result


func find(entries_value: Array[Dictionary], id: String) -> Dictionary:
	for entry in entries_value:
		if String(entry.id) == id:
			return entry
	return {}


func active_scene_error(root: Node, entry: Dictionary) -> String:
	if root == null or not root.has_method("export_snapshot") or \
			String(root.get("region_id")) != String(entry.get("id", "")):
		return "The active scene root does not match the catalogued territory ID."
	if String(root.scene_file_path) != String(entry.get("scene_path", "")):
		return "The active scene path is not the territory's registered authored scene."
	return OWNERSHIP.entry_error(root, entry)


func _json(path: String) -> Dictionary:
	if path.is_empty() or not FileAccess.file_exists(path):
		return {}
	var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return value if value is Dictionary else {}


func _vec3(value: Variant) -> Variant:
	if value is not Array or value.size() != 3:
		return null
	var result := Vector3(float(value[0]), float(value[1]), float(value[2]))
	return result if result.is_finite() else null


func _polygon(value: Variant) -> PackedVector2Array:
	var result := PackedVector2Array()
	if value is not Array:
		return result
	for point: Variant in value:
		if point is not Array or point.size() != 2:
			return PackedVector2Array()
		var parsed := Vector2(float(point[0]), float(point[1]))
		if not parsed.is_finite():
			return PackedVector2Array()
		result.append(parsed)
	return result


func _polygon_array(polygon: PackedVector2Array) -> Array:
	var result: Array = []
	for point in polygon:
		result.append([point.x, point.y])
	return result


func _sha(path: String) -> String:
	return FileAccess.get_sha256(ProjectSettings.globalize_path(path)) \
		if not path.is_empty() and FileAccess.file_exists(path) else ""


func _optional_path(value: Variant) -> String:
	return String(value) if value is String else ""


func _cache_key(entry: Dictionary) -> String:
	var dependencies := {}
	if String(entry.get("source_kind", "")) == "published":
		for path: String in entry.get("source_dependencies", PackedStringArray()):
			dependencies[path] = true
	else:
		_collect_dependencies(String(entry.source_path), dependencies)
	_collect_dependencies(String(entry.manifest_path), dependencies)
	_collect_dependencies(String(entry.authoring_spec_path), dependencies)
	for path: String in entry.get("claim_source_dependencies", PackedStringArray()):
		_collect_dependencies(path, dependencies)
	for path: String in entry.get("ownership_dependency_paths", PackedStringArray()):
		dependencies[path] = true
	for path: String in entry.get("migration_dependency_paths", PackedStringArray()):
		dependencies[path] = true
	var paths := dependencies.keys()
	paths.sort()
	var records := PackedStringArray()
	for path: String in paths:
		records.append("%s:%s" % [path, _sha(path)])
	return "\n".join(records).sha256_text()


func _claimed_plan_feature_footprints(spec_path: String, label: String, ownership: Dictionary) -> Dictionary:
	if not String(ownership.get("error", "")).is_empty():
		return {"features": {}, "dependencies": PackedStringArray(), "error": ownership.error}
	var continent_plan_path: String = ownership.plan_path
	var spec := _json(spec_path)
	var authority: Dictionary = spec.get("authority", {})
	var owned: Variant = authority.get("ownedPlanFeatureIds", [])
	if owned is not Array or owned.is_empty():
		return {"features": {}, "dependencies": PackedStringArray(), "error": ""}
	var provenance_path := spec_path.get_base_dir().path_join("migration-provenance.json")
	var provenance := _json(provenance_path)
	var expected_sha := String((provenance.get("inputs", {}) as Dictionary).get(
		"planSha256", ""))
	# Older authored scenes predate plan-footprint metadata. They retain their existing
	# behavior; migrations that declare a plan hash are validated and fail closed.
	if expected_sha.is_empty():
		return {"features": {}, "dependencies": PackedStringArray(), "error": ""}
	var actual_sha := _sha(continent_plan_path)
	# Mirrorhold and Whitehorn were captured with a later, ID-annotated plan;
	# the byte-frozen plan used for the published composition is separately
	# recorded in the same migration proof.  Its exact original feature records
	# remain valid read-only footprint sources when restored for all-12 editing.
	var composed_sha := String((provenance.get("inputs", {}) as Dictionary).get(
		"compositionPlanSha256", ""))
	if ownership.get("selected", false) and actual_sha != expected_sha and actual_sha != composed_sha:
		# A selector changes the file hash, never the certified original features.
		# The byte-frozen baseline must match the existing per-region certificate;
		# load_source already requires all other active plan content to match it.
		var baseline_sha := String(ownership.get("feature_baseline_sha256", ""))
		if not baseline_sha.is_empty() and baseline_sha in [expected_sha, composed_sha]:
			continent_plan_path = ownership.feature_baseline_path
			actual_sha = baseline_sha
	if actual_sha.is_empty() or (actual_sha != expected_sha and actual_sha != composed_sha):
		return {"features": {}, "dependencies": PackedStringArray(
			[provenance_path, continent_plan_path]),
			"error": "%s original plan-feature footprint hash does not match its migration provenance." % label}
	var plan := _json(continent_plan_path)
	var result := {}
	for feature_id_value: Variant in owned:
		var feature_id := String(feature_id_value)
		var polygon := _plan_feature_polygon(plan, feature_id)
		if polygon.size() < 3:
			return {"features": {}, "dependencies": PackedStringArray(
				[provenance_path, continent_plan_path]),
				"error": "%s claimed plan feature %s has no certified original footprint." % [
					label, feature_id]}
		result[feature_id] = polygon
	return {"features": result, "dependencies": PackedStringArray(
		[provenance_path, continent_plan_path]), "error": ""}


func _plan_feature_polygon(plan: Dictionary, feature_id: String) -> PackedVector2Array:
	for raw: Variant in plan.get("islands", []):
		if raw is not Dictionary or String((raw as Dictionary).get(
				"crownSourceIsland", "")) != feature_id:
			continue
		var center: Variant = (raw as Dictionary).get("center")
		var radii: Variant = (raw as Dictionary).get("crownShelfRadii")
		if center is not Array or center.size() != 2 or radii is not Array or \
				radii.size() != 2 or minf(float(radii[0]), float(radii[1])) <= 0.0:
			return PackedVector2Array()
		var polygon := PackedVector2Array()
		for index in 64:
			var angle := TAU * float(index) / 64.0
			var local := Vector2(cos(angle) * float(radii[0]),
				sin(angle) * float(radii[1])).rotated(float((raw as Dictionary).get("angle", 0.0)))
			polygon.append(Vector2(float(center[0]), float(center[1])) + local)
		return polygon
	for raw: Variant in plan.get("rivers", []):
		if raw is not Dictionary or String((raw as Dictionary).get("id", "")) != feature_id:
			continue
		var centres := PackedVector2Array()
		for point: Variant in (raw as Dictionary).get("points", []):
			if point is not Array or point.size() < 2:
				return PackedVector2Array()
			centres.append(Vector2(float(point[0]), float(point[1])))
		return _corridor_polygon(_legacy_curved_points(centres),
			float((raw as Dictionary).get("width", 0.0)))
	for raw: Variant in plan.get("lakes", []):
		if raw is not Dictionary:
			continue
		var lake: Dictionary = raw
		var idless_match := _idless_published_lake_matches(lake, feature_id)
		if String(lake.get("id", "")) != feature_id and not idless_match:
			continue
		var center: Variant = lake.get("center")
		var radii: Variant = lake.get("radii")
		if center is not Array or center.size() != 2 or radii is not Array or \
				radii.size() != 2:
			return PackedVector2Array()
		var polygon := PackedVector2Array()
		for index in 64:
			var angle := TAU * float(index) / 64.0
			polygon.append(Vector2(float(center[0]) + cos(angle) * float(radii[0]),
				float(center[1]) + sin(angle) * float(radii[1])))
		return polygon
	return PackedVector2Array()


func _idless_published_lake_matches(lake: Dictionary, feature_id: String) -> bool:
	if lake.has("id"):
		return false
	var originals := {
		"moor_headwater_tarn": ["Moor headwater tarn", [255, 350], [25, 18], 27, 2.5],
		"moorwater_pool": ["Moorwater pool", [250, 470], [21, 32], 22, 2.3],
		"mirror_lake": ["Mirror Lake", [893.6788, 831.4641], [48, 33], 80, 4],
	}
	if not originals.has(feature_id):
		return false
	var source: Array = originals[feature_id]
	var center: Variant = lake.get("center")
	var radii: Variant = lake.get("radii")
	if center is not Array or center.size() != 2 or radii is not Array or radii.size() != 2:
		return false
	return String(lake.get("name", "")) == String(source[0]) and \
		float(center[0]) == float(source[1][0]) and float(center[1]) == float(source[1][1]) and \
		float(radii[0]) == float(source[2][0]) and float(radii[1]) == float(source[2][1]) and \
		float(lake.get("level", NAN)) == float(source[3]) and \
		float(lake.get("depth", NAN)) == float(source[4])


func _legacy_curved_points(points: PackedVector2Array) -> PackedVector2Array:
	if points.size() < 2:
		return points
	var result := PackedVector2Array()
	for index in points.size() - 1:
		var a := points[index]
		var b := points[index + 1]
		var before := points[index - 1] if index > 0 else a * 2.0 - b
		var after := points[index + 2] if index + 2 < points.size() else b * 2.0 - a
		for step in 6:
			var t := float(step) / 6.0
			result.append(0.5 * (2.0 * a + (-before + b) * t +
				(2.0 * before - 5.0 * a + 4.0 * b - after) * t * t +
				(-before + 3.0 * a - 3.0 * b + after) * t * t * t))
	result.append(points[-1])
	return result


func _corridor_polygon(centres: PackedVector2Array, half_width: float) -> PackedVector2Array:
	if centres.size() < 2 or half_width <= 0.0:
		return PackedVector2Array()
	var left := PackedVector2Array()
	var right := PackedVector2Array()
	for index in centres.size():
		var tangent := (centres[mini(centres.size() - 1, index + 1)] - \
			centres[maxi(0, index - 1)]).normalized()
		if tangent.length_squared() <= 0.000001:
			return PackedVector2Array()
		var side := Vector2(-tangent.y, tangent.x) * half_width
		left.append(centres[index] + side)
		right.append(centres[index] - side)
	var polygon := left
	for index in range(right.size() - 1, -1, -1):
		polygon.append(right[index])
	return polygon


func _published_sources(manifest_path: String, fallback_glb_path: String) -> Dictionary:
	var manifest := _json(manifest_path)
	if manifest.is_empty():
		return {"error": "manifest is missing or invalid: %s" % manifest_path}
	var streaming: Variant = manifest.get("streamingChunks")
	if streaming == null:
		if fallback_glb_path.is_empty() or not FileAccess.file_exists(fallback_glb_path):
			return {"error": "published GLB is missing: %s" % fallback_glb_path}
		return {"paths": PackedStringArray([fallback_glb_path]),
			"dependencies": PackedStringArray([manifest_path, fallback_glb_path]), "error": ""}
	if streaming is not Dictionary or (streaming as Dictionary).get("chunks") is not Array:
		return {"error": "streamingChunks.chunks must be an array in %s" % manifest_path}
	var chunks: Array = (streaming as Dictionary).get("chunks")
	if chunks.is_empty():
		return {"error": "streamingChunks.chunks is empty in %s" % manifest_path}
	var paths := PackedStringArray()
	var dependencies := PackedStringArray([manifest_path])
	var seen_ids := {}
	var seen_paths := {}
	var seen_dependencies := {manifest_path: true}
	for raw: Variant in chunks:
		if raw is not Dictionary:
			return {"error": "streamingChunks entries must be objects in %s" % manifest_path}
		var chunk: Dictionary = raw
		var chunk_id := String(chunk.get("id", "")).strip_edges()
		var relative_manifest := String(chunk.get("manifest", "")).strip_edges()
		if chunk_id.is_empty() or seen_ids.has(chunk_id):
			return {"error": "streaming chunk IDs must be unique and non-empty in %s" % \
				manifest_path}
		seen_ids[chunk_id] = true
		var chunk_manifest_path := _contained_relative_path(
			manifest_path.get_base_dir(), relative_manifest)
		if chunk_manifest_path.is_empty() or not FileAccess.file_exists(chunk_manifest_path):
			return {"error": "chunk %s manifest is missing or escapes the territory: %s" % [
				chunk_id, relative_manifest]}
		var chunk_manifest := _json(chunk_manifest_path)
		var chunk_asset: Variant = chunk_manifest.get("asset")
		if chunk_asset is not Dictionary:
			return {"error": "chunk %s manifest has no asset record: %s" % [
				chunk_id, chunk_manifest_path]}
		var relative_glb := String((chunk_asset as Dictionary).get("glb", "")).strip_edges()
		var chunk_glb_path := _contained_relative_path(
			chunk_manifest_path.get_base_dir(), relative_glb)
		if chunk_glb_path.is_empty() or not _path_is_within(
				manifest_path.get_base_dir(), chunk_glb_path) or \
				not FileAccess.file_exists(chunk_glb_path):
			return {"error": "chunk %s GLB is missing or escapes the territory: %s" % [
				chunk_id, relative_glb]}
		if seen_paths.has(chunk_glb_path):
			return {"error": "chunk %s repeats published GLB %s" % [chunk_id, chunk_glb_path]}
		seen_paths[chunk_glb_path] = true
		paths.append(chunk_glb_path)
		for dependency: String in [chunk_manifest_path, chunk_glb_path]:
			if not seen_dependencies.has(dependency):
				seen_dependencies[dependency] = true
				dependencies.append(dependency)
		var external: Variant = chunk_manifest.get("externalResources", {})
		if external is not Dictionary:
			return {"error": "chunk %s externalResources must be an object" % chunk_id}
		for relative_external: Variant in (external as Dictionary).keys():
			var external_path := _contained_external_path(chunk_manifest_path.get_base_dir(),
				String(relative_external))
			var expected_sha := String((external as Dictionary)[relative_external])
			if external_path.is_empty() or not FileAccess.file_exists(external_path):
				return {"error": "chunk %s external resource is missing or escapes assets: %s" % [
					chunk_id, relative_external]}
			if not expected_sha.is_empty() and _sha(external_path) != expected_sha:
				return {"error": "chunk %s external resource hash does not match: %s" % [
					chunk_id, relative_external]}
			if not seen_dependencies.has(external_path):
				seen_dependencies[external_path] = true
				dependencies.append(external_path)
	return {"paths": paths, "dependencies": dependencies, "error": ""}


func _contained_relative_path(base_path: String, relative_path: String) -> String:
	if relative_path.is_empty() or relative_path.is_absolute_path() or \
			relative_path.begins_with("res://") or relative_path.begins_with("user://"):
		return ""
	var result := base_path.path_join(relative_path).simplify_path()
	return result if _path_is_within(base_path, result) else ""


func _path_is_within(base_path: String, candidate_path: String) -> bool:
	var base := ProjectSettings.globalize_path(base_path).simplify_path().replace("\\", "/")
	var candidate := ProjectSettings.globalize_path(candidate_path).simplify_path().replace("\\", "/")
	return candidate == base or candidate.begins_with(base.trim_suffix("/") + "/")


func _contained_external_path(base_path: String, relative_path: String) -> String:
	if relative_path.is_empty() or relative_path.is_absolute_path() or \
			relative_path.begins_with("res://") or relative_path.begins_with("user://"):
		return ""
	var result := base_path.path_join(relative_path).simplify_path()
	return result if _path_is_within("res://../eloria-assets", result) else ""


func _paths_sha(paths: PackedStringArray) -> String:
	var records := PackedStringArray()
	var ordered := Array(paths)
	ordered.sort()
	for path: String in ordered:
		records.append("%s:%s" % [path, _sha(path)])
	return "\n".join(records).sha256_text() if not records.is_empty() else ""


func _scene_matches(path: String, expected_id: String) -> bool:
	var packed := ResourceLoader.load(path, "PackedScene",
		ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	if packed == null:
		return false
	var instance := packed.instantiate(PackedScene.GEN_EDIT_STATE_DISABLED)
	var matches := instance is Node3D and instance.has_method("export_snapshot") and \
		String(instance.get("region_id")) == expected_id
	instance.free()
	return matches


func _authored_error(scene_path: String, spec_path: String, manifest_path: String,
		expected_id: String, expected_label: String) -> String:
	if not ResourceLoader.exists(scene_path):
		return "%s authored scene is unavailable: %s" % [expected_label, scene_path]
	if not FileAccess.file_exists(spec_path):
		return "%s authoring spec is unavailable: %s" % [expected_label, spec_path]
	if not _scene_matches(scene_path, expected_id):
		return "%s authored scene root does not declare region_id %s." % [
			expected_label, expected_id]
	var spec := _json(spec_path)
	if String(spec.get("schema", "")) != "eloria-region-authoring-spec-v1" or \
			String(spec.get("regionId", "")) != expected_id or \
			String(spec.get("label", "")) != expected_label:
		return "%s authoring spec identity does not match the territory catalog." % expected_label
	var paths: Dictionary = spec.get("paths", {})
	if _repository_path(String(paths.get("scene", ""))) != \
			_repository_path(scene_path) or \
			_repository_path(String(paths.get("manifest", ""))) != \
			_repository_path(manifest_path):
		return "%s authoring spec paths do not match its registered scene and manifest." % \
			expected_label
	return ""


func _repository_path(path: String) -> String:
	if path.is_empty():
		return ""
	var resource_path := path if path.begins_with("res://") else "res://../" + path
	return ProjectSettings.globalize_path(resource_path).simplify_path()


func _collect_dependencies(path: String, found: Dictionary) -> void:
	if path.is_empty() or found.has(path) or not FileAccess.file_exists(path):
		return
	found[path] = true
	if not ResourceLoader.exists(path):
		return
	for encoded: String in ResourceLoader.get_dependencies(path):
		for part: String in encoded.split("::"):
			if part.begins_with("res://"):
				_collect_dependencies(part, found)
				break
